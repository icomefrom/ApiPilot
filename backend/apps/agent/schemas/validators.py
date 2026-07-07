from apps.agent.services.llm.errors import LLMResponseFormatError


def require_keys(data, keys, schema_name):
    if not isinstance(data, dict):
        raise LLMResponseFormatError(f'{schema_name} 必须是 JSON 对象')
    missing = [key for key in keys if key not in data]
    if missing:
        raise LLMResponseFormatError(f'{schema_name} 缺少字段: {", ".join(missing)}')


def validate_step_plan(data):
    if not isinstance(data, dict):
        raise LLMResponseFormatError('StepPlan 必须是 JSON 对象')
    actions = data.get('actions')
    steps = data.get('steps')
    if isinstance(actions, list) and actions:
        data['steps'] = actions
    elif isinstance(steps, list) and steps:
        data['actions'] = steps
    else:
        raise LLMResponseFormatError('StepPlan.actions/steps 必须是非空数组')

    for idx, step in enumerate(data['steps'], start=1):
        require_keys(step, ['index', 'text', 'depends_on'], f'StepPlan.steps[{idx}]')
        if not isinstance(step['depends_on'], list):
            raise LLMResponseFormatError('depends_on 必须是数组')
        # resolved_text 和 source_span 允许缺失，自动填充
        step.setdefault('resolved_text', step.get('text') or '')
        step.setdefault('source_span', step.get('text') or '')
    data['constraints'] = normalize_constraints(data.get('constraints', []))
    return data


def validate_interface_match(data):
    require_keys(data, ['matches'], 'InterfaceMatch')
    if not isinstance(data['matches'], list):
        raise LLMResponseFormatError('InterfaceMatch.matches 必须是数组')
    for idx, item in enumerate(data['matches'], start=1):
        require_keys(item, ['step_index', 'selected_interface_id', 'confidence', 'reason'], f'InterfaceMatch.matches[{idx}]')
    return data


def validate_dependency_plan(data):
    require_keys(data, ['mappings'], 'DependencyPlan')
    if not isinstance(data['mappings'], list):
        raise LLMResponseFormatError('DependencyPlan.mappings 必须是数组')
    normalized_mappings = []
    for idx, item in enumerate(data['mappings'], start=1):
        if not isinstance(item, dict):
            continue
        # 兼容 from_key/to_key 和旧版 from_field/to_field
        has_from = 'from_key' in item or 'from_field' in item
        has_to = 'to_key' in item or 'to_field' in item
        if not has_from or not has_to:
            raise LLMResponseFormatError(f'DependencyPlan.mappings[{idx}] 缺少 from_key/to_key')
        from_key = item.get('from_key') or item.get('from_field') or item.get('from_var')
        to_key = item.get('to_key') or item.get('to_field')
        if not valid_dependency_key(from_key) or not valid_dependency_key(to_key):
            continue
        item['from_key'] = from_key
        item['to_key'] = to_key
        normalized_mappings.append(item)
    data['mappings'] = normalized_mappings
    data['missing_inputs'] = normalize_missing_inputs(data.get('missing_inputs', []))
    return data


def validate_assertion_plan(data):
    require_keys(data, ['assertions'], 'AssertionPlan')
    if not isinstance(data['assertions'], list):
        raise LLMResponseFormatError('AssertionPlan.assertions 必须是数组')
    normalized = []
    allowed_ops = {
        'equals', 'not_equals', 'contains', 'not_contains',
        'greater_than', 'less_than', 'exists', 'not_exists',
    }
    for item in data['assertions']:
        if not isinstance(item, dict):
            continue
        step_index = item.get('step_index')
        jsonpath = str(item.get('jsonpath') or '').strip()
        operator = item.get('operator') or 'exists'
        if not isinstance(step_index, int) or not jsonpath.startswith('$.'):
            continue
        if operator not in allowed_ops:
            operator = 'exists'
        item['step_index'] = step_index
        item['jsonpath'] = jsonpath
        item['operator'] = operator
        item.setdefault('expected', True if operator in ('exists', 'not_exists') else '')
        item['confidence'] = _clamp_float(item.get('confidence'), default=0.55)
        item['reason'] = str(item.get('reason') or '模型根据业务语义补充断言')[:300]
        normalized.append(item)
    data['assertions'] = normalized
    return data


def _clamp_float(value, default=0.0):
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = default
    return max(0.0, min(1.0, num))


def normalize_missing_inputs(value):
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str) and item.strip():
            normalized.append({
                'step': None,
                'field': '',
                'message': item.strip(),
            })
    return normalized


def normalize_constraints(value):
    if not isinstance(value, list):
        return []
    allowed_ops = {
        'equals', 'not_equals', 'contains', 'not_contains',
        'greater_than', 'less_than', 'exists', 'not_exists',
    }
    normalized = []
    for item in value:
        if isinstance(item, str):
            item = {'text': item}
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or item.get('source_text') or '').strip()
        if not text:
            continue
        target = item.get('target_action_index')
        if not isinstance(target, int):
            target = item.get('target_step_index')
        operator = item.get('operator') or 'exists'
        if operator not in allowed_ops:
            operator = 'exists'
        normalized.append({
            'text': text,
            'target_action_index': target if isinstance(target, int) else None,
            'field_hint': str(item.get('field_hint') or item.get('field_concept') or '').strip(),
            'operator': operator,
            'expected': item.get('expected', True if operator in ('exists', 'not_exists') else ''),
            'confidence': _clamp_float(item.get('confidence'), default=0.65),
        })
    return normalized


def valid_dependency_key(value):
    key = str(value or '').strip()
    if not key or key in ('-', '—', '无', 'none', 'None', 'null'):
        return False
    return any(ch.isalnum() for ch in key)
