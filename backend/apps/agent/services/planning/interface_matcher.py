from apps.agent.prompts.interface_matching_prompt import build_messages
from apps.agent.schemas.validators import validate_interface_match


class InterfaceMatcher:
    def __init__(self, llm):
        self.llm = llm

    # 规则预选最低分数：低于此分数的候选不送入 LLM，避免无关候选干扰匹配
    MIN_CANDIDATE_PRE_SCORE = 0.01

    def match(self, steps, candidates_by_step):
        compact_candidates = []
        valid_ids = set()
        candidates_by_index = {}
        for item in candidates_by_step:
            candidates = []
            for candidate in item.get('candidates', []):
                # 过滤掉极低分候选，减少 LLM 误选概率
                if (candidate.get('pre_score') or 0) < self.MIN_CANDIDATE_PRE_SCORE:
                    continue
                valid_ids.add(candidate['interface_id'])
                candidates.append({
                    'interface_id': candidate['interface_id'],
                    'name': candidate.get('name'),
                    'method': candidate.get('method'),
                    'url': candidate.get('url'),
                    'group': candidate.get('group'),
                    'description': candidate.get('description'),
                    'request_fields': candidate.get('request_fields'),
                    'response_fields': candidate.get('response_fields'),
                    'pre_score': candidate.get('pre_score'),
                })
            candidates_by_index[item['step_index']] = candidates
            compact_candidates.append({
                'step_index': item['step_index'],
                'step_text': item.get('step_text'),
                'resolved_text': item.get('resolved_text'),
                'candidates': candidates,
            })
        result = self.llm.chat_json(build_messages(steps, compact_candidates), temperature=0.1)
        data = validate_interface_match(result['data'])
        by_id = self._candidate_map(candidates_by_step)
        matches = []
        for item in data.get('matches', []):
            selected_id = item.get('selected_interface_id')
            if selected_id is not None and selected_id not in valid_ids:
                selected_id = None
            candidate = by_id.get(selected_id) if selected_id is not None else None
            confidence = float(item.get('confidence') or 0)
            reason = item.get('reason') or ''
            if selected_id is None:
                recommendation = self._recommend_top_candidate(item.get('step_index'), candidates_by_index, reason)
                if recommendation:
                    selected_id = recommendation['interface_id']
                    candidate = by_id.get(selected_id)
                    confidence = recommendation['confidence']
                    reason = recommendation['reason']
            matches.append({
                'step_index': item.get('step_index'),
                'selected_interface_id': selected_id,
                'selected_interface': candidate,
                'confidence': confidence,
                'reason': reason,
            })
        return matches, {'provider': result['provider'], 'model': result['model']}

    def _candidate_map(self, candidates_by_step):
        result = {}
        for item in candidates_by_step:
            for candidate in item.get('candidates', []):
                result[candidate['interface_id']] = candidate
        return result

    def _recommend_top_candidate(self, step_index, candidates_by_index, model_reason=''):
        candidates = candidates_by_index.get(step_index) or []
        if not candidates:
            return None
        top = candidates[0]
        top_score = float(top.get('pre_score') or 0)
        reason = '模型未选择接口，已推荐预选分数最高的候选，请人工确认'
        if model_reason:
            reason = f'{reason}；模型原因：{model_reason}'
        return {
            'interface_id': top['interface_id'],
            'confidence': top_score,
            'reason': reason,
        }
