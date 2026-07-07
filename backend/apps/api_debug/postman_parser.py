"""Postman Collection v2.1 导入解析器

将 Postman Collection JSON 转换为 ApiInterface + ApiGroup 对象。
支持嵌套文件夹自动映射为分组，Postman 变量直接用真实值替换。
"""
import json
import re


def _extract_variables_from_postman_vars(variables):
    """从 Postman 变量列表提取键值对，返回环境变量列表格式 [{'key': ..., 'value': ...}]"""
    result = []
    if not variables:
        return result
    for v in variables:
        if isinstance(v, dict) and 'key' in v:
            val = v.get('value', '')
            # Postman 变量值可能是 dict 类型（如 request headers），转为字符串
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            result.append({'key': v['key'], 'value': str(val) if val is not None else ''})
    return result


def _replace_postman_vars(text, vars_dict):
    """将 Postman 的 {{variable}} 用真实值替换，找不到的保留为 {{env.variable}}

    :param text: 待替换的字符串
    :param vars_dict: Postman 变量字典 {'base_url': 'https://example.com', ...}
    """
    if not text or not isinstance(text, str):
        return text or ''

    def _replace(m):
        inner = m.group(1)
        # 已经是 bug-shoot 内置格式，不替换
        if inner.startswith('vars.') or inner.startswith('globals.') or inner.startswith('env.'):
            return m.group(0)
        # 优先用 Postman 真实值替换
        if inner in vars_dict:
            return str(vars_dict[inner])
        # 找不到真实值，保留为 {{env.xxx}} 格式供用户后续配置
        return '{{env.' + inner + '}}'

    return re.sub(r'\{\{([^}]+)\}\}', _replace, text)


def _parse_postman_url(url_obj):
    """解析 Postman URL 对象为字符串

    Postman v2.1 的 URL 可能是字符串或对象:
    - 字符串: "https://api.example.com/users"
    - 对象: {raw: "...", protocol: "https", host: [...], path: [...], query: [...]}
    """
    if isinstance(url_obj, str):
        return url_obj
    if isinstance(url_obj, dict):
        return url_obj.get('raw', '')
    return str(url_obj) if url_obj else ''


def _parse_postman_headers(header_list):
    """解析 Postman header 列表为字典"""
    headers = {}
    if not header_list:
        return headers
    for h in header_list:
        if isinstance(h, dict):
            key = h.get('key', '')
            value = h.get('value', '')
            if key and not h.get('disabled', False):
                headers[key] = value
    return headers


def _parse_postman_query(query_list):
    """解析 Postman query 参数列表为字典"""
    params = {}
    if not query_list:
        return params
    for q in query_list:
        if isinstance(q, dict):
            key = q.get('key', '')
            value = q.get('value', '')
            if key and not q.get('disabled', False):
                params[key] = value
    return params


def _parse_postman_body(body_obj):
    """解析 Postman request body，返回 (body_type, body_str)

    Postman body modes: raw, formdata, urlencoded, file, graphql
    """
    if not body_obj or not isinstance(body_obj, dict):
        return 'none', ''

    mode = body_obj.get('mode', '')

    if mode == 'raw':
        raw = body_obj.get('raw', '')
        options = body_obj.get('options', {})
        language = options.get('raw', {}).get('language', '')
        if language == 'json' or (raw and raw.strip().startswith('{')):
            return 'json', raw
        elif language == 'xml':
            return 'xml', raw
        else:
            return 'raw', raw

    elif mode == 'urlencoded':
        data = body_obj.get('urlencoded', [])
        form_dict = {}
        for item in data:
            if isinstance(item, dict) and not item.get('disabled', False):
                form_dict[item.get('key', '')] = item.get('value', '')
        return 'form', json.dumps(form_dict, ensure_ascii=False)

    elif mode == 'formdata':
        # multipart form - 跳过文件类型，只保留文本字段
        data = body_obj.get('formdata', [])
        form_dict = {}
        for item in data:
            if isinstance(item, dict) and item.get('type') == 'text' and not item.get('disabled', False):
                form_dict[item.get('key', '')] = item.get('value', '')
        if form_dict:
            return 'form', json.dumps(form_dict, ensure_ascii=False)
        return 'none', ''

    elif mode == 'graphql':
        graphql_data = body_obj.get('graphql', {})
        query = graphql_data.get('query', '')
        variables = graphql_data.get('variables', '')
        if variables:
            try:
                body = json.dumps({'query': query, 'variables': json.loads(variables) if isinstance(variables, str) else variables})
            except (json.JSONDecodeError, TypeError):
                body = json.dumps({'query': query, 'variables': variables})
        else:
            body = json.dumps({'query': query})
        return 'json', body

    return 'none', ''


def _parse_postman_request(request_obj):
    """从 Postman item 的 request 字段提取接口信息

    返回 dict: {method, url, headers, query_params, body_type, body}
    """
    if not request_obj:
        return {}

    method = request_obj.get('method', 'GET').upper()
    url = _parse_postman_url(request_obj.get('url', ''))
    headers = _parse_postman_headers(request_obj.get('header', []))
    query_params = {}

    # 从 URL 对象提取 query 参数（优先于 request.urlencoded）
    url_obj = request_obj.get('url')
    if isinstance(url_obj, dict):
        query_params = _parse_postman_query(url_obj.get('query', []))

    # 解析 body
    body_type, body = _parse_postman_body(request_obj.get('body'))

    return {
        'method': method,
        'url': url,
        'headers': headers,
        'query_params': query_params,
        'body_type': body_type,
        'body': body,
    }


def _process_item(item, user, vars_dict=None, parent_group=None, created_groups=None, created_interfaces=None, project=None):
    """递归处理 Postman collection item

    Postman 结构:
    - item 可以是文件夹 (含 name + item 子数组)
    - item 可以是请求 (含 name + request)

    :param vars_dict: Postman 变量字典，用于将 {{var}} 直接替换为真实值
    """
    if created_groups is None:
        created_groups = []
    if created_interfaces is None:
        created_interfaces = []
    if vars_dict is None:
        vars_dict = {}

    from .models import ApiGroup, ApiInterface

    name = item.get('name', 'Unnamed')
    children = item.get('item', [])
    request_obj = item.get('request')

    if children and not request_obj:
        # 这是一个文件夹 → 创建分组
        group, _ = ApiGroup.objects.get_or_create(
            name=name,
            project=project,
            created_by=user,
            parent=parent_group,
            defaults={'sort_order': len(created_groups)},
        )
        created_groups.append(group)
        # 递归处理子项
        for child in children:
            _process_item(child, user, vars_dict=vars_dict, parent_group=group,
                         created_groups=created_groups,
                         created_interfaces=created_interfaces, project=project)
    elif request_obj:
        # 这是一个请求 → 创建接口
        parsed = _parse_postman_request(request_obj)

        # 用 Postman 真实变量值替换 {{var}}，找不到的保留为 {{env.var}}
        url = _replace_postman_vars(parsed.get('url', ''), vars_dict)
        headers = {k: _replace_postman_vars(v, vars_dict) for k, v in parsed.get('headers', {}).items()}
        query_params = {k: _replace_postman_vars(v, vars_dict) for k, v in parsed.get('query_params', {}).items()}
        body = _replace_postman_vars(parsed.get('body', ''), vars_dict)

        interface = ApiInterface.objects.create(
            project=project,
            name=name,
            protocol='http',
            method=parsed.get('method', 'GET'),
            url=url,
            headers=headers,
            query_params=query_params,
            body_type=parsed.get('body_type', 'none'),
            body=body,
            group=parent_group,
            created_by=user,
        )
        created_interfaces.append(interface)


def import_postman_collection(collection, user, project=None):
    """导入 Postman Collection v2.1

    :param collection: Postman Collection JSON 对象 (dict)
    :param user: 当前用户
    :returns: dict with 'groups_count', 'interfaces_count', 'environments'
    """
    info = collection.get('info', {})
    collection_name = info.get('name', 'Imported Collection')

    # 检查 schema 版本
    schema = info.get('schema', '')
    if 'v2.1' not in schema and 'v2.0' not in schema and not collection.get('item'):
        raise ValueError('不支持的 Postman Collection 格式，仅支持 v2.0/v2.1')

    # 先提取 collection 级别变量，用于导入时直接替换真实值
    postman_vars = collection.get('variable', [])
    vars_dict = {}
    for v in postman_vars:
        if isinstance(v, dict) and 'key' in v:
            val = v.get('value', '')
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            vars_dict[v['key']] = str(val) if val is not None else ''

    created_groups = []
    created_interfaces = []

    # 以 collection 名称创建顶级分组，所有接口和子文件夹挂到该分组下
    from .models import ApiGroup
    root_group, _ = ApiGroup.objects.get_or_create(
        name=collection_name,
        project=project,
        created_by=user,
        parent=None,
        defaults={'sort_order': 0},
    )
    created_groups.append(root_group)

    # 处理所有 items，传入 vars_dict 做真实值替换，父分组为 collection 分组
    items = collection.get('item', [])
    for item in items:
        _process_item(item, user, vars_dict=vars_dict, parent_group=root_group,
                     created_groups=created_groups,
                     created_interfaces=created_interfaces, project=project)

    # 提取 Postman collection 级别变量，作为环境变量返回（供用户后续切换环境）
    environments = []
    if postman_vars:
        env_vars = _extract_variables_from_postman_vars(postman_vars)
        if env_vars:
            environments.append({
                'name': f'{collection_name} - 变量',
                'variables': env_vars,
            })

    return {
        'collection_name': collection_name,
        'groups_count': len(created_groups),
        'interfaces_count': len(created_interfaces),
        'environments': environments,
    }