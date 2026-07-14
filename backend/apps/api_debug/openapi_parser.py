"""OpenAPI 3.x / Swagger 2.0 导入解析器

将 OpenAPI Specification JSON/YAML 转换为 ApiGroup + ApiInterface + Environment 对象。
支持 Swagger 2.0 和 OpenAPI 3.0/3.1。
"""
import json
import re

import yaml

from .models import ApiGroup, ApiInterface


def _resolve_ref(spec, ref_string):
    """解析 $ref 引用，如 '#/components/schemas/Pet' → 对应的 dict"""
    if not ref_string or not ref_string.startswith('#/'):
        return {}
    parts = ref_string.lstrip('#/').split('/')
    node = spec
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part, {})
        else:
            return {}
    return node or {}


def _deep_resolve(spec, obj):
    """递归解析对象中的所有 $ref"""
    if isinstance(obj, dict):
        if '$ref' in obj:
            resolved = _resolve_ref(spec, obj['$ref'])
            return _deep_resolve(spec, resolved)
        return {k: _deep_resolve(spec, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_resolve(spec, item) for item in obj]
    return obj


def _schema_to_example(spec, schema, depth=0):
    """从 schema 生成示例 JSON body（用于 requestBody 默认值）"""
    if depth > 5:
        return {}
    schema = _deep_resolve(spec, schema)
    if not schema or not isinstance(schema, dict):
        return {}

    if 'example' in schema:
        return schema['example']
    if 'default' in schema:
        return schema['default']
    if 'enum' in schema:
        return schema['enum'][0]

    schema_type = schema.get('type', '')

    if schema_type == 'object' or 'properties' in schema:
        result = {}
        for prop_name, prop_schema in schema.get('properties', {}).items():
            result[prop_name] = _schema_to_example(spec, prop_schema, depth + 1)
        return result

    if schema_type == 'array':
        items = schema.get('items', {})
        return [_schema_to_example(spec, items, depth + 1)]

    type_map = {
        'string': 'string',
        'integer': 0,
        'number': 0.0,
        'boolean': True,
    }
    format_examples = {
        'date': '2025-01-01',
        'date-time': '2025-01-01T00:00:00Z',
        'email': 'user@example.com',
        'uri': 'https://example.com',
        'uuid': '00000000-0000-0000-0000-000000000000',
    }
    fmt = schema.get('format', '')
    if fmt in format_examples:
        return format_examples[fmt]

    return type_map.get(schema_type, '')


def _schema_to_json_body(spec, schema):
    """将 schema 转为 JSON 字符串作为默认 body"""
    example = _schema_to_example(spec, schema)
    if example:
        return json.dumps(example, ensure_ascii=False, indent=2)
    return ''


def _detect_version(spec):
    """检测 OpenAPI 规范版本，返回 'swagger2' 或 'openapi3'"""
    if 'swagger' in spec and str(spec['swagger']).startswith('2'):
        return 'swagger2'
    if 'openapi' in spec and str(spec['openapi']).startswith('3'):
        return 'openapi3'
    raise ValueError('不支持的规范版本，仅支持 Swagger 2.0 和 OpenAPI 3.0/3.1')


def _get_base_url_swagger2(spec):
    """从 Swagger 2.0 提取 base URL"""
    host = spec.get('host', '')
    base_path = spec.get('basePath', '/')
    schemes = spec.get('schemes', ['https'])
    scheme = schemes[0] if schemes else 'https'
    if host:
        return f'{scheme}://{host}{base_path}'
    return base_path


def _get_base_url_openapi3(spec):
    """从 OpenAPI 3.x 提取 base URL"""
    servers = spec.get('servers', [])
    if servers and isinstance(servers[0], dict):
        url = servers[0].get('url', '')
        variables = servers[0].get('variables', {})
        for var_name, var_info in variables.items():
            default = var_info.get('default', '')
            url = url.replace('{' + var_name + '}', str(default))
        return url
    return ''


def _extract_security_schemes_swagger2(spec):
    """从 Swagger 2.0 提取安全方案"""
    definitions = spec.get('securityDefinitions', {})
    return _convert_security_schemes(definitions, 'swagger2')


def _extract_security_schemes_openapi3(spec):
    """从 OpenAPI 3.x 提取安全方案"""
    components = spec.get('components', {})
    definitions = components.get('securitySchemes', {})
    return _convert_security_schemes(definitions, 'openapi3')


def _convert_security_schemes(definitions, version):
    """将安全方案转换为 Bug Shoot Environment 认证配置"""
    auth_type = 'none'
    auth_header = 'Authorization'
    auth_token = ''

    for name, scheme in definitions.items():
        scheme = dict(scheme)
        scheme_type = scheme.get('type', '')

        if scheme_type == 'apiKey':
            auth_type = 'api_key'
            auth_header = scheme.get('name', 'X-API-Key')
            break

        if scheme_type == 'http':
            http_scheme = scheme.get('scheme', 'bearer').lower()
            if http_scheme == 'bearer':
                auth_type = 'bearer'
                auth_header = 'Authorization'
            elif http_scheme == 'basic':
                auth_type = 'basic'
            break

        if scheme_type == 'oauth2':
            auth_type = 'bearer'
            auth_header = 'Authorization'
            break

        if version == 'swagger2' and scheme_type == 'basic':
            auth_type = 'basic'
            break

    return {
        'auth_type': auth_type,
        'auth_header': auth_header,
        'auth_token': auth_token,
    }


def _get_path_parameters_oas3(spec, path_item):
    """提取 path 级别的公共参数"""
    params = path_item.get('parameters', [])
    return _resolve_parameters(spec, params)


def _resolve_parameters(spec, params):
    """解析参数列表，返回 (query_params, headers)"""
    query_params = {}
    headers = {}
    for param in params:
        param = _deep_resolve(spec, param)
        if not isinstance(param, dict):
            continue
        name = param.get('name', '')
        location = param.get('in', '')
        schema = _deep_resolve(spec, param.get('schema', {}))
        example = param.get('example') or schema.get('example', '')
        if not name:
            continue
        if location == 'query':
            query_params[name] = str(example) if example else ''
        elif location == 'header':
            headers[name] = str(example) if example else ''
    return query_params, headers


def _parse_request_body_swagger2(spec, operation):
    """解析 Swagger 2.0 的 body parameter"""
    params = operation.get('parameters', [])
    for param in params:
        param = _deep_resolve(spec, param)
        if param.get('in') == 'body':
            schema = param.get('schema', {})
            body = _schema_to_json_body(spec, schema)
            if body:
                return 'json', body
            return 'raw', ''
    for param in params:
        param = _deep_resolve(spec, param)
        if param.get('in') == 'formData':
            return 'form', ''
    return 'none', ''


def _parse_request_body_openapi3(spec, operation):
    """解析 OpenAPI 3.x 的 requestBody"""
    request_body = operation.get('requestBody')
    if not request_body:
        return 'none', ''
    request_body = _deep_resolve(spec, request_body)
    content = request_body.get('content', {})

    priority = [
        'application/json',
        'application/x-www-form-urlencoded',
        'multipart/form-data',
        'application/xml',
        'text/plain',
    ]

    for media_type in priority:
        if media_type in content:
            media_obj = content[media_type]
            schema = media_obj.get('schema', {})
            if 'json' in media_type:
                body = _schema_to_json_body(spec, schema)
                return 'json', body
            elif 'form' in media_type or 'urlencoded' in media_type:
                return 'form', ''
            elif 'xml' in media_type:
                body = _schema_to_json_body(spec, schema)
                return 'xml', body
            else:
                body = _schema_to_json_body(spec, schema)
                return 'raw', body

    for media_type, media_obj in content.items():
        schema = media_obj.get('schema', {})
        if 'json' in media_type:
            return 'json', _schema_to_json_body(spec, schema)
        return 'raw', _schema_to_json_body(spec, schema)

    return 'none', ''


def _build_url_with_path_params(base_url, path, path_params):
    """将 path 参数替换为示例值"""
    url = base_url.rstrip('/') + path
    for param_name in re.findall(r'\{(\w+)\}', path):
        example_value = path_params.get(param_name, 'example')
        url = url.replace('{' + param_name + '}', str(example_value))
    return url


def _extract_path_param_examples(path, path_item, spec):
    """从 path 参数中提取示例值"""
    examples = {}
    params = path_item.get('parameters', [])
    for param in params:
        param = _deep_resolve(spec, param)
        if isinstance(param, dict) and param.get('in') == 'path':
            name = param.get('name', '')
            schema = _deep_resolve(spec, param.get('schema', {}))
            example = param.get('example') or schema.get('example', '')
            if name and example:
                examples[name] = example
    return examples


def import_openapi_spec(spec, user, project=None):
    """导入 OpenAPI / Swagger 规范

    :param spec: OpenAPI JSON 对象 (dict)
    :param user: 当前用户
    :param project: 目标项目
    :returns: dict with 'groups_count', 'interfaces_count', 'environments'
    """
    version = _detect_version(spec)
    info = spec.get('info', {})
    spec_title = info.get('title', 'Imported API')

    if version == 'swagger2':
        base_url = _get_base_url_swagger2(spec)
        auth_info = _extract_security_schemes_swagger2(spec)
    else:
        base_url = _get_base_url_openapi3(spec)
        auth_info = _extract_security_schemes_openapi3(spec)

    created_groups = []
    created_interfaces = []

    root_group, _ = ApiGroup.objects.get_or_create(
        name=spec_title,
        project=project,
        created_by=user,
        parent=None,
        defaults={'sort_order': 0},
    )
    created_groups.append(root_group)

    tag_groups = {}
    tags_list = spec.get('tags', [])
    for tag_info in tags_list:
        tag_name = tag_info.get('name', '')
        if not tag_name:
            continue
        group, _ = ApiGroup.objects.get_or_create(
            name=tag_name,
            project=project,
            created_by=user,
            parent=root_group,
            defaults={'sort_order': len(created_groups)},
        )
        created_groups.append(group)
        tag_groups[tag_name] = group

    paths = spec.get('paths', {})
    http_methods = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        path_param_examples = _extract_path_param_examples(path, path_item, spec)
        common_query, common_headers = _get_path_parameters_oas3(spec, path_item)

        for method in http_methods:
            operation = path_item.get(method)
            if not operation:
                continue

            operation = _deep_resolve(spec, operation)
            op_name = operation.get('summary') or operation.get('operationId') or f'{method.upper()} {path}'
            description = operation.get('description', '')

            url = _build_url_with_path_params(base_url, path, path_param_examples)

            query_params = dict(common_query)
            headers = dict(common_headers)

            op_query, op_headers = _resolve_parameters(
                spec, operation.get('parameters', [])
            )
            query_params.update(op_query)
            headers.update(op_headers)

            if version == 'swagger2':
                body_type, body = _parse_request_body_swagger2(spec, operation)
            else:
                body_type, body = _parse_request_body_openapi3(spec, operation)

            op_tags = operation.get('tags', [])
            group = None
            if op_tags:
                group = tag_groups.get(op_tags[0])

            interface = ApiInterface.objects.create(
                project=project,
                name=op_name,
                protocol='http',
                method=method.upper(),
                url=url,
                headers=headers,
                query_params=query_params,
                body_type=body_type,
                body=body,
                group=group or root_group,
                description=description,
                created_by=user,
            )
            created_interfaces.append(interface)

    environments = []
    if base_url:
        env_data = {
            'name': f'{spec_title} - 环境',
            'base_url': base_url,
            'auth_type': auth_info.get('auth_type', 'none'),
            'auth_header': auth_info.get('auth_header', 'Authorization'),
            'auth_token': auth_info.get('auth_token', ''),
            'variables': [],
        }

        if version == 'openapi3':
            servers = spec.get('servers', [])
            if servers and isinstance(servers[0], dict):
                variables = servers[0].get('variables', {})
                for var_name, var_info in variables.items():
                    env_data['variables'].append({
                        'key': var_name,
                        'value': var_info.get('default', ''),
                    })

        environments.append(env_data)

    return {
        'spec_title': spec_title,
        'version': version,
        'groups_count': len(created_groups),
        'interfaces_count': len(created_interfaces),
        'environments': environments,
    }
