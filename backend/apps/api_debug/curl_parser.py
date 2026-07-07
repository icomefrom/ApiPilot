"""cURL 命令解析器 — 将 cURL 命令字符串解析为结构化数据"""
import shlex
from urllib.parse import urlparse, parse_qs


def parse_curl_command(curl_string: str) -> dict:
    """
    解析 cURL 命令，返回结构化数据。

    识别的标志:
      -X / --request   -> method
      -H / --header    -> headers (累积)
      -d / --data / --data-raw / --data-binary -> body
      -F / --form      -> body (form)
      --url            -> url
      位置参数 (非标志值) -> url (第一个未识别的位置参数)

    返回:
      {
        'method': str,
        'url': str,
        'headers': dict,
        'query_params': dict,
        'body_type': str,  # 'json', 'form', 'raw', 'none'
        'body': str,
      }

    解析失败时抛出 ValueError。
    """
    if not curl_string or not curl_string.strip():
        raise ValueError('cURL 命令不能为空')

    # 预处理：去掉续行符
    text = curl_string.strip()
    text = text.replace('\\\n', ' ').replace('\\\r\n', ' ')

    # 用 shlex 分词
    try:
        tokens = shlex.split(text)
    except ValueError as e:
        raise ValueError(f'cURL 命令格式错误: {e}')

    # 去掉开头的 curl 命令
    if tokens and tokens[0].lower() == 'curl':
        tokens = tokens[1:]

    method = ''
    url = ''
    headers = {}
    body = ''
    body_type = 'none'
    has_data = False
    has_form = False

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token in ('-X', '--request'):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif token in ('-H', '--header'):
            i += 1
            if i < len(tokens):
                header = tokens[i]
                if ':' in header:
                    key, _, value = header.partition(':')
                    headers[key.strip()] = value.strip()

        elif token in ('-d', '--data', '--data-raw', '--data-binary'):
            i += 1
            if i < len(tokens):
                body = tokens[i]
                has_data = True

        elif token == '-F' or token == '--form':
            i += 1
            if i < len(tokens):
                body = tokens[i]
                has_form = True

        elif token == '--url':
            i += 1
            if i < len(tokens):
                url = tokens[i]

        elif token.startswith('http://') or token.startswith('https://') or token.startswith('ws://') or token.startswith('wss://'):
            url = token

        elif not token.startswith('-') and not url:
            # 可能是 URL
            url = token

        i += 1

    if not url:
        raise ValueError('无法从 cURL 命令中解析出 URL')

    # 推断请求方法
    if not method:
        if has_data or has_form:
            method = 'POST'
        else:
            method = 'GET'

    # 推断 body_type
    if has_form:
        body_type = 'form'
    elif has_data:
        content_type = headers.get('Content-Type', '')
        if 'json' in content_type.lower():
            body_type = 'json'
        elif 'xml' in content_type.lower():
            body_type = 'xml'
        else:
            # 尝试判断是否是 JSON
            stripped = body.strip()
            if stripped.startswith('{') or stripped.startswith('['):
                body_type = 'json'
            else:
                body_type = 'raw'

    # 解析 query params
    query_params = {}
    parsed = urlparse(url)
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        query_params = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

    return {
        'method': method,
        'url': url,
        'headers': headers,
        'query_params': query_params,
        'body_type': body_type,
        'body': body,
    }