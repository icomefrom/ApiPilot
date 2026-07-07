import re

from apps.agent.prompts.step_planning_prompt import build_messages
from apps.agent.schemas.validators import validate_step_plan


# ---------------------------------------------------------------------------
# 断言意图识别正则（LLM 分类的兜底，主链路由 LLM constraints 输出）
# ---------------------------------------------------------------------------

# 前缀关键词断言
_ASSERTION_INTENT_PATTERN = re.compile(
    r'^\s*(?:'
    r'断言|校验|验证|检查|确认|确保|期望|要求|判断|'
    r'应该|应当|必须|需要.*(?:为|等于|包含|存在)|'
    r'不能|不可|不允许|'
    r'assert|verify|check|expect|ensure|validate|should\s+be|'
    r'must\s+be|shall\s+be'
    r')\b|^\s*(?:'
    r'断言|校验|验证|检查|确认|确保|期望|要求|判断|'
    r'应该|应当|必须'
    r')',
    re.IGNORECASE,
)

# 表达式形式的断言：field==value, field!=value, field>value, field>=value
_ASSERTION_EXPR_PATTERN = re.compile(
    r'^\s*\S+\s*(?:==|!=|>=|<=|>|<)\s*\S+',
)

# 句中断言模式："订单状态应该是paid" "余额必须大于0"
_MID_SENTENCE_ASSERTION_PATTERN = re.compile(
    r'(?:'
    r'应该(?:是|等于|包含|有)|应当(?:是|等于)|必须(?:是|等于|大于|小于|包含)|'
    r'需要(?:是|等于|大于|小于|包含)|不能(?:是|为|等于|包含|超过)|'
    r'不可(?:是|为|等于|包含)|不应当|不应该|'
    r'should\s+be|must\s+be|shall\s+be|should\s+not\s+be|must\s+not\s+be'
    r')',
    re.IGNORECASE,
)

# 隐式断言模式："不为空" "不能为空" "!=null" 等
_IMPLICIT_ASSERTION_PATTERN = re.compile(
    r'(?:不为空|不能为空|不为null|不为None|'
    r'不仅为空|非空|'
    r'should not be empty|is not empty|is not null|!=\s*null)',
    re.IGNORECASE,
)


class StepPlanner:
    def __init__(self, llm):
        self.llm = llm

    def plan(self, goal):
        result = self.llm.chat_json(build_messages(goal), temperature=0.1)
        data = validate_step_plan(result['data'])

        # 用 LLM 输出的 source_span 做语义对齐
        data['steps'] = self._align_steps_via_source_span(goal, data.get('steps', []))

        # 从 LLM 分类结果中提取断言
        data['assertion_intents'] = self._constraints_to_assertion_intents(
            data.get('constraints', []), data['steps'],
        )
        data['steps'], legacy_intents = self._separate_assertion_intents(data['steps'])
        data['assertion_intents'].extend(legacy_intents)
        # 从原文中补扫 LLM 可能遗漏的断言
        data['assertion_intents'] = self._scan_goal_assertions(
            goal, data['steps'], data['assertion_intents'],
        )
        data.setdefault('goal', goal)
        data.setdefault('questions', [])
        return data, {'provider': result['provider'], 'model': result['model']}

    # ------------------------------------------------------------------
    # 核心对齐：基于 LLM 输出的 source_span（两级回退）
    # ------------------------------------------------------------------

    def _align_steps_via_source_span(self, goal, model_steps):
        """
        基于 LLM 输出的 source_span 做原文对齐。

        优先级：
        1. LLM 输出了 source_span 且至少 50% 能在 goal 中精确匹配
           → 使用 source_span 作为 text（用户的原文片段）
        2. 回退到 LLM 输出的 text 原值，并尝试在 goal 中定位

        每个 step 都附带 original_goal 字段，供双通道召回使用。
        每个 step 的 text 保留用户原文，resolved_text 为 LLM 规范化描述。
        """
        if not model_steps:
            return []

        # 尝试 source_span 对齐
        aligned = self._try_source_span_alignment(goal, model_steps)
        if aligned is not None:
            return aligned

        # 回退：使用 LLM 输出的 text，尝试在 goal 中定位作为 source_span
        steps = []
        for idx, step in enumerate(model_steps, start=1):
            text = str(step.get('text') or '').strip()
            resolved_text = str(step.get('resolved_text') or text).strip()

            # 如果 text 本身就是 goal 的子串，直接作为 source_span
            source_span = text if (text and text in (goal or '')) else ''

            steps.append({
                **step,
                'index': idx,
                'text': text,
                'resolved_text': resolved_text,
                'source_span': source_span,
                'original_goal': goal,
                'depends_on': self._normalize_depends(step.get('depends_on'), idx),
            })
        return steps

    def _try_source_span_alignment(self, goal, model_steps):
        """
        尝试使用 LLM 输出的 source_span 做对齐。

        成功条件：至少 50% 的 steps 的 source_span 能在 goal 中精确匹配。
        返回对齐后的 steps，或 None 表示对齐失败。
        """
        goal_text = goal or ''
        if not goal_text:
            return None

        # 第一轮：验证 source_span 质量
        match_count = 0
        total = len(model_steps)
        span_info = []  # [(step_idx, source_span, found_in_goal)]
        for idx, step in enumerate(model_steps, start=1):
            span = str(step.get('source_span') or '').strip()
            if span and span in goal_text:
                match_count += 1
                span_info.append((idx, span, True))
            else:
                span_info.append((idx, span, False))

        # 对齐成功率低于 50% → 回退
        if total > 0 and match_count / total < 0.5:
            return None

        # 第二轮：构建对齐后的 steps
        steps = []
        for idx, step in enumerate(model_steps, start=1):
            _, span, found = span_info[idx - 1]
            if found and span:
                text = span
            else:
                text = str(step.get('text') or '')
            # resolved_text 始终取 LLM 规范化描述
            resolved_text = str(step.get('resolved_text') or '').strip() or text

            steps.append({
                **step,
                'index': idx,
                'text': text,
                'resolved_text': resolved_text,
                'source_span': span if found else '',
                'original_goal': goal,
                'depends_on': self._normalize_depends(step.get('depends_on'), idx),
            })
        return steps

    # ------------------------------------------------------------------
    # depends_on 归一化
    # ------------------------------------------------------------------

    def _normalize_depends(self, depends_on, index):
        if not isinstance(depends_on, list):
            return []
        return [
            dep for dep in depends_on
            if isinstance(dep, int) and dep < index
        ]

    # ------------------------------------------------------------------
    # 断言分离（正则兜底，主链路由 LLM constraints 输出）
    # ------------------------------------------------------------------

    def _separate_assertion_intents(self, steps):
        executable_steps = []
        assertion_intents = []
        old_to_new_index = {}

        for step in steps or []:
            text = step.get('text') or step.get('resolved_text') or ''
            if self._is_assertion_intent(text) and executable_steps:
                target_step = executable_steps[-1]['index']
                assertion_intents.append({
                    'source_index': step.get('index'),
                    'target_step_index': target_step,
                    'text': text,
                })
                continue

            new_index = len(executable_steps) + 1
            old_to_new_index[step.get('index')] = new_index
            executable_steps.append({
                **step,
                'index': new_index,
                'text': text,
                'resolved_text': step.get('resolved_text') or text,
                'original_goal': step.get('original_goal', ''),
                'source_span': step.get('source_span', ''),
            })

        for step in executable_steps:
            normalized_depends = []
            for dep in step.get('depends_on') or []:
                mapped = old_to_new_index.get(dep)
                if mapped and mapped < step['index']:
                    normalized_depends.append(mapped)
            if not normalized_depends and step['index'] > 1:
                normalized_depends = [step['index'] - 1]
            step['depends_on'] = normalized_depends

        return executable_steps, assertion_intents

    def _is_assertion_intent(self, text):
        text = str(text or '').strip()
        if not text:
            return False
        # 关键词前缀匹配
        if _ASSERTION_INTENT_PATTERN.search(text):
            return True
        # 表达式形式：field==value, field>value
        if _ASSERTION_EXPR_PATTERN.search(text):
            return True
        # 句中断言："订单状态应该是paid" "余额必须大于0"
        if _MID_SENTENCE_ASSERTION_PATTERN.search(text):
            return True
        # 隐式断言："不为空" "不能为空"
        if _IMPLICIT_ASSERTION_PATTERN.search(text):
            return True
        return False

    # ------------------------------------------------------------------
    # constraints → assertion_intents 转换
    # ------------------------------------------------------------------

    def _constraints_to_assertion_intents(self, constraints, steps):
        intents = []
        max_step_index = len(steps or [])
        for idx, item in enumerate(constraints or [], start=1):
            if not isinstance(item, dict):
                continue
            text = item.get('text') or ''
            if not text:
                continue
            target = item.get('target_action_index')
            if not isinstance(target, int):
                target = item.get('target_step_index')
            if not isinstance(target, int) or target < 1 or target > max_step_index:
                target = max_step_index
            intents.append({
                'source_index': item.get('source_index') or idx,
                'target_step_index': target,
                'text': text,
                'field_hint': item.get('field_hint') or '',
                'operator': item.get('operator') or 'exists',
                'expected': item.get('expected'),
                'confidence': item.get('confidence'),
            })
        return intents

    # ------------------------------------------------------------------
    # 从原文中补扫 LLM 可能遗漏的断言意图
    # ------------------------------------------------------------------

    def _scan_goal_assertions(self, goal, steps, assertion_intents):
        """
        扫描用户原始 goal 文本，检查是否有 LLM 遗漏的断言意图。
        对已有 LLM constraints 输出做补充，不依赖标点分片。

        策略：将 goal 中每个 step 的 source_span/text 之间的剩余文本
        提取出来，检查是否包含断言关键词。

        去重：已有断言文本的子串覆盖检测——如果间隙/尾部文本完全包含
        某个已有断言的全文，则视为已被覆盖，不再添加。
        """
        intents = list(assertion_intents or [])
        if not goal or not steps:
            return intents

        seen = {(item.get('target_step_index'), item.get('text')) for item in intents}
        # 已有断言全体文本集合，用于超集去重
        existing_texts = [item.get('text', '') for item in intents if item.get('text')]

        def _is_covered_by_existing(candidate_text):
            """如果已有断言中的某条是候选文本的子串，则候选文本已被覆盖。"""
            for et in existing_texts:
                if et and et in candidate_text:
                    return True
            return False

        # 收集已有 step 在 goal 中的位置，提取间隙文本
        goal_text = goal
        covered_spans = []
        for step in steps:
            span = step.get('source_span') or step.get('text') or ''
            if span and span in goal_text:
                start = goal_text.index(span)
                covered_spans.append((start, start + len(span), step['index']))
        covered_spans.sort()

        # 从间隙文本中提取断言
        cursor = 0
        for start, end, sidx in covered_spans:
            if start > cursor:
                gap = goal_text[cursor:start].strip('，,、；;：: \t\n')
                if gap and self._is_assertion_intent(gap):
                    if _is_covered_by_existing(gap):
                        cursor = end
                        continue
                    # 绑定到前一步或当前步
                    target = sidx - 1 if sidx > 1 else sidx
                    target = max(1, target)
                    if (target, gap) not in seen:
                        intents.append({
                            'source_index': 0,
                            'target_step_index': target,
                            'text': gap,
                        })
                        seen.add((target, gap))
            cursor = end

        # 检查最后一个 step 之后的剩余文本
        if cursor < len(goal_text):
            tail = goal_text[cursor:].strip('，,、；;：: \t\n')
            if tail and self._is_assertion_intent(tail):
                if not _is_covered_by_existing(tail):
                    target = steps[-1]['index'] if steps else 1
                    if (target, tail) not in seen:
                        intents.append({
                            'source_index': 0,
                            'target_step_index': target,
                            'text': tail,
                        })
                        seen.add((target, tail))

        return intents