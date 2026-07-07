from .interface_indexer import tokenize
from .embedding_indexer import EmbeddingIndexer
from ..feedback_memory import normalize_step_text


def _compact_text(value):
    return ''.join(str(value or '').lower().split())


def _char_bigrams(value):
    text = _compact_text(value)
    if len(text) < 2:
        return {text} if text else set()
    return {text[idx:idx + 2] for idx in range(len(text) - 1)}


def _jaccard(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _common_prefix_ratio(left, right):
    left = _compact_text(left)
    right = _compact_text(right)
    if not left or not right:
        return 0.0
    count = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        count += 1
    return count / max(len(left), len(right))


class CandidatePreselector:
    """规则只做候选收缩，不产出最终 Agent 结果。"""

    # 最低预选分数阈值：低于此分数的候选视为无关，不进入 LLM 匹配
    MIN_PRE_SCORE = 0.01
    EXACT_NAME_SCORE = 0.85
    NAME_SIMILARITY_THRESHOLD = 0.35

    MEMORY_EXACT_SCORE = 0.20
    MEMORY_SIMILAR_SCORE = 0.12
    MEMORY_SIMILARITY_THRESHOLD = 0.55

    # 语义召回参数
    EMBEDDING_TOP_K = 30          # 语义召回返回的候选数
    EMBEDDING_WEIGHT = 0.35       # 语义分数在合并时的权重
    TOKEN_WEIGHT = 0.65           # token 分数在合并时的权重

    def __init__(self, embedding_indexer=None):
        """
        Args:
            embedding_indexer: EmbeddingIndexer 实例。
                               如果传入且已 build，则在 select 时合并语义召回候选。
                               如果为 None，则纯走 token 匹配（向后兼容）。
        """
        self._embedding_indexer = embedding_indexer

    def build_embedding_index(self, profiles):
        """便捷方法：构建 embedding 索引。可在 select 之前调用。"""
        if self._embedding_indexer is None:
            self._embedding_indexer = EmbeddingIndexer(
                top_k=self.EMBEDDING_TOP_K,
            )
        if not self._embedding_indexer.is_built:
            self._embedding_indexer.build(profiles)

    def select(self, steps, profiles, limit=20, feedback_memory=None):
        results = []
        feedback_memory = feedback_memory or {}

        # 确保 embedding 索引已构建
        emb = self._embedding_indexer
        if emb and not emb.is_built:
            emb.build(profiles)

        for step in steps:
            step_text = step.get('text') or ''

            # 主通道：用 step.text 做匹配
            primary_candidates = self._select_for_query(
                step_text, profiles, emb, feedback_memory,
            )

            # 双通道：如果有 original_goal 且不同于 step.text，追加召回
            original_goal = step.get('original_goal', '')
            extra_candidates = []
            if original_goal and original_goal.strip() != step_text.strip():
                extra_candidates = self._select_for_query(
                    original_goal, profiles, emb, feedback_memory,
                )

            # 合并双通道候选：取并集，同一接口取高分
            scored = self._merge_candidates(primary_candidates, extra_candidates)

            scored.sort(key=lambda item: item['pre_score'], reverse=True)
            results.append({
                'step_index': step['index'],
                'step_text': step.get('text') or '',
                'resolved_text': step.get('resolved_text') or step.get('text') or '',
                'candidates': scored[:limit],
            })
        return results

    def _select_for_query(self, query, profiles, emb, feedback_memory):
        """对单个 query 文本执行 token + embedding 匹配，返回候选列表。"""
        query_tokens = tokenize(query)

        # 批量获取语义分数（只编码一次 query，比 per-profile 调用快 ~300x）
        sem_scores = {}
        if emb and emb.is_built:
            sem_scores = emb.get_semantic_scores_batch(query)

        scored = []
        for profile in profiles:
            score, reasons, breakdown = self._score(query, query_tokens, profile)
            score, reasons, breakdown = self._apply_feedback_memory(
                score, reasons, breakdown, query, profile, feedback_memory,
            )

            # 合并语义召回分数（从批量结果中查表）
            iid = profile.get('interface_id')
            sem_score = sem_scores.get(iid, 0.0) if sem_scores else 0.0
            if sem_score > 0:
                breakdown['semantic_embedding'] = sem_score
                merged = (
                    self.TOKEN_WEIGHT * score
                    + self.EMBEDDING_WEIGHT * sem_score
                )
                if sem_score > score:
                    reasons.append(
                        f'语义召回命中 (semantic_score={sem_score:.4f})，'
                        f'合并分 {score:.4f} → {merged:.4f}'
                    )
                score = merged
                breakdown['total'] = round(score, 4)

            # 只保留超过最低阈值的候选
            if score >= self.MIN_PRE_SCORE:
                item = {key: value for key, value in profile.items() if key != 'tokens'}
                item.update({
                    'pre_score': round(score, 4),
                    'pre_reason': reasons,
                    'score_reasons': reasons,
                    'score_breakdown': breakdown,
                })
                scored.append(item)

        # 语义召回补充：将 embedding 召回但不在 token 候选中的接口补入
        if emb and emb.is_built:
            emb_candidates = emb.search(query, top_k=self.EMBEDDING_TOP_K)
            existing_ids = {c['interface_id'] for c in scored}
            for ec in emb_candidates:
                if ec['interface_id'] in existing_ids:
                    continue
                sem_score = ec.get('semantic_score', 0)
                if sem_score < self.MIN_PRE_SCORE:
                    continue
                # 纯语义候选：token 部分为 0，合并后分数
                merged_score = self.EMBEDDING_WEIGHT * sem_score
                if merged_score >= self.MIN_PRE_SCORE:
                    ec['pre_score'] = round(merged_score, 4)
                    ec['pre_reason'] = [
                        f'语义召回补充 (semantic_score={sem_score:.4f})'
                    ]
                    ec['score_reasons'] = ec['pre_reason']
                    ec['score_breakdown'] = {
                        'semantic_embedding': sem_score,
                        'total': round(merged_score, 4),
                    }
                    scored.append(ec)
                    existing_ids.add(ec['interface_id'])

        return scored

    def _merge_candidates(self, primary, extra):
        """合并主通道和双通道候选，同一接口取高分。"""
        if not extra:
            return primary

        merged = {}
        # 先放主通道
        for c in primary:
            iid = c['interface_id']
            if iid not in merged or c['pre_score'] > merged[iid]['pre_score']:
                merged[iid] = c

        # 再合并双通道，取高分
        dual_channel_ids = set()
        for c in extra:
            iid = c['interface_id']
            dual_channel_ids.add(iid)
            if iid not in merged:
                # 双通道独有：标记来源
                c = dict(c)
                if 'dual_channel' not in c.get('pre_reason', []):
                    c.setdefault('pre_reason', [])
                    if isinstance(c['pre_reason'], list):
                        c['pre_reason'].append('original_goal 双通道召回')
                merged[iid] = c
            elif c['pre_score'] > merged[iid]['pre_score']:
                # 双通道分数更高：替换并标记
                c = dict(c)
                if isinstance(c.get('pre_reason'), list):
                    c['pre_reason'].append('original_goal 双通道召回提升')
                merged[iid] = c

        return list(merged.values())

    def _apply_feedback_memory(self, score, reasons, breakdown, query, profile, feedback_memory):
        rows = feedback_memory.get(profile.get('interface_id')) or []
        if not rows:
            breakdown.setdefault('feedback_memory', 0.0)
            return score, reasons, breakdown
        query_text = normalize_step_text(query)
        best = None
        best_similarity = 0.0
        for row in rows:
            memory_text = row.get('normalized_step_text') or normalize_step_text(row.get('step_text'))
            if query_text and memory_text == query_text:
                best = row
                best_similarity = 1.0
                break
            similarity = max(
                _jaccard(_char_bigrams(query_text), _char_bigrams(memory_text)),
                _jaccard(set(query_text), set(memory_text)) * 0.85,
                _common_prefix_ratio(query_text, memory_text),
            )
            if similarity > best_similarity:
                best = row
                best_similarity = similarity
        if not best or best_similarity < self.MEMORY_SIMILARITY_THRESHOLD:
            breakdown.setdefault('feedback_memory', 0.0)
            return score, reasons, breakdown
        name_strength = max(
            float(breakdown.get('semantic_name_similarity') or 0),
            min(1.0, float(breakdown.get('name_similarity') or 0) / 0.80) if breakdown.get('name_similarity') else 0.0,
            1.0 if float(breakdown.get('exact_name') or 0) > 0 else 0.0,
        )
        boost = self.MEMORY_EXACT_SCORE if best_similarity == 1.0 else self.MEMORY_SIMILAR_SCORE
        boost = min(0.25, boost + min(0.05, 0.01 * int(best.get('confirm_count') or 1)))
        if name_strength < 0.35:
            boost = min(boost, 0.08)
        breakdown['feedback_memory'] = round(boost, 4)
        new_score = min(score + boost, 1.0)
        breakdown['total'] = round(new_score, 4)
        reasons.append(
            f'用户曾确认「{best.get("step_text") or query}」使用该接口，记忆相似度 {best_similarity:.2f}，贡献 {boost:.2f}'
        )
        return new_score, reasons, breakdown

    def _score(self, query, query_tokens, profile):
        score = 0.0
        reasons = []
        breakdown = {}
        text_fields = {
            'description': profile.get('description') or '',
            'url': profile.get('url') or '',
            'path': profile.get('path') or '',
            'group': profile.get('group') or '',
            'request_fields': ' '.join(profile.get('request_fields') or []),
            'response_fields': ' '.join(profile.get('response_fields') or []),
            'name': profile.get('name') or '',
        }
        weights = {
            'name': 0.30,
            'description': 0.25,
            'url': 0.20,
            'path': 0.18,
            'request_fields': 0.15,
            'response_fields': 0.12,
            'group': 0.10,
        }
        profile_name = (profile.get('name') or '').strip().lower()
        query_normalized = (query or '').strip().lower()
        if query_normalized and profile_name == query_normalized:
            return self.EXACT_NAME_SCORE, ['接口名称与步骤完全匹配，基础分 0.85'], {
                'exact_name': self.EXACT_NAME_SCORE,
                'name_similarity': 1.0,
                'description': 0.0,
                'url': 0.0,
                'path': 0.0,
                'request_fields': 0.0,
                'response_fields': 0.0,
                'group': 0.0,
                'total': self.EXACT_NAME_SCORE,
            }
        name_score, name_reason, name_similarity = self._name_similarity_score(query, profile.get('name') or '')
        if name_score:
            score += name_score
            breakdown['name_similarity'] = round(name_score, 4)
            reasons.append(name_reason)
        for field, value in text_fields.items():
            field_score = 0.0
            value_lower = value.lower()
            if query and query in value:
                field_score += weights[field]
                reasons.append(f'{field} 包含原始步骤')
            hits = query_tokens & tokenize(value_lower)
            if hits:
                hit_score = min(weights[field], 0.04 * len(hits))
                field_score += hit_score
                reasons.append(f'{field} 命中原始步骤 {", ".join(sorted(hits)[:4])}')
            if field_score:
                breakdown[field] = round(field_score, 4)
                score += field_score
            else:
                breakdown.setdefault(field, 0.0)
        total = min(score, 1.0)
        breakdown.setdefault('name_similarity', 0.0)
        breakdown['semantic_name_similarity'] = round(name_similarity, 4)
        breakdown['total'] = round(total, 4)
        return total, reasons, breakdown

    def _name_similarity_score(self, query, name):
        query_text = _compact_text(query)
        name_text = _compact_text(name)
        if not query_text or not name_text:
            return 0.0, '', 0.0
        if query_text in name_text or name_text in query_text:
            similarity = min(len(query_text), len(name_text)) / max(len(query_text), len(name_text))
            score = max(0.45, 0.75 * similarity)
            return score, f'接口名称与步骤部分包含，相似度 {similarity:.2f}，贡献 {score:.2f}', similarity

        bigram_similarity = _jaccard(_char_bigrams(query_text), _char_bigrams(name_text))
        char_similarity = _jaccard(set(query_text), set(name_text))
        prefix_similarity = _common_prefix_ratio(query_text, name_text)
        similarity = max(bigram_similarity, char_similarity * 0.85, prefix_similarity)
        if similarity < self.NAME_SIMILARITY_THRESHOLD:
            return 0.0, '', similarity
        score = min(0.80, max(0.25, 0.80 * similarity))
        return score, (
            f'接口名称与步骤文本相似，相似度 {similarity:.2f}，贡献 {score:.2f}'
            f'（bigram {bigram_similarity:.2f} / char {char_similarity:.2f} / prefix {prefix_similarity:.2f}）'
        ), similarity
