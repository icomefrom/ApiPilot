from rest_framework import serializers

from .models import AgentTask


class AgentPlanRequestSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(required=False)
    environment_id = serializers.IntegerField(required=False, allow_null=True)
    goal = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    auto_save = serializers.BooleanField(required=False, default=False)
    auto_execute = serializers.BooleanField(required=False, default=False)
    candidate_limit = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)

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