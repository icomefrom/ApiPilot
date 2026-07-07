import logging

logger = logging.getLogger(__name__)


class ChainDraftBuilder:
    def build(self, project, goal, steps, matches, dependency_plan, response_samples=None, assertion_plan=None):
        match_by_step = {item['step_index']: item for item in matches}
        mappings = dependency_plan.get('mappings', [])
        extraction_by_step = self._extractions_from_dependencies(mappings)
        override_by_step = self._overrides_from_dependencies(mappings)
        assertion_by_step = self._assertions_by_step(assertion_plan or [])
        nodes = [self._start_node()]
        edges = []
        for idx, step in enumerate(steps, start=1):
            node_id = f'agent_step_{step["index"]}'
            match = match_by_step.get(step['index']) or {}
            interface = match.get('selected_interface') or {}
            step_text = step.get('text') or f'步骤 {idx}'
            nodes.append({
                'id': node_id,
                'type': 'interface',
                'position': {'x': 340 + (idx - 1) * 260, 'y': 120},
                'data': {
                    'label': step_text,
                    'interface_id': match.get('selected_interface_id'),
                    'interface_name': interface.get('name') or '',
                    'agent': {
                        'step_text': step_text,
                        'resolved_text': step_text,
                        'confidence': match.get('confidence', 0),
                        'reason': match.get('reason', ''),
                    },
                    'overrides': {
                        'url': '',
                        'headers': {},
                        'query_params': override_by_step.get(step['index'], {}).get('query_params', {}),
                        'body': '',
                        'body_fields': override_by_step.get(step['index'], {}).get('body_fields', {}),
                        'ws_message': '',
                        'rpc_method': '',
                    },
                    'extractions': extraction_by_step.get(step['index'], []),
                    'assertions': assertion_by_step.get(step['index'], []),
                    'retry_count': 0,
                    'retry_interval': 1,
                },
            })
            for dep in step.get('depends_on') or []:
                edges.append({
                    'id': f'e-agent_step_{dep}-agent_step_{step["index"]}',
                    'source': f'agent_step_{dep}',
                    'target': node_id,
                    'sourceHandle': 'out',
                })
            if idx > 1 and not step.get('depends_on'):
                edges.append({
                    'id': f'e-agent_step_{steps[idx - 2]["index"]}-agent_step_{step["index"]}',
                    'source': f'agent_step_{steps[idx - 2]["index"]}',
                    'target': node_id,
                    'sourceHandle': 'out',
                })
        self._attach_start_and_end(nodes, edges, steps)
        return {
            'name': self._chain_name(goal, steps),
            'description': '由模型驱动 Agent 根据自然语言目标生成的链路草稿，请人工确认接口、参数和提取规则后再执行。',
            'project': project.id,
            'nodes': nodes,
            'edges': edges,
            'globals': [],
            'status': 'draft',
        }

    def _start_node(self):
        return {
            'id': 'agent_start',
            'type': 'start',
            'position': {'x': 80, 'y': 120},
            'data': {'label': '开始'},
        }

    def _end_node(self, steps):
        x = 340 + len(steps) * 260
        return {
            'id': 'agent_end',
            'type': 'end',
            'position': {'x': x, 'y': 120},
            'data': {'label': '结束'},
        }

    def _attach_start_and_end(self, nodes, edges, steps):
        nodes.append(self._end_node(steps))
        if not steps:
            edges.append({
                'id': 'e-agent_start-agent_end',
                'source': 'agent_start',
                'target': 'agent_end',
                'sourceHandle': 'out',
            })
            return

        step_ids = {f'agent_step_{step["index"]}' for step in steps}
        target_ids = {edge['target'] for edge in edges}
        source_ids = {edge['source'] for edge in edges}
        entry_ids = [node_id for node_id in step_ids if node_id not in target_ids]
        exit_ids = [node_id for node_id in step_ids if node_id not in source_ids]
        for node_id in sorted(entry_ids):
            edges.insert(0, {
                'id': f'e-agent_start-{node_id}',
                'source': 'agent_start',
                'target': node_id,
                'sourceHandle': 'out',
            })
        for node_id in sorted(exit_ids):
            edges.append({
                'id': f'e-{node_id}-agent_end',
                'source': node_id,
                'target': 'agent_end',
                'sourceHandle': 'out',
            })

    def _extractions_from_dependencies(self, mappings):
        """只为下游依赖实际需要的 from_key 生成提取规则。"""
        result = {}
        seen = set()
        for item in mappings or []:
            from_step = item.get('from_step')
            from_key = item.get('from_key') or item.get('from_field') or item.get('from_var') or ''
            if not from_step or not self._valid_key(from_key):
                continue
            dedupe_key = (from_step, from_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            var_name = self._var_name(from_key)
            jsonpath = '$.body.' + from_key
            result.setdefault(from_step, []).append({'var_name': var_name, 'jsonpath': jsonpath})
        if result:
            logger.info(f'[ChainDraftBuilder] dependency extractions={result}')
        return result

    def _overrides_from_dependencies(self, mappings):
        """LLM 只输出 from_var → to_key 的语义映射，用于生成 overrides。"""
        result = {}
        for item in mappings:
            to_step = item.get('to_step')
            to_key = item.get('to_key') or item.get('to_field') or ''
            if not to_step or not self._valid_key(to_key):
                continue
            from_key = item.get('from_key') or item.get('from_field') or item.get('from_var') or ''
            if not self._valid_key(from_key):
                continue
            var_name = self._var_name(from_key)
            target = result.setdefault(to_step, {'query_params': {}, 'body_fields': {}})
            field_name = to_key.split('.')[-1]
            if '.query.' in to_key or 'query' in to_key:
                target['query_params'][field_name] = f'{{{{vars.{var_name}}}}}'
            else:
                target['body_fields'][field_name] = f'{{{{vars.{var_name}}}}}'
        return result

    def _assertions_by_step(self, assertion_plan):
        result = {}
        for item in assertion_plan or []:
            step_index = item.get('step_index')
            if not step_index:
                continue
            assertions = []
            for assertion in item.get('assertions') or []:
                if assertion.get('enabled') is False:
                    continue
                if assertion.get('type') != 'jsonpath' or not assertion.get('jsonpath'):
                    continue
                assertions.append(assertion)
            result[step_index] = assertions
        return result

    def _var_name(self, field):
        """从 key 路径生成变量名，如 data.id → data_id"""
        parts = [p for p in field.split('.') if p]
        if not parts:
            return 'value'
        name = '_'.join(parts)
        return ''.join(ch if ch.isalnum() else '_' for ch in name).strip('_') or 'value'

    def _valid_key(self, value):
        key = str(value or '').strip()
        if not key or key in ('-', '—', '无', 'none', 'None', 'null'):
            return False
        return any(ch.isalnum() for ch in key)

    def _chain_name(self, goal, steps):
        if goal and len(goal) <= 80:
            return goal
        return '-'.join([step.get('text') or '' for step in steps])[:80] or 'Agent 生成链路'
