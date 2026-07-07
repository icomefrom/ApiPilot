class PlanValidator:
    # 置信度低于此值视为弱匹配，需要人工确认
    CONFIDENCE_WARNING_THRESHOLD = 0.6

    def validate(self, steps, matches, dependency_plan, chain_draft, auto_execute=False):
        warnings = []
        missing_inputs = list(dependency_plan.get('missing_inputs') or [])
        match_by_step = {item['step_index']: item for item in matches}
        for step in steps:
            match = match_by_step.get(step['index'])
            if not match or not match.get('selected_interface_id'):
                missing_inputs.append({
                    'step': step['index'],
                    'field': 'interface',
                    'message': f"第 {step['index']} 步未选择接口：{step.get('resolved_text') or step.get('text')}",
                })
            elif match.get('confidence', 0) < self.CONFIDENCE_WARNING_THRESHOLD:
                warnings.append(f"第 {step['index']} 步接口匹配置信度较低（{match.get('confidence', 0):.0%}），建议人工确认")
                # 标记弱匹配，前端可区分展示
                match['is_weak_match'] = True
        if auto_execute:
            warnings.append('开源版 Agent 只生成链路草稿，不自动执行')
        return {
            'valid': not missing_inputs,
            'warnings': warnings,
            'missing_inputs': missing_inputs,
        }
