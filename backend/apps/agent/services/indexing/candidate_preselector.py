from .interface_indexer import tokenize


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

    def select(self, steps, profiles, limit=20):
        results = []
        for step in steps:
            step_text = step.get('text') or ''
            query_tokens = tokenize(step_text)
            scored = []
            for profile in profiles:
                score, reasons = self._score(step_text, query_tokens, profile)
                # 只保留超过最低阈值的候选，过滤掉完全不相关的接口
                if score >= self.MIN_PRE_SCORE:
                    item = {key: value for key, value in profile.items() if key != 'tokens'}
                    item.update({'pre_score': round(score, 4), 'pre_reason': reasons})
                    scored.append(item)
            scored.sort(key=lambda item: item['pre_score'], reverse=True)
            results.append({
                'step_index': step['index'],
                'step_text': step.get('text') or '',
                'resolved_text': step.get('resolved_text') or step.get('text') or '',
                'candidates': scored[:limit],
            })
        return results

    def _score(self, query, query_tokens, profile):
        score = 0.0
        reasons = []
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
            return self.EXACT_NAME_SCORE, ['name 与原始步骤完全匹配']
        name_score, name_reason = self._name_similarity_score(query, profile.get('name') or '')
        if name_score:
            score += name_score
            reasons.append(name_reason)
        for field, value in text_fields.items():
            value_lower = value.lower()
            if query and query in value:
                score += weights[field]
                reasons.append(f'{field} 包含原始步骤')
            hits = query_tokens & tokenize(value_lower)
            if hits:
                score += min(weights[field], 0.04 * len(hits))
                reasons.append(f'{field} 命中原始步骤 {", ".join(sorted(hits)[:4])}')
        return min(score, 1.0), reasons

    def _name_similarity_score(self, query, name):
        query_text = _compact_text(query)
        name_text = _compact_text(name)
        if not query_text or not name_text:
            return 0.0, ''
        if query_text in name_text or name_text in query_text:
            similarity = min(len(query_text), len(name_text)) / max(len(query_text), len(name_text))
            score = max(0.45, 0.75 * similarity)
            return score, f'name 与原始步骤部分包含，相似度 {similarity:.2f}'

        bigram_similarity = _jaccard(_char_bigrams(query_text), _char_bigrams(name_text))
        char_similarity = _jaccard(set(query_text), set(name_text))
        prefix_similarity = _common_prefix_ratio(query_text, name_text)
        similarity = max(bigram_similarity, char_similarity * 0.85, prefix_similarity)
        if similarity < self.NAME_SIMILARITY_THRESHOLD:
            return 0.0, ''
        score = min(0.80, max(0.25, 0.80 * similarity))
        return score, (
            f'name 与原始步骤文本相似，相似度 {similarity:.2f}'
            f'（bigram {bigram_similarity:.2f} / char {char_similarity:.2f} / prefix {prefix_similarity:.2f}）'
        )
