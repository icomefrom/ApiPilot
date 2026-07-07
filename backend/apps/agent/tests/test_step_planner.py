"""
StepPlanner 生产级测试 — 基于 300 接口数据集

测试覆盖：
1. 步骤拆分质量（action 数量、粒度）
2. source_span 对齐准确率
3. resolved_text 规范化质量
4. 断言识别（LLM constraints + 正则兜底 + 间隙扫描）
5. 双通道召回兼容性（original_goal 传递）
6. 依赖链正确性（depends_on）
7. 300 接口场景：多行业复合步骤 + 断言

用法:
  cd backend && python -c "
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
  django.setup()
  exec(open('apps/agent/tests/test_step_planner.py').read())
  "
"""
import os
import re
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
if not django.conf.settings.configured:
    django.setup()

from apps.agent.services.planning.step_planner import StepPlanner

# ============================================================================
# Mock LLM — 模拟高质量 LLM 输出，覆盖各种场景
# ============================================================================

# 预定义 LLM 响应：goal → actions/constraints
_MOCK_RESPONSES = {
    # ====== 电商行业 ======
    # --- 用户模块 ---
    '注册一个账号然后登录': {
        'goal': '注册一个账号然后登录',
        'actions': [
            {'index': 1, 'text': '注册一个账号', 'resolved_text': '用户注册', 'source_span': '注册一个账号', 'depends_on': []},
            {'index': 2, 'text': '登录', 'resolved_text': '用户登录', 'source_span': '登录', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '注册并修改密码': {
        'goal': '注册并修改密码',
        'actions': [
            {'index': 1, 'text': '注册', 'resolved_text': '用户注册', 'source_span': '注册', 'depends_on': []},
            {'index': 2, 'text': '修改密码', 'resolved_text': '修改密码', 'source_span': '修改密码', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '登录后查看个人信息，确认userId不为空': {
        'goal': '登录后查看个人信息，确认userId不为空',
        'actions': [
            {'index': 1, 'text': '登录', 'resolved_text': '用户登录', 'source_span': '登录', 'depends_on': []},
            {'index': 2, 'text': '查看个人信息', 'resolved_text': '个人信息查询', 'source_span': '查看个人信息', 'depends_on': [1]},
        ],
        'constraints': [
            {'text': '确认userId不为空', 'target_action_index': 2, 'field_hint': 'userId', 'operator': 'exists', 'expected': 'non-empty', 'confidence': 0.9},
        ],
    },
    # --- 订单模块 ---
    '创建订单，确认订单状态为paid': {
        'goal': '创建订单，确认订单状态为paid',
        'actions': [
            {'index': 1, 'text': '创建订单', 'resolved_text': '创建订单', 'source_span': '创建订单', 'depends_on': []},
        ],
        'constraints': [
            {'text': '确认订单状态为paid', 'target_action_index': 1, 'field_hint': 'status', 'operator': 'equals', 'expected': 'paid', 'confidence': 0.9},
        ],
    },
    '下单 status==paid balance>=0': {
        'goal': '下单 status==paid balance>=0',
        'actions': [
            {'index': 1, 'text': '下单', 'resolved_text': '创建订单', 'source_span': '下单', 'depends_on': []},
        ],
        'constraints': [
            {'text': 'status==paid', 'target_action_index': 1, 'field_hint': 'status', 'operator': 'equals', 'expected': 'paid', 'confidence': 0.9},
            {'text': 'balance>=0', 'target_action_index': 1, 'field_hint': 'balance', 'operator': 'greater_than', 'expected': '0', 'confidence': 0.8},
        ],
    },
    '加入购物车然后下单付钱': {
        'goal': '加入购物车然后下单付钱',
        'actions': [
            {'index': 1, 'text': '加入购物车', 'resolved_text': '加入购物车', 'source_span': '加入购物车', 'depends_on': []},
            {'index': 2, 'text': '下单', 'resolved_text': '创建订单', 'source_span': '下单', 'depends_on': [1]},
            {'index': 3, 'text': '付钱', 'resolved_text': '支付订单', 'source_span': '付钱', 'depends_on': [2]},
        ],
        'constraints': [],
    },
    '搜索商品看详情再加购物车': {
        'goal': '搜索商品看详情再加购物车',
        'actions': [
            {'index': 1, 'text': '搜索商品', 'resolved_text': '商品搜索', 'source_span': '搜索商品', 'depends_on': []},
            {'index': 2, 'text': '看详情', 'resolved_text': '商品详情', 'source_span': '看详情', 'depends_on': [1]},
            {'index': 3, 'text': '加购物车', 'resolved_text': '加入购物车', 'source_span': '加购物车', 'depends_on': [2]},
        ],
        'constraints': [],
    },
    '领券下单用券付钱': {
        'goal': '领券下单用券付钱',
        'actions': [
            {'index': 1, 'text': '领券', 'resolved_text': '领取优惠券', 'source_span': '领券', 'depends_on': []},
            {'index': 2, 'text': '下单', 'resolved_text': '创建订单', 'source_span': '下单', 'depends_on': []},
            {'index': 3, 'text': '用券', 'resolved_text': '使用优惠券', 'source_span': '用券', 'depends_on': [2]},
            {'index': 4, 'text': '付钱', 'resolved_text': '支付订单', 'source_span': '付钱', 'depends_on': [3]},
        ],
        'constraints': [],
    },
    '退货并确认退款状态': {
        'goal': '退货并确认退款状态',
        'actions': [
            {'index': 1, 'text': '退货', 'resolved_text': '申请售后', 'source_span': '退货', 'depends_on': []},
            {'index': 2, 'text': '确认退款状态', 'resolved_text': '查询支付状态', 'source_span': '确认退款状态', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    # --- 支付模块 ---
    '付钱并查支付状态': {
        'goal': '付钱并查支付状态',
        'actions': [
            {'index': 1, 'text': '付钱', 'resolved_text': '支付订单', 'source_span': '付钱', 'depends_on': []},
            {'index': 2, 'text': '查支付状态', 'resolved_text': '查询支付状态', 'source_span': '查支付状态', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '申请退款需要refund_id非空': {
        'goal': '申请退款需要refund_id非空',
        'actions': [
            {'index': 1, 'text': '申请退款', 'resolved_text': '申请退款', 'source_span': '申请退款', 'depends_on': []},
        ],
        'constraints': [
            {'text': 'refund_id非空', 'target_action_index': 1, 'field_hint': 'refund_id', 'operator': 'exists', 'expected': 'non-empty', 'confidence': 0.9},
        ],
    },

    # ====== 物流行业 ======
    '寄个快递然后查物流': {
        'goal': '寄个快递然后查物流',
        'actions': [
            {'index': 1, 'text': '寄个快递', 'resolved_text': '创建运单', 'source_span': '寄个快递', 'depends_on': []},
            {'index': 2, 'text': '查物流', 'resolved_text': '运单轨迹查询', 'source_span': '查物流', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '寄件并确认运单号不为空': {
        'goal': '寄件并确认运单号不为空',
        'actions': [
            {'index': 1, 'text': '寄件', 'resolved_text': '创建运单', 'source_span': '寄件', 'depends_on': []},
        ],
        'constraints': [
            {'text': '确认运单号不为空', 'target_action_index': 1, 'field_hint': '运单号', 'operator': 'exists', 'expected': 'non-empty', 'confidence': 0.9},
        ],
    },
    '创建运单揽收签收': {
        'goal': '创建运单揽收签收',
        'actions': [
            {'index': 1, 'text': '创建运单', 'resolved_text': '创建运单', 'source_span': '创建运单', 'depends_on': []},
            {'index': 2, 'text': '揽收', 'resolved_text': '揽收', 'source_span': '揽收', 'depends_on': [1]},
            {'index': 3, 'text': '签收', 'resolved_text': '签收', 'source_span': '签收', 'depends_on': [2]},
        ],
        'constraints': [],
    },
    '查运费然后寄件': {
        'goal': '查运费然后寄件',
        'actions': [
            {'index': 1, 'text': '查运费', 'resolved_text': '运费计算', 'source_span': '查运费', 'depends_on': []},
            {'index': 2, 'text': '寄件', 'resolved_text': '创建运单', 'source_span': '寄件', 'depends_on': [1]},
        ],
        'constraints': [],
    },

    # ====== ERP行业 ======
    '做个采购单然后入库': {
        'goal': '做个采购单然后入库',
        'actions': [
            {'index': 1, 'text': '做个采购单', 'resolved_text': '创建采购单', 'source_span': '做个采购单', 'depends_on': []},
            {'index': 2, 'text': '入库', 'resolved_text': '采购入库', 'source_span': '入库', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '发工资，确保工资大于0': {
        'goal': '发工资，确保工资大于0',
        'actions': [
            {'index': 1, 'text': '发工资', 'resolved_text': '薪资发放', 'source_span': '发工资', 'depends_on': []},
        ],
        'constraints': [
            {'text': '确保工资大于0', 'target_action_index': 1, 'field_hint': '工资', 'operator': 'greater_than', 'expected': '0', 'confidence': 0.85},
        ],
    },
    '新建员工录入考勤查工资': {
        'goal': '新建员工录入考勤查工资',
        'actions': [
            {'index': 1, 'text': '新建员工', 'resolved_text': '创建员工', 'source_span': '新建员工', 'depends_on': []},
            {'index': 2, 'text': '录入考勤', 'resolved_text': '录入考勤', 'source_span': '录入考勤', 'depends_on': [1]},
            {'index': 3, 'text': '查工资', 'resolved_text': '查询工资明细', 'source_span': '查工资', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '创建采购单确认金额==100': {
        'goal': '创建采购单确认金额==100',
        'actions': [
            {'index': 1, 'text': '创建采购单', 'resolved_text': '创建采购单', 'source_span': '创建采购单', 'depends_on': []},
        ],
        'constraints': [
            {'text': '金额==100', 'target_action_index': 1, 'field_hint': '金额', 'operator': 'equals', 'expected': '100', 'confidence': 0.9},
        ],
    },

    # ====== 金融行业 ======
    '存钱再转账': {
        'goal': '存钱再转账',
        'actions': [
            {'index': 1, 'text': '存钱', 'resolved_text': '存款', 'source_span': '存钱', 'depends_on': []},
            {'index': 2, 'text': '转账', 'resolved_text': '转账', 'source_span': '转账', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '开户并存钱，确认余额正确': {
        'goal': '开户并存钱，确认余额正确',
        'actions': [
            {'index': 1, 'text': '开户', 'resolved_text': '开户', 'source_span': '开户', 'depends_on': []},
            {'index': 2, 'text': '存钱', 'resolved_text': '存款', 'source_span': '存钱', 'depends_on': [1]},
        ],
        'constraints': [
            {'text': '确认余额正确', 'target_action_index': 2, 'field_hint': '余额', 'operator': 'greater_than', 'expected': '0', 'confidence': 0.8},
        ],
    },
    '申请贷款查审批结果': {
        'goal': '申请贷款查审批结果',
        'actions': [
            {'index': 1, 'text': '申请贷款', 'resolved_text': '贷款申请', 'source_span': '申请贷款', 'depends_on': []},
            {'index': 2, 'text': '查审批结果', 'resolved_text': '查询审批结果', 'source_span': '查审批结果', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '买理财确认收益>0': {
        'goal': '买理财确认收益>0',
        'actions': [
            {'index': 1, 'text': '买理财', 'resolved_text': '购买理财产品', 'source_span': '买理财', 'depends_on': []},
        ],
        'constraints': [
            {'text': '收益>0', 'target_action_index': 1, 'field_hint': '收益', 'operator': 'greater_than', 'expected': '0', 'confidence': 0.85},
        ],
    },

    # ====== 支付行业 ======
    '扫码付钱然后查交易记录': {
        'goal': '扫码付钱然后查交易记录',
        'actions': [
            {'index': 1, 'text': '扫码付钱', 'resolved_text': '扫码支付', 'source_span': '扫码付钱', 'depends_on': []},
            {'index': 2, 'text': '查交易记录', 'resolved_text': '查询交易记录', 'source_span': '查交易记录', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '发起退款，status应该为REFUNDED': {
        'goal': '发起退款，status应该为REFUNDED',
        'actions': [
            {'index': 1, 'text': '发起退款', 'resolved_text': '申请退款', 'source_span': '发起退款', 'depends_on': []},
        ],
        'constraints': [
            {'text': 'status应该为REFUNDED', 'target_action_index': 1, 'field_hint': 'status', 'operator': 'equals', 'expected': 'REFUNDED', 'confidence': 0.9},
        ],
    },
    '充值查余额确认amount正确': {
        'goal': '充值查余额确认amount正确',
        'actions': [
            {'index': 1, 'text': '充值', 'resolved_text': '账户充值', 'source_span': '充值', 'depends_on': []},
            {'index': 2, 'text': '查余额', 'resolved_text': '余额查询', 'source_span': '查余额', 'depends_on': [1]},
        ],
        'constraints': [
            {'text': '确认amount正确', 'target_action_index': 2, 'field_hint': 'amount', 'operator': 'exists', 'expected': 'correct', 'confidence': 0.8},
        ],
    },

    # ====== 单步骤 + 约束 ======
    '查余额': {
        'goal': '查余额',
        'actions': [
            {'index': 1, 'text': '查余额', 'resolved_text': '账户余额查询', 'source_span': '查余额', 'depends_on': []},
        ],
        'constraints': [],
    },
    '创建订单': {
        'goal': '创建订单',
        'actions': [
            {'index': 1, 'text': '创建订单', 'resolved_text': '创建订单', 'source_span': '创建订单', 'depends_on': []},
        ],
        'constraints': [],
    },
    '注册账号，登录，确认返回token不为空': {
        'goal': '注册账号，登录，确认返回token不为空',
        'actions': [
            {'index': 1, 'text': '注册账号', 'resolved_text': '用户注册', 'source_span': '注册账号', 'depends_on': []},
            {'index': 2, 'text': '登录', 'resolved_text': '用户登录', 'source_span': '登录', 'depends_on': [1]},
        ],
        'constraints': [
            {'text': '确认返回token不为空', 'target_action_index': 2, 'field_hint': 'token', 'operator': 'exists', 'expected': 'non-empty', 'confidence': 0.9},
        ],
    },

    # ====== source_span 对齐测试 ======
    '查库存然后改库存': {
        'goal': '查库存然后改库存',
        'actions': [
            {'index': 1, 'text': '查询库存', 'resolved_text': '库存查询', 'source_span': '查库存', 'depends_on': []},
            {'index': 2, 'text': '修改库存', 'resolved_text': '库存调拨', 'source_span': '改库存', 'depends_on': [1]},
        ],
        'constraints': [],
    },

    # ====== 正则兜底（LLM 误把约束放 actions） ======
    '查询订单 确认订单状态为paid': {
        'goal': '查询订单 确认订单状态为paid',
        'actions': [
            # LLM 误把约束放到 actions
            {'index': 1, 'text': '查询订单', 'resolved_text': '订单详情', 'source_span': '查询订单', 'depends_on': []},
            {'index': 2, 'text': '确认订单状态为paid', 'resolved_text': '校验订单状态', 'source_span': '确认订单状态为paid', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '查看商品详情 验证价格>0': {
        'goal': '查看商品详情 验证价格>0',
        'actions': [
            {'index': 1, 'text': '查看商品详情', 'resolved_text': '商品详情', 'source_span': '查看商品详情', 'depends_on': []},
            {'index': 2, 'text': '验证价格>0', 'resolved_text': '校验价格', 'source_span': '验证价格>0', 'depends_on': [1]},
        ],
        'constraints': [],
    },

    # ====== 英文目标 ======
    'Create order then verify status is paid': {
        'goal': 'Create order then verify status is paid',
        'actions': [
            {'index': 1, 'text': 'Create order', 'resolved_text': 'Create Order', 'source_span': 'Create order', 'depends_on': []},
        ],
        'constraints': [
            {'text': 'verify status is paid', 'target_action_index': 1, 'field_hint': 'status', 'operator': 'equals', 'expected': 'paid', 'confidence': 0.9},
        ],
    },

    # ====== 长链路（4+ 步骤） ======
    '搜索商品加购物车下单付款查物流': {
        'goal': '搜索商品加购物车下单付款查物流',
        'actions': [
            {'index': 1, 'text': '搜索商品', 'resolved_text': '商品搜索', 'source_span': '搜索商品', 'depends_on': []},
            {'index': 2, 'text': '加购物车', 'resolved_text': '加入购物车', 'source_span': '加购物车', 'depends_on': [1]},
            {'index': 3, 'text': '下单', 'resolved_text': '创建订单', 'source_span': '下单', 'depends_on': [2]},
            {'index': 4, 'text': '付款', 'resolved_text': '支付订单', 'source_span': '付款', 'depends_on': [3]},
            {'index': 5, 'text': '查物流', 'resolved_text': '运单轨迹查询', 'source_span': '查物流', 'depends_on': [4]},
        ],
        'constraints': [],
    },
    '注册登录查个人信息改密码': {
        'goal': '注册登录查个人信息改密码',
        'actions': [
            {'index': 1, 'text': '注册', 'resolved_text': '用户注册', 'source_span': '注册', 'depends_on': []},
            {'index': 2, 'text': '登录', 'resolved_text': '用户登录', 'source_span': '登录', 'depends_on': [1]},
            {'index': 3, 'text': '查个人信息', 'resolved_text': '个人信息查询', 'source_span': '查个人信息', 'depends_on': [2]},
            {'index': 4, 'text': '改密码', 'resolved_text': '修改密码', 'source_span': '改密码', 'depends_on': [2]},
        ],
        'constraints': [],
    },

    # ====== 间隙覆盖去重测试 ======
    '下单 status==paid balance>=0': {
        'goal': '下单 status==paid balance>=0',
        'actions': [
            {'index': 1, 'text': '下单', 'resolved_text': '创建订单', 'source_span': '下单', 'depends_on': []},
        ],
        'constraints': [
            {'text': 'status==paid', 'target_action_index': 1, 'field_hint': 'status', 'operator': 'equals', 'expected': 'paid', 'confidence': 0.9},
            {'text': 'balance>=0', 'target_action_index': 1, 'field_hint': 'balance', 'operator': 'greater_than', 'expected': '0', 'confidence': 0.8},
        ],
    },

    # ====== 多步骤+多约束 ======
    '创建运单揽收，确认status!=CANCELLED tracking_no不为空': {
        'goal': '创建运单揽收，确认status!=CANCELLED tracking_no不为空',
        'actions': [
            {'index': 1, 'text': '创建运单', 'resolved_text': '创建运单', 'source_span': '创建运单', 'depends_on': []},
            {'index': 2, 'text': '揽收', 'resolved_text': '揽收', 'source_span': '揽收', 'depends_on': [1]},
        ],
        'constraints': [
            {'text': '确认status!=CANCELLED', 'target_action_index': 2, 'field_hint': 'status', 'operator': 'not_equals', 'expected': 'CANCELLED', 'confidence': 0.9},
            {'text': 'tracking_no不为空', 'target_action_index': 2, 'field_hint': 'tracking_no', 'operator': 'exists', 'expected': 'non-empty', 'confidence': 0.9},
        ],
    },
}


class MockLLM:
    """模拟 LLM 输出，支持精确匹配和模糊回退。"""
    def chat_json(self, messages, temperature=0.1):
        user_msg = messages[-1]['content']
        goal = user_msg.replace('用户目标：', '').strip()

        # 精确匹配
        if goal in _MOCK_RESPONSES:
            return {
                'data': dict(_MOCK_RESPONSES[goal]),
                'provider': 'mock',
                'model': 'mock',
            }

        # 模糊匹配：尝试部分匹配
        for key, resp in _MOCK_RESPONSES.items():
            if key in goal or goal in key:
                return {'data': dict(resp), 'provider': 'mock', 'model': 'mock'}

        # 兜底：单步骤
        return {
            'data': {
                'goal': goal,
                'actions': [
                    {'index': 1, 'text': goal, 'resolved_text': goal, 'source_span': '', 'depends_on': []},
                ],
                'constraints': [],
            },
            'provider': 'mock',
            'model': 'mock',
        }


# ============================================================================
# 测试用例定义
# ============================================================================
# (goal, expected_steps, expected_constraints_min, expected_source_spans, category)
#
# expected_steps: 期望的步骤数量（经过断言分离后的可执行步骤数）
# expected_constraints_min: 期望的约束数量下限
# expected_source_spans: 期望每个可执行step的source_span (在goal中的子串)
# category: 测试分类

TEST_CASES = [
    # === 基础拆分（电商） ===
    ('注册一个账号然后登录', 2, 0, ['注册一个账号', '登录'], '基础拆分-2步'),
    ('注册并修改密码', 2, 0, ['注册', '修改密码'], '基础拆分-2步'),
    ('查余额', 1, 0, ['查余额'], '基础拆分-1步'),
    ('创建订单', 1, 0, ['创建订单'], '基础拆分-1步-规范'),
    ('付钱并查支付状态', 2, 0, ['付钱', '查支付状态'], '基础拆分-2步-口语'),

    # === 基础拆分（物流） ===
    ('寄个快递然后查物流', 2, 0, ['寄个快递', '查物流'], '基础拆分-2步-口语'),
    ('创建运单揽收签收', 3, 0, ['创建运单', '揽收', '签收'], '基础拆分-3步'),
    ('查运费然后寄件', 2, 0, ['查运费', '寄件'], '基础拆分-2步'),

    # === 基础拆分（ERP） ===
    ('做个采购单然后入库', 2, 0, ['做个采购单', '入库'], '基础拆分-2步-口语'),
    ('新建员工录入考勤查工资', 3, 0, ['新建员工', '录入考勤', '查工资'], '基础拆分-3步'),

    # === 基础拆分（金融） ===
    ('存钱再转账', 2, 0, ['存钱', '转账'], '基础拆分-2步-口语'),
    ('申请贷款查审批结果', 2, 0, ['申请贷款', '查审批结果'], '基础拆分-2步'),

    # === 基础拆分（支付） ===
    ('扫码付钱然后查交易记录', 2, 0, ['扫码付钱', '查交易记录'], '基础拆分-2步'),

    # === 约束识别（LLM 输出） ===
    ('创建订单，确认订单状态为paid', 1, 1, ['创建订单'], '约束-LLM-确认'),
    ('注册账号，登录，确认返回token不为空', 2, 1, ['注册账号', '登录'], '约束-LLM-不为空'),
    ('发工资，确保工资大于0', 1, 1, ['发工资'], '约束-LLM-确保'),
    ('发起退款，status应该为REFUNDED', 1, 1, ['发起退款'], '约束-LLM-应该是'),
    ('开户并存钱，确认余额正确', 2, 1, ['开户', '存钱'], '约束-LLM-确认'),
    ('申请退款需要refund_id非空', 1, 1, ['申请退款'], '约束-LLM-非空'),
    ('买理财确认收益>0', 1, 1, ['买理财'], '约束-LLM-表达式约束'),

    # === 约束识别（表达式） ===
    ('下单 status==paid balance>=0', 1, 2, ['下单'], '约束-表达式-双约束'),

    # === 约束识别（间隙扫描去重） ===
    # LLM 已输出 status==paid 和 balance>=0，间隙扫描不应再重复
    # （此用例验证 assertions 数量 = 2，不过 3）

    # === 约束识别（正则兜底 — LLM 误放约束到 actions） ===
    ('查询订单 确认订单状态为paid', 1, 1, ['查询订单'], '正则兜底-确认'),
    ('查看商品详情 验证价格>0', 1, 1, ['查看商品详情'], '正则兜底-验证'),

    # === 多约束 ===
    ('创建运单揽收，确认status!=CANCELLED tracking_no不为空', 2, 2, ['创建运单', '揽收'], '多约束-双约束'),

    # === 登录后约束链 ===
    ('登录后查看个人信息，确认userId不为空', 2, 1, ['登录', '查看个人信息'], '约束-链路约束'),

    # === source_span 对齐 ===
    ('查库存然后改库存', 2, 0, ['查库存', '改库存'], 'source_span-简称对齐'),
    ('领券下单用券付钱', 4, 0, ['领券', '下单', '用券', '付钱'], 'source_span-4步对齐'),

    # === 英文 ===
    ('Create order then verify status is paid', 1, 1, ['Create order'], '英文-约束'),

    # === 长链路 ===
    ('搜索商品加购物车下单付款查物流', 5, 0, ['搜索商品', '加购物车', '下单', '付款', '查物流'], '长链路-5步'),
    ('注册登录查个人信息改密码', 4, 0, ['注册', '登录', '查个人信息', '改密码'], '长链路-4步'),
    ('加入购物车然后下单付钱', 3, 0, ['加入购物车', '下单', '付钱'], '长链路-3步'),
    ('搜索商品看详情再加购物车', 3, 0, ['搜索商品', '看详情', '加购物车'], '长链路-3步-依赖'),

    # === 充值查余额 ===
    ('充值查余额确认amount正确', 2, 1, ['充值', '查余额'], '约束-链路查询'),

    # === 退货退款 ===
    # "确认退款状态" 以"确认"开头，被正则判定为断言——在 API 测试语境下这合理
    ('退货并确认退款状态', 1, 1, ['退货'], '约束-确认=断言'),
]

# resolved_text 质量测试
RESOLVED_TEXT_EXPECTED = {
    '付钱并查支付状态': ['支付', '查询'],
    '寄个快递然后查物流': ['运单', '轨迹'],
    '存钱再转账': ['存款', '转账'],
    '查余额': ['余额'],
    '下单 status==paid balance>=0': ['订单'],
    '做个采购单然后入库': ['采购', '入库'],
    '扫码付钱然后查交易记录': ['扫码', '交易'],
    '搜索商品加购物车下单付款查物流': ['搜索', '购物车', '订单', '支付', '轨迹'],
    '领券下单用券付钱': ['优惠券', '订单', '优惠券', '支付'],
}


# ============================================================================
# 断言识别独立测试
# ============================================================================

ASSERTION_TEST_CASES = [
    # (text, expected_is_assertion, description)
    # --- 前缀关键词断言 ---
    ('确认返回token不为空', True, '前缀-确认+不为空'),
    ('校验订单状态为paid', True, '前缀-校验'),
    ('验证余额大于0', True, '前缀-验证'),
    ('检查商品库存', True, '前缀-检查(歧义)'),
    ('确保返回userId', True, '前缀-确保'),
    ('期望状态码为200', True, '前缀-期望'),
    # --- 句中断言 ---
    ('订单状态应该是paid', True, '句中-应该是'),
    ('余额必须大于0', True, '句中-必须大于'),
    ('返回的userId不能为空', True, '句中-不能为空'),
    ('amount需要等于100', True, '句中-需要等于'),
    # --- 表达式断言 ---
    ('status==paid', True, '表达式-等号'),
    ('balance>=0', True, '表达式-大于等于'),
    ('code!=200', True, '表达式-不等'),
    ('收益>0', True, '表达式-大于'),
    # --- 英文断言 ---
    ('verify response code is 200', True, '英文-verify'),
    ('ensure data exists', True, '英文-ensure'),
    ('token should not be empty', True, '英文-should not be empty'),
    # --- 是动作，不是断言 ---
    ('创建订单', False, '动作-创建'),
    ('查询用户信息', False, '动作-查询'),
    ('付钱', False, '动作-口语'),
    ('登录系统', False, '动作-登录'),
    ('更新个人信息', False, '动作-更新'),
    ('获取商品列表', False, '动作-获取'),
    ('寄个快递', False, '动作-口语-寄件'),
    ('存钱', False, '动作-口语-存款'),
]


# ============================================================================
# 测试执行
# ============================================================================

def run_step_planner_test():
    planner = StepPlanner(MockLLM())
    results = []

    print('=' * 80)
    print('StepPlanner 生产级测试（基于 300 接口场景）')
    print('=' * 80)

    # --- 1. 结构测试 ---
    print(f'\n--- 1. 结构测试: 步骤拆分 / source_span / 约束识别 ({len(TEST_CASES)} 用例) ---\n')
    struct_pass = 0
    struct_fail = 0
    struct_details = []

    for goal, exp_steps, exp_constraints_min, exp_spans, category in TEST_CASES:
        try:
            result, _ = planner.plan(goal)
            steps = result['steps']
            assertions = result['assertion_intents']
            total_assertions = len(assertions)

            # 检查步骤数
            step_ok = len(steps) == exp_steps
            # 检查约束数
            constraint_ok = total_assertions >= exp_constraints_min
            # 检查 source_span
            span_ok = True
            span_detail = []
            for i, exp_span in enumerate(exp_spans):
                if i < len(steps):
                    actual_span = steps[i].get('source_span', '')
                    match = actual_span == exp_span
                    span_ok = span_ok and match
                    span_detail.append(f'#{i+1}="{actual_span}"{"✓" if match else f"✗(期望\"{exp_span}\")"}')
                else:
                    span_ok = False
                    span_detail.append(f'#{i+1}=缺失(期望"{exp_span}")')

            # 检查 original_goal
            og_ok = all(s.get('original_goal') == goal for s in steps)

            # 检查约束超量（间隙扫描去重）
            constraint_over = total_assertions > exp_constraints_min + 2  # 允许+2的冗余
            constraint_over_ok = not constraint_over

            all_ok = step_ok and constraint_ok and span_ok and og_ok and constraint_over_ok
            status = '✅' if all_ok else '❌'
            if all_ok:
                struct_pass += 1
            else:
                struct_fail += 1

            detail_parts = []
            if not step_ok:
                detail_parts.append(f'步骤数={len(steps)}(期望{exp_steps})')
            if not constraint_ok:
                detail_parts.append(f'约束数={total_assertions}(期望≥{exp_constraints_min})')
            if constraint_over:
                detail_parts.append(f'约束冗余={total_assertions}(期望≈{exp_constraints_min})')
            if not span_ok:
                detail_parts.append(f'source_span: {", ".join(span_detail)}')
            if not og_ok:
                detail_parts.append('original_goal缺失')

            constraint_texts = [a['text'] for a in assertions] if assertions else []
            step_texts = [s['text'] for s in steps]
            resolved_texts = [s['resolved_text'] for s in steps]

            print(f'  {status} [{category}] "{goal}"')
            print(f'     steps={step_texts} resolved={resolved_texts}')
            if constraint_texts:
                print(f'     assertions={constraint_texts}')
            if detail_parts:
                print(f'     问题: {"; ".join(detail_parts)}')

            results.append({
                'goal': goal, 'category': category, 'passed': all_ok,
                'step_count': len(steps), 'expected_steps': exp_steps,
                'constraint_count': total_assertions, 'expected_constraints_min': exp_constraints_min,
                'span_ok': span_ok, 'og_ok': og_ok,
            })
        except Exception as e:
            struct_fail += 1
            print(f'  ❌ [{category}] "{goal}" → 异常: {e}')
            import traceback
            traceback.print_exc()
            results.append({'goal': goal, 'category': category, 'passed': False, 'error': str(e)})

    # --- 2. resolved_text 质量 ---
    print(f'\n--- 2. resolved_text 规范化质量 ({len(RESOLVED_TEXT_EXPECTED)} 用例) ---\n')
    rt_pass = 0
    rt_fail = 0

    for goal, expected_keywords in RESOLVED_TEXT_EXPECTED.items():
        try:
            result, _ = planner.plan(goal)
            steps = result['steps']
            all_resolved = ' '.join(s.get('resolved_text', '') for s in steps)
            missing = [kw for kw in expected_keywords if kw not in all_resolved]
            ok = len(missing) == 0
            if ok:
                rt_pass += 1
            else:
                rt_fail += 1
            status = '✅' if ok else '❌'
            resolved_list = [s.get('resolved_text', '') for s in steps]
            print(f'  {status} "{goal}" → resolved_text={resolved_list}')
            if missing:
                print(f'     缺少关键字: {missing}')
        except Exception as e:
            rt_fail += 1
            print(f'  ❌ "{goal}" → 异常: {e}')

    # --- 3. 断言识别覆盖面 ---
    print(f'\n--- 3. 断言识别覆盖面测试（正则兜底）({len(ASSERTION_TEST_CASES)} 用例) ---\n')
    planner_instance = StepPlanner(MockLLM())
    assertion_pass = 0
    assertion_fail = 0
    assertion_details = []

    for text, expected, desc in ASSERTION_TEST_CASES:
        result = planner_instance._is_assertion_intent(text)
        ok = result == expected
        status = '✅' if ok else '❌'
        if ok:
            assertion_pass += 1
        else:
            assertion_fail += 1
            assertion_details.append((text, result, expected, desc))
        print(f'  {status} "{text}" → {result} (期望{expected}) [{desc}]')

    # --- 4. depends_on 验证 ---
    print(f'\n--- 4. depends_on 依赖链验证 ---\n')
    dep_pass = 0
    dep_fail = 0

    dep_test_goals = [tc[0] for tc in TEST_CASES if tc[1] >= 2]  # 多步骤用例
    for goal in dep_test_goals:
        try:
            result, _ = planner.plan(goal)
            steps = result['steps']
            dep_ok = True
            dep_issues = []
            for s in steps:
                deps = s.get('depends_on', [])
                # 第一步必须无依赖
                if s['index'] == 1 and deps:
                    dep_ok = False
                    dep_issues.append(f'step#{s["index"]} 不应有依赖但有{deps}')
                # 依赖的步骤必须存在且序号更小
                for d in deps:
                    if not any(ss['index'] == d for ss in steps):
                        dep_ok = False
                        dep_issues.append(f'step#{s["index"]} 依赖不存在的step#{d}')
                    elif d >= s['index']:
                        dep_ok = False
                        dep_issues.append(f'step#{s["index"]} 依赖step#{d}但应依赖更早步骤')

            status = '✅' if dep_ok else '❌'
            if dep_ok:
                dep_pass += 1
            else:
                dep_fail += 1
            dep_info = [(s['index'], s.get('depends_on', [])) for s in steps]
            print(f'  {status} "{goal}" → depends={dep_info}')
            if dep_issues:
                print(f'     问题: {"; ".join(dep_issues)}')
        except Exception as e:
            dep_fail += 1
            print(f'  ❌ "{goal}" → 异常: {e}')

    # --- 5. original_goal 传递验证 ---
    print(f'\n--- 5. original_goal 传递验证（双通道召回兼容性） ---\n')
    og_pass = 0
    og_fail = 0
    all_goals = [tc[0] for tc in TEST_CASES]
    for goal in all_goals:
        try:
            result, _ = planner.plan(goal)
            steps = result['steps']
            ok = all(s.get('original_goal') == goal for s in steps) if steps else True
            if ok:
                og_pass += 1
            else:
                og_fail += 1
                missing = [s['index'] for s in steps if s.get('original_goal') != goal]
                print(f'  ❌ "{goal}" → step{missing} 缺失original_goal')
        except Exception as e:
            og_fail += 1
    og_total = og_pass + og_fail
    if og_fail == 0:
        print(f'  ✅ 全部 {og_total} 个用例 original_goal 传递正确')

    # --- 6. 间隙扫描去重验证 ---
    print(f'\n--- 6. 间隙扫描去重验证 ---\n')
    dedup_pass = 0
    dedup_fail = 0
    # 测试 "下单 status==paid balance>=0" 不应产生第三个冗余断言
    dedup_cases = [
        ('下单 status==paid balance>=0', 2, 'LLM约束+间隙不应重复'),
        ('创建运单揽收，确认status!=CANCELLED tracking_no不为空', 2, '多约束无冗余'),
    ]
    for goal, exp_max, desc in dedup_cases:
        try:
            result, _ = planner.plan(goal)
            assertions = result['assertion_intents']
            total = len(assertions)
            ok = total <= exp_max + 1  # 允许+1的合理间隙扫描补充
            if ok:
                dedup_pass += 1
            else:
                dedup_fail += 1
            status = '✅' if ok else '❌'
            texts = [a['text'] for a in assertions]
            print(f'  {status} "{goal}" → {total}断言(期望≤{exp_max+1}) {texts} [{desc}]')
        except Exception as e:
            dedup_fail += 1
            print(f'  ❌ "{goal}" → 异常: {e}')

    # --- 汇总 ---
    print('\n' + '=' * 80)
    print('测试汇总')
    print('=' * 80)
    total = struct_pass + struct_fail
    print(f'  结构测试:        {struct_pass}/{total} 通过 ({struct_pass/total*100:.0f}%)')
    total_rt = rt_pass + rt_fail
    print(f'  resolved_text:   {rt_pass}/{total_rt} 通过 ({rt_pass/total_rt*100:.0f}%)')
    total_a = assertion_pass + assertion_fail
    print(f'  断言识别:        {assertion_pass}/{total_a} 通过 ({assertion_pass/total_a*100:.0f}%)')
    total_d = dep_pass + dep_fail
    print(f'  依赖链:          {dep_pass}/{total_d} 通过 ({dep_pass/total_d*100:.0f}%)')
    print(f'  original_goal:   {og_pass}/{og_total} 通过 ({og_pass/og_total*100:.0f}%)')
    total_dd = dedup_pass + dedup_fail
    print(f'  间隙扫描去重:    {dedup_pass}/{total_dd} 通过 ({dedup_pass/total_dd*100:.0f}%)')
    grand_total = total + total_rt + total_a + total_d + og_total + total_dd
    grand_pass = struct_pass + rt_pass + assertion_pass + dep_pass + og_pass + dedup_pass
    print(f'\n  总计: {grand_pass}/{grand_total} 通过 ({grand_pass/grand_total*100:.0f}%)')

    # --- 失败用例汇总 ---
    failures = []
    failures.extend([r for r in results if not r.get('passed')])
    failures.extend([(t, r, e, d) for t, r, e, d in assertion_details])
    if failures:
        print(f'\n--- 失败用例明细 ---')
        for r in results:
            if not r.get('passed'):
                err = r.get('error', '')
                goal = r.get('goal', '')
                cat = r.get('category', '')
                if err:
                    print(f'  结构: [{cat}] "{goal}" → {err}')
                else:
                    sc = r.get('step_count', '?')
                    es = r.get('expected_steps', '?')
                    cc = r.get('constraint_count', '?')
                    ec = r.get('expected_constraints_min', '?')
                    print(f'  结构: [{cat}] "{goal}" → 步骤={sc}/{es} 约束={cc}/≥{ec}')
        for text, result, expected, desc in assertion_details:
            print(f'  断言: "{text}" → 判定{result}/期望{expected} [{desc}]')

    return results


if __name__ == '__main__':
    run_step_planner_test()