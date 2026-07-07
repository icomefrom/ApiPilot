class ChainBuilder:
    """把 Agent 计划转换为现有 Chain.nodes / Chain.edges 草稿。"""

    def build(self, project, goal, intent_steps, matched_interfaces, dependencies):
        nodes = [self._start_node()]
        edges = []
        selected = {m['step_index']: (m['candidates'][0] if m.get('candidates') else None) for m in matched_interfaces}
        object_var_names = {}

        for step in intent_steps:
            index = step['index']
            candidate = selected.get(index)
            node_id = f'agent_step_{index}'
            object_name = step.get('object') or 'object'
            var_name = self._safe_var_name(object_name)
            object_var_names[object_name] = var_name
            extractions = []
            if index == 1 and object_name:
                extractions = [
                    {'var_name': f'{var_name}_id', 'jsonpath': '$.body.data.id'},
                ]
            nodes.append({
                'id': node_id,
                'type': 'interface',
                'position': {'x': 340 + (index - 1) * 260, 'y': 120},
                'data': {
                    'label': step.get('source_text') or f"步骤 {index}",
                    'interface_id': candidate['interface_id'] if candidate else None,
                    'interface_name': candidate['name'] if candidate else '',
                    'agent_intent': {
                        'operation': step.get('operation'),
                        'object': step.get('object'),
                        'source_text': step.get('source_text'),
                        'candidate_score': candidate['score'] if candidate else 0,
                    },
                    'overrides': {
                        'url': '',
                        'headers': {},
                        'query_params': {},
                        'body': '',
                        'body_fields': {},
                        'ws_message': '',
                        'rpc_method': '',
                    },
                    'extractions': extractions,
                    'assertions': [],
                    'retry_count': 0,
                    'retry_interval': 1,
                },
            })
            if index > 1:
                edges.append({
                    'id': f'e-agent_step_{index - 1}-agent_step_{index}',
                    'source': f'agent_step_{index - 1}',
                    'target': node_id,
                    'sourceHandle': 'out',
                })

        self._attach_start_and_end(nodes, edges, intent_steps)
        return {
            'name': self._chain_name(goal, intent_steps),
            'description': '由开源版 Agent 根据自然语言目标生成的链路草稿，请人工确认接口和参数后再执行。',
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
        if not steps:
            nodes.append(self._end_node(steps))
            edges.append({
                'id': 'e-agent_start-agent_end',
                'source': 'agent_start',
                'target': 'agent_end',
                'sourceHandle': 'out',
            })
            return

        nodes.append(self._end_node(steps))
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

    def _chain_name(self, goal, steps):
        if goal and len(goal) <= 80:
            return goal
        names = [step.get('source_text') or step.get('name') for step in steps]
        return '-'.join([name for name in names if name])[:80] or 'Agent 生成链路'

    def _safe_var_name(self, value):
        value = ''.join(ch if ch.isalnum() else '_' for ch in value).strip('_')
        return value or 'object'
