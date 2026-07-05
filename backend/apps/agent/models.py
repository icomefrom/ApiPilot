import uuid

from django.conf import settings
from django.db import models


class AgentTask(models.Model):
    """Agent 异步任务"""

    TASK_TYPE_PLAN = 'plan'
    TASK_TYPE_CHOICES = [
        (TASK_TYPE_PLAN, '规划任务'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_TIMEOUT = 'timeout'
    STATUS_CHOICES = [
        (STATUS_PENDING, '等待中'),
        (STATUS_RUNNING, '运行中'),
        (STATUS_COMPLETED, '完成'),
        (STATUS_FAILED, '失败'),
        (STATUS_TIMEOUT, '超时'),
    ]

    task_id = models.UUIDField('任务ID', unique=True, default=uuid.uuid4, editable=False)
    task_type = models.CharField('任务类型', max_length=20, choices=TASK_TYPE_CHOICES, default=TASK_TYPE_PLAN)
    status = models.CharField('执行状态', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Input
    input_data = models.JSONField('输入数据', default=dict, blank=True)

    # Output / Progress
    progress = models.IntegerField('进度百分比', default=0)
    current_step = models.CharField('当前步骤', max_length=100, blank=True, default='')
    step_results = models.JSONField('步骤结果', default=dict, blank=True)
    result = models.JSONField('最终结果', null=True, blank=True)
    error_message = models.TextField('错误信息', blank=True, default='')

    # Timing
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    # Ownership
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='agent_tasks', verbose_name='创建人', null=True, blank=True,
    )
    project = models.ForeignKey(
        'api_debug.Project', on_delete=models.CASCADE,
        related_name='agent_tasks', verbose_name='项目', null=True, blank=True,
    )

    class Meta:
        db_table = 'api_debug_agent_task'
        verbose_name = 'Agent任务'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'AgentTask({self.task_id}, {self.status})'