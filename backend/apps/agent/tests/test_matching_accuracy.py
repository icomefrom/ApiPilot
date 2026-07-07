"""
Agent 接口匹配准确率本地测试脚本 (300 接口版)

用法:
  # 仅测试规则预选（不需要 LLM）
  cd backend && python -c "
  import os, django
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
  django.setup()
  exec(open('apps/agent/tests/test_matching_accuracy.py').read())
  "

  # 如需测试 LLM 匹配，确保 .env 中配置了 AGENT_OPENAI_* 或 Ollama
"""
import os
import sys
import json
import time
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
if not django.conf.settings.configured:
    django.setup()

from apps.agent.services.indexing.candidate_preselector import CandidatePreselector
from apps.agent.services.indexing.interface_indexer import InterfaceIndexer
from apps.agent.services.indexing.embedding_indexer import EmbeddingIndexer

# ============================================================================
# 导入 300 接口数据集
# ============================================================================
from apps.agent.tests.test_data_300 import (
    ECOMMERCE, ECOMMERCE_CASES,
    LOGISTICS, LOGISTICS_CASES,
    ERP, ERP_CASES,
    FINANCE, FINANCE_CASES,
    PAYMENT, PAYMENT_CASES,
    TOTAL_INTERFACES, TOTAL_CASES,
)

INDUSTRIES = [
    ('电商', ECOMMERCE, ECOMMERCE_CASES),
    ('物流', LOGISTICS, LOGISTICS_CASES),
    ('ERP', ERP, ERP_CASES),
    ('金融', FINANCE, FINANCE_CASES),
    ('支付', PAYMENT, PAYMENT_CASES),
]

def run_preselector_test(use_embedding=False):
    """测试规则预选。use_embedding=True 时启用语义召回合并。"""
    if use_embedding:
        emb = EmbeddingIndexer(top_k=30)
        # 合并所有接口构建全局 embedding 索引
        all_profiles = []
        for _, interfaces, _ in INDUSTRIES:
            all_profiles.extend(interfaces)
        emb.build(all_profiles)
        preselector = CandidatePreselector(embedding_indexer=emb)
        mode_label = '规则预选 + 语义召回'
    else:
        preselector = CandidatePreselector()
        mode_label = '规则预选 (仅token)'

    all_results = []

    print('=' * 80)
    print(f'接口匹配准确率测试 — {mode_label}')
    print('=' * 80)

    for industry_name, interfaces, test_cases in INDUSTRIES:
        results = []
        for step_text, expected_id, desc in test_cases:
            steps = [{'index': 1, 'text': step_text, 'resolved_text': step_text}]
            candidates_by_step = preselector.select(steps, interfaces, limit=20)

            candidates = candidates_by_step[0]['candidates']
            top_candidate = candidates[0] if candidates else None
            top_id = top_candidate['interface_id'] if top_candidate else None

            # 检查期望接口是否在候选中
            rank = None
            for i, c in enumerate(candidates):
                if c['interface_id'] == expected_id:
                    rank = i + 1
                    break

            hit_top1 = (top_id == expected_id)
            hit_top3 = rank is not None and rank <= 3
            hit_top5 = rank is not None and rank <= 5
            in_candidates = rank is not None

            results.append({
                'step': step_text,
                'expected_id': expected_id,
                'top1_id': top_id,
                'top1_name': top_candidate['name'] if top_candidate else 'N/A',
                'top1_score': top_candidate['pre_score'] if top_candidate else 0,
                'expected_rank': rank,
                'expected_score': next((c['pre_score'] for c in candidates if c['interface_id'] == expected_id), 0),
                'hit_top1': hit_top1,
                'hit_top3': hit_top3,
                'hit_top5': hit_top5,
                'in_candidates': in_candidates,
                'desc': desc,
            })

        total = len(results)
        top1 = sum(1 for r in results if r['hit_top1'])
        top3 = sum(1 for r in results if r['hit_top3'])
        top5 = sum(1 for r in results if r['hit_top5'])
        in_cand = sum(1 for r in results if r['in_candidates'])

        print(f'\n--- {industry_name} (共 {total} 条) ---')
        print(f'  Top-1 准确率: {top1}/{total} = {top1/total*100:.1f}%')
        print(f'  Top-3 准确率: {top3}/{total} = {top3/total*100:.1f}%')
        print(f'  Top-5 准确率: {top5}/{total} = {top5/total*100:.1f}%')
        print(f'  召回率(在候选中): {in_cand}/{total} = {in_cand/total*100:.1f}%')

        # 打印匹配详情
        for r in results:
            status = '✅' if r['hit_top1'] else ('⚠️' if r['hit_top3'] else '❌')
            rank_str = f'Rank#{r["expected_rank"]}' if r['in_candidates'] else 'NOT_IN_CANDIDATES'
            print(f'  {status} "{r["step"]}" → 期望ID={r["expected_id"]}({rank_str}, score={r["expected_score"]:.4f}), '
                  f'实际Top1=ID{r["top1_id"]}({r["top1_name"]}, score={r["top1_score"]:.4f})  [{r["desc"]}]')

        # 错误分析
        failures = [r for r in results if not r['hit_top1']]
        if failures:
            print(f'\n  错误分析 ({len(failures)} 条Top-1未命中):')
            for r in failures:
                print(f'    ❌ "{r["step"]}" → 期望ID={r["expected_id"]}, 实际选了ID={r["top1_id"]}({r["top1_name"]})  [{r["desc"]}]')

        all_results.extend([(industry_name, r) for r in results])

    # 汇总
    print('\n' + '=' * 80)
    print('汇总')
    print('=' * 80)
    total = len(all_results)
    top1 = sum(1 for _, r in all_results if r['hit_top1'])
    top3 = sum(1 for _, r in all_results if r['hit_top3'])
    top5 = sum(1 for _, r in all_results if r['hit_top5'])
    in_cand = sum(1 for _, r in all_results if r['in_candidates'])

    print(f'总用例数: {total}')
    print(f'Top-1 准确率: {top1}/{total} = {top1/total*100:.1f}%')
    print(f'Top-3 准确率: {top3}/{total} = {top3/total*100:.1f}%')
    print(f'Top-5 准确率: {top5}/{total} = {top5/total*100:.1f}%')
    print(f'召回率(在候选中): {in_cand}/{total} = {in_cand/total*100:.1f}%')

    # 按难度分类统计
    print('\n按用例难度分类:')
    CAT_MAP = {
        '基础': '基础匹配', '口语': '口语化', '同义': '同义替换',
        '术语': '行业术语', '问句': '问句式', '倒序': '词序颠倒',
    }
    categories = {}
    for _, r in all_results:
        label = CAT_MAP.get(r['desc'], '其他')
        categories.setdefault(label, []).append(r)
    for cat in ['基础匹配', '口语化', '同义替换', '行业术语', '问句式', '词序颠倒', '其他']:
        items = categories.get(cat, [])
        if not items:
            continue
        t = len(items)
        h = sum(1 for r in items if r['hit_top1'])
        ic = sum(1 for r in items if r['in_candidates'])
        print(f'  {cat}: Top-1 = {h}/{t} = {h/t*100:.1f}%, 召回 = {ic}/{t} = {ic/t*100:.1f}%')

    # 按失败模式分析
    print('\n失败模式分析:')
    not_in_cand = [(_, r) for _, r in all_results if not r['in_candidates']]
    in_cand_but_wrong = [(_, r) for _, r in all_results if r['in_candidates'] and not r['hit_top1']]
    print(f'  未进入候选集 (NOT_IN_CANDIDATES): {len(not_in_cand)}')
    print(f'  在候选集中但排名不是Top1: {len(in_cand_but_wrong)}')
    if not_in_cand:
        print('\n  未进入候选集的用例 (Top 20):')
        for ind, r in not_in_cand[:20]:
            print(f'    [{ind}] "{r["step"]}" → 期望ID={r["expected_id"]}  [{r["desc"]}]')
        if len(not_in_cand) > 20:
            print(f'    ... 还有 {len(not_in_cand)-20} 条')

    return all_results


def run_llm_test(all_profiles, test_cases):
    """测试完整流程：规则预选 + LLM 匹配。"""
    print('\n' + '=' * 80)
    print('接口匹配准确率测试 — LLM 匹配阶段')
    print('=' * 80)

    try:
        from apps.agent.services.llm.gateway import LLMGateway
        from apps.agent.services.planning.interface_matcher import InterfaceMatcher
    except ImportError as e:
        print(f'无法导入 LLM 模块: {e}')
        return

    llm = LLMGateway()
    matcher = InterfaceMatcher(llm)
    preselector = CandidatePreselector()

    total = 0
    correct = 0

    for step_text, expected_id, desc in test_cases:
        steps = [{'index': 1, 'text': step_text, 'resolved_text': step_text}]
        candidates_by_step = preselector.select(steps, all_profiles, limit=20)

        try:
            matches, llm_info = matcher.match(steps, candidates_by_step)
        except Exception as e:
            print(f'  ❌ LLM 调用失败: {e}')
            continue

        match = matches[0] if matches else {}
        selected_id = match.get('selected_interface_id')
        confidence = match.get('confidence', 0)
        reason = match.get('reason', '')
        hit = (selected_id == expected_id)

        total += 1
        if hit:
            correct += 1

        status = '✅' if hit else '❌'
        print(f'  {status} "{step_text}" → 期望ID={expected_id}, LLM选了ID={selected_id} '
              f'(confidence={confidence:.2f}) [{desc}]')
        if not hit:
            print(f'      LLM理由: {reason}')
            # 找到期望接口在候选中的排名
            for item in candidates_by_step:
                for i, c in enumerate(item.get('candidates', [])):
                    if c['interface_id'] == expected_id:
                        print(f'      期望接口在预选候选中排名: #{i+1} (pre_score={c["pre_score"]:.4f})')
                        break

        time.sleep(0.5)  # 避免 LLM 限流

    print(f'\nLLM 匹配准确率: {correct}/{total} = {correct/total*100:.1f}%' if total else '无结果')


# ============================================================================
# 双通道召回测试
# ============================================================================

# 模拟 StepPlanner 重写场景：original_goal 是用户的原始口语表达，
# step.text 是 LLM 重写后的规范化步骤。双通道应弥补重写后的信息丢失。
DUAL_CHANNEL_TEST_CASES = [
    # (original_goal, step_text, expected_interface_id, description)
    #
    # 关键设计：step.text 是 LLM 重写后【脱离接口名】的泛化描述，
    #           original_goal 保留用户原始口语表达。
    #           单通道只用 step.text → 可能匹配不上；
    #           双通道追加 original_goal → 通过语义召回补回。
    #
    # 电商 (ID 1-60)
    ('付钱', '完成支付流程', 38, 'LLM改写: 付钱→完成支付流程'),
    ('我要退货', '提交退换申请', 51, 'LLM改写: 退货→提交退换申请'),
    ('开发票', '处理发票请求', 30, 'LLM改写: 开发票→处理发票请求'),
    ('领券', '获取优惠券', 44, 'LLM改写: 领券→获取优惠券'),
    ('买东西', '下单采购', 23, 'LLM改写: 买东西→下单采购'),
    ('加车', '添加到购物篮', 33, 'LLM改写: 加车→添加到购物篮'),
    ('看评价', '查看商品反馈', 18, 'LLM改写: 看评价→查看商品反馈'),
    ('还有货吗', '检查商品可用性', 20, 'LLM改写: 还有货吗→检查可用性'),

    # 物流 (ID 101-160)
    ('寄包裹', '创建配送单据', 101, 'LLM改写: 寄包裹→创建配送单据'),
    ('取件', '揽收取件操作', 111, 'LLM改写: 取件→揽收取件操作'),
    ('送快递', '执行配送任务', 112, 'LLM改写: 送快递→执行配送任务'),
    ('快递丢了', '申报丢失赔偿', 144, 'LLM改写: 快递丢了→申报丢失赔偿'),
    ('附近网点', '查找最近站点', 121, 'LLM改写: 附近网点→查找最近站点'),

    # ERP (ID 201-260)
    ('收钱', '登记收款', 242, 'LLM改写: 收钱→登记收款'),
    ('付钱', '登记付款', 243, 'LLM改写: 付钱→登记付款'),
    ('发工资', '执行薪资处理', 255, 'LLM改写: 发工资→执行薪资处理'),
    ('做账', '编制会计分录', 239, 'LLM改写: 做账→编制会计分录'),
    ('看利润', '查看盈利数据', 258, 'LLM改写: 看利润→查看盈利数据'),
    ('查员工', '检索人员信息', 251, 'LLM改写: 查员工→检索人员信息'),

    # 金融 (ID 301-360)
    ('存钱', '办理储蓄业务', 311, 'LLM改写: 存钱→办理储蓄业务'),
    ('取钱', '办理取款操作', 312, 'LLM改写: 取钱→办理取款操作'),
    ('借钱', '提交信贷申请', 333, 'LLM改写: 借钱→提交信贷申请'),
    ('冻卡', '限制账户使用', 304, 'LLM改写: 冻卡→限制账户使用'),
    ('买基金', '执行基金投资', 350, 'LLM改写: 买基金→执行基金投资'),
    ('卖基金', '赎回基金份额', 351, 'LLM改写: 卖基金→赎回基金份额'),

    # 支付 (ID 401-460)
    ('付钱', '发起收款请求', 401, 'LLM改写: 付钱→发起收款请求'),
    ('退钱', '发起退款流程', 411, 'LLM改写: 退钱→发起退款流程'),
    ('收款', '处理入账', 401, 'LLM改写: 收款→处理入账'),
    ('查流水', '查看账户记录', 459, 'LLM改写: 查流水→查看账户记录'),
    ('结算', '执行资金清算', 429, 'LLM改写: 结算→执行资金清算'),

    # 复合目标：original_goal 包含口语化多步骤，step.text 是 LLM 提取的规范化子步骤
    ('付钱并查状态', '完成支付操作', 38, '复合: 付钱→完成支付操作(脱离)'),
    ('下单然后查物流', '提交采购请求', 23, '复合: 下单→提交采购请求(脱离)'),
    ('查余额再转账', '查看资金情况', 307, '复合: 查余额→查看资金情况(脱离)'),
    ('冻卡然后报警', '冻结账户', 304, '复合: 冻卡→冻结账户(部分匹配)'),
]


def run_dual_channel_test():
    """测试双通道召回：对比有/无 original_goal 时候选召回的差异。"""
    import time as _time

    # 合并所有接口
    all_profiles = []
    for _, interfaces, _ in INDUSTRIES:
        all_profiles.extend(interfaces)

    # 构建 embedding 索引
    emb = EmbeddingIndexer(top_k=30)
    emb.build(all_profiles)
    preselector = CandidatePreselector(embedding_indexer=emb)

    print('=' * 80)
    print('双通道召回测试 — original_goal 对匹配的影响')
    print('=' * 80)

    # 阶段 A：单通道（step.text only，无 original_goal）
    print('\n--- 阶段 A: 单通道 (step.text only) ---')
    results_single = []
    for original_goal, step_text, expected_id, desc in DUAL_CHANNEL_TEST_CASES:
        steps = [{'index': 1, 'text': step_text, 'resolved_text': step_text}]
        candidates_by_step = preselector.select(steps, all_profiles, limit=20)
        candidates = candidates_by_step[0]['candidates']
        rank = None
        for i, c in enumerate(candidates):
            if c['interface_id'] == expected_id:
                rank = i + 1
                break
        top_c = candidates[0] if candidates else None
        results_single.append({
            'original_goal': original_goal,
            'step_text': step_text,
            'expected_id': expected_id,
            'desc': desc,
            'rank': rank,
            'in_candidates': rank is not None,
            'hit_top1': top_c and top_c['interface_id'] == expected_id,
            'top1_id': top_c['interface_id'] if top_c else None,
            'top1_name': top_c['name'] if top_c else 'N/A',
        })

    # 阶段 B：双通道（step.text + original_goal）
    print('--- 阶段 B: 双通道 (step.text + original_goal) ---')
    results_dual = []
    for original_goal, step_text, expected_id, desc in DUAL_CHANNEL_TEST_CASES:
        steps = [{'index': 1, 'text': step_text, 'resolved_text': step_text,
                  'original_goal': original_goal}]
        candidates_by_step = preselector.select(steps, all_profiles, limit=20)
        candidates = candidates_by_step[0]['candidates']
        rank = None
        for i, c in enumerate(candidates):
            if c['interface_id'] == expected_id:
                rank = i + 1
                break
        top_c = candidates[0] if candidates else None
        # 检查是否有双通道召回标记
        dual_marked = False
        for c in candidates:
            if c['interface_id'] == expected_id:
                r = c.get('pre_reason', [])
                dual_marked = any('双通道' in str(x) for x in r)
                break
        results_dual.append({
            'original_goal': original_goal,
            'step_text': step_text,
            'expected_id': expected_id,
            'desc': desc,
            'rank': rank,
            'in_candidates': rank is not None,
            'hit_top1': top_c and top_c['interface_id'] == expected_id,
            'top1_id': top_c['interface_id'] if top_c else None,
            'top1_name': top_c['name'] if top_c else 'N/A',
            'dual_channel_marked': dual_marked,
        })

    # 对比
    print('\n' + '=' * 80)
    print('双通道 vs 单通道 对比')
    print('=' * 80)
    total = len(DUAL_CHANNEL_TEST_CASES)
    s_recall = sum(1 for r in results_single if r['in_candidates'])
    d_recall = sum(1 for r in results_dual if r['in_candidates'])
    s_top1 = sum(1 for r in results_single if r['hit_top1'])
    d_top1 = sum(1 for r in results_dual if r['hit_top1'])
    print(f'  用例数:        {total}')
    print(f'  Top-1:         {s_top1}/{total} ({s_top1/total*100:.1f}%) → {d_top1}/{total} ({d_top1/total*100:.1f}%)  ({d_top1-s_top1:+d})')
    print(f'  召回率:        {s_recall}/{total} ({s_recall/total*100:.1f}%) → {d_recall}/{total} ({d_recall/total*100:.1f}%)  ({d_recall-s_recall:+d})')

    # 逐条详情
    print('\n逐条对比:')
    for i, (rs, rd) in enumerate(zip(results_single, results_dual)):
        s_status = '✅' if rs['hit_top1'] else ('⚠️' if rs['in_candidates'] else '❌')
        d_status = '✅' if rd['hit_top1'] else ('⚠️' if rd['in_candidates'] else '❌')
        improved = ''
        if rd['in_candidates'] and not rs['in_candidates']:
            improved = ' 🆕 双通道新召回'
        elif rd['hit_top1'] and not rs['hit_top1']:
            improved = ' ⬆️ 双通道提升Top1'
        elif rd['in_candidates'] and rs['in_candidates'] and rd['rank'] < rs['rank']:
            improved = f' ⬆️ 排名提升 #{rs["rank"]}→#{rd["rank"]}'
        dual_mark = ' [双通道]' if rd['dual_channel_marked'] else ''
        print(f'  {s_status}→{d_status} "{rs["original_goal"]}" / step="{rs["step_text"]}" '
              f'→ ID={rs["expected_id"]} '
              f'(单#{rs["rank"] or "X"} 双#{rd["rank"] or "X"}){dual_mark}{improved}  [{rs["desc"]}]')


if __name__ == '__main__':
    # 阶段1a：纯 token 规则预选测试
    print('\n' + '#' * 80)
    print('# PHASE 1a: Token-only preselector')
    print('#' * 80)
    results_token = run_preselector_test(use_embedding=False)

    # 阶段1b：token + embedding 语义召回合并测试
    print('\n\n' + '#' * 80)
    print('# PHASE 1b: Token + Embedding preselector')
    print('#' * 80)
    results_merged = run_preselector_test(use_embedding=True)

    # 对比
    print('\n\n' + '=' * 80)
    print('BEFORE vs AFTER 对比')
    print('=' * 80)
    def _stats(results):
        total = len(results)
        top1 = sum(1 for _, r in results if r['hit_top1'])
        top3 = sum(1 for _, r in results if r['hit_top3'])
        in_c = sum(1 for _, r in results if r['in_candidates'])
        not_in = sum(1 for _, r in results if not r['in_candidates'])
        return total, top1, top3, in_c, not_in

    t1, top1_1, top3_1, ic1, nic1 = _stats(results_token)
    t2, top1_2, top3_2, ic2, nic2 = _stats(results_merged)
    print(f'  总用例数:            {t1}')
    print(f'  Top-1 准确率:        {top1_1/t1*100:.1f}% → {top1_2/t2*100:.1f}%  ({top1_2-top1_1:+d})')
    print(f'  Top-3 准确率:        {top3_1/t1*100:.1f}% → {top3_2/t2*100:.1f}%  ({top3_2-top3_1:+d})')
    print(f'  召回率:              {ic1/t1*100:.1f}% → {ic2/t2*100:.1f}%  ({ic2-ic1:+d})')
    print(f'  NOT_IN_CANDIDATES:   {nic1} → {nic2}  ({nic2-nic1:+d})')

    # 分难度对比
    CAT_MAP = {
        '基础': '基础匹配', '口语': '口语化', '同义': '同义替换',
        '术语': '行业术语', '问句': '问句式', '倒序': '词序颠倒',
    }
    print('\n分难度召回率对比:')
    for cat_label in ['基础匹配', '口语化', '同义替换', '行业术语', '问句式', '词序颠倒']:
        ic_before = sum(1 for _, r in results_token if CAT_MAP.get(r['desc']) == cat_label and r['in_candidates'])
        ic_after = sum(1 for _, r in results_merged if CAT_MAP.get(r['desc']) == cat_label and r['in_candidates'])
        t_cat = sum(1 for _, r in results_token if CAT_MAP.get(r['desc']) == cat_label)
        if t_cat == 0:
            continue
        print(f'  {cat_label}: {ic_before}/{t_cat} ({ic_before/t_cat*100:.0f}%) → {ic_after}/{t_cat} ({ic_after/t_cat*100:.0f}%)  ({ic_after-ic_before:+d})')

    # embedding 新召回的用例
    before_ids = {(ind, r['step'], r['expected_id']) for ind, r in results_token if r['in_candidates']}
    after_ids = {(ind, r['step'], r['expected_id']) for ind, r in results_merged if r['in_candidates']}
    newly_recalled = after_ids - before_ids
    if newly_recalled:
        print(f'\n语义召回新找回的用例 ({len(newly_recalled)} 条):')
        for ind, step, eid in sorted(newly_recalled, key=lambda x: x[0]):
            print(f'  [{ind}] "{step}" → ID={eid}')

    # 阶段2：LLM 匹配测试（需要配置 LLM）
    llm_enabled = os.environ.get('AGENT_OPENAI_API_KEY') or os.environ.get('AGENT_OPENAI_BASE_URL')
    if llm_enabled:
        print('\n\n检测到 LLM 配置，开始 LLM 匹配测试...')
        all_profiles = []
        all_cases = []
        for industry_name, interfaces, test_cases in INDUSTRIES:
            all_profiles.extend(interfaces)
            all_cases.extend(test_cases)
        run_llm_test(all_profiles, all_cases)
    else:
        print('\n\n未检测到 LLM 配置(AGENT_OPENAI_API_KEY/AGENT_OPENAI_BASE_URL)，跳过 LLM 匹配测试')
        print('如需测试 LLM 匹配，请在 .env 中配置后重新运行')

    # 阶段3：双通道召回测试
    print('\n\n' + '#' * 80)
    print('# PHASE 3: Dual-channel recall test (original_goal)')
    print('#' * 80)
    run_dual_channel_test()