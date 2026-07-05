import re
from urllib.parse import urlparse

from apps.agent.schemas import METHOD_HINTS, OPERATION_ALIASES
from apps.api_debug.models import ApiInterface

_TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+')


def tokenize(value):
    if value is None:
        return set()
    return {token.lower() for token in _TOKEN_PATTERN.findall(str(value)) if token.strip()}


class InterfaceRetriever:
    """基于项目内接口元数据做轻量检索。"""

    def retrieve(self, project, intent_steps, limit=5):
        interfaces = list(
            ApiInterface.objects.filter(project=project)
            .select_related('group')
            .order_by('-updated_at', '-id')
        )
        return [self._rank_for_step(step, interfaces, limit) for step in intent_steps]

    def _rank_for_step(self, step, interfaces, limit):
        candidates = []
        for interface in interfaces:
            score, reasons = self._score(step, interface)
            if score > 0:
                candidates.append({
                    'interface_id': interface.id,
                    'name': interface.name,
                    'method': interface.method,
                    'url': interface.url,
                    'protocol': interface.protocol,
                    'group_name': interface.group.name if interface.group else '',
                    'score': round(min(score, 1), 4),
                    'reason': '；'.join(reasons),
                })
        candidates.sort(key=lambda item: item['score'], reverse=True)
        return {
            'step_index': step['index'],
            'operation': step['operation'],
            'object': step.get('object') or '',
            'source_text': step.get('source_text') or '',
            'candidates': candidates[:limit],
        }

    def _score(self, step, interface):
        operation = step.get('operation') or 'unknown'
        obj = step.get('object') or ''
        source_text = step.get('source_text') or ''
        reasons = []
        score = 0.0

        haystack = ' '.join([
            interface.name or '', interface.url or '', interface.description or '',
            interface.rpc_method or '', interface.rpc_service or '',
            interface.group.name if interface.group else '',
            str(interface.query_params or ''), interface.body or '', str(interface.headers or ''),
        ])
        haystack_lower = haystack.lower()

        obj_tokens = tokenize(obj)
        source_tokens = tokenize(source_text)
        haystack_tokens = tokenize(haystack)
        if obj and obj in haystack:
            score += 0.32
            reasons.append('业务对象命中')
        token_hits = (obj_tokens | source_tokens) & haystack_tokens
        if token_hits:
            score += min(0.26, 0.08 * len(token_hits))
            reasons.append('关键词命中: ' + ', '.join(sorted(token_hits)[:4]))

        aliases = OPERATION_ALIASES.get(operation, [])
        alias_hits = [alias for alias in aliases if alias.lower() in haystack_lower]
        if alias_hits:
            score += 0.22
            reasons.append('动作词命中: ' + alias_hits[0])

        method_hints = METHOD_HINTS.get(operation, set())
        if interface.method in method_hints:
            score += 0.12
            reasons.append('请求方法匹配')

        path = urlparse(interface.url).path or interface.url or ''
        if path and any(token in path.lower() for token in source_tokens):
            score += 0.08
            reasons.append('URL 路径命中')

        return score, reasons
