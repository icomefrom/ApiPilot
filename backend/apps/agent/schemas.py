OPERATION_ALIASES = {
    'login': ['登录', '认证', '获取token', '获取 token', 'sign in', 'login'],
    'logout': ['退出', '登出', 'logout'],
    'create': ['创建', '新建', '新增', '生成', '发起', 'create', 'add'],
    'read': ['查询', '查看', '获取', '读取', '详情', 'read', 'get'],
    'search': ['搜索', '检索', '筛选', '查找', 'search', 'find'],
    'list': ['列表', '分页', 'list'],
    'update': ['修改', '更新', '编辑', '变更', 'update', 'edit'],
    'delete': ['删除', '移除', 'delete', 'remove'],
    'submit': ['提交', '上报', '申请', '递交', 'submit', 'apply'],
    'approve': ['审批', '审核通过', '通过', '同意', 'approve', 'pass'],
    'reject': ['驳回', '拒绝', '审核拒绝', 'reject'],
    'cancel': ['取消', '撤销', '作废', 'cancel'],
    'upload': ['上传', '导入', 'upload', 'import'],
    'download': ['下载', '导出', 'download', 'export'],
    'execute': ['执行', '运行', '触发', 'execute', 'run', 'trigger'],
    'verify': ['校验', '验证', '断言', '检查', 'verify', 'check', 'assert'],
}

READ_OPERATIONS = {'read', 'search', 'list', 'download', 'verify'}
WRITE_OPERATIONS = {'create', 'update', 'submit', 'upload', 'execute'}
HIGH_RISK_OPERATIONS = {'delete', 'approve', 'reject', 'cancel'}

METHOD_HINTS = {
    'read': {'GET'},
    'search': {'GET', 'POST'},
    'list': {'GET'},
    'download': {'GET', 'POST'},
    'verify': {'GET', 'POST'},
    'create': {'POST'},
    'submit': {'POST'},
    'approve': {'POST', 'PUT', 'PATCH'},
    'reject': {'POST', 'PUT', 'PATCH'},
    'cancel': {'POST', 'PUT', 'PATCH', 'DELETE'},
    'update': {'PUT', 'PATCH', 'POST'},
    'delete': {'DELETE', 'POST'},
    'upload': {'POST', 'PUT'},
    'execute': {'POST'},
    'login': {'POST'},
    'logout': {'POST'},
}
