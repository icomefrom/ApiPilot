from rest_framework import serializers
from django.db.models import Q
from apps.authentication.models import User
from .models import ApiGroup, ApiInterface, DebugResult, Chain, ChainResult, Environment, Project, ProjectMember, MockRule


class ProjectMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = ProjectMember
        fields = ['id', 'project', 'user', 'username', 'email', 'role', 'joined_at']
        read_only_fields = ['project', 'user', 'username', 'email', 'joined_at']


class ProjectMemberInviteSerializer(serializers.Serializer):
    user = serializers.CharField(help_text='用户名或邮箱')
    role = serializers.ChoiceField(choices=ProjectMember.ROLE_CHOICES, default=ProjectMember.ROLE_VIEWER)

    def validate_user(self, value):
        user = User.objects.filter(Q(username=value) | Q(email=value)).first()
        if not user:
            raise serializers.ValidationError('用户不存在，请先让该用户注册')
        return user


class ProjectMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ProjectMember.ROLE_CHOICES)


class ProjectSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    members_count = serializers.IntegerField(source='members.count', read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'role', 'members_count', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'role', 'members_count']

    def get_role(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        if request.user.is_superuser:
            return ProjectMember.ROLE_OWNER
        membership = obj.members.filter(user=request.user).first()
        return membership.role if membership else None

    def validate_name(self, value):
        name = (value or '').strip()
        if not name:
            raise serializers.ValidationError('项目名称不能为空')
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            qs = Project.objects.filter(members__user=request.user, name=name)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError('项目名称已存在')
        return name


class ApiGroupSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ApiGroup
        fields = ['id', 'project', 'name', 'parent', 'sort_order', 'created_by', 'created_at']
        read_only_fields = ['project', 'created_by', 'created_at']


class ApiInterfaceListSerializer(serializers.ModelSerializer):
    """接口列表序列化器（精简字段）"""
    group_name = serializers.CharField(source='group.name', default='', read_only=True)

    class Meta:
        model = ApiInterface
        fields = ['id', 'project', 'name', 'protocol', 'method', 'url', 'group', 'group_name', 'updated_at']


class ApiInterfaceDetailSerializer(serializers.ModelSerializer):
    """接口详情序列化器（完整字段）"""
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ApiInterface
        fields = [
            'id', 'project', 'name', 'protocol', 'method', 'url',
            'headers', 'query_params', 'body_type', 'body',
            'assertions',
            'ws_message', 'rpc_method', 'rpc_service',
            'group', 'description',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['project', 'created_by', 'created_at', 'updated_at']

    def validate(self, data):
        is_partial = self.partial and self.instance
        protocol = data.get('protocol', self.instance.protocol if self.instance else 'http')
        if protocol == 'http':
            if is_partial:
                # PATCH 时仅校验显式传入的 method
                if 'method' in data and not data['method']:
                    raise serializers.ValidationError({'method': 'HTTP 协议必须指定请求方法'})
            else:
                if not data.get('method'):
                    raise serializers.ValidationError({'method': 'HTTP 协议必须指定请求方法'})
        if not is_partial and not data.get('url'):
            raise serializers.ValidationError({'url': '请求地址不能为空'})
        return data


class CurlParseSerializer(serializers.Serializer):
    """cURL 解析输入"""
    curl_command = serializers.CharField(required=True, help_text='cURL 命令字符串')


class CurlParseResultSerializer(serializers.Serializer):
    """cURL 解析输出"""
    method = serializers.CharField()
    url = serializers.CharField()
    headers = serializers.DictField()
    query_params = serializers.DictField()
    body_type = serializers.CharField()
    body = serializers.CharField()


class DebugExecuteSerializer(serializers.Serializer):
    """临时调试请求输入"""
    protocol = serializers.ChoiceField(choices=['http', 'websocket', 'rpc'], default='http')
    method = serializers.CharField(required=False, default='GET', allow_blank=True)
    url = serializers.CharField(required=True)
    headers = serializers.DictField(required=False, default=dict)
    query_params = serializers.DictField(required=False, default=dict)
    body_type = serializers.CharField(required=False, default='none', allow_blank=True)
    body = serializers.CharField(required=False, default='', allow_blank=True)
    ws_message = serializers.CharField(required=False, default='', allow_blank=True)
    assertions = serializers.ListField(required=False, default=list)
    rpc_method = serializers.CharField(required=False, default='', allow_blank=True)
    rpc_service = serializers.CharField(required=False, default='', allow_blank=True)
    timeout = serializers.IntegerField(required=False, default=30, min_value=1, max_value=120)


class DebugResultSerializer(serializers.ModelSerializer):
    """调试结果序列化器"""
    interface_name = serializers.CharField(source='interface.name', default=None, read_only=True)

    class Meta:
        model = DebugResult
        fields = [
            'id', 'project', 'interface', 'interface_name', 'protocol',
            'request_url', 'request_method', 'request_headers', 'request_body',
            'status_code', 'response_headers', 'response_body',
            'elapsed_ms', 'status', 'error_message', 'created_at',
        ]
        read_only_fields = fields


class ScriptAssertSerializer(serializers.Serializer):
    """脚本断言执行输入"""
    script = serializers.CharField(required=True, help_text='Python 断言脚本代码')
    context = serializers.DictField(required=False, default=dict, help_text='响应上下文')
    timeout = serializers.IntegerField(
        required=False, default=10, min_value=1, max_value=30,
        help_text='执行超时(秒)',
    )


# ============ 环境变量序列化器 ============


class EnvironmentSerializer(serializers.ModelSerializer):
    """环境变量序列化器。敏感认证值默认脱敏返回。"""
    MASKED_VALUE = '******'
    SENSITIVE_KEYWORDS = (
        'token', 'secret', 'password', 'passwd', 'pwd', 'apikey', 'api_key',
        'access_key', 'private_key', 'authorization', 'cookie', 'session',
    )

    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    auth_token = serializers.CharField(required=False, allow_blank=True, write_only=True)
    auth_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    auth_token_masked = serializers.SerializerMethodField()
    auth_password_masked = serializers.SerializerMethodField()

    class Meta:
        model = Environment
        fields = [
            'id', 'project', 'name',
            'base_url', 'ws_base_url', 'rpc_base_url',
            'auth_type', 'auth_header', 'auth_token', 'auth_token_masked',
            'auth_username', 'auth_password', 'auth_password_masked',
            'variables', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['project', 'created_by', 'created_at', 'updated_at', 'auth_token_masked', 'auth_password_masked']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['variables'] = self._mask_variables(data.get('variables'))
        return data

    def get_auth_token_masked(self, obj):
        return self.MASKED_VALUE if obj.auth_token else ''

    def get_auth_password_masked(self, obj):
        return self.MASKED_VALUE if obj.auth_password else ''

    def _clean_secret_value(self, attrs, field_name):
        if field_name not in attrs:
            return
        value = attrs.get(field_name)
        if self.instance and value in ('', self.MASKED_VALUE, None):
            attrs.pop(field_name, None)

    def validate(self, attrs):
        self._clean_secret_value(attrs, 'auth_token')
        self._clean_secret_value(attrs, 'auth_password')
        if self.instance and 'variables' in attrs:
            attrs['variables'] = self._merge_masked_variables(attrs.get('variables') or [])
        return attrs

    def _is_sensitive_key(self, key):
        normalized = str(key or '').lower()
        return any(keyword in normalized for keyword in self.SENSITIVE_KEYWORDS)

    def _mask_variables(self, variables):
        if isinstance(variables, list):
            result = []
            for item in variables:
                if not isinstance(item, dict):
                    result.append(item)
                    continue
                copied = dict(item)
                if self._is_sensitive_key(copied.get('key')) and copied.get('value'):
                    copied['value'] = self.MASKED_VALUE
                result.append(copied)
            return result
        if isinstance(variables, dict):
            return {
                key: self.MASKED_VALUE if self._is_sensitive_key(key) and value else value
                for key, value in variables.items()
            }
        return variables

    def _merge_masked_variables(self, variables):
        existing = getattr(self.instance, 'variables', None) or []
        existing_by_key = {}
        if isinstance(existing, list):
            existing_by_key = {
                item.get('key'): item.get('value')
                for item in existing
                if isinstance(item, dict) and item.get('key')
            }
        elif isinstance(existing, dict):
            existing_by_key = existing

        if isinstance(variables, list):
            result = []
            for item in variables:
                if not isinstance(item, dict):
                    result.append(item)
                    continue
                copied = dict(item)
                key = copied.get('key')
                if key and copied.get('value') == self.MASKED_VALUE:
                    copied['value'] = existing_by_key.get(key, '')
                result.append(copied)
            return result
        if isinstance(variables, dict):
            return {
                key: existing_by_key.get(key, '') if value == self.MASKED_VALUE else value
                for key, value in variables.items()
            }
        return variables


# ============ 链路测试序列化器 ============


class ChainListSerializer(serializers.ModelSerializer):
    """链路列表序列化器（精简字段）"""

    class Meta:
        model = Chain
        fields = ['id', 'project', 'name', 'status', 'updated_at']


class ChainDetailSerializer(serializers.ModelSerializer):
    """链路详情序列化器（完整字段）"""
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Chain
        fields = [
            'id', 'project', 'name', 'description',
            'nodes', 'edges', 'globals',
            'status',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['project', 'created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', None))
        if status == Chain.STATUS_READY:
            nodes = attrs.get('nodes', getattr(self.instance, 'nodes', []) or [])
            start_count = sum(1 for node in nodes if isinstance(node, dict) and node.get('type') == 'start')
            end_count = sum(1 for node in nodes if isinstance(node, dict) and node.get('type') == 'end')
            if start_count != 1 or end_count != 1:
                raise serializers.ValidationError({
                    'nodes': '链路必须且只能包含一个开始节点和一个结束节点'
                })
        return attrs


class ChainResultSerializer(serializers.ModelSerializer):
    """链路执行结果序列化器"""
    chain_name = serializers.CharField(source='chain.name', default=None, read_only=True)

    class Meta:
        model = ChainResult
        fields = [
            'id', 'project', 'chain', 'chain_name',
            'status', 'step_results',
            'started_at', 'finished_at', 'error_message',
            'created_by',
        ]
        read_only_fields = fields


# ============ Mock 规则序列化器 ============


class MockRuleSerializer(serializers.ModelSerializer):
    """Mock 规则序列化器"""
    interface_name = serializers.CharField(source='interface.name', default='', read_only=True)
    interface_method = serializers.CharField(source='interface.method', default='', read_only=True)
    interface_url = serializers.CharField(source='interface.url', default='', read_only=True)

    class Meta:
        model = MockRule
        fields = [
            'id', 'interface', 'interface_name', 'interface_method', 'interface_url',
            'enabled', 'status_code', 'response_headers', 'response_body',
            'delay_ms', 'scenario', 'content_type', 'response_mode',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


# ============ 测试接口序列化器 ============


class TestPostSerializer(serializers.Serializer):
    """测试 POST 接口入参"""
    id = serializers.IntegerField(help_text='整数 ID')
    name = serializers.CharField(help_text='名称')
