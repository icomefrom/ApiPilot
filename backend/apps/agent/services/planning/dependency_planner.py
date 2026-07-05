from apps.agent.prompts.dependency_planning_prompt import build_messages
from apps.agent.schemas.validators import validate_dependency_plan


class ModelDependencyPlanner:
    def __init__(self, llm):
        self.llm = llm

    def plan(self, steps, matches, response_samples=None):
        selected_steps = []
        match_by_step = {item['step_index']: item for item in matches}
        for step in steps:
            match = match_by_step.get(step['index']) or {}
            interface = match.get('selected_interface') or {}
            step_data = {
                'index': step['index'],
                'text': step.get('text'),
                'resolved_text': step.get('resolved_text'),
                'depends_on': step.get('depends_on', []),
                'interface': {
                    'interface_id': interface.get('interface_id'),
                    'method': interface.get('method'),
                    'url': interface.get('url'),
                    # LLM 只看到扁平字段名列表做语义匹配
                    'request_fields': interface.get('request_fields') or [],
                },
            }
            # 注入真实响应的键路径列表
            sample = (response_samples or {}).get(step['index'])
            if sample and not sample.get('error') and sample.get('body_keys'):
                step_data['body_keys'] = sample['body_keys']
            else:
                # 无真实响应时降级用 response_fields
                step_data['body_keys'] = []
                step_data['note'] = '试运行未获取到响应，无法推断响应结构'
            selected_steps.append(step_data)

        result = self.llm.chat_json(build_messages(selected_steps), temperature=0.1)
        data = validate_dependency_plan(result['data'])
        self._normalize_from_keys(data.get('mappings', []), selected_steps)
        data.setdefault('missing_inputs', [])
        return data, {'provider': result['provider'], 'model': result['model']}

    def _normalize_from_keys(self, mappings, selected_steps):
        body_keys_by_step = {
            step['index']: step.get('body_keys') or []
            for step in selected_steps
        }
        for item in mappings or []:
            from_step = item.get('from_step')
            from_key = item.get('from_key') or item.get('from_var')
            if not from_step or not from_key:
                continue
            body_keys = body_keys_by_step.get(from_step) or []
            if from_key in body_keys:
                continue
            suffix_matches = [key for key in body_keys if key.split('.')[-1] == from_key]
            if len(suffix_matches) == 1:
                item['from_key'] = suffix_matches[0]
