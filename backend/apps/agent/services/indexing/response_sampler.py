"""响应采样器 — 试运行接口获取真实响应结构，供依赖规划使用。"""
import json
import logging

from apps.api_debug.executor import dry_run_interface

logger = logging.getLogger(__name__)

# 采样响应体最大保留字符数
MAX_SAMPLE_BODY_SIZE = 2048


class ResponseSampler:
    """对匹配的接口执行试运行，提取真实响应结构。"""

    def sample(self, matches, env=None):
        """对每个已匹配的接口执行试运行。

        :param matches: InterfaceMatcher 输出的 matches 列表
        :param env: 环境配置（Environment 模型实例或配置 dict）
        :returns: dict {step_index: response_sample}
        """
        results = {}
        for match in matches:
            step_index = match.get('step_index')
            interface = match.get('selected_interface') or {}
            interface_id = interface.get('interface_id')
            if not interface_id:
                results[step_index] = {'error': '未匹配接口，跳过试运行', 'body_keys': []}
                continue

            result = self._try_run(interface_id, env)
            logger.info(f'[ResponseSampler] step={step_index} interface={interface_id} '
                        f'status={result.get("status_code")} error={result.get("error")} '
                        f'body_keys={result.get("body_keys")}')
            results[step_index] = result
        return results

    def sample_one(self, interface_id, env=None):
        """对单个接口执行试运行，供响应证据策略按需调用。"""
        return self._try_run(interface_id, env)

    def _try_run(self, interface_id, env=None):
        """执行单个接口的试运行并解析响应结构。"""
        from apps.api_debug.models import ApiInterface
        try:
            interface = ApiInterface.objects.select_related('group').get(id=interface_id)
        except ApiInterface.DoesNotExist:
            logger.warning(f'[ResponseSampler] interface {interface_id} not found')
            return {'error': f'接口 {interface_id} 不存在', 'body_keys': []}

        logger.info(f'[ResponseSampler] dry_run interface={interface_id} method={interface.method} '
                    f'url={interface.url} env={type(env).__name__ if env else None}')

        exec_result = dry_run_interface(interface, env_vars=env)

        if exec_result is None:
            logger.warning(f'[ResponseSampler] dry_run returned None for interface {interface_id}')
            return {'error': '试运行被跳过(DELETE方法)', 'body_keys': []}

        logger.info(f'[ResponseSampler] dry_run result: status={exec_result.status} '
                    f'http_code={exec_result.status_code} '
                    f'body_len={len(exec_result.response_body or "")} '
                    f'error={exec_result.error_message}')

        if exec_result.status != 'success':
            return {
                'error': f'试运行失败: {exec_result.error_message or f"HTTP {exec_result.status_code}"}',
                'status_code': exec_result.status_code,
                'body_keys': [],
            }

        # 解析响应体
        body = exec_result.response_body or ''
        body_structure, body_keys = self._parse_response(body)

        logger.info(f'[ResponseSampler] parsed body_keys={body_keys}')

        return {
            'status_code': exec_result.status_code,
            'body_structure': body_structure,
            'body_keys': body_keys,
            'error': None,
        }

    def _parse_response(self, body_str):
        """解析响应体，提取扁平化键路径。"""
        if not body_str:
            return None, []

        # 截断超大响应
        if len(body_str) > MAX_SAMPLE_BODY_SIZE:
            body_str = body_str[:MAX_SAMPLE_BODY_SIZE]

        try:
            parsed = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            return None, []

        if not isinstance(parsed, dict):
            return parsed, []

        # 扁平化提取键路径（深度限制 4 层）
        keys = []
        self._flatten_keys(parsed, keys, prefix='', max_depth=4)
        return parsed, keys

    def _flatten_keys(self, obj, keys, prefix='', max_depth=4, depth=0):
        """递归提取 dict 的键路径，用点号分隔。"""
        if depth >= max_depth or not isinstance(obj, dict):
            return
        for key, value in obj.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            keys.append(path)
            if isinstance(value, dict):
                self._flatten_keys(value, keys, prefix=path, max_depth=max_depth, depth=depth + 1)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # 列表内取第一个元素的结构
                self._flatten_keys(value[0], keys, prefix=path, max_depth=max_depth, depth=depth + 1)
