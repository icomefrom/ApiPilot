class DependencyPlanner:
    """开源版依赖规划：先建立顺序依赖，保留字段映射建议。"""

    def plan(self, intent_steps, matched_interfaces):
        dependencies = []
        warnings = []
        previous_object = ''
        for step in intent_steps:
            index = step['index']
            if index > 1:
                dependencies.append({
                    'from_step': index - 1,
                    'to_step': index,
                    'type': 'sequence',
                    'description': '按用户描述顺序执行',
                })
            if step.get('object') and previous_object and step['object'] == previous_object:
                dependencies.append({
                    'from_step': index - 1,
                    'to_step': index,
                    'type': 'same_object',
                    'description': f"步骤 {index} 可能依赖上一步返回的 {step['object']} 标识",
                    'suggested_extractors': [
                        {'var_name': f"{step['object']}_id", 'jsonpath': '$.body.data.id'},
                        {'var_name': 'id', 'jsonpath': '$.body.data.id'},
                    ],
                })
            previous_object = step.get('object') or previous_object

        for matched in matched_interfaces:
            if not matched.get('candidates'):
                warnings.append(f"第 {matched['step_index']} 步未匹配到接口：{matched.get('source_text')}")
        return {'dependencies': dependencies, 'warnings': warnings}
