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
                    'score_breakdown': candidate.get('score_breakdown') or {},
                    'score_reasons': candidate.get('score_reasons') or candidate.get('pre_reason') or [],
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
            correction = self._prefer_stronger_name_candidate(item.get('step_index'), candidate, candidates_by_index)
            if correction:
                selected_id = correction['interface_id']
                candidate = by_id.get(selected_id)
                confidence = correction['confidence']
                reason = correction['reason']
            if candidate:
                candidate = {
                    **candidate,
                    'llm_confidence': confidence,
                    'llm_reason': reason,
                }
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

    def _prefer_stronger_name_candidate(self, step_index, selected_candidate, candidates_by_index):
        """Prevent stale feedback/model choices from overriding a clearly better name match."""
        candidates = candidates_by_index.get(step_index) or []
        if not candidates:
            return None

        selected_strength = self._name_match_strength(selected_candidate)
        best = None
        best_strength = 0.0
        for candidate in candidates:
            strength = self._name_match_strength(candidate)
            if strength > best_strength:
                best = candidate
                best_strength = strength

        if not best or not best.get('interface_id'):
            return None
        if selected_candidate and best.get('interface_id') == selected_candidate.get('interface_id'):
            return None

        selected_breakdown = (selected_candidate or {}).get('score_breakdown') or {}
        selected_memory = float(selected_breakdown.get('feedback_memory') or 0)
        best_pre_score = float(best.get('pre_score') or 0)

        # Conservative guard: only override when name relevance is clearly stronger.
        if best_strength >= 0.60 and best_strength >= selected_strength + 0.25:
            reason = (
                '候选接口名称与步骤更匹配，已优先选择名称相关性更高的接口'
                f'（名称相关性 {best_strength:.2f} > {selected_strength:.2f}）'
            )
            if selected_memory:
                reason += f'；原选择包含历史记忆加权 {selected_memory:.2f}，但名称匹配不足'
            return {
                'interface_id': best['interface_id'],
                'confidence': max(best_pre_score, min(0.85, best_strength)),
                'reason': reason,
            }
        return None

    def _name_match_strength(self, candidate):
        if not candidate:
            return 0.0
        breakdown = candidate.get('score_breakdown') or {}
        if float(breakdown.get('exact_name') or 0) > 0:
            return 1.0
        semantic = float(breakdown.get('semantic_name_similarity') or 0)
        name_score = float(breakdown.get('name_similarity') or 0)
        # name_similarity is a weighted score contribution, normalize it back to a rough 0~1 strength.
        normalized_name = min(1.0, name_score / 0.80) if name_score else 0.0
        return max(semantic, normalized_name)
