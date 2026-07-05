import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_debug.models import Project
from apps.api_debug.views import ensure_default_project, get_user_projects

from .models import AgentTask
from .serializers import AgentPlanRequestSerializer, AgentTaskStatusSerializer
from .services.task_executor import AgentBusyError, start_agent_plan_task

logger = logging.getLogger(__name__)

# Stale task detection threshold (seconds)
STALE_THRESHOLD = getattr(settings, 'AGENT_TASK_TIMEOUT', 300) + 60


class AgentPlanView(APIView):
    """创建 Agent 链路编排任务（异步）。

    POST 立即返回 task_id，后台线程执行编排，前端通过 status 端点轮询进度。
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project = self._get_project(request, data.get('project_id'))
        if not project:
            return Response({'detail': '项目不存在或无权访问'}, status=status.HTTP_404_NOT_FOUND)

        try:
            task = start_agent_plan_task(
                goal=data['goal'],
                project=project,
                user=request.user,
                auto_save=data.get('auto_save', False),
                auto_execute=data.get('auto_execute', False),
                candidate_limit=data.get('candidate_limit', 5),
                environment_id=data.get('environment_id'),
            )
        except AgentBusyError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response({
            'task_id': str(task.task_id),
            'status': task.status,
            'progress': task.progress,
            'current_step': task.current_step,
            'created_at': task.created_at,
        }, status=status.HTTP_202_ACCEPTED)

    def _get_project(self, request, project_id):
        projects = get_user_projects(request.user)
        if project_id:
            try:
                return projects.get(id=project_id)
            except (Project.DoesNotExist, ValueError, TypeError):
                return None
        header_project_id = request.headers.get('X-Project-Id')
        if header_project_id:
            try:
                return projects.get(id=header_project_id)
            except (Project.DoesNotExist, ValueError, TypeError):
                return None
        return ensure_default_project(request.user)


class AgentPlanStatusView(APIView):
    """查询 Agent 编排任务状态（轮询端点）。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        try:
            task = AgentTask.objects.get(task_id=task_id)
        except AgentTask.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        # Ownership check
        if task.created_by and task.created_by != request.user:
            return Response({'detail': '无权访问此任务'}, status=status.HTTP_403_FORBIDDEN)

        # Stale task detection: if running for too long, mark as timeout
        if task.status == AgentTask.STATUS_RUNNING and task.started_at:
            elapsed = (timezone.now() - task.started_at).total_seconds()
            if elapsed > STALE_THRESHOLD:
                task.status = AgentTask.STATUS_TIMEOUT
                task.error_message = '任务超时（线程异常终止）'
                task.finished_at = timezone.now()
                task.save(update_fields=['status', 'error_message', 'finished_at'])

        serializer = AgentTaskStatusSerializer(task)
        return Response(serializer.data)