class ParameterRequirementInferer:
    """Infer which selected interface request fields are satisfied or missing."""

    def infer(self, steps, matches, dependency_plan=None, response_samples=None):
        match_by_step = {item.get('step_index'): item for item in matches or []}
        mappings = dependency_plan.get('mappings', []) if dependency_plan else []
        missing_inputs = dependency_plan.get('missing_inputs', []) if dependency_plan else []
        requirements = []

        for step in steps or []:
            step_index = step.get('index')
            match = match_by_step.get(step_index) or {}
            interface = match.get('selected_interface') or {}
            request_fields = self._target_fields_for_step(step_index, mappings, missing_inputs)
            if not request_fields:
                request_fields = []
            field_items = []
            for field in request_fields:
                mapping = self._find_mapping_to_step(mappings, step_index, field)
                missing = self._find_missing_input(missing_inputs, step_index, field)
                if mapping:
                    field_items.append({
                        'field': field,
                        'status': 'mapped',
                        'source': f"第 {mapping.get('from_step')} 步 {mapping.get('from_key') or mapping.get('from_var') or ''}".strip(),
                        'message': '已从上游响应映射',
                    })
                elif missing:
                    field_items.append({
                        'field': field,
                        'status': 'missing',
                        'source': '',
                        'message': missing.get('message') or '需要用户补充',
                    })
                else:
                    upstream = self._find_upstream_candidate(response_samples or {}, step_index, field)
                    if upstream:
                        field_items.append({
                            'field': field,
                            'status': 'suggested',
                            'source': f"第 {upstream['step']} 步 {upstream['key']}",
                            'message': '响应字段同名，可考虑映射',
                        })
                    else:
                        field_items.append({
                            'field': field,
                            'status': 'missing',
                            'source': '',
                            'message': '未发现上游映射或默认值，需要用户确认',
                        })
            if field_items:
                requirements.append({
                    'step_index': step_index,
                    'step_text': step.get('text') or step.get('resolved_text') or '',
                    'interface_id': interface.get('interface_id'),
                    'interface_name': interface.get('name'),
                    'fields': field_items,
                })
        return requirements

    def _target_fields_for_step(self, step_index, mappings, missing_inputs):
        fields = []
        for item in mappings or []:
            if not isinstance(item, dict) or item.get('to_step') != step_index:
                continue
            field = item.get('to_key') or item.get('to_field') or item.get('field')
            if self._valid_field(field):
                fields.append(str(field).strip())
        for item in missing_inputs or []:
            if not isinstance(item, dict) or item.get('step') not in (None, step_index):
                continue
            field = item.get('field') or item.get('to_key') or item.get('to_field')
            if self._valid_field(field):
                fields.append(str(field).strip())
        return sorted(set(fields))

    def _filter_request_fields(self, fields):
        ignored = {'content-type', 'authorization', 'cookie'}
        result = []
        for field in fields:
            key = str(field or '').strip()
            if not key or key.lower() in ignored or not self._valid_field(key):
                continue
            result.append(key)
        return result

    def _find_mapping_to_step(self, mappings, step_index, field):
        for item in mappings or []:
            if item.get('to_step') != step_index:
                continue
            to_key = item.get('to_key') or item.get('to_field') or item.get('field')
            if self._field_matches(to_key, field):
                return item
        return None

    def _find_missing_input(self, missing_inputs, step_index, field):
        for item in missing_inputs or []:
            if not isinstance(item, dict):
                continue
            if item.get('step') not in (None, step_index):
                continue
            if self._field_matches(item.get('field'), field):
                return item
        return None

    def _find_upstream_candidate(self, response_samples, step_index, field):
        field_leaf = str(field).split('.')[-1].lower()
        for from_step, sample in sorted(response_samples.items()):
            if from_step >= step_index or sample.get('error'):
                continue
            for key in sample.get('body_keys') or []:
                if str(key).split('.')[-1].lower() == field_leaf:
                    return {'step': from_step, 'key': key}
        return None

    def _field_matches(self, left, right):
        if not left or not right:
            return False
        left = str(left)
        right = str(right)
        return left == right or left.split('.')[-1] == right.split('.')[-1]

    def _valid_field(self, value):
        field = str(value or '').strip()
        if not field or field in ('-', '—', '无', 'none', 'None', 'null'):
            return False
        return any(ch.isalnum() for ch in field)
