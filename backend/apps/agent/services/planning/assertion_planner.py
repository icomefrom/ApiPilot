"""Assertion planning for Agent-generated chains."""

import re

from apps.agent.prompts.assertion_planning_prompt import build_messages
from apps.agent.schemas.validators import validate_assertion_plan


class AssertionPlanner:
    """Generate safe, explainable assertions for each matched step."""

    SOURCE_BASE = {
        'dependency': 0.92,
        'base': 0.88,
        'schema': 0.82,
        'semantic': 0.65,
        'model': 0.55,
        'user_memory': 0.95,
    }

    COMMON_SUCCESS_FIELDS = {'code', 'success', 'status', 'data'}
    DYNAMIC_FIELD_NAMES = {'id', 'uuid', 'token', 'time', 'timestamp', 'created_at', 'updated_at'}
    WRAPPER_FIELD_NAMES = {
        'code', 'message', 'msg', 'success', 'error', 'errors', 'data', 'result',
        'results', 'list', 'items', 'records', 'rows', 'total', 'count', 'page',
        'page_no', 'page_num', 'page_size', 'pagination', 'meta',
    }
    TECHNICAL_FIELD_NAMES = {
        'trace_id', 'traceid', 'request_id', 'requestid', 'session_id', 'sessionid',
        'token', 'access_token', 'refresh_token', 'secret', 'password', 'signature',
        'nonce', 'timestamp', 'time', 'created_at', 'updated_at', 'deleted_at',
    }
    BUSINESS_SIGNAL_SUFFIXES = (
        'id', 'no', 'number', 'code', 'name', 'title', 'type', 'status', 'state',
        'amount', 'price', 'total', 'balance', 'quantity', 'qty', 'stock', 'rate',
        'level', 'role', 'category', 'sku', 'email', 'phone', 'account', 'currency',
        'date', 'result',
    )

    def __init__(self, llm=None):
        self.llm = llm

    def plan(self, steps, matches, dependency_plan=None, response_samples=None, goal='', assertion_intents=None):
        match_by_step = {item.get('step_index'): item for item in matches or []}
        mappings = dependency_plan.get('mappings', []) if dependency_plan else []
        response_samples = response_samples or {}
        intents_by_step = self._assertion_intents_by_step(assertion_intents or [])
        result = []
        model_assertions, model_trace = self._model_assertions(goal, steps, matches, response_samples, intents_by_step)
        model_by_step = {}
        for assertion in model_assertions:
            model_by_step.setdefault(assertion.get('step_index'), []).append(assertion)

        for step in steps or []:
            step_index = step.get('index')
            match = match_by_step.get(step_index) or {}
            interface = match.get('selected_interface') or {}
            if not match.get('selected_interface_id'):
                result.append({
                    'step_index': step_index,
                    'step_text': step.get('text') or step.get('resolved_text') or '',
                    'interface_id': None,
                    'interface_name': '',
                    'assertions': [],
                })
                continue

            sample = response_samples.get(step_index) or {}
            assertions = []
            assertions.extend(self._base_assertions(sample))
            assertions.extend(self._schema_assertions(sample))
            assertions.extend(self._dependency_assertions(step_index, mappings, sample))
            assertions.extend(self._intent_assertions(intents_by_step.get(step_index) or [], sample, assertions))
            assertions.extend(self._intent_assertions_without_sample(
                intents_by_step.get(step_index) or [], interface, assertions,
            ))
            assertions.extend(self._semantic_assertions(model_by_step.get(step_index) or [], sample, assertions))
            assertions.extend(self._semantic_fallback_assertions(step, interface, sample, assertions))
            assertions = self._dedupe(assertions)

            result.append({
                'step_index': step_index,
                'step_text': step.get('text') or step.get('resolved_text') or '',
                'interface_id': match.get('selected_interface_id'),
                'interface_name': interface.get('name') or interface.get('url') or '',
                'assertions': assertions,
            })
        return result, model_trace

    def _base_assertions(self, sample):
        evidence = {
            'exists_in_response': sample.get('status_code') is not None,
            'used_by_downstream': False,
            'is_common_success_field': True,
            'is_dynamic_equals': False,
            'response_missing': bool(sample.get('error')) or sample.get('status_code') is None,
        }
        return [self._rule(
            jsonpath='$.status_code',
            operator='less_than',
            expected=400,
            source='base',
            reason='基础成功断言：HTTP 状态码小于 400',
            evidence=evidence,
        )]

    def _schema_assertions(self, sample):
        if sample.get('error') or not isinstance(sample.get('body_structure'), dict):
            return []
        body = sample.get('body_structure') or {}
        keys = set(sample.get('body_keys') or [])
        assertions = []

        if 'code' in keys and body.get('code') in (0, '0'):
            assertions.append(self._rule(
                jsonpath='$.body.code',
                operator='equals',
                expected=0,
                source='schema',
                reason='真实响应中 code 为 0，符合常见成功码结构',
                evidence=self._schema_evidence('code', sample, operator='equals'),
            ))
        if 'success' in keys and body.get('success') is True:
            assertions.append(self._rule(
                jsonpath='$.body.success',
                operator='equals',
                expected=True,
                source='schema',
                reason='真实响应中 success 为 true，符合常见成功标识',
                evidence=self._schema_evidence('success', sample, operator='equals'),
            ))
        if 'data' in keys:
            assertions.append(self._rule(
                jsonpath='$.body.data',
                operator='exists',
                expected=True,
                source='schema',
                reason='真实响应中存在 data 字段，作为业务数据结构断言',
                evidence=self._schema_evidence('data', sample, operator='exists'),
            ))
        return assertions

    def _dependency_assertions(self, step_index, mappings, sample):
        assertions = []
        body_keys = set(sample.get('body_keys') or [])
        for item in mappings or []:
            if not isinstance(item, dict) or item.get('from_step') != step_index:
                continue
            from_key = item.get('from_key') or item.get('from_field') or item.get('from_var') or ''
            if not self._valid_key(from_key):
                continue
            field = str(from_key).strip()
            evidence = {
                'exists_in_response': self._field_in_keys(field, body_keys),
                'used_by_downstream': True,
                'is_common_success_field': field.split('.')[-1].lower() in self.COMMON_SUCCESS_FIELDS or field.split('.')[-1].lower() == 'id',
                'is_dynamic_equals': False,
                'response_missing': bool(sample.get('error')) or not body_keys,
            }
            assertions.append(self._rule(
                jsonpath='$.body.' + field,
                operator='exists',
                expected=True,
                source='dependency',
                reason=f"后续第 {item.get('to_step')} 步需要使用 {field}，因此需要确认响应中存在该字段",
                evidence=evidence,
                used_by_step=item.get('to_step'),
                field=field,
            ))
        return assertions

    def _semantic_assertions(self, suggestions, sample, existing_assertions):
        if not suggestions or sample.get('error'):
            return []
        body_keys = set(sample.get('body_keys') or [])
        existing = {
            (item.get('jsonpath'), item.get('operator'), str(item.get('expected')))
            for item in existing_assertions or []
        }
        assertions = []
        for item in suggestions:
            jsonpath = item.get('jsonpath') or ''
            operator = item.get('operator') or 'exists'
            expected = item.get('expected')
            if not self._jsonpath_allowed(jsonpath, body_keys):
                continue
            if (jsonpath, operator, str(expected)) in existing:
                continue
            field = jsonpath.replace('$.body.', '').replace('$.', '')
            evidence = {
                'exists_in_response': self._field_in_keys(field, body_keys) or jsonpath == '$.status_code',
                'used_by_downstream': False,
                'is_common_success_field': field.split('.')[-1].lower() in self.COMMON_SUCCESS_FIELDS,
                'is_dynamic_equals': operator == 'equals' and field.split('.')[-1].lower() in self.DYNAMIC_FIELD_NAMES,
                'response_missing': not body_keys and jsonpath != '$.status_code',
            }
            rule = self._rule(
                jsonpath=jsonpath,
                operator=operator,
                expected=True if operator in ('exists', 'not_exists') else expected,
                source='semantic',
                reason=item.get('reason') or '模型根据业务语义补充断言',
                evidence=evidence,
                field=field,
            )
            model_confidence = float(item.get('confidence') or 0.55)
            rule['model_confidence'] = round(model_confidence, 2)
            rule['confidence'] = min(rule['confidence'], round(model_confidence, 2), 0.78)
            rule['enabled'] = rule['confidence'] >= 0.80
            rule['level'] = 'warning'
            rule['score_parts'].append({'label': '模型业务置信度上限', 'value': round(rule['confidence'] - self.SOURCE_BASE['semantic'], 2)})
            assertions.append(rule)
        return assertions

    def _semantic_fallback_assertions(self, step, interface, sample, existing_assertions):
        """Domain-agnostic business-field fallback when model suggestions are empty or sparse."""
        if sample.get('error') or not sample.get('body_keys'):
            return []
        existing_paths = {item.get('jsonpath') for item in existing_assertions or []}
        body_keys = sample.get('body_keys') or []
        selected_keys = self._select_business_assertion_keys(step, interface, sample, existing_paths)
        if not selected_keys:
            return []
        assertions = []
        for key in selected_keys:
            leaf = key.split('.')[-1].lower()
            evidence = {
                'exists_in_response': True,
                'used_by_downstream': False,
                'is_common_success_field': leaf in self.COMMON_SUCCESS_FIELDS or leaf.endswith('id'),
                'is_dynamic_equals': False,
                'response_missing': False,
            }
            assertions.append(self._rule(
                jsonpath='$.body.' + key,
                operator='exists',
                expected=True,
                source='semantic',
                reason=f'根据接口语义和真实响应字段补充业务字段“{key}”存在性断言',
                evidence=evidence,
                field=key,
            ))
        return assertions

    def _intent_assertions(self, intents, sample, existing_assertions):
        if not intents or sample.get('error') or not sample.get('body_keys'):
            return []
        existing_paths = {item.get('jsonpath') for item in existing_assertions or []}
        body_keys = sample.get('body_keys') or []
        assertions = []
        for intent in intents:
            parsed = self._normalize_assertion_intent(intent)
            if not parsed:
                continue
            field_hint, operator, expected = parsed
            key = self._find_best_intent_field(field_hint, body_keys)
            if not key or '$.body.' + key in existing_paths:
                continue
            evidence = {
                'exists_in_response': True,
                'used_by_downstream': False,
                'is_common_success_field': key.split('.')[-1].lower() in self.COMMON_SUCCESS_FIELDS,
                'is_dynamic_equals': False,
                'response_missing': False,
            }
            rule = self._rule(
                jsonpath='$.body.' + key,
                operator=operator,
                expected=expected,
                source='semantic',
                reason=f'根据用户校验意图“{intent.get("text") or ""}”生成业务断言',
                evidence=evidence,
                field=key,
            )
            rule['confidence'] = max(rule['confidence'], 0.86)
            rule['enabled'] = rule['confidence'] >= 0.80
            rule['level'] = 'warning' if not rule['enabled'] else 'error'
            rule['score_parts'].append({'label': '用户显式校验意图', 'value': 0.08})
            assertions.append(rule)
        return assertions

    def _intent_assertions_without_sample(self, intents, interface, existing_assertions):
        if not intents:
            return []
        candidate_keys = self._candidate_response_keys_from_interface(interface)
        if not candidate_keys:
            return []
        existing_paths = {item.get('jsonpath') for item in existing_assertions or []}
        assertions = []
        for intent in intents:
            parsed = self._normalize_assertion_intent(intent)
            if not parsed:
                continue
            field_hint, operator, expected = parsed
            key = self._find_best_intent_field(field_hint, candidate_keys)
            if not key or '$.body.' + key in existing_paths:
                continue
            evidence = {
                'exists_in_response': False,
                'used_by_downstream': False,
                'is_common_success_field': key.split('.')[-1].lower() in self.COMMON_SUCCESS_FIELDS,
                'is_dynamic_equals': False,
                'response_missing': True,
            }
            rule = self._rule(
                jsonpath='$.body.' + key,
                operator=operator,
                expected=expected,
                source='semantic',
                reason=f'根据用户校验意图“{intent.get("text") or ""}”和接口已有响应字段生成断言；试运行未获取真实响应，建议确认环境后运行',
                evidence=evidence,
                field=key,
            )
            rule['confidence'] = max(rule['confidence'], 0.80)
            rule['enabled'] = True
            rule['level'] = 'error'
            rule['score_parts'].append({'label': '用户显式校验意图', 'value': 0.08})
            rule['score_parts'].append({'label': '来自接口已有响应字段', 'value': 0.04})
            assertions.append(rule)
        return assertions

    def _select_business_assertion_keys(self, step, interface, sample, existing_paths):
        body_keys = sample.get('body_keys') or []
        body_structure = sample.get('body_structure')
        method = str(interface.get('method') or '').upper()
        context_text = ' '.join([
            str(step.get('text') or step.get('resolved_text') or ''),
            str(interface.get('name') or ''),
            str(interface.get('url') or ''),
            method,
        ]).lower()
        is_mutation_method = method in {'POST', 'PUT', 'PATCH', 'DELETE'}

        scored = []
        for key in body_keys:
            key = str(key or '').strip()
            if not key or '$.body.' + key in existing_paths:
                continue
            score, reasons = self._business_field_score(key, body_structure, context_text, is_mutation_method)
            if score <= 0:
                continue
            scored.append((score, self._field_depth(key), key, reasons))

        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected = []
        selected_leafs = set()
        for _, _, key, _ in scored:
            leaf = key.split('.')[-1].lower()
            if leaf in selected_leafs:
                continue
            selected.append(key)
            selected_leafs.add(leaf)
            if len(selected) >= 3:
                break
        return selected

    def _business_field_score(self, key, body_structure, context_text, is_mutation_method):
        normalized_key = key.lower()
        leaf = normalized_key.split('.')[-1]
        score = 0.0
        reasons = []

        if leaf in self.TECHNICAL_FIELD_NAMES:
            return -1.0, ['技术字段']
        if leaf in self.WRAPPER_FIELD_NAMES:
            score -= 0.25
            reasons.append('包装字段')
        if self._value_at_path(body_structure, key) in (None, [], {}):
            score -= 0.05
            reasons.append('值为空')
        else:
            score += 0.15
            reasons.append('真实响应有值')

        if self._is_nested_business_key(key):
            score += 0.18
            reasons.append('嵌套业务字段')
        if leaf.endswith('id') or leaf in {'id', 'uuid'}:
            score += 0.18 if is_mutation_method else 0.12
            reasons.append('资源标识字段')
        if leaf.endswith(self.BUSINESS_SIGNAL_SUFFIXES) or any(part in leaf for part in ['amount', 'price', 'balance', 'stock', 'status', 'state']):
            score += 0.16
            reasons.append('常见业务字段形态')
        if leaf and leaf in context_text:
            score += 0.10
            reasons.append('字段名与步骤/接口语义相关')
        if any(part and part in context_text for part in normalized_key.replace('[].', '.').split('.')):
            score += 0.06
            reasons.append('路径片段与接口语义相关')
        if is_mutation_method:
            score += 0.04
            reasons.append('变更类接口需要确认业务结果')
        if self._field_depth(key) >= 2:
            score += 0.04
            reasons.append('非顶层包装字段')

        return score, reasons

    def _is_nested_business_key(self, key):
        parts = [part for part in str(key).replace('[]', '').split('.') if part]
        return len(parts) >= 2 and parts[-1].lower() not in self.WRAPPER_FIELD_NAMES

    def _field_depth(self, key):
        return len([part for part in str(key).replace('[]', '').split('.') if part])

    def _value_at_path(self, body, key):
        current = body
        for raw_part in str(key or '').replace('[]', '').split('.'):
            part = raw_part.strip()
            if not part:
                continue
            if isinstance(current, list):
                current = current[0] if current else None
            if not isinstance(current, dict) or part not in current:
                return None
            current = current.get(part)
        return current

    def _model_assertions(self, goal, steps, matches, response_samples, intents_by_step=None):
        if not self.llm:
            return [], {}
        selected_steps = self._selected_steps_for_model(steps, matches, response_samples, intents_by_step or {})
        if not selected_steps:
            return [], {}
        try:
            result = self.llm.chat_json(build_messages(goal, selected_steps), temperature=0.1)
            data = validate_assertion_plan(result['data'])
            return data.get('assertions') or [], {
                'provider': result.get('provider'),
                'model': result.get('model'),
            }
        except Exception:
            return [], {}

    def _selected_steps_for_model(self, steps, matches, response_samples, intents_by_step=None):
        match_by_step = {item.get('step_index'): item for item in matches or []}
        intents_by_step = intents_by_step or {}
        selected = []
        for step in steps or []:
            step_index = step.get('index')
            match = match_by_step.get(step_index) or {}
            interface = match.get('selected_interface') or {}
            sample = (response_samples or {}).get(step_index) or {}
            body_keys = sample.get('body_keys') or []
            if not match.get('selected_interface_id') or not body_keys:
                continue
            selected.append({
                'index': step_index,
                'text': step.get('text') or step.get('resolved_text') or '',
                'interface': {
                    'interface_id': match.get('selected_interface_id'),
                    'name': interface.get('name'),
                    'method': interface.get('method'),
                    'url': interface.get('url'),
                },
                'status_code': sample.get('status_code'),
                'body_keys': body_keys[:80],
                'body_sample': sample.get('body_structure'),
                'assertion_intents': [item.get('text') for item in intents_by_step.get(step_index, [])],
            })
        return selected

    def _assertion_intents_by_step(self, assertion_intents):
        result = {}
        for item in assertion_intents or []:
            if not isinstance(item, dict):
                continue
            target = item.get('target_step_index')
            if isinstance(target, int):
                result.setdefault(target, []).append(item)
        return result

    def _parse_simple_assertion_intent(self, text):
        text = str(text or '').strip()
        if not text:
            return None
        patterns = [
            r'(?:状态|status|state)\s*(?:为|是|=|==|equals?|should\s+be|is)\s*["\']?([\w\u4e00-\u9fa5.-]+)["\']?',
            r'["\']?([\w\u4e00-\u9fa5.-]+)["\']?\s*(?:状态|status|state)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return 'status', match.group(1)
        return None

    def _normalize_assertion_intent(self, intent):
        field_hint = str(intent.get('field_hint') or '').strip()
        operator = intent.get('operator') or ''
        expected = intent.get('expected')
        allowed_ops = {
            'equals', 'not_equals', 'contains', 'not_contains',
            'greater_than', 'less_than', 'exists', 'not_exists',
        }
        if field_hint and operator in allowed_ops:
            if operator in ('exists', 'not_exists') and expected in (None, ''):
                expected = True
            return self._normalize_field_hint(field_hint), operator, expected

        parsed = self._parse_simple_assertion_intent(intent.get('text') or '')
        if not parsed:
            return None
        parsed_field, parsed_expected = parsed
        return self._normalize_field_hint(parsed_field), 'equals', parsed_expected

    def _normalize_field_hint(self, field_hint):
        text = str(field_hint or '').strip().lower()
        aliases = {
            '状态': 'status',
            '订单状态': 'status',
            '支付状态': 'payment_status',
            '库存': 'stock',
            '余额': 'balance',
            '金额': 'amount',
            '价格': 'price',
            '数量': 'quantity',
            '名称': 'name',
            '标题': 'title',
            '编号': 'no',
            '订单号': 'order_no',
            '流水号': 'transaction_no',
        }
        return aliases.get(text, text.replace(' ', '_'))

    def _find_best_intent_field(self, field_hint, body_keys):
        hint = str(field_hint or '').lower()
        hint_tokens = {part for part in re.split(r'[\s_.-]+', hint) if part}
        candidates = []
        for key in body_keys or []:
            key = str(key)
            leaf = key.split('.')[-1].lower()
            leaf_tokens = {part for part in re.split(r'[\s_.-]+', leaf) if part}
            if hint and (
                leaf == hint
                or leaf.endswith('_' + hint)
                or leaf.endswith(hint)
                or hint in leaf
                or bool(hint_tokens and hint_tokens.issubset(leaf_tokens))
            ):
                candidates.append(key)
        if not candidates and hint == 'status':
            candidates = [
                str(key) for key in body_keys or []
                if 'status' in str(key).split('.')[-1].lower()
                or str(key).split('.')[-1].lower() == 'state'
            ]
        candidates.sort(key=lambda item: (
            0 if item.split('.')[-1].lower() in ('order_status', 'status', 'state') else 1,
            len(item),
        ))
        return candidates[0] if candidates else None

    def _candidate_response_keys_from_interface(self, interface):
        keys = []
        for field in interface.get('response_fields') or []:
            key = str(field or '').strip()
            if key.startswith('$.body.'):
                key = key.replace('$.body.', '', 1)
            elif key.startswith('body.'):
                key = key.replace('body.', '', 1)
            elif key.startswith('$.'):
                key = key.replace('$.', '', 1)
            if self._valid_key(key):
                keys.append(key)
        return sorted(set(keys))

    def _jsonpath_allowed(self, jsonpath, body_keys):
        if jsonpath == '$.status_code':
            return True
        if not jsonpath.startswith('$.body.'):
            return False
        key = jsonpath.replace('$.body.', '', 1)
        return self._field_in_keys(key, body_keys)

    def _schema_evidence(self, field, sample, operator='exists'):
        leaf = str(field).split('.')[-1].lower()
        return {
            'exists_in_response': True,
            'used_by_downstream': False,
            'is_common_success_field': leaf in self.COMMON_SUCCESS_FIELDS,
            'is_dynamic_equals': operator == 'equals' and leaf in self.DYNAMIC_FIELD_NAMES,
            'response_missing': bool(sample.get('error')),
        }

    def _rule(self, *, jsonpath, operator, expected, source, reason, evidence, used_by_step=None, field=None):
        confidence, score_parts = self._score(source, evidence)
        return {
            'type': 'jsonpath',
            'jsonpath': jsonpath,
            'target': jsonpath,
            'operator': operator,
            'expected': expected,
            'enabled': confidence >= 0.80,
            'level': 'error' if confidence >= 0.80 else 'warning',
            'source': source,
            'reason': reason,
            'confidence': confidence,
            'score_parts': score_parts,
            'used_by_step': used_by_step,
            'field': field or jsonpath.split('.')[-1],
        }

    def _score(self, source, evidence):
        score = self.SOURCE_BASE.get(source, 0.55)
        parts = [{'label': f'来源基础分({source})', 'value': self.SOURCE_BASE.get(source, 0.55)}]

        if evidence.get('exists_in_response'):
            score += 0.04
            parts.append({'label': '真实响应存在该字段', 'value': 0.04})
        if evidence.get('used_by_downstream'):
            score += 0.03
            parts.append({'label': '后续节点使用该字段', 'value': 0.03})
        if evidence.get('is_common_success_field'):
            score += 0.02
            parts.append({'label': '常见关键字段', 'value': 0.02})
        if evidence.get('is_dynamic_equals'):
            score -= 0.08
            parts.append({'label': '动态字段不适合固定值断言', 'value': -0.08})
        if evidence.get('response_missing'):
            score -= 0.05
            parts.append({'label': '缺少真实响应证据', 'value': -0.05})

        return max(0.10, min(0.98, round(score, 2))), parts

    def _dedupe(self, assertions):
        result = []
        seen = set()
        for item in assertions:
            key = (item.get('jsonpath'), item.get('operator'), str(item.get('expected')))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _field_in_keys(self, field, body_keys):
        field = str(field or '').strip()
        if field in body_keys:
            return True
        leaf = field.split('.')[-1].lower()
        return any(str(key).split('.')[-1].lower() == leaf for key in body_keys)

    def _valid_key(self, value):
        key = str(value or '').strip()
        if not key or key in ('-', '—', '无', 'none', 'None', 'null'):
            return False
        return any(ch.isalnum() for ch in key)
