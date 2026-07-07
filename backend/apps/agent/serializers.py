from rest_framework import serializers

from .models import AgentTask


class AgentPlanRequestSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(required=False)
    environment_id = serializers.IntegerField(required=False, allow_null=True)
    goal = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    auto_save = serializers.BooleanField(required=False, default=False)
    auto_execute = serializers.BooleanField(required=False, default=False)
    candidate_limit = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)
    trial_policy = serializers.DictField(required=False, default=dict)

    def validate_environment_id(self, value):
        """如果传了 environment_id，验证它属于当前项目。"""
        if value is None:
            return value
        project_id = self.initial_data.get('project_id')
        if project_id:
            from apps.api_debug.models import Environment
            if not Environment.objects.filter(id=value, project_id=project_id).exists():
                raise serializers.ValidationError('环境不存在或不属于当前项目')
        return value


class AgentPlanResumeSerializer(serializers.Serializer):
    """从断点恢复 Agent 编排任务（写接口授权后继续）。"""
    trial_policy = serializers.DictField(required=True)

    def validate_trial_policy(self, value):
        """确保 trial_policy 包含有效的授权信息。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError('trial_policy 必须是字典')
        # 至少有一个授权字段
        has_steps = 'authorized_step_indexes' in value
        has_ifaces = 'authorized_interface_ids' in value
        if not has_steps and not has_ifaces:
            raise serializers.ValidationError(
                'trial_policy 需要包含 authorized_step_indexes 或 authorized_interface_ids'
            )
        return value


class AgentInterfaceFeedbackSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(required=False)
    step_text = serializers.CharField(required=True, allow_blank=False, max_length=255)
    interface_id = serializers.IntegerField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class AgentTaskStatusSerializer(serializers.ModelSerializer):
    """Agent 任务状态输出，用于轮询端点。"""
    task_id = serializers.UUIDField(format='hex_verbose')

    class Meta:
        model = AgentTask
        fields = [
            'task_id',
            'task_type',
            'status',
            'progress',
            'current_step',
            'step_results',
            'result',
            'error_message',
            'started_at',
            'finished_at',
            'created_at',
        ]
        read_only_fields = fields
