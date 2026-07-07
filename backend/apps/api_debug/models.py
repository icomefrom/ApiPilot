from django.db import models
from django.conf import settings


class Project(models.Model):
    """团队项目空间。"""
    name = models.CharField('项目名称', max_length=120)
    description = models.TextField('项目描述', blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='owned_projects', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'api_debug_project'
        verbose_name = '项目'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    @property
    def is_default_project(self):
        return self.name == '默认项目' and self.description in (
            '系统自动创建的默认项目',
            '迁移已有个人数据时自动创建的项目',
        )

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    """项目成员与角色。"""
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_EDITOR = 'editor'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_EDITOR, 'Editor'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members', verbose_name='项目')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='project_memberships', verbose_name='用户')
    role = models.CharField('角色', max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    joined_at = models.DateTimeField('加入时间', auto_now_add=True)

    class Meta:
        db_table = 'api_debug_project_member'
        verbose_name = '项目成员'
        verbose_name_plural = verbose_name
        unique_together = [('project', 'user')]
        ordering = ['project_id', 'id']

    def __str__(self):
        return f'{self.project} - {self.user} ({self.role})'


class ApiGroup(models.Model):
    """接口分组"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='api_groups', verbose_name='项目')
    name = models.CharField('分组名称', max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                               related_name='children', verbose_name='父分组')
    sort_order = models.IntegerField('排序', default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='api_groups', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'api_debug_group'
        verbose_name = '接口分组'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', '-id']

    def __str__(self):
        return self.name


class ApiInterface(models.Model):
    """API 接口定义"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='api_interfaces', verbose_name='项目')
    PROTOCOL_HTTP = 'http'
    PROTOCOL_WEBSOCKET = 'websocket'
    PROTOCOL_RPC = 'rpc'
    PROTOCOL_CHOICES = [
        (PROTOCOL_HTTP, 'HTTP'),
        (PROTOCOL_WEBSOCKET, 'WebSocket'),
        (PROTOCOL_RPC, 'RPC'),
    ]

    METHOD_CHOICES = [
        ('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'),
        ('DELETE', 'DELETE'), ('PATCH', 'PATCH'),
        ('HEAD', 'HEAD'), ('OPTIONS', 'OPTIONS'),
    ]

    BODY_TYPE_CHOICES = [
        ('json', 'JSON'), ('form', 'Form'), ('xml', 'XML'),
        ('raw', 'Raw'), ('none', 'None'),
    ]

    name = models.CharField('接口名称', max_length=200)
    protocol = models.CharField('协议类型', max_length=20, choices=PROTOCOL_CHOICES,
                                default=PROTOCOL_HTTP)
    method = models.CharField('请求方法', max_length=10, choices=METHOD_CHOICES,
                              blank=True, default='GET')
    url = models.CharField('请求地址', max_length=2048)

    # HTTP 相关
    headers = models.JSONField('请求头', default=dict, blank=True)
    query_params = models.JSONField('查询参数', default=dict, blank=True)
    body_type = models.CharField('请求体类型', max_length=20, choices=BODY_TYPE_CHOICES,
                                 blank=True, default='none')
    body = models.TextField('请求体', blank=True, default='')
    assertions = models.JSONField('断言规则', default=list, blank=True)

    # WebSocket 相关
    ws_message = models.TextField('WebSocket消息', blank=True, default='')

    # RPC 相关
    rpc_method = models.CharField('RPC方法名', max_length=200, blank=True, default='')
    rpc_service = models.CharField('RPC服务名', max_length=200, blank=True, default='')

    # 分组与描述
    group = models.ForeignKey(ApiGroup, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='interfaces', verbose_name='分组')
    description = models.TextField('描述', blank=True, default='')

    # 所属用户与时间
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='api_interfaces', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'api_debug_interface'
        verbose_name = 'API接口'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return f'{self.name} ({self.get_protocol_display()})'


class Chain(models.Model):
    """链路测试定义"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='chains', verbose_name='项目')
    STATUS_DRAFT = 'draft'
    STATUS_READY = 'ready'
    STATUS_CHOICES = [
        (STATUS_DRAFT, '草稿'),
        (STATUS_READY, '就绪'),
    ]

    name = models.CharField('链路名称', max_length=200)
    description = models.TextField('描述', blank=True, default='')
    nodes = models.JSONField('节点列表', default=list, blank=True)
    edges = models.JSONField('连线列表', default=list, blank=True)
    globals = models.JSONField('全局参数', default=list, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='chains', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'api_debug_chain'
        verbose_name = '链路测试'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name


class ChainResult(models.Model):
    """链路执行结果"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='chain_results', verbose_name='项目')
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_TIMEOUT = 'timeout'
    STATUS_CHOICES = [
        (STATUS_RUNNING, '运行中'),
        (STATUS_COMPLETED, '完成'),
        (STATUS_FAILED, '失败'),
        (STATUS_TIMEOUT, '超时'),
    ]

    chain = models.ForeignKey(Chain, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='results', verbose_name='关联链路')
    status = models.CharField('执行状态', max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    step_results = models.JSONField('步骤结果', default=list, blank=True)
    started_at = models.DateTimeField('开始时间', auto_now_add=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    error_message = models.TextField('错误信息', blank=True, default='')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='chain_results', verbose_name='执行人')

    class Meta:
        db_table = 'api_debug_chain_result'
        verbose_name = '链路结果'
        verbose_name_plural = verbose_name
        ordering = ['-id']


class Environment(models.Model):
    """环境变量配置"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='environments', verbose_name='项目')

    AUTH_TYPE_NONE = 'none'
    AUTH_TYPE_BEARER = 'bearer'
    AUTH_TYPE_API_KEY = 'api_key'
    AUTH_TYPE_BASIC = 'basic'
    AUTH_TYPE_CUSTOM = 'custom'
    AUTH_TYPE_CHOICES = [
        (AUTH_TYPE_NONE, '无认证'),
        (AUTH_TYPE_BEARER, 'Bearer Token'),
        (AUTH_TYPE_API_KEY, 'API Key'),
        (AUTH_TYPE_BASIC, 'Basic Auth'),
        (AUTH_TYPE_CUSTOM, '自定义 Header'),
    ]

    name = models.CharField('环境名称', max_length=100)
    base_url = models.CharField('HTTP基础地址', max_length=2048, blank=True, default='')
    ws_base_url = models.CharField('WebSocket基础地址', max_length=2048, blank=True, default='')
    rpc_base_url = models.CharField('RPC基础地址', max_length=2048, blank=True, default='')
    auth_type = models.CharField('认证类型', max_length=20, choices=AUTH_TYPE_CHOICES, default=AUTH_TYPE_NONE)
    auth_header = models.CharField('认证Header名', max_length=100, blank=True, default='Authorization')
    auth_token = models.TextField('认证Token/值', blank=True, default='')
    auth_username = models.CharField('Basic用户名', max_length=200, blank=True, default='')
    auth_password = models.TextField('Basic密码', blank=True, default='')
    variables = models.JSONField('环境变量', default=list, blank=True,
                                 help_text='键值对列表，如 [{"key": "base_url", "value": "http://..."}]')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='environments', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'api_debug_environment'
        verbose_name = '环境变量'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name


class DebugResult(models.Model):
    """调试执行结果"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='debug_results', verbose_name='项目')
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_TIMEOUT = 'timeout'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, '成功'),
        (STATUS_FAILED, '失败'),
        (STATUS_TIMEOUT, '超时'),
    ]

    interface = models.ForeignKey(ApiInterface, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='debug_results', verbose_name='关联接口')
    protocol = models.CharField('协议类型', max_length=20, choices=ApiInterface.PROTOCOL_CHOICES)
    request_url = models.CharField('请求地址', max_length=2048)
    request_method = models.CharField('请求方法', max_length=10, blank=True, default='')
    request_headers = models.JSONField('请求头', default=dict, blank=True)
    request_body = models.TextField('请求体', blank=True, default='')

    status_code = models.IntegerField('HTTP状态码', null=True, blank=True)
    response_headers = models.JSONField('响应头', default=dict, blank=True)
    response_body = models.TextField('响应体', blank=True, default='')
    elapsed_ms = models.IntegerField('耗时(ms)', null=True, blank=True)
    status = models.CharField('执行状态', max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField('错误信息', blank=True, default='')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='debug_results', verbose_name='执行人')
    created_at = models.DateTimeField('执行时间', auto_now_add=True)

    class Meta:
        db_table = 'api_debug_result'
        verbose_name = '调试结果'
        verbose_name_plural = verbose_name
        ordering = ['-id']