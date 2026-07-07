import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_debug.models import ApiInterface, Project
from apps.api_debug.views import ensure_default_project, get_user_projects

from .models import AgentTask
from .serializers import (
    AgentInterfaceFeedbackSerializer,
    AgentPlanRequestSerializer,
    AgentPlanResumeSerializer,
    AgentTaskStatusSerializer,
)
from .services.feedback_memory import save_interface_feedback
from .services.task_executor import (
    AgentBusyError,
    cancel_agent_task,
    resume_agent_plan_task,
    start_agent_plan_task,
)

logger = logging.getLogger(__name__)

# Stale task detection threshold (seconds) — slightly above AGENT_TASK_TIMEOUT
from .services.task_executor import AGENT_TASK_TIMEOUT
STALE_THRESHOLD = AGENT_TASK_TIMEOUT + 60


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
                trial_policy=data.get('trial_policy') or {},
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


class AgentPlanCancelView(APIView):
    """取消 Agent 编排任务。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        try:
            task = AgentTask.objects.get(task_id=task_id)
        except AgentTask.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        # Ownership check
        if task.created_by and task.created_by != request.user:
            return Response({'detail': '无权取消此任务'}, status=status.HTTP_403_FORBIDDEN)

        # Only running/pending tasks can be cancelled
        if task.status not in (AgentTask.STATUS_RUNNING, AgentTask.STATUS_PENDING):
            return Response(
                {'detail': f'任务状态为 {task.status}，无法取消'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Signal the thread to stop
        cancelled = cancel_agent_task(str(task.task_id))

        # Also update DB status immediately for responsiveness
        # (the thread will also try to update, but this gives instant feedback)
        task.refresh_from_db()
        if task.status in (AgentTask.STATUS_RUNNING, AgentTask.STATUS_PENDING):
            task.status = AgentTask.STATUS_CANCELLED
            task.current_step = '已取消'
            task.finished_at = timezone.now()
            step_results = task.step_results or {}
            for key, value in step_results.items():
                if isinstance(value, dict) and value.get('status') == 'running':
                    step_results[key] = {'status': 'cancelled'}
            task.step_results = step_results
            task.save(update_fields=['status', 'current_step', 'finished_at', 'step_results'])

        return Response({
            'task_id': str(task.task_id),
            'status': AgentTask.STATUS_CANCELLED,
            'message': '取消请求已发送',
        })


class AgentPlanResumeView(APIView):
    """从断点恢复 Agent 编排任务（写接口授权后继续）。

    POST /api/agent/plan/<task_id>/resume/
    Body: { "trial_policy": { "authorized_step_indexes": [...], "authorized_interface_ids": [...] } }

    与重新提交整个任务不同，此端点会：
    1. 加载原始任务的断点数据（步骤规划、接口匹配等 LLM 结果）
    2. 仅从 response_evidence 阶段重新开始执行
    3. 使用合并后的 trial_policy（原始 + 新授权）
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        serializer = AgentPlanResumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trial_policy = serializer.validated_data['trial_policy']

        try:
            original_task = AgentTask.objects.get(task_id=task_id)
        except AgentTask.DoesNotExist:
            return Response({'detail': '原始任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        # Ownership check
        if original_task.created_by and original_task.created_by != request.user:
            return Response({'detail': '无权操作此任务'}, status=status.HTTP_403_FORBIDDEN)

        # Only completed tasks (with questions) can be resumed
        if original_task.status != AgentTask.STATUS_COMPLETED:
            return Response(
                {'detail': f'原始任务状态为 {original_task.status}，只能从已完成的任务恢复'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check checkpoint data exists
        step_results = original_task.step_results or {}
        for stage_key in ['step_planning', 'interface_matching']:
            stage_data = step_results.get(stage_key, {})
            if stage_data.get('status') != 'completed' or 'output' not in stage_data:
                return Response(
                    {'detail': f'原始任务缺少 {stage_key} 阶段的断点数据，无法从断点恢复'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            new_task = resume_agent_plan_task(
                original_task=original_task,
                user=request.user,
                trial_policy=trial_policy,
            )
        except AgentBusyError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response({
            'task_id': str(new_task.task_id),
            'original_task_id': str(original_task.task_id),
            'status': new_task.status,
            'progress': new_task.progress,
            'current_step': new_task.current_step,
            'created_at': new_task.created_at,
        }, status=status.HTTP_202_ACCEPTED)


class AgentInterfaceFeedbackView(APIView):
    """记录用户确认的步骤-接口匹配，用于后续候选加权。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentInterfaceFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project = self._get_project(request, data.get('project_id'))
        if not project:
            return Response({'detail': '项目不存在或无权访问'}, status=status.HTTP_404_NOT_FOUND)
        try:
            interface = ApiInterface.objects.get(id=data['interface_id'], project=project)
        except ApiInterface.DoesNotExist:
            return Response({'detail': '接口不存在或不属于当前项目'}, status=status.HTTP_404_NOT_FOUND)

        feedback = save_interface_feedback(
            project=project,
            interface=interface,
            step_text=data['step_text'],
            user=request.user,
            reason=data.get('reason') or '用户在 Agent 候选列表中确认使用该接口',
        )
        return Response({
            'id': feedback.id,
            'step_text': feedback.step_text,
            'interface_id': feedback.interface_id,
            'confirm_count': feedback.confirm_count,
            'reason': feedback.reason,
        }, status=status.HTTP_201_CREATED)

    def _get_project(self, request, project_id):
        projects = get_user_projects(request.user)
        if project_id:
            try:
                return projects.get(id=project_id)
            except (Project.DoesNotExist, ValueError, TypeError):
                return None
        return ensure_default_project(request.user)
