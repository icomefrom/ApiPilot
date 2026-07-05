from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import ApiGroup, ApiInterface, DebugResult, Chain, ChainResult, Environment, Project, ProjectMember
from .serializers import (
    ApiGroupSerializer,
    ApiInterfaceListSerializer,
    ApiInterfaceDetailSerializer,
    CurlParseSerializer,
    CurlParseResultSerializer,
    DebugExecuteSerializer,
    DebugResultSerializer,
    ScriptAssertSerializer,
    ChainListSerializer,
    ChainDetailSerializer,
    ChainResultSerializer,
    EnvironmentSerializer,
    ProjectSerializer,
    ProjectMemberSerializer,
    ProjectMemberInviteSerializer,
    ProjectMemberRoleSerializer,
    TestPostSerializer,
)
from .curl_parser import parse_curl_command
from .executor import execute_interface, execute_adhoc
from .script_executor import execute_assertion_script
from .chain_executor import execute_chain
from .permissions import ProjectResourcePermission, can_edit, can_manage, can_own


def ensure_default_project(user):
    """Ensure every authenticated user has at least one project."""
    membership = ProjectMember.objects.filter(user=user).select_related('project').order_by('id').first()
    if membership:
        return membership.project
    project = Project.objects.create(name='默认项目', description='系统自动创建的默认项目', created_by=user)
    ProjectMember.objects.create(project=project, user=user, role=ProjectMember.ROLE_OWNER)
    return project


def get_user_projects(user):
    if user.is_superuser:
        return Project.objects.all()
    return Project.objects.filter(members__user=user).distinct()


class ProjectScopedMixin:
    """Helpers for resources that belong to a project."""

    project_field = 'project'

    def get_current_project(self):
        project_id = (
            self.request.query_params.get('project')
            or self.request.query_params.get('project_id')
            or self.request.data.get('project')
            or self.request.data.get('project_id')
            or self.request.headers.get('X-Project-Id')
        )
        projects = get_user_projects(self.request.user)
        if project_id:
            try:
                return projects.get(id=project_id)
            except (Project.DoesNotExist, ValueError, TypeError):
                return None
        return ensure_default_project(self.request.user)

    def filter_by_project(self, qs):
        projects = get_user_projects(self.request.user)
        project = self.get_current_project()
        if project:
            return qs.filter(project=project)
        return qs.filter(project__in=projects)

    def perform_create(self, serializer):
        project = self.get_current_project()
        if not project or not can_edit(self.request.user, project):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('没有项目编辑权限')
        serializer.save(project=project, created_by=self.request.user)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_user_projects(self.request.user).prefetch_related('members')

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        ProjectMember.objects.get_or_create(
            project=project,
            user=self.request.user,
            defaults={'role': ProjectMember.ROLE_OWNER},
        )

    def perform_update(self, serializer):
        if not can_manage(self.request.user, self.get_object()):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('没有项目管理权限')
        serializer.save()

    def perform_destroy(self, instance):
        from rest_framework.exceptions import PermissionDenied
        if instance.is_default_project:
            raise PermissionDenied('默认项目不能删除')
        if not can_own(self.request.user, instance):
            raise PermissionDenied('只有 Owner 可以删除项目')
        instance.delete()


    def _owner_count(self, project):
        return project.members.filter(role=ProjectMember.ROLE_OWNER).count()

    def _ensure_can_change_member(self, request, project):
        if not can_manage(request.user, project):
            return Response({'detail': '没有项目管理权限'}, status=status.HTTP_403_FORBIDDEN)
        return None

    @action(detail=True, methods=['get'], url_path='members')
    def members(self, request, pk=None):
        project = self.get_object()
        if not can_manage(request.user, project):
            return Response({'detail': '没有项目管理权限'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProjectMemberSerializer(project.members.select_related('user'), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='members/invite')
    def invite_member(self, request, pk=None):
        project = self.get_object()
        denied = self._ensure_can_change_member(request, project)
        if denied:
            return denied

        serializer = ProjectMemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        role = serializer.validated_data['role']
        member, created = ProjectMember.objects.get_or_create(
            project=project,
            user=user,
            defaults={'role': role},
        )
        if not created:
            member.role = role
            member.save(update_fields=['role'])
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='members/(?P<member_id>[^/.]+)/role')
    def update_member_role(self, request, pk=None, member_id=None):
        project = self.get_object()
        denied = self._ensure_can_change_member(request, project)
        if denied:
            return denied

        try:
            member = project.members.select_related('user').get(id=member_id)
        except ProjectMember.DoesNotExist:
            return Response({'detail': '成员不存在'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProjectMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data['role']
        if member.role == ProjectMember.ROLE_OWNER and new_role != ProjectMember.ROLE_OWNER and self._owner_count(project) <= 1:
            return Response({'detail': '不能降级最后一个 Owner'}, status=status.HTTP_400_BAD_REQUEST)
        member.role = new_role
        member.save(update_fields=['role'])
        return Response(ProjectMemberSerializer(member).data)

    @action(detail=True, methods=['delete'], url_path='members/(?P<member_id>[^/.]+)')
    def remove_member(self, request, pk=None, member_id=None):
        project = self.get_object()
        denied = self._ensure_can_change_member(request, project)
        if denied:
            return denied

        try:
            member = project.members.get(id=member_id)
        except ProjectMember.DoesNotExist:
            return Response({'detail': '成员不存在'}, status=status.HTTP_404_NOT_FOUND)
        if member.role == ProjectMember.ROLE_OWNER and self._owner_count(project) <= 1:
            return Response({'detail': '不能移除最后一个 Owner'}, status=status.HTTP_400_BAD_REQUEST)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class EnvironmentViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """环境变量 CRUD"""
    serializer_class = EnvironmentSerializer
    permission_classes = [IsAuthenticated, ProjectResourcePermission]

    def get_queryset(self):
        return self.filter_by_project(Environment.objects.all())


class ApiGroupViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """接口分组 CRUD"""
    serializer_class = ApiGroupSerializer
    permission_classes = [IsAuthenticated, ProjectResourcePermission]

    def get_queryset(self):
        return self.filter_by_project(ApiGroup.objects.all())


class ApiInterfaceViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """接口 CRUD + 解析cURL + 在线调试"""
    permission_classes = [IsAuthenticated, ProjectResourcePermission]

    def get_queryset(self):
        qs = self.filter_by_project(ApiInterface.objects.all()).select_related('group', 'project')
        # 支持按分组、协议、方法筛选
        group = self.request.query_params.get('group')
        if group:
            qs = qs.filter(group_id=group)
        protocol = self.request.query_params.get('protocol')
        if protocol:
            qs = qs.filter(protocol=protocol)
        method = self.request.query_params.get('method')
        if method:
            qs = qs.filter(method=method)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiInterfaceListSerializer
        return ApiInterfaceDetailSerializer

    @action(detail=False, methods=['post'], url_path='parse-curl')
    def parse_curl(self, request):
        """解析 cURL 命令，返回结构化数据（不保存）"""
        serializer = CurlParseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = parse_curl_command(serializer.validated_data['curl_command'])
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CurlParseResultSerializer(result).data)

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        """调试已保存的接口（支持 environment_id）"""
        interface = self.get_object()
        env_vars = self._get_env_vars(request)
        result = execute_interface(interface, request.user, env_vars=env_vars)
        return Response(DebugResultSerializer(result).data)

    @action(detail=False, methods=['post'], url_path='execute')
    def execute_adhoc(self, request):
        """调试临时请求（不保存接口，支持 environment_id）"""
        serializer = DebugExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        env_vars = self._get_env_vars(request)
        result = execute_adhoc(serializer.validated_data, request.user, env_vars=env_vars)
        return Response(DebugResultSerializer(result).data)

    def _get_env_vars(self, request):
        """从请求中获取环境配置；未选择环境时返回 None，保持原请求行为。"""
        env_id = request.data.get('environment_id')
        if env_id:
            try:
                project = self.get_current_project()
                qs = Environment.objects.filter(id=env_id)
                if project:
                    qs = qs.filter(project=project)
                else:
                    qs = qs.filter(project__in=get_user_projects(request.user))
                return qs.get()
            except Environment.DoesNotExist:
                return None
        env_vars = request.data.get('env_vars')
        if env_vars and isinstance(env_vars, (dict, list)):
            return env_vars
        return None

    @action(detail=False, methods=['post'], url_path='run-script')
    def run_script(self, request):
        """执行 Python 断言脚本"""
        serializer = ScriptAssertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = execute_assertion_script(
            script_code=data['script'],
            context=data.get('context', {}),
            timeout=data.get('timeout', 10),
        )
        return Response(result)

    @action(detail=False, methods=['post'], url_path='import-postman')
    def import_postman(self, request):
        """导入 Postman Collection v2.1 JSON"""
        collection = request.data.get('collection')
        if not collection:
            return Response({'detail': '缺少 collection 数据'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(collection, dict):
            return Response({'detail': 'collection 必须是 JSON 对象'}, status=status.HTTP_400_BAD_REQUEST)

        from .postman_parser import import_postman_collection
        try:
            project = self.get_current_project()
            if not project or not can_edit(request.user, project):
                return Response({'detail': '没有项目编辑权限'}, status=status.HTTP_403_FORBIDDEN)
            result = import_postman_collection(collection, request.user, project=project)
            return Response(result)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DebugResultViewSet(viewsets.ReadOnlyModelViewSet):
    """调试历史记录（只读）"""
    serializer_class = DebugResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DebugResult.objects.filter(project__in=get_user_projects(self.request.user)).select_related('interface', 'project')
        interface_id = self.request.query_params.get('interface_id')
        if interface_id:
            qs = qs.filter(interface_id=interface_id)
        return qs


class ChainViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """链路测试 CRUD + 执行"""
    permission_classes = [IsAuthenticated, ProjectResourcePermission]

    def get_queryset(self):
        qs = self.filter_by_project(Chain.objects.all())
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ChainListSerializer
        return ChainDetailSerializer

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        """执行链路（支持 environment_id）"""
        chain = self.get_object()
        env_vars = None
        env_id = request.data.get('environment_id')
        if env_id:
            try:
                env_vars = Environment.objects.get(id=env_id, project=chain.project)
            except Environment.DoesNotExist:
                env_vars = None
        else:
            env_vars = request.data.get('env_vars')
        result = execute_chain(chain, request.user, env_vars=env_vars)
        return Response(ChainResultSerializer(result).data)


class ChainResultViewSet(viewsets.ReadOnlyModelViewSet):
    """链路执行结果（只读）"""
    serializer_class = ChainResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ChainResult.objects.filter(project__in=get_user_projects(self.request.user)).select_related('chain', 'project')
        chain_id = self.request.query_params.get('chain_id')
        if chain_id:
            qs = qs.filter(chain_id=chain_id)
        return qs


# ============ 测试接口 ============


@api_view(['POST'])
@permission_classes([AllowAny])
def test_post(request):
    """测试 POST 接口 — 入参 id:int, name:string"""
    serializer = TestPostSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    return Response({
        'code': 0,
        'message': 'ok',
        'data': {
            'id': data['id'],
            'name': data['name'],
        },
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def test_rpc(request):
    """JSON-RPC 2.0 测试接口，用于验证 RPC 协议调试。"""
    payload = request.data if isinstance(request.data, dict) else {}
    request_id = payload.get('id', 1)
    method = payload.get('method', '')
    params = payload.get('params') or {}
    if not isinstance(params, dict):
        params = {}

    if method == 'note.get':
        note_id = params.get('id', 123)
        return Response({
            'jsonrpc': '2.0',
            'id': request_id,
            'result': {
                'code': 0,
                'message': 'ok',
                'data': {
                    'id': note_id,
                    'title': '示例笔记',
                    'content': '这是一条 JSON-RPC 示例响应',
                },
            },
        })

    if method == 'note.create':
        title = params.get('title') or params.get('name') or '新笔记'
        return Response({
            'jsonrpc': '2.0',
            'id': request_id,
            'result': {
                'code': 0,
                'message': 'ok',
                'data': {
                    'id': 456,
                    'title': title,
                    'content': params.get('content', ''),
                },
            },
        })

    return Response({
        'jsonrpc': '2.0',
        'id': request_id,
        'error': {
            'code': -32601,
            'message': 'Method not found',
        },
    })
