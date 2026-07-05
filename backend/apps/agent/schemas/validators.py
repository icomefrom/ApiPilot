from apps.agent.services.llm.errors import LLMResponseFormatError


def require_keys(data, keys, schema_name):
    if not isinstance(data, dict):
        raise LLMResponseFormatError(f'{schema_name} 必须是 JSON 对象')
    missing = [key for key in keys if key not in data]
    if missing:
        raise LLMResponseFormatError(f'{schema_name} 缺少字段: {", ".join(missing)}')


def validate_step_plan(data):
    require_keys(data, ['steps'], 'StepPlan')
    if not isinstance(data['steps'], list) or not data['steps']:
        raise LLMResponseFormatError('StepPlan.steps 必须是非空数组')
    for idx, step in enumerate(data['steps'], start=1):
        require_keys(step, ['index', 'text', 'resolved_text', 'depends_on'], f'StepPlan.steps[{idx}]')
        if not isinstance(step['depends_on'], list):
            raise LLMResponseFormatError('depends_on 必须是数组')
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
    for idx, item in enumerate(data['mappings'], start=1):
        # 兼容 from_key/to_key 和旧版 from_field/to_field
        has_from = 'from_key' in item or 'from_field' in item
        has_to = 'to_key' in item or 'to_field' in item
        if not has_from or not has_to:
            raise LLMResponseFormatError(f'DependencyPlan.mappings[{idx}] 缺少 from_key/to_key')
    return data
