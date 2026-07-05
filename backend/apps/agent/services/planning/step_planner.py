import re

from apps.agent.prompts.step_planning_prompt import build_messages
from apps.agent.schemas.validators import validate_step_plan


_STEP_SPLIT_PATTERN = re.compile(r'\s*(?:，|,|、|；|;|\n+|->|→|=>| then |\bthen\b)\s*', re.IGNORECASE)


class StepPlanner:
    def __init__(self, llm):
        self.llm = llm

    def plan(self, goal):
        result = self.llm.chat_json(build_messages(goal), temperature=0.1)
        data = validate_step_plan(result['data'])
        data['steps'] = self._align_steps_to_original_fragments(goal, data.get('steps', []))
        data.setdefault('goal', goal)
        data.setdefault('questions', [])
        return data, {'provider': result['provider'], 'model': result['model']}

    def _align_steps_to_original_fragments(self, goal, model_steps):
        fragments = self._split_goal(goal)
        if len(fragments) == len(model_steps):
            steps = []
            for idx, text in enumerate(fragments, start=1):
                model_step = model_steps[idx - 1]
                steps.append({
                    **model_step,
                    'index': idx,
                    'text': text,
                    'resolved_text': text,
                    'depends_on': self._normalize_depends(model_step.get('depends_on'), idx),
                })
            return steps

        steps = []
        for idx, step in enumerate(model_steps, start=1):
            text = step.get('text') or ''
            steps.append({
                **step,
                'index': idx,
                'text': text,
                'resolved_text': text,
                'depends_on': self._normalize_depends(step.get('depends_on'), idx),
            })
        return steps

    def _split_goal(self, goal):
        return [
            item.strip()
            for item in _STEP_SPLIT_PATTERN.split(goal or '')
            if item and item.strip()
        ]

    def _normalize_depends(self, depends_on, index):
        if not isinstance(depends_on, list):
            return []
        return [
            dep for dep in depends_on
            if isinstance(dep, int) and dep < index
        ]
