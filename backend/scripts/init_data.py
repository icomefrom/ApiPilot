"""
初始化数据脚本：创建管理员账号和演示接口数据。
脚本设计为幂等执行，适合 Docker Compose 每次启动时运行。
"""
import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.authentication.models import User
from apps.api_debug.models import ApiGroup, ApiInterface, Chain, Environment, Project, ProjectMember


def create_superuser():
    """创建超级管理员账号。"""
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')

    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'is_staff': True, 'is_superuser': True},
    )
    if created:
        user.set_password(password)
        user.save(update_fields=['password'])
        print(f'超级管理员账号创建成功: {username} / {password}')
    else:
        changed = False
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            changed = True
        if email and user.email != email:
            user.email = email
            changed = True
        if changed:
            user.save()
        print(f'超级管理员账号已存在: {username}')
    return user


def ensure_default_project(user):
    membership = ProjectMember.objects.filter(user=user).select_related('project').order_by('id').first()
    if membership:
        return membership.project
    project = Project.objects.create(name='默认项目', description='系统自动创建的默认项目', created_by=user)
    ProjectMember.objects.create(project=project, user=user, role=ProjectMember.ROLE_OWNER)
    print(f'默认项目创建成功: {project.name}')
    return project


def create_sample_data(user):
    """创建新用户上手所需的示例环境、分组、接口和链路。"""
    project = ensure_default_project(user)

    if os.environ.get('LOAD_SAMPLE_DATA', 'True').lower() != 'true':
        print('已跳过示例数据初始化：LOAD_SAMPLE_DATA != True')
        return

    env, env_created = Environment.objects.get_or_create(
        name='本地演示环境',
        project=project,
        created_by=user,
        defaults={
            'base_url': 'http://backend:8000',
            'variables': [
                {'key': 'base_url', 'value': 'http://backend:8000', 'description': 'Docker 内部后端地址'},
                {'key': 'demo_name', 'value': 'Bug Shoot', 'description': '示例请求名称'},
            ],
        },
    )
    print(('已创建' if env_created else '已存在') + f'示例环境: {env.name}')

    group, group_created = ApiGroup.objects.get_or_create(
        name='示例接口',
        project=project,
        created_by=user,
        defaults={'sort_order': 10},
    )
    print(('已创建' if group_created else '已存在') + f'接口分组: {group.name}')

    en_group, en_group_created = ApiGroup.objects.get_or_create(
        name='Sample APIs',
        project=project,
        created_by=user,
        defaults={'sort_order': 20},
    )
    print(('已创建' if en_group_created else '已存在') + f'接口分组: {en_group.name}')

    ping, ping_created = ApiInterface.objects.get_or_create(
        name='示例 POST：回显参数',
        project=project,
        created_by=user,
        defaults={
            'group': group,
            'protocol': ApiInterface.PROTOCOL_HTTP,
            'method': 'POST',
            'url': '{{env.base_url}}/api/debug/test-post/',
            'headers': {'Content-Type': 'application/json'},
            'body_type': 'json',
            'body': '{"id": 1, "name": "{{env.demo_name}}"}',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.data.name', 'operator': 'contains', 'expected': 'Bug'},
            ],
            'description': '内置演示接口，可用于验证请求、环境变量和 JSONPath 断言。',
        },
    )
    if ping.project_id != project.id:
        ping.project = project
        ping.save(update_fields=['project', 'updated_at'])
    if group.project_id != project.id:
        group.project = project
        group.save(update_fields=['project'])
    if env.project_id != project.id:
        env.project = project
        env.save(update_fields=['project', 'updated_at'])

    if not ping_created and ping.url != '{{env.base_url}}/api/debug/test-post/':
        ping.url = '{{env.base_url}}/api/debug/test-post/'
        ping.save(update_fields=['url', 'updated_at'])
        print(f'已修正示例接口 URL: {ping.name}')
    print(('已创建' if ping_created else '已存在') + f'示例接口: {ping.name}')

    rpc, rpc_created = ApiInterface.objects.get_or_create(
        name='示例 RPC：获取笔记',
        project=project,
        created_by=user,
        defaults={
            'group': group,
            'protocol': ApiInterface.PROTOCOL_RPC,
            'method': 'POST',
            'url': '{{env.base_url}}/api/debug/test-rpc/',
            'headers': {'Content-Type': 'application/json'},
            'body_type': 'json',
            'body': '{"id": 123}',
            'rpc_service': 'note',
            'rpc_method': 'note.get',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.result.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.result.data.id', 'operator': 'equals', 'expected': '123'},
            ],
            'description': '内置 JSON-RPC 2.0 演示接口，可用于验证 RPC 协议调试和 JSONPath 断言。',
        },
    )
    if not rpc_created:
        changed_fields = []
        if rpc.url != '{{env.base_url}}/api/debug/test-rpc/':
            rpc.url = '{{env.base_url}}/api/debug/test-rpc/'
            changed_fields.append('url')
        if rpc.protocol != ApiInterface.PROTOCOL_RPC:
            rpc.protocol = ApiInterface.PROTOCOL_RPC
            changed_fields.append('protocol')
        if rpc.rpc_method != 'note.get':
            rpc.rpc_method = 'note.get'
            changed_fields.append('rpc_method')
        if rpc.rpc_service != 'note':
            rpc.rpc_service = 'note'
            changed_fields.append('rpc_service')
        if changed_fields:
            changed_fields.append('updated_at')
            rpc.save(update_fields=changed_fields)
            print(f'已修正示例 RPC 接口: {rpc.name}')
    print(('已创建' if rpc_created else '已存在') + f'示例 RPC 接口: {rpc.name}')

    order_create, order_create_created = ApiInterface.objects.get_or_create(
        name='创建订单',
        project=project,
        created_by=user,
        defaults={
            'group': group,
            'protocol': ApiInterface.PROTOCOL_HTTP,
            'method': 'POST',
            'url': '{{env.base_url}}/api/debug/demo/orders/',
            'headers': {'Content-Type': 'application/json'},
            'body_type': 'json',
            'body': '{"sku": "SKU-1001", "quantity": 2, "customer_name": "Alice", "unit_price": 99.9}',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
            ],
            'description': '电商订单 Demo：创建订单并返回订单号、订单状态、金额等业务字段。',
        },
    )
    _sync_interface(
        order_create,
        group=group,
        protocol=ApiInterface.PROTOCOL_HTTP,
        method='POST',
        url='{{env.base_url}}/api/debug/demo/orders/',
        headers={'Content-Type': 'application/json'},
        body_type='json',
        body='{"sku": "SKU-1001", "quantity": 2, "customer_name": "Alice", "unit_price": 99.9}',
        assertions=[
            {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
            {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
        ],
        description='电商订单 Demo：创建订单并返回订单号、订单状态、金额等业务字段。',
    )
    print(('已创建' if order_create_created else '已存在') + f'示例接口: {order_create.name}')

    order_detail, order_detail_created = ApiInterface.objects.get_or_create(
        name='查询订单',
        project=project,
        created_by=user,
        defaults={
            'group': group,
            'protocol': ApiInterface.PROTOCOL_HTTP,
            'method': 'GET',
            'url': '{{env.base_url}}/api/debug/demo/orders/detail/',
            'query_params': {'order_id': '{{vars.order_id}}'},
            'headers': {},
            'body_type': 'none',
            'body': '',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
            ],
            'description': '电商订单 Demo：根据订单号查询订单详情，用于演示上游变量传递和订单状态断言。',
        },
    )
    _sync_interface(
        order_detail,
        group=group,
        protocol=ApiInterface.PROTOCOL_HTTP,
        method='GET',
        url='{{env.base_url}}/api/debug/demo/orders/detail/',
        query_params={'order_id': '{{vars.order_id}}'},
        headers={},
        body_type='none',
        body='',
        assertions=[
            {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
            {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
        ],
        description='电商订单 Demo：根据订单号查询订单详情，用于演示上游变量传递和订单状态断言。',
    )
    print(('已创建' if order_detail_created else '已存在') + f'示例接口: {order_detail.name}')

    order_create_en, order_create_en_created = ApiInterface.objects.get_or_create(
        name='Create order',
        project=project,
        created_by=user,
        defaults={
            'group': en_group,
            'protocol': ApiInterface.PROTOCOL_HTTP,
            'method': 'POST',
            'url': '{{env.base_url}}/api/debug/demo/orders/',
            'headers': {'Content-Type': 'application/json'},
            'body_type': 'json',
            'body': '{"sku": "SKU-1001", "quantity": 2, "customer_name": "Alice", "unit_price": 99.9}',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
            ],
            'description': 'E-commerce order demo: create an order and return order ID, order status, amount, and customer fields.',
        },
    )
    _sync_interface(
        order_create_en,
        group=en_group,
        protocol=ApiInterface.PROTOCOL_HTTP,
        method='POST',
        url='{{env.base_url}}/api/debug/demo/orders/',
        headers={'Content-Type': 'application/json'},
        body_type='json',
        body='{"sku": "SKU-1001", "quantity": 2, "customer_name": "Alice", "unit_price": 99.9}',
        assertions=[
            {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
            {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
        ],
        description='E-commerce order demo: create an order and return order ID, order status, amount, and customer fields.',
    )
    print(('已创建' if order_create_en_created else '已存在') + f'示例接口: {order_create_en.name}')

    order_detail_en, order_detail_en_created = ApiInterface.objects.get_or_create(
        name='Query order',
        project=project,
        created_by=user,
        defaults={
            'group': en_group,
            'protocol': ApiInterface.PROTOCOL_HTTP,
            'method': 'GET',
            'url': '{{env.base_url}}/api/debug/demo/orders/detail/',
            'query_params': {'order_id': '{{vars.order_id}}'},
            'headers': {},
            'body_type': 'none',
            'body': '',
            'assertions': [
                {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
                {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
            ],
            'description': 'E-commerce order demo: query order details by order ID and verify the final order status.',
        },
    )
    _sync_interface(
        order_detail_en,
        group=en_group,
        protocol=ApiInterface.PROTOCOL_HTTP,
        method='GET',
        url='{{env.base_url}}/api/debug/demo/orders/detail/',
        query_params={'order_id': '{{vars.order_id}}'},
        headers={},
        body_type='none',
        body='',
        assertions=[
            {'type': 'jsonpath', 'jsonpath': '$.body.code', 'operator': 'equals', 'expected': '0'},
            {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
        ],
        description='E-commerce order demo: query order details by order ID and verify the final order status.',
    )
    print(('已创建' if order_detail_en_created else '已存在') + f'示例接口: {order_detail_en.name}')

    chain_nodes = [
        {
            'id': 'sample_post_node',
            'type': 'interface',
            'position': {'x': 80, 'y': 120},
            'data': {
                'label': '调用示例 POST',
                'interface_id': ping.id,
                'overrides': {},
                'extractions': [
                    {'key': 'echo_name', 'jsonpath': '$.body.data.name'},
                ],
                'assertions': [
                    {'type': 'jsonpath', 'jsonpath': '$.body.message', 'operator': 'equals', 'expected': 'ok'},
                ],
                'retry_count': 0,
                'retry_interval': 1,
            },
        },
        {
            'id': 'sample_script_node',
            'type': 'script',
            'position': {'x': 380, 'y': 120},
            'data': {
                'label': '校验提取变量',
                'script': "assert vars.get('echo_name') == 'Bug Shoot'",
                'timeout': 10,
            },
        },
    ]
    chain_edges = [
        {'id': 'sample_edge_post_script', 'source': 'sample_post_node', 'target': 'sample_script_node', 'sourceHandle': 'out'},
    ]
    chain, chain_created = Chain.objects.get_or_create(
        name='示例链路：接口调用与变量提取',
        project=project,
        created_by=user,
        defaults={
            'description': '演示如何串联接口节点和脚本节点，并从响应中提取变量。',
            'nodes': chain_nodes,
            'edges': chain_edges,
            'globals': [{'key': 'project', 'value': 'bug-shoot'}],
            'status': Chain.STATUS_READY,
        },
    )
    if chain.project_id != project.id:
        chain.project = project
        chain.save(update_fields=['project', 'updated_at'])
    if not chain_created and not chain.nodes:
        chain.nodes = chain_nodes
        chain.edges = chain_edges
        chain.status = Chain.STATUS_READY
        chain.save(update_fields=['nodes', 'edges', 'status', 'updated_at'])
    print(('已创建' if chain_created else '已存在') + f'示例链路: {chain.name}')

    order_chain_nodes = [
        {
            'id': 'demo_create_order',
            'type': 'interface',
            'position': {'x': 80, 'y': 180},
            'data': {
                'label': '创建订单',
                'interface_id': order_create.id,
                'overrides': {},
                'extractions': [
                    {'var_name': 'order_id', 'jsonpath': '$.body.data.order_id'},
                ],
                'assertions': [
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_id', 'operator': 'exists', 'expected': True},
                ],
                'retry_count': 0,
                'retry_interval': 1,
            },
        },
        {
            'id': 'demo_query_order',
            'type': 'interface',
            'position': {'x': 440, 'y': 180},
            'data': {
                'label': '查询订单并断言状态',
                'interface_id': order_detail.id,
                'overrides': {
                    'query_params': {'order_id': '{{vars.order_id}}'},
                },
                'extractions': [],
                'assertions': [
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_id', 'operator': 'exists', 'expected': True},
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
                ],
                'retry_count': 0,
                'retry_interval': 1,
            },
        },
    ]
    order_chain_edges = [
        {'id': 'demo_order_edge', 'source': 'demo_create_order', 'target': 'demo_query_order', 'sourceHandle': 'out'},
    ]
    order_chain, order_chain_created = Chain.objects.get_or_create(
        name='示例链路：创建订单并校验状态',
        project=project,
        created_by=user,
        defaults={
            'description': '演示“创建订单 -> 提取 order_id -> 查询订单 -> 断言订单状态”的 Agent 编排典型场景。',
            'nodes': order_chain_nodes,
            'edges': order_chain_edges,
            'globals': [],
            'status': Chain.STATUS_READY,
        },
    )
    if order_chain.project_id != project.id:
        order_chain.project = project
        order_chain.save(update_fields=['project', 'updated_at'])
    if not order_chain_created:
        order_chain.nodes = order_chain_nodes
        order_chain.edges = order_chain_edges
        order_chain.description = '演示“创建订单 -> 提取 order_id -> 查询订单 -> 断言订单状态”的 Agent 编排典型场景。'
        order_chain.status = Chain.STATUS_READY
        order_chain.save(update_fields=['nodes', 'edges', 'description', 'status', 'updated_at'])
    print(('已创建' if order_chain_created else '已存在') + f'示例链路: {order_chain.name}')

    order_chain_en_nodes = [
        {
            'id': 'demo_en_create_order',
            'type': 'interface',
            'position': {'x': 80, 'y': 180},
            'data': {
                'label': 'Create order',
                'interface_id': order_create_en.id,
                'overrides': {},
                'extractions': [
                    {'var_name': 'order_id', 'jsonpath': '$.body.data.order_id'},
                ],
                'assertions': [
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'created'},
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_id', 'operator': 'exists', 'expected': True},
                ],
                'retry_count': 0,
                'retry_interval': 1,
            },
        },
        {
            'id': 'demo_en_query_order',
            'type': 'interface',
            'position': {'x': 440, 'y': 180},
            'data': {
                'label': 'Query order and assert status',
                'interface_id': order_detail_en.id,
                'overrides': {
                    'query_params': {'order_id': '{{vars.order_id}}'},
                },
                'extractions': [],
                'assertions': [
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_id', 'operator': 'exists', 'expected': True},
                    {'type': 'jsonpath', 'jsonpath': '$.body.data.order_status', 'operator': 'equals', 'expected': 'paid'},
                ],
                'retry_count': 0,
                'retry_interval': 1,
            },
        },
    ]
    order_chain_en_edges = [
        {'id': 'demo_en_order_edge', 'source': 'demo_en_create_order', 'target': 'demo_en_query_order', 'sourceHandle': 'out'},
    ]
    order_chain_en, order_chain_en_created = Chain.objects.get_or_create(
        name='Sample chain: create order and verify status',
        project=project,
        created_by=user,
        defaults={
            'description': 'Demonstrates Create order -> extract order_id -> Query order -> assert order_status is paid.',
            'nodes': order_chain_en_nodes,
            'edges': order_chain_en_edges,
            'globals': [],
            'status': Chain.STATUS_READY,
        },
    )
    if order_chain_en.project_id != project.id:
        order_chain_en.project = project
        order_chain_en.save(update_fields=['project', 'updated_at'])
    if not order_chain_en_created:
        order_chain_en.nodes = order_chain_en_nodes
        order_chain_en.edges = order_chain_en_edges
        order_chain_en.description = 'Demonstrates Create order -> extract order_id -> Query order -> assert order_status is paid.'
        order_chain_en.status = Chain.STATUS_READY
        order_chain_en.save(update_fields=['nodes', 'edges', 'description', 'status', 'updated_at'])
    print(('已创建' if order_chain_en_created else '已存在') + f'示例链路: {order_chain_en.name}')


def _sync_interface(interface, **fields):
    changed = []
    for key, value in fields.items():
        if getattr(interface, key) != value:
            setattr(interface, key, value)
            changed.append(key)
    if changed:
        changed.append('updated_at')
        interface.save(update_fields=changed)


def main():
    print('=' * 50)
    print('开始初始化数据...')
    print('=' * 50)
    user = create_superuser()
    create_sample_data(user)
    print('=' * 50)
    print('数据初始化完成！')
    print('=' * 50)


if __name__ == '__main__':
    main()
