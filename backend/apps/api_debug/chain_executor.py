"""链路测试执行引擎 — 按拓扑顺序逐节点执行，支持变量提取/替换/条件分支"""
import json
import re
import time
import requests as _requests
from datetime import datetime

from .models import Chain, ChainResult, ApiInterface
from .executor import (
    _apply_env_request_context,
    _build_env_context,
    _is_private_host,
    MAX_RESPONSE_BODY_SIZE,
    execute_websocket,
    execute_rpc,
)
from .script_executor import execute_assertion_script


# 链路节点单步响应体最大存储（64KB，足以覆盖绝大多数 API 响应同时保持 JSONField 体积合理）
MAX_CHAIN_STEP_BODY_SIZE = 65536

# 变量占位符正则：{{globals.key}} 或 {{vars.key}}
_VAR_PATTERN = re.compile(r'\{\{(globals|vars)\.(\w+)\}\}')

# 环境变量占位符正则：{{env.key}}
_ENV_VAR_PATTERN = re.compile(r'\{\{env\.(\w+)\}\}')


def _replace_vars(template, vars_pool, env_vars=None):
    """将字符串中的 {{globals.key}} / {{vars.key}} / {{env.key}} 替换为实际值"""
    if not isinstance(template, str):
        return template

    def _sub(m):
        scope, key = m.group(1), m.group(2)
        source = vars_pool.get(scope, {})
        val = source.get(key, m.group(0))  # 未找到保留原始占位符
        if not isinstance(val, str):
            val = json.dumps(val, ensure_ascii=False)
        return val

    result = _VAR_PATTERN.sub(_sub, template)

    # 替换环境变量 {{env.key}}
    if env_vars:
        def _env_sub(m):
            key = m.group(1)
            val = env_vars.get(key, m.group(0))
            if not isinstance(val, str):
                val = json.dumps(val, ensure_ascii=False)
            return val
        result = _ENV_VAR_PATTERN.sub(_env_sub, result)

    return result


def _deep_replace_vars(obj, vars_pool, env_vars=None):
    """深度遍历 dict/list，替换所有字符串值中的变量占位符"""
    if isinstance(obj, str):
        return _replace_vars(obj, vars_pool, env_vars)
    if isinstance(obj, dict):
        return {k: _deep_replace_vars(v, vars_pool, env_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_replace_vars(v, vars_pool, env_vars) for v in obj]
    return obj


def _extract_jsonpath(data, jsonpath_expr):
    """从数据中按 JSONPath 提取值（简化实现，支持 $.body.xxx.yyy 形式）"""
    try:
        from jsonpath_ng import parse as jp_parse
        match = jp_parse(jsonpath_expr)
        matches = match.find(data)
        if matches:
            return matches[0].value
    except ImportError:
        # jsonpath_ng 未安装，用简化路径解析
        pass
    except Exception:
        pass

    # 简化路径解析：$.body.data.token → data["body"]["data"]["token"]
    path = jsonpath_expr.strip()
    if path.startswith('$.'):
        path = path[2:]
    elif path.startswith('$'):
        path = path[1:]

    keys = []
    for part in re.split(r'\.|\[|\]', path):
        part = part.strip().strip('"').strip("'")
        if not part:
            continue
        try:
            keys.append(int(part))
        except ValueError:
            keys.append(part)

    current = data
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int):
                current = current[key]
            else:
                return None
        except (KeyError, IndexError, TypeError):
            return None
    return current


def _compare_values(actual, operator, expected):
    """通用值比较，供断言和条件节点共用"""
    if operator == 'equals':
        return str(actual) == str(expected)
    elif operator == 'not_equals':
        return str(actual) != str(expected)
    elif operator == 'contains':
        return str(expected) in str(actual)
    elif operator == 'not_contains':
        return str(expected) not in str(actual)
    elif operator == 'greater_than':
        try:
            return float(actual) > float(expected)
        except (ValueError, TypeError):
            return False
    elif operator == 'less_than':
        try:
            return float(actual) < float(expected)
        except (ValueError, TypeError):
            return False
    elif operator == 'exists':
        return actual is not None
    elif operator == 'not_exists':
        return actual is None
    return False


def _run_assertions_jsonpath(assertions, wrapper):
    """执行 JSONPath 断言（复用前端逻辑的后端版本）"""
    results = []
    for rule in assertions:
        if rule.get('type') != 'jsonpath' and 'jsonpath' not in rule:
            continue
        jsonpath = rule.get('jsonpath', '')
        operator = rule.get('operator', 'equals')
        expected = rule.get('expected', '')

        actual = _extract_jsonpath(wrapper, jsonpath)
        if actual is None:
            results.append({'pass': False, 'error': f'JSONPath 未匹配: {jsonpath}', 'rule': rule})
            continue

        pass_ = _compare_values(actual, operator, expected)
        results.append({'pass': pass_, 'actual': actual, 'rule': rule})

    return results


def _run_assertions_script(assertions, response_wrapper, vars_pool):
    """执行脚本断言规则（复用 script_executor 的沙箱）"""
    results = []
    for rule in assertions:
        if rule.get('type') != 'script':
            continue
        script_code = rule.get('script', '')
        timeout = rule.get('timeout', 10)
        if not script_code.strip():
            continue

        # 构建 context：body 需转回字符串给 _ResponseProxy
        body_str = response_wrapper.get('body')
        if not isinstance(body_str, str):
            try:
                body_str = json.dumps(body_str, ensure_ascii=False)
            except (TypeError, ValueError):
                body_str = str(body_str) if body_str is not None else ''

        context = {
            'status_code': response_wrapper.get('status_code', 0),
            'headers': response_wrapper.get('headers', {}),
            'body': body_str,
            'elapsed_ms': response_wrapper.get('elapsed_ms', 0),
            'vars': vars_pool.get('vars', {}),
            'globals': vars_pool.get('globals', {}),
        }

        result = execute_assertion_script(script_code, context, timeout)
        results.append({
            'pass': result.get('pass', False),
            'error': result.get('error'),
            'output': result.get('output', ''),
            'rule': rule,
        })

    return results


def _topological_sort(nodes, edges):
    """拓扑排序：返回按执行顺序排列的节点 ID 列表（BFS，支持分叉）"""
    node_ids = [n['id'] for n in nodes]
    in_degree = {nid: 0 for nid in node_ids}
    adj = {nid: [] for nid in node_ids}

    for edge in edges:
        src, tgt = edge['source'], edge['target']
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    # 入度为 0 的节点入队
    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    ordered = []

    while queue:
        nid = queue.pop(0)
        ordered.append(nid)
        for next_nid in adj[nid]:
            in_degree[next_nid] -= 1
            if in_degree[next_nid] == 0:
                queue.append(next_nid)

    return ordered


def _get_next_nodes(node_id, edges, condition_result=None):
    """获取当前节点执行后应该走的下游节点列表

    condition_result: None 表示无条件；True/False 表示条件分支结果
    """
    next_nodes = []
    for edge in edges:
        if edge['source'] != node_id:
            continue
        handle = edge.get('sourceHandle', 'out')
        if condition_result is None:
            # 非条件节点，走 out
            if handle in ('out', None):
                next_nodes.append(edge['target'])
        elif condition_result is True:
            if handle == 'true':
                next_nodes.append(edge['target'])
        elif condition_result is False:
            if handle == 'false':
                next_nodes.append(edge['target'])
    return next_nodes


def execute_chain(chain, user, env_vars=None):
    """执行链路测试

    :param chain: Chain 模型实例
    :param user: 执行用户
    :param env_vars: 环境变量字典 {'key': 'value', ...} 或列表 [{'key': 'k', 'value': 'v'}, ...]
    :returns: ChainResult 模型实例
    """
    env_context = _build_env_context(env_vars)
    env_dict = env_context['vars']

    nodes_list = chain.nodes or []
    edges_list = chain.edges or []
    globals_list = chain.globals or []

    # 初始化运行时变量池
    vars_pool = {
        'globals': {g['key']: g.get('value', '') for g in globals_list},
        'vars': {},
    }

    # 追踪最近上游接口节点的响应包装，供条件节点 JSONPath/脚本模式使用
    _last_response_wrapper = None

    # 构建节点 ID → 节点数据映射
    node_map = {n['id']: n for n in nodes_list}

    # 创建执行结果记录
    chain_result = ChainResult.objects.create(
        project=chain.project,
        chain=chain,
        status=ChainResult.STATUS_RUNNING,
        step_results=[],
        created_by=user,
    )

    step_results = []
    executed_nodes = set()

    try:
        # 找入口节点（入度为 0 的节点）
        ordered = _topological_sort(nodes_list, edges_list)
        if not ordered:
            chain_result.status = ChainResult.STATUS_FAILED
            chain_result.error_message = '链路中没有可执行的节点'
            chain_result.finished_at = datetime.now()
            chain_result.save(update_fields=['status', 'error_message', 'finished_at'])
            return chain_result

        # 从入口节点开始 BFS 执行
        queue = [ordered[0]]  # 从排序的第一个节点开始
        visited_edges = set()

        while queue:
            node_id = queue.pop(0)
            if node_id in executed_nodes:
                continue

            node = node_map.get(node_id)
            if not node:
                continue

            node_type = node.get('type', 'interface')
            node_data = node.get('data', {})
            node_label = node_data.get('label', node_id)

            step_result = {
                'node_id': node_id,
                'node_type': node_type,
                'label': node_label,
                'status': 'pending',
                'response': None,
                'script_result': None,
                'assertion_results': None,
                'extractions': None,
                'error': None,
                'elapsed_ms': None,
            }

            # 读取重试配置
            retry_count = int(node_data.get('retry_count', 0) or 0)
            retry_interval = float(node_data.get('retry_interval', 1) or 1)
            import time as _time

            for _attempt in range(1 + retry_count):
                step_result['status'] = 'pending'
                step_result['error'] = None
                try:
                    if node_type == 'interface':
                        step_result = _execute_interface_node(
                            {**node_data, '_project_id': chain.project_id}, vars_pool, step_result, env_context
                        )
                        # 记录最近的接口响应，供下游条件节点 JSONPath/脚本模式使用
                        if step_result.get('response'):
                            resp = step_result['response']
                            try:
                                _last_response_wrapper = {
                                    'status_code': resp['status_code'],
                                    'elapsed_ms': resp.get('elapsed_ms', 0),
                                    'headers': resp.get('headers', {}),
                                    'body': json.loads(resp['body']) if resp.get('body') else None,
                                }
                            except (json.JSONDecodeError, TypeError):
                                _last_response_wrapper = {
                                    'status_code': resp['status_code'],
                                    'elapsed_ms': resp.get('elapsed_ms', 0),
                                    'headers': resp.get('headers', {}),
                                    'body': resp.get('body'),
                                }
                    elif node_type == 'script':
                        step_result = _execute_script_node(
                            {**node_data, '_project_id': chain.project_id}, vars_pool, step_result, env_context
                        )
                    elif node_type == 'timer':
                        step_result = _execute_timer_node(
                            node_data, step_result
                        )
                    elif node_type == 'condition':
                        step_result = _execute_condition_node(
                            node_data, vars_pool, step_result, _last_response_wrapper
                        )
                    else:
                        step_result['status'] = 'skipped'
                        step_result['error'] = f'未知节点类型: {node_type}'

                except Exception as e:
                    step_result['status'] = 'failed'
                    step_result['error'] = f'{type(e).__name__}: {str(e)}'

                # 记录尝试次数
                step_result['attempts'] = _attempt + 1

                # 成功则跳出重试循环
                if step_result['status'] != 'failed':
                    break

                # 还有重试机会则等待后继续
                if _attempt < retry_count:
                    _time.sleep(retry_interval)

            step_results.append(step_result)
            executed_nodes.add(node_id)

            # 如果节点失败，决定是否继续
            if step_result['status'] == 'failed' and node_type == 'interface':
                # 接口节点失败时不走下游
                break

            # 确定条件分支结果
            condition_result = None
            if node_type == 'condition' and step_result['status'] == 'success':
                condition_result = step_result.pop('_condition_result', None)

            # 将下游节点加入队列
            next_ids = _get_next_nodes(node_id, edges_list, condition_result)
            for nid in next_ids:
                if nid not in executed_nodes:
                    queue.append(nid)

        # 标记未执行的节点为 skipped
        for node in nodes_list:
            if node['id'] not in executed_nodes:
                step_results.append({
                    'node_id': node['id'],
                    'node_type': node.get('type', ''),
                    'label': node.get('data', {}).get('label', node['id']),
                    'status': 'skipped',
                    'error': None,
                })

        # 汇总状态
        has_failed = any(s['status'] == 'failed' for s in step_results)
        chain_result.status = ChainResult.STATUS_FAILED if has_failed else ChainResult.STATUS_COMPLETED

    except Exception as e:
        chain_result.status = ChainResult.STATUS_FAILED
        chain_result.error_message = f'{type(e).__name__}: {str(e)}'

    chain_result.step_results = step_results
    chain_result.finished_at = datetime.now()
    chain_result.save()
    return chain_result


def _execute_interface_node(node_data, vars_pool, step_result, env_context=None):
    """执行接口节点 — 支持 HTTP/WebSocket/RPC 三种协议"""
    interface_id = node_data.get('interface_id')
    if not interface_id:
        step_result['status'] = 'failed'
        step_result['error'] = '未选择接口'
        return step_result

    try:
        interface = ApiInterface.objects.get(id=interface_id, project_id=node_data.get('_project_id'))
    except ApiInterface.DoesNotExist:
        step_result['status'] = 'failed'
        step_result['error'] = f'接口不存在: {interface_id}'
        return step_result

    # 构建执行参数（基于接口定义 + 覆盖）
    overrides = node_data.get('overrides', {})
    exec_data = {
        'protocol': interface.protocol,
        'method': interface.method,
        'url': interface.url,
        'headers': dict(interface.headers or {}),
        'query_params': dict(interface.query_params or {}),
        'body_type': interface.body_type,
        'body': interface.body,
        'ws_message': interface.ws_message,
        'rpc_method': interface.rpc_method,
        'rpc_service': interface.rpc_service,
        'timeout': 30,
    }

    # 合并覆盖（headers/query_params 深度合并仅非空值，其余直接替换）
    for dict_key in ('headers', 'query_params'):
        override_dict = overrides.get(dict_key)
        if isinstance(override_dict, dict):
            for k, v in override_dict.items():
                if v != '' and v is not None:  # 空字符串表示使用原始值，不覆盖
                    exec_data[dict_key][k] = v
    for key in ('url', 'method', 'body', 'ws_message',
                'rpc_method', 'rpc_service'):
        if key in overrides and overrides[key] is not None and overrides[key] != '':
            exec_data[key] = overrides[key]

    # body_fields: JSON body 字段级合并（仅当无完整 body 覆盖时生效）
    # 支持点号路径访问嵌套字段，如 user.name 表示 body_obj["user"]["name"]
    body_fields = overrides.get('body_fields')
    if (isinstance(body_fields, dict) and body_fields
            and not (overrides.get('body') and overrides['body'] != '')
            and exec_data.get('body_type') == 'json'
            and exec_data.get('body')):
        try:
            body_obj = json.loads(exec_data['body']) if isinstance(exec_data['body'], str) else exec_data['body']
            if isinstance(body_obj, dict):
                for k, v in body_fields.items():
                    if v == '' or v is None:
                        continue
                    # 支持点号路径：user.name → body_obj["user"]["name"] = v
                    if '.' in k:
                        parts = k.split('.')
                        target = body_obj
                        for part in parts[:-1]:
                            if isinstance(target, dict) and part in target:
                                target = target[part]
                            else:
                                target = None
                                break
                        if isinstance(target, dict):
                            target[parts[-1]] = v
                    else:
                        body_obj[k] = v
                exec_data['body'] = json.dumps(body_obj, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    env_context = env_context or _build_env_context(None)

    # 变量替换
    exec_data = _deep_replace_vars(exec_data, vars_pool, env_context.get('vars', {}))

    protocol = exec_data.get('protocol', 'http')
    exec_data['url'], exec_data['headers'] = _apply_env_request_context(
        protocol, exec_data.get('url', ''), exec_data.get('headers', {}), env_context
    )

    if protocol == 'websocket':
        step_result = _execute_ws(exec_data, step_result)
    elif protocol == 'rpc':
        step_result = _execute_rpc(exec_data, step_result)
    else:
        step_result = _execute_http(exec_data, step_result)

    # 执行失败则直接返回
    if step_result['status'] == 'failed':
        return step_result

    # 执行提取规则
    extractions = node_data.get('extractions', [])
    extraction_results = []
    resp_info = step_result['response']
    try:
        response_wrapper = {
            'status_code': resp_info['status_code'],
            'elapsed_ms': resp_info['elapsed_ms'],
            'headers': resp_info.get('headers', {}),
            'body': json.loads(resp_info['body']) if resp_info.get('body') else None,
        }
    except (json.JSONDecodeError, TypeError):
        response_wrapper = {
            'status_code': resp_info['status_code'],
            'elapsed_ms': resp_info['elapsed_ms'],
            'headers': resp_info.get('headers', {}),
            'body': resp_info.get('body'),
        }

    for ext in extractions:
        var_name = ext.get('var_name', '')
        jsonpath = ext.get('jsonpath', '')
        if not var_name or not jsonpath:
            continue
        value = _extract_jsonpath(response_wrapper, jsonpath)
        vars_pool['vars'][var_name] = value
        extraction_results.append({
            'var_name': var_name,
            'jsonpath': jsonpath,
            'value': value,
        })

    step_result['extractions'] = extraction_results

    # 执行断言（JSONPath + 脚本）
    assertions = node_data.get('assertions', [])
    if assertions:
        jsonpath_results = _run_assertions_jsonpath(assertions, response_wrapper)
        script_results = _run_assertions_script(assertions, response_wrapper, vars_pool)
        all_assertion_results = jsonpath_results + script_results
        step_result['assertion_results'] = all_assertion_results
        if any(not a['pass'] for a in all_assertion_results):
            step_result['status'] = 'failed'
            step_result['error'] = '断言失败'
            return step_result

    step_result['status'] = 'success'
    return step_result


def _execute_http(exec_data, step_result):
    """链路中执行 HTTP 请求"""
    start = time.time()
    try:
        url = exec_data.get('url', '')
        method = exec_data.get('method', 'GET').upper()
        headers = exec_data.get('headers', {})
        params = exec_data.get('query_params', {})
        body = exec_data.get('body', '')
        body_type = exec_data.get('body_type', 'none')
        timeout = min(exec_data.get('timeout', 30), 120)

        # SSRF 检查
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname
        if hostname and _is_private_host(hostname):
            step_result['status'] = 'failed'
            step_result['error'] = '目标地址属于私有网络，禁止访问'
            step_result['elapsed_ms'] = int((time.time() - start) * 1000)
            return step_result

        req_kwargs = {'headers': headers, 'params': params, 'timeout': timeout}
        if body_type == 'json' and body:
            req_kwargs['json'] = json.loads(body) if isinstance(body, str) else body
        elif body_type in ('form',) and body:
            req_kwargs['data'] = body if isinstance(body, dict) else json.loads(body)
        elif body:
            req_kwargs['data'] = body

        resp = _requests.request(method, url, **req_kwargs)
        elapsed = int((time.time() - start) * 1000)
        step_result['elapsed_ms'] = elapsed

        resp_body = resp.text[:MAX_RESPONSE_BODY_SIZE]
        step_result['response'] = {
            'status_code': resp.status_code,
            'headers': dict(resp.headers),
            'body': resp_body[:MAX_CHAIN_STEP_BODY_SIZE],
            'elapsed_ms': elapsed,
            'status': 'success',
            'error_message': '',
        }

    except _requests.Timeout:
        elapsed = int((time.time() - start) * 1000)
        step_result['status'] = 'failed'
        step_result['error'] = f'请求超时（{timeout}秒）'
        step_result['elapsed_ms'] = elapsed
        return step_result
    except _requests.ConnectionError as e:
        elapsed = int((time.time() - start) * 1000)
        step_result['status'] = 'failed'
        step_result['error'] = f'连接失败: {str(e)[:200]}'
        step_result['elapsed_ms'] = elapsed
        return step_result
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        step_result['status'] = 'failed'
        step_result['error'] = f'{type(e).__name__}: {str(e)[:200]}'
        step_result['elapsed_ms'] = elapsed
        return step_result

    if step_result['response']['status_code'] >= 400:
        step_result['status'] = 'failed'
        step_result['error'] = f'HTTP {step_result["response"]["status_code"]}'
        return step_result

    return step_result


def _execute_ws(exec_data, step_result):
    """链路中执行 WebSocket 请求"""
    url = exec_data.get('url', '')
    message = exec_data.get('ws_message', '')
    headers = exec_data.get('headers', {})
    timeout = min(exec_data.get('timeout', 30), 120)

    # 复用 executor 中的 WebSocket 执行器
    result = execute_websocket(
        url=url,
        message=message,
        headers=headers,
        timeout=timeout,
    )

    step_result['elapsed_ms'] = result.elapsed_ms or 0

    if result.status == 'failed':
        step_result['status'] = 'failed'
        step_result['error'] = result.error_message or 'WebSocket 连接失败'
        return step_result
    elif result.status == 'timeout':
        step_result['status'] = 'failed'
        step_result['error'] = result.error_message or 'WebSocket 连接超时'
        return step_result

    # 成功 → 构造统一 response 格式
    resp_body = result.response_body or ''
    step_result['response'] = {
        'status_code': result.status_code or 101,
        'headers': result.response_headers or {},
        'body': resp_body[:MAX_CHAIN_STEP_BODY_SIZE],
        'elapsed_ms': result.elapsed_ms or 0,
        'status': 'success',
        'error_message': '',
    }

    return step_result


def _execute_rpc(exec_data, step_result):
    """链路中执行 RPC 请求"""
    url = exec_data.get('url', '')
    rpc_method = exec_data.get('rpc_method', '')
    rpc_service = exec_data.get('rpc_service', '')
    headers = exec_data.get('headers', {})
    body = exec_data.get('body', '')
    timeout = min(exec_data.get('timeout', 30), 120)

    # 复用 executor 中的 RPC 执行器
    result = execute_rpc(
        url=url,
        rpc_method=rpc_method,
        rpc_service=rpc_service,
        headers=headers,
        body=body,
        timeout=timeout,
    )

    step_result['elapsed_ms'] = result.elapsed_ms or 0

    if result.status == 'failed':
        step_result['status'] = 'failed'
        step_result['error'] = result.error_message or 'RPC 请求失败'
        return step_result
    elif result.status == 'timeout':
        step_result['status'] = 'failed'
        step_result['error'] = result.error_message or 'RPC 请求超时'
        return step_result

    # 成功 → 构造统一 response 格式
    resp_body = result.response_body or ''
    step_result['response'] = {
        'status_code': result.status_code or 200,
        'headers': result.response_headers or {},
        'body': resp_body[:MAX_CHAIN_STEP_BODY_SIZE],
        'elapsed_ms': result.elapsed_ms or 0,
        'status': 'success',
        'error_message': '',
    }

    # HTTP 状态码检查
    if step_result['response']['status_code'] >= 400:
        step_result['status'] = 'failed'
        step_result['error'] = f'HTTP {step_result["response"]["status_code"]}'
        return step_result

    return step_result


def _execute_script_node(node_data, vars_pool, step_result, env_dict=None):
    """执行脚本节点"""
    script = node_data.get('script', '')
    timeout = node_data.get('timeout', 10)

    if not script.strip():
        step_result['status'] = 'skipped'
        step_result['error'] = '脚本为空'
        return step_result

    # 构建脚本上下文：注入 vars 到沙箱
    context = {
        'vars': vars_pool.get('vars', {}),
        'globals': vars_pool.get('globals', {}),
        'status_code': 0,
        'headers': {},
        'body': json.dumps(vars_pool.get('vars', {}), ensure_ascii=False),
        'elapsed_ms': 0,
    }

    start = time.time()
    result = execute_assertion_script(script, context, timeout)
    elapsed = int((time.time() - start) * 1000)
    step_result['elapsed_ms'] = elapsed

    step_result['script_result'] = {
        'pass': result.get('pass', False),
        'error': result.get('error'),
        'output': result.get('output', ''),
    }

    if result.get('pass'):
        step_result['status'] = 'success'
    else:
        step_result['status'] = 'failed'
        step_result['error'] = result.get('error') or '脚本断言失败'

    return step_result


def _execute_timer_node(node_data, step_result):
    """执行定时器节点"""
    delay = node_data.get('delay', 1)
    delay = max(0.1, min(delay, 300))

    start = time.time()
    time.sleep(delay)
    elapsed = int((time.time() - start) * 1000)

    step_result['status'] = 'success'
    step_result['elapsed_ms'] = elapsed
    return step_result


def _execute_condition_node(node_data, vars_pool, step_result, last_response=None):
    """执行条件分支节点 — 支持变量/JSONPath/脚本三种模式"""
    condition_type = node_data.get('condition_type', 'variable')
    if condition_type == 'jsonpath':
        return _condition_jsonpath(node_data, vars_pool, step_result, last_response)
    elif condition_type == 'script':
        return _condition_script(node_data, vars_pool, step_result, last_response)
    else:
        return _condition_variable(node_data, vars_pool, step_result)


def _condition_variable(node_data, vars_pool, step_result):
    """条件节点变量模式（原有逻辑）"""
    source_var = node_data.get('source_var', '')
    operator = node_data.get('operator', 'equals')
    expected = node_data.get('expected', '')

    # 从 vars 和 globals 中查找变量值
    actual = vars_pool.get('vars', {}).get(source_var)
    if actual is None:
        actual = vars_pool.get('globals', {}).get(source_var)

    if actual is None:
        step_result['status'] = 'failed'
        step_result['error'] = f'变量不存在: {source_var}'
        step_result['_condition_result'] = False
        return step_result

    condition_result = _compare_values(actual, operator, expected)

    step_result['status'] = 'success'
    step_result['_condition_result'] = condition_result
    step_result['condition_detail'] = {
        'condition_type': 'variable',
        'source_var': source_var,
        'actual': actual,
        'operator': operator,
        'expected': expected,
        'result': condition_result,
    }
    return step_result


def _condition_jsonpath(node_data, vars_pool, step_result, last_response):
    """条件节点 JSONPath 模式：从上游响应提取值并比较"""
    jsonpath_expr = node_data.get('jsonpath', '')
    operator = node_data.get('operator', 'equals')
    expected = node_data.get('expected', '')

    if not jsonpath_expr:
        step_result['status'] = 'failed'
        step_result['error'] = 'JSONPath 为空'
        step_result['_condition_result'] = False
        return step_result

    if not last_response:
        step_result['status'] = 'failed'
        step_result['error'] = '无上游接口响应，无法使用 JSONPath 模式'
        step_result['_condition_result'] = False
        return step_result

    actual = _extract_jsonpath(last_response, jsonpath_expr)
    if actual is None:
        step_result['status'] = 'failed'
        step_result['error'] = f'JSONPath 未匹配: {jsonpath_expr}'
        step_result['_condition_result'] = False
        return step_result

    condition_result = _compare_values(actual, operator, expected)

    step_result['status'] = 'success'
    step_result['_condition_result'] = condition_result
    step_result['condition_detail'] = {
        'condition_type': 'jsonpath',
        'jsonpath': jsonpath_expr,
        'actual': actual,
        'operator': operator,
        'expected': expected,
        'result': condition_result,
    }
    return step_result


def _condition_script(node_data, vars_pool, step_result, last_response):
    """条件节点脚本模式：执行 Python 脚本，断言语义决定路由"""
    script_code = node_data.get('script', '')
    timeout = node_data.get('timeout', 10)

    if not script_code.strip():
        step_result['status'] = 'failed'
        step_result['error'] = '脚本为空'
        step_result['_condition_result'] = False
        return step_result

    # 构建 context
    if last_response:
        body_str = last_response.get('body')
        if not isinstance(body_str, str):
            try:
                body_str = json.dumps(body_str, ensure_ascii=False)
            except (TypeError, ValueError):
                body_str = str(body_str) if body_str is not None else ''
        context = {
            'status_code': last_response.get('status_code', 0),
            'headers': last_response.get('headers', {}),
            'body': body_str,
            'elapsed_ms': last_response.get('elapsed_ms', 0),
        }
    else:
        context = {
            'status_code': 0,
            'headers': {},
            'body': json.dumps(vars_pool.get('vars', {}), ensure_ascii=False),
            'elapsed_ms': 0,
        }
    context['vars'] = vars_pool.get('vars', {})
    context['globals'] = vars_pool.get('globals', {})

    result = execute_assertion_script(script_code, context, timeout)
    # 脚本执行通过(无 AssertionError) → True 分支；断言失败 → False 分支
    condition_result = result.get('pass', False)

    step_result['status'] = 'success'
    step_result['_condition_result'] = condition_result
    step_result['condition_detail'] = {
        'condition_type': 'script',
        'pass': condition_result,
        'error': result.get('error'),
        'output': result.get('output', ''),
        'result': condition_result,
    }
    return step_result