import re

from apps.agent.schemas import HIGH_RISK_OPERATIONS, OPERATION_ALIASES, READ_OPERATIONS, WRITE_OPERATIONS

_SPLIT_PATTERN = re.compile(r'(?:，|,|。|；|;|、|\s+然后\s*|\s*再\s*|\s*之后\s*|\s*并且\s*|\s*->\s*)')


class IntentParser:
    """领域无关意图解析器。

    开源版默认使用轻量规则，目标是稳定输出“动作 + 对象 + 顺序”。
    后续可以在同一接口后接 LLM，把规则结果作为 fallback。
    """

    def parse(self, goal):
        normalized_goal = (goal or '').strip()
        raw_steps = self._split_goal(normalized_goal)
        steps = [self._parse_step(index + 1, text) for index, text in enumerate(raw_steps)]
        self._fill_missing_objects(steps)
        risk_level, risk_reasons = self._risk(steps)
        return {
            'goal': normalized_goal,
            'task_type': 'api_orchestration',
            'steps': steps,
            'constraints': {
                'must_include': [],
                'must_exclude': [],
                'environment': None,
                'auto_execute': False,
            },
            'risk_level': risk_level,
            'risk_reasons': risk_reasons,
            'needs_clarification': not steps,
            'questions': [] if steps else ['请描述你要编排的接口链路，例如：提交发票，审批，下载发票'],
        }

    def _split_goal(self, goal):
        pieces = [p.strip() for p in _SPLIT_PATTERN.split(goal) if p and p.strip()]
        return pieces or ([goal] if goal else [])

    def _parse_step(self, index, text):
        operation, keyword = self._detect_operation(text)
        obj = self._extract_object(text, keyword)
        return {
            'index': index,
            'name': text,
            'operation': operation,
            'object': obj,
            'source_text': text,
            'keywords': [keyword] if keyword else [],
            'depends_on': [index - 1] if index > 1 else [],
            'required': True,
            'confidence': 0.72 if operation != 'unknown' else 0.35,
        }

    def _detect_operation(self, text):
        lowered = text.lower()
        best = ('unknown', '')
        best_len = 0
        for operation, aliases in OPERATION_ALIASES.items():
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in lowered and len(alias_lower) > best_len:
                    best = (operation, alias)
                    best_len = len(alias_lower)
        return best

    def _extract_object(self, text, keyword):
        value = text.strip()
        if keyword:
            value = value.replace(keyword, '', 1).strip()
        value = re.sub(r'^(一个|一条|一次|该|这个|这条|对应的|一下)', '', value).strip()
        value = re.sub(r'(接口|流程|操作|一下)$', '', value).strip()
        return value or ''

    def _fill_missing_objects(self, steps):
        last_obj = ''
        for step in steps:
            if step.get('object'):
                last_obj = step['object']
            elif last_obj:
                step['object'] = last_obj
        next_obj = ''
        for step in reversed(steps):
            if step.get('object'):
                next_obj = step['object']
            elif next_obj:
                step['object'] = next_obj

    def _risk(self, steps):
        operations = {step['operation'] for step in steps}
        if operations & HIGH_RISK_OPERATIONS:
            return 'high', ['包含审批、驳回、取消或删除等高风险动作，建议人工确认后执行']
        if operations & WRITE_OPERATIONS:
            return 'medium', ['包含写入类动作，建议先生成草稿并人工确认']
        if operations and operations <= READ_OPERATIONS:
            return 'low', []
        return 'medium', ['存在未识别动作，需要人工确认']
