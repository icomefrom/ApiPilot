import logging

from apps.agent.prompts.interface_matching_prompt import build_messages
from apps.agent.schemas.validators import validate_interface_match

logger = logging.getLogger(__name__)


class InterfaceMatcher:
    def __init__(self, llm):
        self.llm = llm

    # 规则预选最低分数：低于此分数的候选不送入 LLM，避免无关候选干扰匹配
    MIN_CANDIDATE_PRE_SCORE = 0.01

    # 名称匹配强度阈值：>= 此值直接跳过 LLM
    FAST_MATCH_NAME_THRESHOLD = 0.80

    def match(self, steps, candidates_by_step):
        """Match interfaces per-step with two-phase strategy.

        Phase 1 (fast path): If a candidate's name strongly matches the step text
        (exact name match or high semantic similarity), skip LLM entirely.

        Phase 2 (batch LLM): Remaining unmatched steps are batched into a single
        LLM call instead of N sequential calls, reducing total LLM round-trips.
        """
        # Build candidate index once (shared across steps)
        candidates_by_index = {}
        for item in candidates_by_step:
            candidates = []
            for candidate in item.get('candidates', []):
                if (candidate.get('pre_score') or 0) < self.MIN_CANDIDATE_PRE_SCORE:
                    continue
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

        by_id = self._candidate_map(candidates_by_step)
        all_valid_ids = set()
        for candidates in candidates_by_index.values():
            for c in candidates:
                all_valid_ids.add(c['interface_id'])

        matches = []
        llm_needed = []

        # ── Phase 1: fast name-based match (no LLM) ──────────────────
        for item in candidates_by_step:
            step_index = item['step_index']
            step_candidates = candidates_by_index.get(step_index, [])
            if not step_candidates:
                matches.append({
                    'step_index': step_index,
                    'selected_interface_id': None,
                    'selected_interface': None,
                    'confidence': 0,
                    'reason': '无可用候选接口',
                })
                continue

            fast = self._try_fast_name_match(step_index, item, step_candidates)
            if fast:
                matches.append(fast)
            else:
                llm_needed.append((item, step_candidates))

        # ── Phase 2: batch LLM for remaining unmatched steps ─────────
        provider_info = {'provider': 'unknown', 'model': 'unknown'}

        if llm_needed:
            batch_result = self._batch_llm_match(llm_needed)
            provider_info = batch_result['provider_info']

            for item, step_candidates in llm_needed:
                step_index = item['step_index']
                match_item = batch_result['step_matches'].get(step_index)

                if not match_item:
                    matches.append({
                        'step_index': step_index,
                        'selected_interface_id': None,
                        'selected_interface': None,
                        'confidence': 0,
                        'reason': 'LLM 未返回匹配结果',
                    })
                    continue

                selected_id = match_item.get('selected_interface_id')
                if selected_id is not None and selected_id not in all_valid_ids:
                    selected_id = None
                candidate = by_id.get(selected_id) if selected_id is not None else None
                confidence = float(match_item.get('confidence') or 0)
                reason = match_item.get('reason') or ''

                if selected_id is None:
                    recommendation = self._recommend_top_candidate(step_index, candidates_by_index, reason)
                    if recommendation:
                        selected_id = recommendation['interface_id']
                        candidate = by_id.get(selected_id)
                        confidence = recommendation['confidence']
                        reason = recommendation['reason']

                correction = self._prefer_stronger_name_candidate(step_index, candidate, candidates_by_index)
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
                    'step_index': step_index,
                    'selected_interface_id': selected_id,
                    'selected_interface': candidate,
                    'confidence': confidence,
                    'reason': reason,
                })

        # Sort by step_index for consistent ordering
        matches.sort(key=lambda m: m['step_index'])
        return matches, provider_info

    # ------------------------------------------------------------------
    # Batch LLM: send all unmatched steps in a single call
    # ------------------------------------------------------------------

    def _batch_llm_match(self, llm_needed):
        """Send all unmatched steps to LLM in ONE call instead of N."""
        compact = []
        steps_for_prompt = []
        for item, step_candidates in llm_needed:
            compact.append({
                'step_index': item['step_index'],
                'step_text': item.get('step_text'),
                'resolved_text': item.get('resolved_text'),
                'candidates': step_candidates,
            })
            steps_for_prompt.extend(
                s for s in [item] if s.get('index') is not None
            )

        # Build prompt steps from original step data
        prompt_steps = []
        for item, _ in llm_needed:
            prompt_steps.append({
                'index': item.get('step_index'),
                'text': item.get('step_text'),
                'resolved_text': item.get('resolved_text'),
            })

        messages = build_messages(prompt_steps, compact)
        try:
            result = self.llm.chat_json(messages, temperature=0.1)
            provider_info = {'provider': result['provider'], 'model': result['model']}
            data = validate_interface_match(result['data'])
        except Exception as exc:
            logger.warning(f'[InterfaceMatcher] batch LLM failed: {exc}, falling back to per-step')
            return self._fallback_per_step_llm(llm_needed)

        # Index LLM results by step_index
        step_matches = {}
        for match_item in data.get('matches', []):
            si = match_item.get('step_index')
            if si is not None:
                step_matches[si] = match_item

        return {
            'provider_info': provider_info,
            'step_matches': step_matches,
        }

    def _fallback_per_step_llm(self, llm_needed):
        """Fallback: call LLM per-step if batch call fails."""
        step_matches = {}
        provider_info = {'provider': 'unknown', 'model': 'unknown'}
        for item, step_candidates in llm_needed:
            step_index = item['step_index']
            compact_single = [{
                'step_index': step_index,
                'step_text': item.get('step_text'),
                'resolved_text': item.get('resolved_text'),
                'candidates': step_candidates,
            }]
            single_step = [{
                'index': step_index,
                'text': item.get('step_text'),
                'resolved_text': item.get('resolved_text'),
            }]
            try:
                result = self.llm.chat_json(
                    build_messages(single_step, compact_single),
                    temperature=0.1,
                )
                provider_info = {'provider': result['provider'], 'model': result['model']}
                data = validate_interface_match(result['data'])
                for match_item in data.get('matches', []):
                    if match_item.get('step_index') == step_index:
                        step_matches[step_index] = match_item
                        break
            except Exception:
                pass
        return {
            'provider_info': provider_info,
            'step_matches': step_matches,
        }

    # ------------------------------------------------------------------
    # Fast name match
    # ------------------------------------------------------------------

    def _try_fast_name_match(self, step_index, item, candidates):
        """If a candidate's name strongly matches the step, skip LLM entirely."""
        best_candidate = None
        best_strength = 0.0
        for candidate in candidates:
            strength = self._name_match_strength(candidate)
            if strength > best_strength:
                best_strength = strength
                best_candidate = candidate

        if not best_candidate or best_strength < self.FAST_MATCH_NAME_THRESHOLD:
            return None

        confidence = max(0.80, min(0.95, best_strength))
        return {
            'step_index': step_index,
            'selected_interface_id': best_candidate['interface_id'],
            'selected_interface': {
                **best_candidate,
                'llm_confidence': confidence,
                'llm_reason': '名称快速匹配：接口名称与步骤文本高度匹配，跳过LLM推理',
            },
            'confidence': confidence,
            'reason': '名称快速匹配：接口名称与步骤文本高度匹配，跳过LLM推理',
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
