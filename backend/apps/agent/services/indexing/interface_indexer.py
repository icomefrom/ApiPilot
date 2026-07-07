import json
import re
from urllib.parse import urlparse

from apps.api_debug.models import ApiInterface

_TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+')


def tokenize(value):
    if value is None:
        return set()
    return {token.lower() for token in _TOKEN_PATTERN.findall(str(value)) if token.strip()}


def flatten_json_keys(value, prefix=''):
    keys = []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return keys
    if isinstance(value, dict):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            keys.append(path)
            keys.extend(flatten_json_keys(child, path))
    elif isinstance(value, list) and value:
        keys.extend(flatten_json_keys(value[0], prefix))
    return keys


class InterfaceIndexer:
    def build_profiles(self, project):
        interfaces = ApiInterface.objects.filter(project=project).select_related('group').order_by('-updated_at', '-id')
        return [self.build_profile(interface) for interface in interfaces]

    def build_profile(self, interface):
        request_fields = sorted(set(
            list((interface.query_params or {}).keys())
            + list((interface.headers or {}).keys())
            + flatten_json_keys(interface.body)
        ))
        response_fields = self._extract_response_fields(interface)
        group_name = interface.group.name if interface.group else ''
        path = urlparse(interface.url or '').path or interface.url or ''
        search_text = ' '.join([
            interface.name or '', interface.method or '', interface.url or '', path,
            group_name, interface.description or '', ' '.join(request_fields), ' '.join(response_fields),
        ])
        return {
            'interface_id': interface.id,
            'name': interface.name,
            'method': interface.method,
            'protocol': interface.protocol,
            'url': interface.url,
            'path': path,
            'group': group_name,
            'description': interface.description,
            'request_fields': request_fields[:80],
            'response_fields': response_fields[:80],
            'tokens': sorted(tokenize(search_text)),
        }

    def _extract_response_fields(self, interface):
        fields = []
        for assertion in interface.assertions or []:
            if isinstance(assertion, dict):
                target = assertion.get('target') or assertion.get('jsonpath') or assertion.get('field')
                if target:
                    fields.append(str(target))
        return sorted(set(fields))
