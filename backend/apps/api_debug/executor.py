"""请求执行器 — 支持HTTP/WebSocket/RPC三种协议的在线调试"""
import json
import re
import time
import ipaddress
import socket
import base64
from urllib.parse import urlparse, urljoin

import requests as http_requests
import websocket

from .models import DebugResult

# 响应体最大存储大小 1MB
MAX_RESPONSE_BODY_SIZE = 1024 * 1024

# 默认超时(秒)
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

# 环境变量占位符正则：{{env.key}}
_ENV_VAR_PATTERN = re.compile(r'\{\{env\.(\w+)\}\}')

# SSRF 防护：私有 IP 网段
PRIVATE_NETWORKS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fd00::/8'),
]


def _replace_env_vars(obj, env_vars):
    """递归替换对象中的 {{env.key}} 占位符为环境变量值

    :param obj: 要替换的对象（str/dict/list）
    :param env_vars: 环境变量字典 {'key': 'value', ...}
    """
    if not env_vars:
        return obj
    if isinstance(obj, str):
        def _sub(m):
            key = m.group(1)
            val = env_vars.get(key, m.group(0))  # 未找到保留原始占位符
            if not isinstance(val, str):
                val = json.dumps(val, ensure_ascii=False)
            return val
        return _ENV_VAR_PATTERN.sub(_sub, obj)
    if isinstance(obj, dict):
        return {k: _replace_env_vars(v, env_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_env_vars(v, env_vars) for v in obj]
    return obj


def _is_private_host(hostname):
    """检查主机名是否解析到私有 IP（SSRF 防护）

    允许 localhost / 127.0.0.1 访问，以便调试本机服务。
    """
    if not hostname:
        return False
    # 允许本机回环地址和 Docker Compose 内置后端服务名，方便调测内置示例接口。
    if hostname in ('localhost', '127.0.0.1', '::1', 'backend'):
        return False
    try:
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = ipaddress.ip_address(addr[4][0])
            # 跳过回环地址
            if ip.is_loopback:
                continue
            for net in PRIVATE_NETWORKS:
                if ip in net:
                    return True
    except socket.gaierror:
        pass
    return False


def _truncate_body(body):
    """截断过大的响应体"""
    if body and len(body) > MAX_RESPONSE_BODY_SIZE:
        return body[:MAX_RESPONSE_BODY_SIZE] + '\n\n... (响应体已截断，超过1MB)'
    return body or ''


def _build_result(interface, protocol, request_url, request_method,
                  request_headers, request_body, status_code,
                  response_headers, response_body, elapsed_ms,
                  status, error_message, user):
    """构造并保存 DebugResult"""
    return DebugResult.objects.create(
        project=getattr(interface, 'project', None),
        interface=interface,
        protocol=protocol,
        request_url=request_url,
        request_method=request_method,
        request_headers=request_headers,
        request_body=request_body or '',
        status_code=status_code,
        response_headers=response_headers,
        response_body=_truncate_body(response_body),
        elapsed_ms=elapsed_ms,
        status=status,
        error_message=error_message,
        created_by=user,
    )


class _ExecResult:
    """轻量执行结果对象（不写库），供链路执行器使用"""
    __slots__ = (
        'interface', 'protocol', 'request_url', 'request_method',
        'request_headers', 'request_body', 'status_code',
        'response_headers', 'response_body', 'elapsed_ms',
        'status', 'error_message',
    )

    def __init__(self, interface, protocol, request_url, request_method,
                 request_headers, request_body, status_code,
                 response_headers, response_body, elapsed_ms,
                 status, error_message):
        self.interface = interface
        self.protocol = protocol
        self.request_url = request_url
        self.request_method = request_method
        self.request_headers = request_headers
        self.request_body = request_body or ''
        self.status_code = status_code
        self.response_headers = response_headers
        self.response_body = _truncate_body(response_body) if response_body else ''
        self.elapsed_ms = elapsed_ms
        self.status = status
        self.error_message = error_message


def _make_result(interface, protocol, request_url, request_method,
                 request_headers, request_body, status_code,
                 response_headers, response_body, elapsed_ms,
                 status, error_message):
    """构造轻量结果对象（不写库），供链路执行器使用"""
    return _ExecResult(
        interface=interface,
        protocol=protocol,
        request_url=request_url,
        request_method=request_method,
        request_headers=request_headers,
        request_body=request_body or '',
        status_code=status_code,
        response_headers=response_headers,
        response_body=_truncate_body(response_body) if response_body else '',
        elapsed_ms=elapsed_ms,
        status=status,
        error_message=error_message,
    )


def _result_builder(user):
    """统一轻量结果和入库结果的调用签名。"""
    if user is None:
        return _make_result

    def _save_result(interface, protocol, request_url, request_method,
                     request_headers, request_body, status_code,
                     response_headers, response_body, elapsed_ms,
                     status, error_message):
        return _build_result(
            interface, protocol, request_url, request_method,
            request_headers, request_body, status_code,
            response_headers, response_body, elapsed_ms,
            status, error_message, user,
        )

    return _save_result


def _vars_list_to_dict(variables):
    """将环境变量列表转换为字典。"""
    if not variables:
        return {}
    if isinstance(variables, dict):
        return dict(variables)
    if isinstance(variables, list):
        result = {}
        for item in variables:
            if isinstance(item, dict) and item.get('key'):
                result[item['key']] = item.get('value', '')
        return result
    return {}


def _build_env_context(env_config):
    """构造运行时环境上下文；无环境时保持原请求行为。"""
    context = {
        'enabled': False,
        'vars': {},
        'base_url': '',
        'ws_base_url': '',
        'rpc_base_url': '',
        'auth_type': 'none',
        'auth_header': 'Authorization',
        'auth_token': '',
        'auth_username': '',
        'auth_password': '',
    }
    if not env_config:
        return context

    context['enabled'] = True
    if isinstance(env_config, (list, dict)):
        if isinstance(env_config, dict) and any(k in env_config for k in ('variables', 'base_url', 'auth_type')):
            variables = env_config.get('variables', {})
            for key in ('base_url', 'ws_base_url', 'rpc_base_url', 'auth_type',
                        'auth_header', 'auth_token', 'auth_username', 'auth_password'):
                if key in env_config and env_config.get(key) is not None:
                    context[key] = env_config.get(key)
        else:
            variables = env_config
    else:
        variables = getattr(env_config, 'variables', {})
        for key in ('base_url', 'ws_base_url', 'rpc_base_url', 'auth_type',
                    'auth_header', 'auth_token', 'auth_username', 'auth_password'):
            value = getattr(env_config, key, None)
            if value is not None:
                context[key] = value

    env_vars = _vars_list_to_dict(variables)
    for key in ('base_url', 'ws_base_url', 'rpc_base_url', 'auth_token',
                'auth_username', 'auth_password'):
        if context.get(key) and key not in env_vars:
            env_vars[key] = context[key]
    context['vars'] = env_vars
    return context


def _get_env_vars_dict(env_vars):
    """返回可用于 {{env.key}} 替换的变量字典。"""
    return _build_env_context(env_vars)['vars']


def _has_header(headers, header_name):
    lower_name = (header_name or '').lower()
    return any(str(k).lower() == lower_name for k in (headers or {}))


def _join_base_url(protocol, url, env_context):
    """相对 URL 按协议拼接环境基础地址，绝对 URL 原样返回。"""
    if not env_context.get('enabled') or not url:
        return url
    if urlparse(url).scheme:
        return url

    if protocol == 'websocket':
        base_url = env_context.get('ws_base_url') or ''
    elif protocol == 'rpc':
        base_url = env_context.get('rpc_base_url') or env_context.get('base_url') or ''
    else:
        base_url = env_context.get('base_url') or ''

    if not base_url:
        return url
    return urljoin(base_url.rstrip('/') + '/', url.lstrip('/'))


def _apply_env_auth(headers, env_context):
    """按环境认证配置注入 Header。用户显式填写的同名 Header 优先。"""
    req_headers = dict(headers or {})
    if not env_context.get('enabled'):
        return req_headers

    auth_type = env_context.get('auth_type') or 'none'
    if auth_type == 'none':
        return req_headers

    header_name = env_context.get('auth_header') or 'Authorization'
    if _has_header(req_headers, header_name):
        return req_headers

    if auth_type == 'bearer':
        token = env_context.get('auth_token') or ''
        if token:
            req_headers[header_name] = token if token.lower().startswith('bearer ') else f'Bearer {token}'
    elif auth_type in ('api_key', 'custom'):
        token = env_context.get('auth_token') or ''
        if token:
            req_headers[header_name] = token
    elif auth_type == 'basic':
        username = env_context.get('auth_username') or ''
        password = env_context.get('auth_password') or ''
        if username or password:
            raw = f'{username}:{password}'.encode('utf-8')
            req_headers[header_name] = 'Basic ' + base64.b64encode(raw).decode('ascii')

    return req_headers


def _apply_env_request_context(protocol, url, headers, env_context):
    """应用环境基础地址和认证 Header。"""
    final_url = _join_base_url(protocol, url, env_context)
    final_headers = _apply_env_auth(headers, env_context)
    return final_url, final_headers


def execute_http(method, url, headers=None, query_params=None,
                 body_type='none', body='', timeout=DEFAULT_TIMEOUT,
                 interface=None, user=None):
    """执行 HTTP 请求"""
    # SSRF 防护
    parsed = urlparse(url)
    if _is_private_host(parsed.hostname or ''):
        return _build_result(
            interface, 'http', url, method,
            headers or {}, body, None, {}, None, None,
            'failed', '目标地址指向内网，不允许访问', user,
        )

    start = time.time()
    try:
        req_headers = dict(headers or {})
        req_kwargs = {
            'method': method,
            'url': url,
            'headers': req_headers,
            'params': query_params or {},
            'timeout': min(timeout, MAX_TIMEOUT),
            'allow_redirects': True,
        }

        if body_type == 'json':
            req_kwargs['data'] = body
            req_headers.setdefault('Content-Type', 'application/json')
        elif body_type == 'form':
            if isinstance(body, str):
                # 尝试解析为 dict
                try:
                    form_data = json.loads(body)
                    if isinstance(form_data, dict):
                        req_kwargs['data'] = form_data
                    else:
                        req_kwargs['data'] = body
                except (json.JSONDecodeError, ValueError):
                    req_kwargs['data'] = body
            else:
                req_kwargs['data'] = body
            req_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        elif body_type == 'xml':
            req_kwargs['data'] = body
            req_headers.setdefault('Content-Type', 'application/xml')
        elif body_type == 'raw':
            req_kwargs['data'] = body
            req_headers.setdefault('Content-Type', 'text/plain')

        response = http_requests.request(**req_kwargs)
        elapsed = int((time.time() - start) * 1000)

        resp_headers = dict(response.headers)
        resp_body = response.text

        return _build_result(
            interface, 'http', url, method,
            req_headers, body if body_type != 'none' else '',
            response.status_code, resp_headers, resp_body,
            elapsed, 'success', '', user,
        )

    except http_requests.exceptions.Timeout:
        elapsed = int((time.time() - start) * 1000)
        return _build_result(
            interface, 'http', url, method,
            headers or {}, body, None, {}, None,
            elapsed, 'timeout', '请求超时', user,
        )
    except http_requests.exceptions.ConnectionError as e:
        elapsed = int((time.time() - start) * 1000)
        return _build_result(
            interface, 'http', url, method,
            headers or {}, body, None, {}, None,
            elapsed, 'failed', f'连接失败: {str(e)[:200]}', user,
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return _build_result(
            interface, 'http', url, method,
            headers or {}, body, None, {}, None,
            elapsed, 'failed', f'请求异常: {str(e)[:200]}', user,
        )


def execute_websocket(url, message='', headers=None, timeout=DEFAULT_TIMEOUT,
                      interface=None, user=None):
    """执行 WebSocket 请求"""
    _result = _result_builder(user)

    parsed = urlparse(url)
    if _is_private_host(parsed.hostname or ''):
        return _result(
            interface, 'websocket', url, '',
            headers or {}, message, None, {}, None, None,
            'failed', '目标地址指向内网，不允许访问',
        )

    start = time.time()
    max_elapsed = min(timeout, MAX_TIMEOUT)
    try:
        ws = websocket.create_connection(
            url,
            timeout=min(timeout, MAX_TIMEOUT),
            header=[f'{k}: {v}' for k, v in (headers or {}).items()],
        )
        try:
            if message:
                ws.send(message)
            # 接收消息（最多等 max_elapsed 秒，同时限制总耗时不超过 timeout）
            responses = []
            try:
                while True:
                    elapsed_so_far = time.time() - start
                    if elapsed_so_far >= max_elapsed:
                        break
                    # 动态缩短 recv 超时，避免超出总时限
                    remaining = max_elapsed - elapsed_so_far
                    ws.settimeout(remaining)
                    resp = ws.recv()
                    responses.append(resp)
                    if len(responses) >= 10:
                        break
            except websocket.WebSocketTimeoutException:
                pass
            except Exception:
                pass

            elapsed = int((time.time() - start) * 1000)
            resp_body = '\n---\n'.join(responses) if responses else '(无返回消息)'

            return _result(
                interface, 'websocket', url, '',
                headers or {}, message,
                None, {}, resp_body,
                elapsed, 'success', '',
            )
        finally:
            ws.close()

    except websocket.WebSocketTimeoutException:
        elapsed = int((time.time() - start) * 1000)
        return _result(
            interface, 'websocket', url, '',
            headers or {}, message, None, {}, None,
            elapsed, 'timeout', 'WebSocket 连接超时',
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return _result(
            interface, 'websocket', url, '',
            headers or {}, message, None, {}, None,
            elapsed, 'failed', f'WebSocket 错误: {str(e)[:200]}',
        )


def execute_rpc(url, rpc_method, rpc_service='', headers=None, body='',
                timeout=DEFAULT_TIMEOUT, interface=None, user=None):
    """执行 RPC 请求 (JSON-RPC 2.0 over HTTP)"""
    _result = _result_builder(user)

    parsed = urlparse(url)
    if _is_private_host(parsed.hostname or ''):
        return _result(
            interface, 'rpc', url, 'POST',
            headers or {}, body, None, {}, None, None,
            'failed', '目标地址指向内网，不允许访问',
        )

    # 构造 JSON-RPC 请求体
    try:
        params = json.loads(body) if body else []
    except (json.JSONDecodeError, ValueError):
        params = []

    rpc_request = {
        'jsonrpc': '2.0',
        'method': rpc_method,
        'params': params,
        'id': 1,
    }
    if rpc_service:
        rpc_request['service'] = rpc_service

    rpc_body = json.dumps(rpc_request)
    req_headers = dict(headers or {})
    req_headers.setdefault('Content-Type', 'application/json')

    start = time.time()
    try:
        response = http_requests.post(
            url,
            data=rpc_body,
            headers=req_headers,
            timeout=min(timeout, MAX_TIMEOUT),
        )
        elapsed = int((time.time() - start) * 1000)
        resp_headers = dict(response.headers)
        resp_body = response.text

        return _result(
            interface, 'rpc', url, 'POST',
            req_headers, rpc_body,
            response.status_code, resp_headers, resp_body,
            elapsed, 'success', '',
        )

    except http_requests.exceptions.Timeout:
        elapsed = int((time.time() - start) * 1000)
        return _result(
            interface, 'rpc', url, 'POST',
            req_headers, rpc_body, None, {}, None,
            elapsed, 'timeout', '请求超时',
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return _result(
            interface, 'rpc', url, 'POST',
            req_headers, rpc_body, None, {}, None,
            elapsed, 'failed', f'RPC 请求异常: {str(e)[:200]}',
        )


def execute_interface(interface, user, env_vars=None):
    """执行已保存的接口。环境为空时保持原请求行为。"""
    env_context = _build_env_context(env_vars)
    env_dict = env_context['vars']

    if interface.protocol == 'http':
        url = _replace_env_vars(interface.url, env_dict) if env_dict else interface.url
        headers = _replace_env_vars(interface.headers, env_dict) if env_dict else interface.headers
        query_params = _replace_env_vars(interface.query_params, env_dict) if env_dict else interface.query_params
        body = _replace_env_vars(interface.body, env_dict) if env_dict else interface.body
        url, headers = _apply_env_request_context('http', url, headers, env_context)
        return execute_http(
            method=interface.method,
            url=url,
            headers=headers,
            query_params=query_params,
            body_type=interface.body_type,
            body=body,
            interface=interface,
            user=user,
        )
    elif interface.protocol == 'websocket':
        url = _replace_env_vars(interface.url, env_dict) if env_dict else interface.url
        headers = _replace_env_vars(interface.headers, env_dict) if env_dict else interface.headers
        ws_message = _replace_env_vars(interface.ws_message, env_dict) if env_dict else interface.ws_message
        url, headers = _apply_env_request_context('websocket', url, headers, env_context)
        return execute_websocket(
            url=url,
            message=ws_message,
            headers=headers,
            interface=interface,
            user=user,
        )
    elif interface.protocol == 'rpc':
        url = _replace_env_vars(interface.url, env_dict) if env_dict else interface.url
        headers = _replace_env_vars(interface.headers, env_dict) if env_dict else interface.headers
        body = _replace_env_vars(interface.body, env_dict) if env_dict else interface.body
        rpc_method = _replace_env_vars(interface.rpc_method, env_dict) if env_dict else interface.rpc_method
        rpc_service = _replace_env_vars(interface.rpc_service, env_dict) if env_dict else interface.rpc_service
        url, headers = _apply_env_request_context('rpc', url, headers, env_context)
        return execute_rpc(
            url=url,
            rpc_method=rpc_method,
            rpc_service=rpc_service,
            headers=headers,
            body=body,
            interface=interface,
            user=user,
        )


def execute_adhoc(data, user, env_vars=None):
    """执行临时请求（不保存接口）。环境为空时保持原请求行为。"""
    env_context = _build_env_context(env_vars)
    env_dict = env_context['vars']
    protocol = data.get('protocol', 'http')
    timeout = data.get('timeout', DEFAULT_TIMEOUT)

    if env_dict:
        data = _replace_env_vars(data, env_dict)

    if protocol == 'http':
        url, headers = _apply_env_request_context('http', data['url'], data.get('headers', {}), env_context)
        return execute_http(
            method=data.get('method', 'GET'),
            url=url,
            headers=headers,
            query_params=data.get('query_params', {}),
            body_type=data.get('body_type', 'none'),
            body=data.get('body', ''),
            timeout=timeout,
            user=user,
        )
    elif protocol == 'websocket':
        url, headers = _apply_env_request_context('websocket', data['url'], data.get('headers', {}), env_context)
        return execute_websocket(
            url=url,
            message=data.get('ws_message', ''),
            headers=headers,
            timeout=timeout,
            user=user,
        )
    elif protocol == 'rpc':
        url, headers = _apply_env_request_context('rpc', data['url'], data.get('headers', {}), env_context)
        return execute_rpc(
            url=url,
            rpc_method=data.get('rpc_method', ''),
            rpc_service=data.get('rpc_service', ''),
            headers=headers,
            body=data.get('body', ''),
            timeout=timeout,
            user=user,
        )


def dry_run_interface(interface, env_vars=None):
    """试运行接口（不写库、不发用户），返回轻量 _ExecResult 供 Agent 采样响应结构。

    对所有 HTTP 方法都执行（写操作用空 body，仅探测响应结构）。
    对于 DELETE 方法跳过执行以避免删除数据。
    超时设置为 10 秒。
    """
    if interface.protocol == 'http' and interface.method and interface.method.upper() == 'DELETE':
        return None

    env_context = _build_env_context(env_vars)
    env_dict = env_context['vars']

    try:
        if interface.protocol == 'http':
            url = _replace_env_vars(interface.url, env_dict) if env_dict else interface.url
            headers = _replace_env_vars(interface.headers, env_dict) if env_dict else interface.headers
            query_params = _replace_env_vars(interface.query_params, env_dict) if env_dict else interface.query_params
            body = _replace_env_vars(interface.body, env_dict) if env_dict else interface.body
            url, headers = _apply_env_request_context('http', url, headers, env_context)
            return _execute_http_light(
                method=interface.method,
                url=url,
                headers=headers,
                query_params=query_params,
                body_type=interface.body_type,
                body=body,
                timeout=10,
                interface=interface,
            )
        elif interface.protocol == 'websocket':
            return None
        elif interface.protocol == 'rpc':
            return None
    except Exception:
        return None
    return None


def _execute_http_light(method, url, headers=None, query_params=None,
                        body_type='none', body='', timeout=10,
                        interface=None):
    """轻量 HTTP 执行，不写库，返回 _ExecResult。"""
    parsed = urlparse(url)
    if _is_private_host(parsed.hostname or ''):
        return _make_result(
            interface, 'http', url, method,
            headers or {}, body, None, {}, None, None,
            'failed', '目标地址指向内网，不允许访问',
        )

    start = time.time()
    try:
        req_headers = dict(headers or {})
        req_kwargs = {
            'method': method,
            'url': url,
            'headers': req_headers,
            'params': query_params or {},
            'timeout': min(timeout, MAX_TIMEOUT),
            'allow_redirects': True,
        }
        if method and method.upper() not in ('GET', 'HEAD', 'OPTIONS') and body:
            if body_type == 'json':
                req_headers.setdefault('Content-Type', 'application/json')
                req_kwargs['json'] = body if isinstance(body, (dict, list)) else json.loads(body)
            elif body_type == 'form':
                if isinstance(body, dict):
                    req_kwargs['data'] = body
                else:
                    try:
                        form_data = json.loads(body)
                        req_kwargs['data'] = form_data if isinstance(form_data, dict) else body
                    except (TypeError, ValueError):
                        req_kwargs['data'] = body
            else:
                req_kwargs['data'] = body

        response = http_requests.request(**req_kwargs)
        elapsed = int((time.time() - start) * 1000)

        resp_headers = dict(response.headers)
        resp_body = response.text

        return _make_result(
            interface, 'http', url, method,
            req_headers, body, response.status_code, resp_headers, resp_body,
            elapsed, 'success', '',
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return _make_result(
            interface, 'http', url, method,
            headers or {}, '', None, {}, None,
            elapsed, 'failed', f'请求异常: {str(e)[:200]}',
        )
