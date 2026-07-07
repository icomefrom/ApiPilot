"""
StepPlanner + CandidatePreselector 端到端测试 — 基于 300 接口数据集

验证 StepPlanner 输出的步骤（text/resolved_text/original_goal）经过
CandidatePreselector 后能否正确匹配到目标接口。

测试覆盖：
1. 单步骤匹配：step.text → 预选 Top-K
2. 双通道匹配：resolved_text 规范化后提升排序
3. 多步骤链路：每步独立匹配
4. 口语化表达：step.text 是口语，resolved_text 是术语 → 双通道兜底

用法:
  cd backend && python -c "
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
  django.setup()
  exec(open('apps/agent/tests/test_planner_e2e.py').read())
  "
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
if not django.conf.settings.configured:
    django.setup()

from apps.agent.services.planning.step_planner import StepPlanner
from apps.agent.services.indexing.candidate_preselector import CandidatePreselector
from apps.agent.services.indexing.embedding_indexer import EmbeddingIndexer
from apps.agent.tests.test_data_300 import (
    ECOMMERCE, ECOMMERCE_CASES,
    LOGISTICS, LOGISTICS_CASES,
    ERP, ERP_CASES,
    FINANCE, FINANCE_CASES,
    PAYMENT, PAYMENT_CASES,
    TOTAL_INTERFACES,
)

# 合并所有接口
ALL_INTERFACES = ECOMMERCE + LOGISTICS + ERP + FINANCE + PAYMENT

# 构建 ID → 接口名 映射
ID_TO_NAME = {p['interface_id']: p['name'] for p in ALL_INTERFACES}


# ============================================================================
# Mock LLM — 模拟 StepPlanner 需要的 LLM 输出
# ============================================================================

# 多步骤目标 → LLM 输出
_MULTI_STEP_RESPONSES = {
    '注册一个账号然后登录': {
        'goal': '注册一个账号然后登录',
        'actions': [
            {'index': 1, 'text': '注册一个账号', 'resolved_text': '用户注册', 'source_span': '注册一个账号', 'depends_on': []},
            {'index': 2, 'text': '登录', 'resolved_text': '用户登录', 'source_span': '登录', 'depends_on': [1]},
        ],
        'constraints': [],
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
    '寄个快递然后查物流': {
        'goal': '寄个快递然后查物流',
        'actions': [
            {'index': 1, 'text': '寄个快递', 'resolved_text': '创建运单', 'source_span': '寄个快递', 'depends_on': []},
            {'index': 2, 'text': '查物流', 'resolved_text': '运单轨迹查询', 'source_span': '查物流', 'depends_on': [1]},
        ],
        'constraints': [],
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
    '存钱再转账': {
        'goal': '存钱再转账',
        'actions': [
            {'index': 1, 'text': '存钱', 'resolved_text': '存款', 'source_span': '存钱', 'depends_on': []},
            {'index': 2, 'text': '转账', 'resolved_text': '转账', 'source_span': '转账', 'depends_on': [1]},
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
    '付钱并查支付状态': {
        'goal': '付钱并查支付状态',
        'actions': [
            {'index': 1, 'text': '付钱', 'resolved_text': '支付订单', 'source_span': '付钱', 'depends_on': []},
            {'index': 2, 'text': '查支付状态', 'resolved_text': '查询支付状态', 'source_span': '查支付状态', 'depends_on': [1]},
        ],
        'constraints': [],
    },
    '申请贷款查审批结果': {
        'goal': '申请贷款查审批结果',
        'actions': [
            {'index': 1, 'text': '申请贷款', 'resolved_text': '贷款申请', 'source_span': '申请贷款', 'depends_on': []},
            {'index': 2, 'text': '查审批结果', 'resolved_text': '查询审批结果', 'source_span': '查审批结果', 'depends_on': [1]},
        ],
        'constraints': [],
    },
}


class MockLLM:
    """模拟 LLM 输出。"""
    def chat_json(self, messages, temperature=0.1):
        user_msg = messages[-1]['content']
        goal = user_msg.replace('用户目标：', '').strip()
        if goal in _MULTI_STEP_RESPONSES:
            return {'data': dict(_MULTI_STEP_RESPONSES[goal]), 'provider': 'mock', 'model': 'mock'}
        # 兜底单步骤
        return {
            'data': {
                'goal': goal,
                'actions': [{'index': 1, 'text': goal, 'resolved_text': goal, 'source_span': goal, 'depends_on': []}],
                'constraints': [],
            },
            'provider': 'mock',
            'model': 'mock',
        }


# ============================================================================
# 测试用例
# ============================================================================
# 多步骤 E2E：goal → step.text/resolved_text → 每步期望匹配接口
# (goal, [(step_index, step_text, resolved_text, expected_interface_id), ...])

MULTI_STEP_E2E = [
    ('注册一个账号然后登录', [
        (1, '注册一个账号', '用户注册', 1),   # 用户注册
        (2, '登录', '用户登录', 2),            # 用户登录
    ]),
    ('加入购物车然后下单付钱', [
        (1, '加入购物车', '加入购物车', 33),
        (2, '下单', '创建订单', 23),
        (3, '付钱', '支付订单', 38),
    ]),
    ('搜索商品看详情再加购物车', [
        (1, '搜索商品', '商品搜索', 13),
        (2, '看详情', '商品详情', 12),
        (3, '加购物车', '加入购物车', 33),
    ]),
    ('寄个快递然后查物流', [
        (1, '寄个快递', '创建运单', 101),
        (2, '查物流', '运单轨迹查询', 104),
    ]),
    ('创建运单揽收签收', [
        (1, '创建运单', '创建运单', 101),
        (2, '揽收', '揽收', 111),
        (3, '签收', '签收', 113),
    ]),
    ('存钱再转账', [
        (1, '存钱', '存款', 311),              # 存款 ID=311
        (2, '转账', '转账', 319),              # 转账 ID=319
    ]),
    ('领券下单用券付钱', [
        (1, '领券', '领取优惠券', 44),
        (2, '下单', '创建订单', 23),
        (3, '用券', '使用优惠券', 45),
        (4, '付钱', '支付订单', 38),
    ]),
    ('付钱并查支付状态', [
        (1, '付钱', '支付订单', 38),
        (2, '查支付状态', '查询支付状态', 40),
    ]),
    ('申请贷款查审批结果', [
        (1, '申请贷款', '贷款申请', 333),      # 贷款申请 ID=333
        (2, '查审批结果', '贷款审批', 334),    # 贷款审批 ID=334
    ]),
]

# 单步骤 E2E：直接利用 300 接口的测试用例
# 抽取各行业代表用例，模拟 StepPlanner 对单步的输出
SINGLE_STEP_E2E = [
    # 电商 (1-60)
    ('注册', '用户注册', 1), ('登录', '用户登录', 2), ('查个人信息', '个人信息查询', 5),
    ('搜商品', '商品搜索', 13), ('看商品详情', '商品详情', 12),
    ('下单', '创建订单', 23), ('看订单信息', '订单详情', 25),
    ('付钱', '支付订单', 38), ('退款', '申请退款', 41),
    ('领券', '领取优惠券', 44), ('退货', '申请售后', 51),
    # 物流 (101-160)
    ('寄快递', '创建运单', 101), ('查物流', '运单轨迹查询', 104),
    ('揽收', '揽收', 111), ('签收', '签收', 113),
    ('算运费', '运费计算', 129),
    # ERP (201-260)
    ('做采购单', '创建采购单', 201), ('入库', '采购入库', 204),
    ('查库存', '库存查询', 221), ('发工资', '薪资发放', 255),
    # 金融 (301-360)
    ('开户', '开户', 301), ('存款', '存款', 311), ('转账', '转账', 319),
    ('申请贷款', '贷款申请', 333), ('买理财', '购买理财', 345),
    ('查余额', '账户余额查询', 307),
    # 支付 (401-460)
    ('创建收单', '创建收单', 401), ('查询收单状态', '查询收单状态', 402),
    ('申请退款', '申请退款', 411), ('查询退款状态', '查询退款状态', 412),
    ('对账结果查询', '对账结果查询', 438),
    ('商户入驻', '商户入驻', 419),
]


def run_e2e_test():
    print('=' * 80)
    print('StepPlanner + CandidatePreselector 端到端测试（300 接口）')
    print('=' * 80)

    # 构建 embedding 索引
    print('\n构建 Embedding 索引...')
    emb = EmbeddingIndexer(top_k=30)
    emb.build(ALL_INTERFACES)
    print(f'  索引构建完成: {emb._index.ntotal} 个接口')

    preselector_text_only = CandidatePreselector()  # 纯 token 预选
    preselector_with_emb = CandidatePreselector(embedding_indexer=emb)  # token + 语义

    planner = StepPlanner(MockLLM())

    # ---- 1. 多步骤端到端测试 ----
    print(f'\n--- 1. 多步骤端到端: StepPlanner → Preselector ({len(MULTI_STEP_E2E)} 条链路) ---\n')

    multi_pass_text = 0
    multi_pass_emb = 0
    multi_total = 0
    multi_details = []

    for goal, step_specs in MULTI_STEP_E2E:
        try:
            result, _ = planner.plan(goal)
            steps = result['steps']

            # 用 text (口语) 做预选
            steps_text = [{'index': s['index'], 'text': s['text'], 'resolved_text': s['text']} for s in steps]
            cands_text = preselector_text_only.select(steps_text, ALL_INTERFACES, limit=20)

            # 用 resolved_text (规范化) 做预选
            steps_resolved = [{'index': s['index'], 'text': s['resolved_text'], 'resolved_text': s['resolved_text']} for s in steps]
            cands_resolved = preselector_with_emb.select(steps_resolved, ALL_INTERFACES, limit=20)

            # 用 text + original_goal (双通道) 做预选
            steps_dual = [{'index': s['index'], 'text': s['text'], 'resolved_text': s['resolved_text'], 'original_goal': goal} for s in steps]
            cands_dual = preselector_with_emb.select(steps_dual, ALL_INTERFACES, limit=20)

            print(f'  链路: "{goal}" ({len(steps)} 步)')
            for idx, (step_idx, step_text, resolved_text, expected_id) in enumerate(step_specs):
                expected_name = ID_TO_NAME.get(expected_id, '?')
                multi_total += 1

                # text-only Top-1
                text_cands = cands_text[idx]['candidates'] if idx < len(cands_text) else []
                text_top1 = text_cands[0]['interface_id'] if text_cands else None
                text_top1_name = text_cands[0]['name'] if text_cands else 'N/A'
                text_rank = next((i+1 for i, c in enumerate(text_cands) if c['interface_id'] == expected_id), None)

                # resolved_text + embedding Top-1
                res_cands = cands_resolved[idx]['candidates'] if idx < len(cands_resolved) else []
                res_top1 = res_cands[0]['interface_id'] if res_cands else None
                res_top1_name = res_cands[0]['name'] if res_cands else 'N/A'
                res_rank = next((i+1 for i, c in enumerate(res_cands) if c['interface_id'] == expected_id), None)

                # dual-channel Top-1
                dual_cands = cands_dual[idx]['candidates'] if idx < len(cands_dual) else []
                dual_top1 = dual_cands[0]['interface_id'] if dual_cands else None
                dual_top1_name = dual_cands[0]['name'] if dual_cands else 'N/A'
                dual_rank = next((i+1 for i, c in enumerate(dual_cands) if c['interface_id'] == expected_id), None)

                text_hit = text_top1 == expected_id
                res_hit = res_top1 == expected_id
                dual_hit = dual_top1 == expected_id

                if text_hit:
                    multi_pass_text += 1
                if dual_hit:
                    multi_pass_emb += 1

                sym = '✅' if dual_hit else ('⚠️' if dual_rank and dual_rank <= 3 else '❌')
                text_r = f'#{text_rank}' if text_rank else 'OUT'
                res_r = f'#{res_rank}' if res_rank else 'OUT'
                dual_r = f'#{dual_rank}' if dual_rank else 'OUT'
                print(f'    {sym} Step{step_idx}: text="{step_text}" resolved="{resolved_text}" → 期望={expected_name}(ID={expected_id})')
                print(f'       text-only: {text_top1_name}({text_r}) | resolved+emb: {res_top1_name}({res_r}) | dual: {dual_top1_name}({dual_r})')

                multi_details.append({
                    'goal': goal, 'step': step_text, 'expected_id': expected_id,
                    'text_hit': text_hit, 'text_rank': text_rank,
                    'res_hit': res_hit, 'res_rank': res_rank,
                    'dual_hit': dual_hit, 'dual_rank': dual_rank,
                })
        except Exception as e:
            print(f'  ❌ 链路 "{goal}" 异常: {e}')
            import traceback
            traceback.print_exc()

    if multi_total > 0:
        print(f'\n  多步骤汇总: text-only Top-1={multi_pass_text}/{multi_total} ({multi_pass_text/multi_total*100:.1f}%), '
              f'dual Top-1={multi_pass_emb}/{multi_total} ({multi_pass_emb/multi_total*100:.1f}%)')

    # ---- 2. 单步骤端到端测试 ----
    print(f'\n--- 2. 单步骤端到端: resolved_text 已知正确时匹配率 ({len(SINGLE_STEP_E2E)} 用例) ---\n')

    single_pass_text = 0
    single_pass_emb = 0
    single_total = 0

    for step_text, resolved_text, expected_id in SINGLE_STEP_E2E:
        expected_name = ID_TO_NAME.get(expected_id, '?')
        single_total += 1

        # text-only
        steps_t = [{'index': 1, 'text': step_text, 'resolved_text': step_text}]
        cands_t = preselector_text_only.select(steps_t, ALL_INTERFACES, limit=20)
        text_cands = cands_t[0]['candidates'] if cands_t else []
        text_top1 = text_cands[0]['interface_id'] if text_cands else None
        text_rank = next((i+1 for i, c in enumerate(text_cands) if c['interface_id'] == expected_id), None)

        # resolved_text + embedding
        steps_r = [{'index': 1, 'text': resolved_text, 'resolved_text': resolved_text}]
        cands_r = preselector_with_emb.select(steps_r, ALL_INTERFACES, limit=20)
        res_cands = cands_r[0]['candidates'] if cands_r else []
        res_top1 = res_cands[0]['interface_id'] if res_cands else None
        res_rank = next((i+1 for i, c in enumerate(res_cands) if c['interface_id'] == expected_id), None)

        text_hit = text_top1 == expected_id
        res_hit = res_top1 == expected_id

        if text_hit:
            single_pass_text += 1
        if res_hit:
            single_pass_emb += 1

        sym = '✅' if res_hit else ('⚠️' if res_rank and res_rank <= 3 else '❌')
        text_r = f'#{text_rank}' if text_rank else 'OUT'
        res_r_str = f'#{res_rank}' if res_rank else 'OUT'
        improved = '↑' if (not text_hit and res_hit) else ('=' if text_hit == res_hit else '↓')
        text_name = text_cands[0]['name'] if text_cands else 'N/A'
        res_name = res_cands[0]['name'] if res_cands else 'N/A'
        print(f'  {sym} "{step_text}"→"{resolved_text}" → 期望={expected_name}(ID={expected_id}) '
              f'| text:{text_name}({text_r}) | resolved+emb:{res_name}({res_r_str}) {improved}')

    if single_total > 0:
        print(f'\n  单步骤汇总: text-only Top-1={single_pass_text}/{single_total} ({single_pass_text/single_total*100:.1f}%), '
              f'resolved+emb Top-1={single_pass_emb}/{single_total} ({single_pass_emb/single_total*100:.1f}%)')

    # ---- 3. 总汇总 ----
    print('\n' + '=' * 80)
    print('端到端测试汇总')
    print('=' * 80)
    print(f'  多步骤链路: {len(MULTI_STEP_E2E)} 条, {multi_total} 个步骤')
    print(f'    text-only Top-1: {multi_pass_text}/{multi_total} ({multi_pass_text/multi_total*100:.1f}% 比如出问题)' if multi_total > 0 else '')
    print(f'    dual-channel Top-1: {multi_pass_emb}/{multi_total} ({multi_pass_emb/multi_total*100:.1f}%)' if multi_total > 0 else '')
    print(f'  单步骤: {single_total} 用例')
    print(f'    text-only Top-1: {single_pass_text}/{single_total} ({single_pass_text/single_total*100:.1f}%)' if single_total > 0 else '')
    print(f'    resolved+emb Top-1: {single_pass_emb}/{single_total} ({single_pass_emb/single_total*100:.1f}%)' if single_total > 0 else '')
    total_s = multi_total + single_total
    total_p_t = multi_pass_text + single_pass_text
    total_p_e = multi_pass_emb + single_pass_emb
    print(f'\n  总计: {total_s} 步骤')
    print(f'    text-only Top-1: {total_p_t}/{total_s} ({total_p_t/total_s*100:.1f}%)')
    print(f'    规范化+语义 Top-1: {total_p_e}/{total_s} ({total_p_e/total_s*100:.1f}%)')

    # 双通道提升分析
    if multi_total > 0:
        improved_count = sum(1 for d in multi_details if not d['text_hit'] and d['dual_hit'])
        degraded_count = sum(1 for d in multi_details if d['text_hit'] and not d['dual_hit'])
        print(f'\n  双通道提升: +{improved_count} (text未中→dual命中) / -{degraded_count} (text命中→dual未中)')

    return {
        'multi_total': multi_total,
        'multi_pass_text': multi_pass_text,
        'multi_pass_dual': multi_pass_emb,
        'single_total': single_total,
        'single_pass_text': single_pass_text,
        'single_pass_emb': single_pass_emb,
    }


if __name__ == '__main__':
    run_e2e_test()