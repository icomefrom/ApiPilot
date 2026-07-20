"""Mock 引擎 — 拦截请求并返回模拟响应"""
import json
import time


class MockResponse:
    """Mock 响应数据对象"""
    __slots__ = ('status_code', 'headers', 'body', 'content_type', 'is_mock')

    def __init__(self, status_code, headers, body, content_type, is_mock=True):
        self.status_code = status_code
        self.headers = {**(headers or {}), 'Content-Type': content_type, 'X-Mock': 'true'}
        self.body = body
        self.content_type = content_type
        self.is_mock = is_mock


def resolve_mock(interface):
    """检查接口是否命中 Mock 规则

    :param interface: ApiInterface 实例
    :returns: MockResponse 对象或 None（未命中）
    """
    try:
        rule = interface.mock_rule
    except Exception:
        return None

    if not rule.enabled:
        return None

    return build_mock_response(rule)


def build_mock_response(rule):
    """根据 MockRule 构造模拟响应"""
    # 模拟延迟
    if rule.delay_ms > 0:
        time.sleep(rule.delay_ms / 1000.0)

    body = rule.response_body or '{}'

    # 按响应模式处理
    response_mode = getattr(rule, 'response_mode', 'static')
    if response_mode == 'echo':
        # 回显模式：body 由调用方注入请求体后替换
        # 这里先用静态 body 作为 fallback
        pass
    elif response_mode == 'template':
        # 模板模式：body 中的 {{vars.key}} 等由调用方替换
        pass
    # static 模式直接使用 response_body

    return MockResponse(
        status_code=rule.status_code,
        headers=rule.response_headers or {},
        body=body,
        content_type=rule.content_type or 'application/json',
    )
