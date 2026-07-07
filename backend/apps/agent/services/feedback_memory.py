import re

from django.db.models import F

from apps.agent.models import AgentInterfaceFeedback


_SPACE_PATTERN = re.compile(r'\s+')


def normalize_step_text(value):
    text = _SPACE_PATTERN.sub('', str(value or '').strip().lower())
    return text[:255]


def load_feedback_memory(project):
    """Load feedback grouped by interface id for the candidate preselector."""
    if not project:
        return {}
    rows = AgentInterfaceFeedback.objects.filter(project=project).values(
        'interface_id',
        'step_text',
        'normalized_step_text',
        'confirm_count',
        'reason',
    )
    memory = {}
    for row in rows:
        memory.setdefault(row['interface_id'], []).append(row)
    return memory


def save_interface_feedback(*, project, interface, step_text, user=None, reason=''):
    normalized = normalize_step_text(step_text)
    feedback, created = AgentInterfaceFeedback.objects.get_or_create(
        project=project,
        interface=interface,
        normalized_step_text=normalized,
        defaults={
            'step_text': step_text[:255],
            'reason': reason or '用户确认该接口适配该步骤',
            'created_by': user if getattr(user, 'is_authenticated', False) else None,
        },
    )
    if created:
        return feedback
    AgentInterfaceFeedback.objects.filter(id=feedback.id).update(
        step_text=step_text[:255],
        reason=reason or feedback.reason,
        confirm_count=F('confirm_count') + 1,
    )
    feedback.refresh_from_db()
    return feedback
