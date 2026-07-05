from apps.agent.schemas import HIGH_RISK_OPERATIONS


class PlanValidator:
    def validate(self, intent, matched_interfaces, chain_draft, auto_save=False, auto_execute=False):
        warnings = []
        missing_inputs = []
        questions = []

        for matched in matched_interfaces:
            if not matched.get('candidates'):
                missing_inputs.append({
                    'step': matched['step_index'],
                    'field': 'interface',
                    'message': f"第 {matched['step_index']} 步没有匹配到接口，需要手动选择",
                })

        risky_steps = [s for s in intent.get('steps', []) if s.get('operation') in HIGH_RISK_OPERATIONS]
        if risky_steps:
            warnings.append('包含审批、驳回、取消或删除等高风险动作，开源版默认只生成草稿，不自动执行')

        if auto_execute:
            warnings.append('开源版 Agent 不支持自动执行，请先保存草稿并人工确认')

        if not chain_draft.get('nodes'):
            questions.append('请补充要编排的业务目标')

        return {
            'valid': not missing_inputs,
            'warnings': warnings,
            'missing_inputs': missing_inputs,
            'questions': questions,
        }
