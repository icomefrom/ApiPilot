"""脚本断言执行器 — 在受限沙箱中执行用户 Python 断言脚本"""
import json
import re as _re_module
import sys
import io
import threading
import builtins as _builtins
import warnings

from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Guards import (
    safer_getattr,
    guarded_unpack_sequence,
    full_write_guard,
)


# 脚本执行超时(秒)
DEFAULT_SCRIPT_TIMEOUT = 10
MAX_SCRIPT_TIMEOUT = 30

# 输出最大长度
MAX_OUTPUT_SIZE = 10240


class _ResponseProxy:
    """响应上下文代理对象，注入脚本沙箱供用户访问"""

    def __init__(self, status_code, headers, body, elapsed_ms):
        self._status_code = status_code
        self._headers = headers or {}
        self._body = body or ''
        self._elapsed_ms = elapsed_ms

    @property
    def status_code(self):
        return self._status_code

    @property
    def headers(self):
        return dict(self._headers)

    @property
    def body(self):
        return self._body

    @property
    def elapsed_ms(self):
        return self._elapsed_ms

    def json(self):
        """解析响应体为 JSON，失败抛 ValueError"""
        return json.loads(self._body)

    def contains(self, substring):
        """检查响应体是否包含指定子串"""
        return substring in self._body

    def header(self, name, default=None):
        """获取指定响应头（大小写不敏感）"""
        lower_name = name.lower()
        for k, v in self._headers.items():
            if k.lower() == lower_name:
                return v
        return default


class _PrintCollector:
    """收集脚本中 print() 的输出（RestrictedPython 8.x 守卫模式）"""

    def __init__(self):
        self.parts = []

    def _call_print(self, *args, **kwargs):
        self.parts.append(' '.join(str(a) for a in args))

    def __str__(self):
        return '\n'.join(self.parts)


class _ScriptTimeout(Exception):
    """脚本执行超时异常"""
    pass


# 允许在沙箱中使用的安全内置名称
_SAFE_NAMES = (
    'True', 'False', 'None',
    'len', 'range', 'enumerate', 'zip',
    'abs', 'min', 'max', 'sum', 'round', 'pow',
    'sorted', 'reversed',
    'isinstance', 'type', 'issubclass', 'hasattr', 'getattr',
    'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set', 'frozenset',
    'bytes', 'bytearray',
    'print',
    'AssertionError',
    'ValueError', 'TypeError', 'KeyError', 'IndexError',
    'AttributeError', 'RuntimeError', 'StopIteration',
    'NotImplementedError', 'ZeroDivisionError',
)


def _build_restricted_builtins():
    """构建受限 builtins 字典，基于 safe_builtins 并补充常用安全内置 + RP 8.x 守卫"""
    restricted = {}

    # 从 safe_builtins 取白名单内置
    for name in _SAFE_NAMES:
        if name in safe_builtins:
            restricted[name] = safe_builtins[name]
        elif hasattr(_builtins, name):
            restricted[name] = getattr(_builtins, name)

    # RestrictedPython 8.x 必需的守卫函数
    restricted['_getattr_'] = safer_getattr
    restricted['_write_'] = full_write_guard
    restricted['_unpack_sequence_'] = guarded_unpack_sequence
    restricted['_getitem_'] = _safe_getitem

    return restricted


def _safe_getitem(ob, index):
    """安全索引访问守卫 — 允许列表/字典/切片的 [] 操作"""
    return ob[index]


def execute_assertion_script(script_code, context, timeout=DEFAULT_SCRIPT_TIMEOUT):
    """
    在受限沙箱中执行断言脚本。

    :param script_code: 用户 Python 脚本代码
    :param context: 响应上下文 dict，含 status_code, headers, body, elapsed_ms
    :param timeout: 超时秒数
    :returns: { pass: bool, error: str|null, output: str }
    """
    effective_timeout = min(timeout, MAX_SCRIPT_TIMEOUT)

    # 1. 编译受限代码
    # RestrictedPython 8.x: compile_restricted 直接返回 code 对象
    # 语法错误 / 编译错误直接抛 SyntaxError
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            code_obj = compile_restricted(script_code, filename='<assertion_script>', mode='exec')
    except SyntaxError as e:
        error_msg = e.args[0] if e.args else f'第 {e.lineno} 行语法错误'
        return {
            'pass': False,
            'error': f'语法错误: {error_msg}',
            'output': '',
        }

    # 2. 构建沙箱全局命名空间
    response = _ResponseProxy(
        status_code=context.get('status_code'),
        headers=context.get('headers', {}),
        body=context.get('body', ''),
        elapsed_ms=context.get('elapsed_ms'),
    )

    restricted_builtins = _build_restricted_builtins()

    # print 守卫：RP 8.x 编译后调用 _print_(_getattr_) 得到 PrintCollector
    printer = _PrintCollector()

    sandbox_globals = {
        '__builtins__': restricted_builtins,
        'response': response,
        'json': type('json', (), {
            'loads': staticmethod(json.loads),
            'dumps': staticmethod(json.dumps),
        })(),
        're': _re_module,
        'vars': context.get('vars', {}),
        'globals': context.get('globals', {}),
        '_print_': lambda _getattr: printer,   # RP 8.x print 守卫
        'printed': printer,                     # RP 8.x printed 变量
    }

    # 3. 用线程执行脚本 + threading.Timer 实现超时
    #    （signal.SIGALRM 只能在主线程使用，Django runserver 不满足）
    result_container = {'timeout': False, 'exception': None}
    exec_lock = threading.Lock()

    def _run_script():
        try:
            exec(code_obj, sandbox_globals)
        except Exception as e:
            with exec_lock:
                if not result_container['timeout']:
                    result_container['exception'] = e

    script_thread = threading.Thread(target=_run_script, daemon=True)
    timer = threading.Timer(effective_timeout, lambda: result_container.update({'timeout': True}))

    timer.start()
    script_thread.start()
    script_thread.join(timeout=effective_timeout + 2)  # 额外 2s 保证 timer 回调完成

    timer.cancel()

    # 检查结果
    if result_container['timeout'] or script_thread.is_alive():
        return {
            'pass': False,
            'error': f'脚本执行超时（{effective_timeout}秒）',
            'output': str(printer)[:MAX_OUTPUT_SIZE],
        }

    exc = result_container['exception']
    if exc is not None:
        if isinstance(exc, AssertionError):
            error_msg = str(exc) if str(exc) else '断言失败'
            return {
                'pass': False,
                'error': error_msg,
                'output': str(printer)[:MAX_OUTPUT_SIZE],
            }
        else:
            error_msg = f'{type(exc).__name__}: {str(exc)}'
            return {
                'pass': False,
                'error': error_msg,
                'output': str(printer)[:MAX_OUTPUT_SIZE],
            }

    # 正常执行完毕 → 通过
    output = str(printer)[:MAX_OUTPUT_SIZE]
    return {
        'pass': True,
        'error': None,
        'output': output,
    }