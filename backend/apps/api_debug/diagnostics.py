import json
import re


_VAR_PATTERN = re.compile(r'\{\{vars\.(\w+)\}\}')
_ENV_PATTERN = re.compile(r'\{\{env\.(\w+)\}\}')


class ChainFailureDiagnoser:
    """Rule-based chain execution diagnostics."""

    def diagnose(self, chain, step_results):
        node_map = {node.get('id'): node for node in chain.nodes or []}
        available_vars = set()
        response_keys_by_node = {}
        diagnostics = []

        for step in step_results or []:
            node_id = step.get('node_id')
            node = node_map.get(node_id) or {}
            node_diagnostics = []

            node_diagnostics.extend(self._diagnose_unresolved_placeholders(step))
            node_diagnostics.extend(self._diagnose_http_status(step))
            node_diagnostics.extend(self._diagnose_extractions(step))
            node_diagnostics.extend(self._diagnose_assertions(step))
            node_diagnostics.extend(self._diagnose_missing_vars(node, available_vars, step))

            body_keys = self._body_keys(step)
            if body_keys:
                response_keys_by_node[node_id] = body_keys
                for item in node_diagnostics:
                    if item.get('type') == 'jsonpath_not_found':
                        suggestion = self._suggest_jsonpath(item.get('jsonpath'), body_keys)
                        if suggestion:
                            item['suggestion'] = f'响应中存在相似字段 {suggestion}，建议改为该路径'
                            item['patch'] = {
                                'op': 'update_jsonpath',
                                'node_id': node_id,
                                'jsonpath': suggestion,
                                'target': item.get('target'),
                            }

            for extraction in step.get('extractions') or []:
                if extraction.get('value') is not None and extraction.get('var_name'):
                    available_vars.add(extraction['var_name'])

            if node_diagnostics:
                step['diagnostics'] = node_diagnostics
                diagnostics.extend(node_diagnostics)

        return diagnostics

    def _diagnose_unresolved_placeholders(self, step):
        result = []
        response = step.get('response') or {}
        body = response.get('body') or ''
        error = step.get('error') or ''
        for key in sorted(set(_ENV_PATTERN.findall(body + error))):
            result.append({
                'level': 'error',
                'type': 'missing_env_var',
                'node_id': step.get('node_id'),
                'message': f'环境变量 env.{key} 未替换',
                'suggestion': f'在当前环境中补充变量 {key}，或检查接口地址/请求体中的占位符',
                'confidence': 0.9,
            })
        for key in sorted(set(_VAR_PATTERN.findall(body + error))):
            result.append({
                'level': 'error',
                'type': 'missing_chain_var',
                'node_id': step.get('node_id'),
                'message': f'链路变量 vars.{key} 未生成',
                'suggestion': f'检查上游节点是否提取了变量 {key}，或手动补充参数映射',
                'confidence': 0.9,
            })
        return result

    def _diagnose_http_status(self, step):
        response = step.get('response') or {}
        status_code = response.get('status_code')
        error = step.get('error') or ''
        if not status_code and step.get('status') == 'failed':
            if '超时' in error or 'timeout' in error.lower():
                return [self._diag(step, 'timeout', '请求超时或服务无响应', '检查服务是否可达，或适当调大超时时间', 0.82)]
            if '连接失败' in error:
                return [self._diag(step, 'connection_error', '服务连接失败', '检查环境 base_url、网络连通性和目标服务是否启动', 0.82)]
            return []
        if status_code in (401, 403):
            return [self._diag(step, 'auth_failed', f'接口返回 {status_code}，认证或权限失败', '检查环境认证配置、Authorization Header 或用户权限', 0.88)]
        if status_code == 404:
            return [self._diag(step, 'url_not_found', '接口返回 404，地址可能不正确', '检查接口 URL、环境 base_url 和路径是否拼接正确', 0.82)]
        if status_code in (400, 422):
            missing_field = self._extract_missing_field(response.get('body'))
            suggestion = '检查请求参数是否缺失或格式错误'
            if missing_field:
                suggestion = f'响应提示字段 {missing_field} 可能缺失，请补充该参数或从上游映射'
            return [self._diag(step, 'bad_request', f'接口返回 {status_code}，请求参数可能不满足接口要求', suggestion, 0.78)]
        if status_code and status_code >= 500:
            return [self._diag(step, 'server_error', f'接口返回 {status_code}，服务端异常', '查看服务端日志；如果请求参数异常，也可能触发服务端错误', 0.65)]
        return []

    def _diagnose_extractions(self, step):
        result = []
        for extraction in step.get('extractions') or []:
            if extraction.get('value') is None:
                result.append({
                    'level': 'error',
                    'type': 'jsonpath_not_found',
                    'node_id': step.get('node_id'),
                    'target': extraction.get('var_name'),
                    'jsonpath': extraction.get('jsonpath'),
                    'message': f"提取 {extraction.get('var_name')} 失败，路径 {extraction.get('jsonpath')} 未匹配到值",
                    'suggestion': '检查响应结构是否变化，或改用实际存在的 JSONPath',
                    'confidence': 0.86,
                })
        return result

    def _diagnose_assertions(self, step):
        result = []
        for assertion in step.get('assertion_results') or []:
            if assertion.get('pass'):
                continue
            rule = assertion.get('rule') or {}
            jsonpath = rule.get('jsonpath')
            message = assertion.get('error') or f"断言 {jsonpath or '脚本'} 未通过"
            suggestion = '检查断言路径、期望值或接口响应是否符合预期'
            if jsonpath and 'JSONPath 未匹配' in message:
                suggestion = '断言路径不存在，建议根据实际响应字段调整 JSONPath'
            result.append({
                'level': 'warning',
                'type': 'assertion_failed',
                'node_id': step.get('node_id'),
                'jsonpath': jsonpath,
                'message': message,
                'suggestion': suggestion,
                'confidence': 0.78,
            })
        return result

    def _diagnose_missing_vars(self, node, available_vars, step):
        if step.get('node_type') != 'interface':
            return []
        data = json.dumps(node.get('data') or {}, ensure_ascii=False)
        missing = sorted({key for key in _VAR_PATTERN.findall(data) if key not in available_vars})
        return [{
            'level': 'error',
            'type': 'missing_chain_var',
            'node_id': step.get('node_id'),
            'message': f'节点引用变量 vars.{key}，但执行到该节点前尚未生成',
            'suggestion': f'在上游节点增加 {key} 的提取规则，或调整节点依赖顺序',
            'confidence': 0.9,
        } for key in missing]

    def _body_keys(self, step):
        response = step.get('response') or {}
        body = response.get('body')
        if not body:
            return []
        try:
            data = json.loads(body) if isinstance(body, str) else body
        except (TypeError, ValueError):
            return []
        return self._flatten_keys({'body': data})

    def _flatten_keys(self, value, prefix=''):
        keys = []
        if isinstance(value, dict):
            for key, child in value.items():
                path = f'{prefix}.{key}' if prefix else str(key)
                keys.append(path)
                keys.extend(self._flatten_keys(child, path))
        elif isinstance(value, list) and value:
            keys.extend(self._flatten_keys(value[0], prefix))
        return keys

    def _suggest_jsonpath(self, jsonpath, body_keys):
        if not jsonpath:
            return ''
        leaf = str(jsonpath).split('.')[-1].strip("]'\"").lower()
        suffix_matches = [key for key in body_keys if key.split('.')[-1].lower() == leaf]
        if suffix_matches:
            return '$.' + suffix_matches[0]
        return ''

    def _extract_missing_field(self, body):
        if not body:
            return ''
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        patterns = [
            r'["\']?([A-Za-z_][\w.-]*)["\']?\s+(?:is\s+)?required',
            r'缺少(?:字段|参数)?[:：]?\s*([A-Za-z_][\w.-]*)',
            r'missing\s+(?:field|param|parameter)?[:：]?\s*["\']?([A-Za-z_][\w.-]*)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ''

    def _diag(self, step, type_, message, suggestion, confidence):
        return {
            'level': 'error',
            'type': type_,
            'node_id': step.get('node_id'),
            'message': message,
            'suggestion': suggestion,
            'confidence': confidence,
        }
