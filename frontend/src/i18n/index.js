import { computed, nextTick, ref, watch } from 'vue'

const STORAGE_KEY = 'bug_shoot_locale'

const zh = {
  localeName: '中文',
  language: '语言',
}

const en = {
  localeName: 'English',
  language: 'Language',
  '缺陷猎手': 'TestPilot',
  'Bug Shoot': 'TestPilot',
  '首页': 'Home',
  '接口测试': 'API Test',
  '链路测试': 'Chain Test',
  'Agent 编排': 'Agent Planner',
  '个人信息': 'Profile',
  '退出登录': 'Log out',
  '选择项目': 'Select project',
  '新建项目': 'New project',
  '项目成员': 'Project members',
  '选择环境': 'Select environment',
  '默认项目': 'Default project',
  '测试环境': 'Test environment',
  '本地演示环境': 'Local demo environment',
  '创建订单，查询订单': 'Create order, query order',
  '项目名称': 'Project name',
  '请输入项目名称': 'Please enter project name',
  '用户名或邮箱': 'Username or email',
  '邀请': 'Invite',
  '用户': 'User',
  '角色': 'Role',
  '加入时间': 'Joined at',
  '操作': 'Actions',
  '移除': 'Remove',
  '无邮箱': 'No email',
  '确认退出': 'Confirm logout',
  '确定要退出登录吗？': 'Are you sure you want to log out?',
  '删除项目': 'Delete project',
  '默认项目不能删除': 'The default project cannot be deleted.',
  '确定要删除项目': 'Are you sure you want to delete project ',
  '吗？该操作会删除项目下的接口、环境、链路和执行记录。': '? This will delete APIs, environments, chains, and execution records under the project.',
  '项目已删除': 'Project deleted',
  '成员已加入项目': 'Member added to project',
  '角色已更新': 'Role updated',
  '移除成员': 'Remove member',
  '确定要移除': 'Are you sure you want to remove',
  '吗？': '?',
  '成员已移除': 'Member removed',
  '删除': 'Delete',
  '取消': 'Cancel',
  '登录已过期，请重新登录': 'Login expired. Please sign in again.',
  '没有操作权限': 'No permission.',
  '请求的资源不存在': 'Resource not found.',
  '请求参数错误': 'Invalid request parameters.',
  '服务器错误': 'Server error.',
  '网络连接失败': 'Network connection failed.',

  '用户名': 'Username',
  '密码': 'Password',
  '邮箱（可选）': 'Email (optional)',
  '密码（至少6位）': 'Password (at least 6 characters)',
  '确认密码': 'Confirm password',
  '登 录': 'Sign in',
  '注 册': 'Sign up',
  '默认管理员账号: admin / admin123': 'Default admin account: admin / admin123',
  '没有账号？': 'No account?',
  '去注册': 'Sign up',
  '已有账号？': 'Already have an account?',
  '去登录': 'Sign in',
  '请输入用户名': 'Please enter username',
  '请输入密码': 'Please enter password',
  '请输入用户名或邮箱': 'Please enter username or email',
  '用户名至少3个字符': 'Username must be at least 3 characters',
  '密码至少6位': 'Password must be at least 6 characters',
  '请确认密码': 'Please confirm password',
  '两次密码不一致': 'Passwords do not match',
  '登录成功': 'Signed in',
  '注册成功': 'Registered',
  '抱歉，您没有权限访问此页面。': 'Sorry, you do not have permission to access this page.',
  '返回首页': 'Back home',

  '接口列表': 'API list',
  '导入': 'Import',
  '新建分组': 'New group',
  '响应结果': 'Response',
  '断言校验': 'Assertions',
  '清除': 'Clear',
  '输入分组名称': 'Group name',
  '分组名称不能为空': 'Group name is required',
  '分组创建成功': 'Group created',
  '默认分组': 'Default group',
  '暂无接口': 'No APIs',
  '搜索接口...': 'Search APIs...',
  '接口名称（保存时使用）': 'API name (used when saving)',
  '选择分组': 'Select group',
  '更新': 'Update',
  '保存': 'Save',
  '发送': 'Send',
  '导入cURL': 'Import cURL',
  '参数': 'Params',
  '请求头': 'Headers',
  '消息': 'Message',
  '服务名': 'Service',
  '方法名': 'Method',
  '参数 (JSON)': 'Params (JSON)',
  'ws:// 或 wss:// 地址': 'ws:// or wss:// URL',
  'RPC 服务地址 (HTTP)': 'RPC service URL (HTTP)',
  '输入要发送的消息内容': 'Enter message content',
  'RPC 服务名 (可选)': 'RPC service (optional)',
  'RPC 方法名': 'RPC method',
  '请求体内容': 'Request body',
  '请输入请求地址': 'Please enter request URL',
  '更新成功': 'Updated',
  '保存成功': 'Saved',
  '响应体': 'Body',
  '响应头': 'Headers',
  '键': 'Key',
  '值': 'Value',
  '格式化': 'Pretty',
  '原始': 'Raw',
  '复制': 'Copy',
  '点击 发送 按钮查看响应结果': 'Click Send to view the response',
  '已复制到剪贴板': 'Copied to clipboard',
  '添加一行': 'Add row',
  '通过': 'Passed',

  '链路名称': 'Chain name',
  '环境：': 'Environment:',
  '全局参数': 'Globals',
  '运行': 'Run',
  '请先创建链路': 'Please create a chain first',
  '请先保存链路再运行': 'Please save the chain before running',
  '链路已保存': 'Chain saved',
  '保存失败': 'Save failed',
  '链路执行完成，全部通过': 'Chain run completed. All passed.',
  '链路执行完成，': 'Chain run completed. ',
  ' 个节点失败': ' node(s) failed',
  '链路执行失败': 'Chain run failed',
  '未知错误': 'Unknown error',
  '参数名': 'Key',
  '参数值': 'Value',
  '说明': 'Description',
  '添加参数': 'Add parameter',
  '节点标签': 'Node label',
  '选择接口': 'Select API',
  '请选择已保存的接口': 'Select a saved API',
  '变量引用': 'Variable references',
  '用 {{vars.变量名}} 引用上游提取值，{{globals.变量名}} 引用全局参数': 'Use {{vars.name}} for upstream extracted values, and {{globals.name}} for globals.',
  '上游变量:': 'Upstream variable:',
  '全局参数:': 'Global:',
  '添加请求头': 'Add header',
  '请求体字段': 'Body fields',
  '添加字段': 'Add field',
  '切换为完整请求体': 'Switch to full body',
  '切换为字段编辑': 'Switch to field editor',
  '请求体': 'Body',
  '请求体内容，可使用 {{vars.xxx}} 引用变量': 'Request body. Use {{vars.xxx}} to reference variables.',
  'WS 消息': 'WS message',
  'WebSocket 发送消息': 'WebSocket message',
  'RPC 方法': 'RPC method',
  '方法名': 'Method name',
  '提取规则': 'Extraction rules',
  '添加': 'Add',
  '变量名': 'Variable name',
  '暂无提取规则': 'No extraction rules',
  '断言规则': 'Assertion rules',
  '期望值': 'Expected value',
  '超时': 'Timeout',
  '秒': 'sec',
  '暂无断言规则': 'No assertion rules',
  '执行配置': 'Execution config',
  '失败重试': 'Retry on failure',
  '节点执行失败后的最大重试次数': 'Maximum retries after node execution fails',
  '重试间隔(秒)': 'Retry interval (sec)',
  '脚本': 'Script',
  '超时(秒)': 'Timeout (sec)',
  '延迟(秒)': 'Delay (sec)',
  '条件类型': 'Condition type',
  '变量来源': 'Variable source',
  '选择变量': 'Select variable',
  '比较符': 'Operator',
  '等于': 'equals',
  '不等于': 'not equals',
  '包含': 'contains',
  '不包含': 'does not contain',
  '大于': 'greater than',
  '小于': 'less than',
  '变量': 'Variable',
  '请先运行链路后，可通过 JSONPath 选择上游接口响应字段': 'Run the chain first, then select upstream response fields with JSONPath.',
  '执行结果': 'Execution result',
  '实际值': 'Actual value',
  '接口返回': 'API response',
  '脚本断言占位符': `# Available variables: vars, globals, response
# vars - variables extracted from upstream nodes
# response.status_code / .body / .headers
assert vars.get('token') is not None`,
  '条件脚本占位符': `# Available variables: vars, globals, response
# A passing script goes to the True branch. A failed assertion goes to the False branch.
# response.status_code / .body / .headers
assert response.status_code == 200`,
  '节点面板': 'Node panel',
  '开始': 'Start',
  '结束': 'End',
  '开始节点': 'Start node',
  '结束节点': 'End node',
  '点击画布放置': 'Click canvas to place',
  '链路列表': 'Chain list',
  '新建': 'New',
  '就绪': 'Ready',
  '草稿': 'Draft',
  '暂无链路': 'No chains',
  '新建链路': 'New chain',
  '链路已创建': 'Chain created',
  '链路必须且只能包含一个开始节点和一个结束节点': 'A chain must contain exactly one start node and one end node.',
  '删除链路': 'Delete chain',
  '确定要删除': 'Are you sure you want to delete ',
  '吗？删除后不可恢复。': '? This cannot be undone.',
  '链路已删除': 'Chain deleted',
  '节点属性': 'Node properties',
  '接口节点': 'API node',
  '脚本节点': 'Script node',
  '定时器': 'Timer',
  '条件分支': 'Condition',
  '等待': 'Wait',
  '点击节点连线创建 · 点击空白放置 · Esc 取消': 'Click a node to connect · click empty space to place · Esc to cancel',

  '根据自然语言目标生成链路草稿，确认后可保存到编辑器或直接运行调试。': 'Generate chain drafts from natural language goals. Save to editor or run directly after review.',
  '目标描述': 'Goal',
  '描述你要自动化执行的业务链路…': 'Describe the business flow you want to automate...',
  '生成链路草稿': 'Generate draft',
  '校验结果': 'Validation',
  '暂无结果': 'No result',
  '编排失败': 'Planning failed',
  '所有步骤已匹配接口，可保存或运行': 'All steps are matched. You can save or run.',
  '需要调试确认': 'Debug confirmation required',
  '需要授权试跑': 'Trial run authorization required',
  '授权本次试跑': 'Authorize this trial run',
  '授权调试并重新规划': 'Authorize debugging and replan',
  '跳过试跑': 'Skip trial run',
  '第 {step} 步「{name}」是写接口，当前环境需要授权试运行以获取响应字段': 'Step {step} "{name}" is a write API. Authorize a trial run in this environment to collect response fields.',
  '第 {step} 步「{name}」是写接口，链路规划完成后请进入编辑器授权调试以补充响应字段': 'Step {step} "{name}" is a write API. After planning is complete, open the editor and authorize debugging to collect response fields.',
  '保存并打开编辑器': 'Save and open editor',
  '直接运行': 'Run directly',
  '编排进度': 'Progress',
  '生成时展示进度': 'Progress appears while generating',
  '查看规划内容 JSON': 'View planning JSON',
  '识别步骤': 'Recognized steps',
  '生成后展示步骤': 'Steps appear after generation',
  '未匹配到接口': 'No API matched',
  '参数需求': 'Parameter requirements',
  '参数已满足': 'Parameters satisfied',
  '该接口未识别到请求参数': 'No request parameters detected',
  '接口候选': 'API candidates',
  '暂无候选接口': 'No candidates',
  '未匹配接口': 'Unmatched',
  '已匹配': 'Matched',
  '分数': 'Score',
  '方法': 'Method',
  '接口': 'API',
  '地址': 'URL',
  '解释': 'Explain',
  '最终选择': 'Selected',
  '可展开': 'Expand',
  '记住': 'Remember',
  '模型判断': 'Model judgment',
  '规则评分': 'Rule score',
  '命中原因': 'Reasons',
  '未找到相关候选接口': 'No relevant API candidates found',
  '项目中没有与该步骤语义匹配的接口，请在链路编辑器中手动创建或选择接口': 'No API semantically matches this step. Create or select one in the chain editor.',
  '运行结果': 'Run result',
  '执行完成': 'Completed',
  '执行失败': 'Failed',
  '自动诊断': 'Auto diagnostics',
  '错误': 'Error',
  '警告': 'Warning',
  '提示': 'Info',
  '变量提取': 'Variable extraction',
  '断言': 'Assertion',
  '收起响应': 'Hide response',
  '查看响应': 'View response',
  '链路草稿 JSON': 'Chain draft JSON',
  '解析步骤': 'Parse steps',
  '检索接口': 'Search APIs',
  '匹配接口': 'Match APIs',
  '规划依赖': 'Plan dependencies',
  '生成草稿': 'Generate draft',
  '校验结果': 'Validate',
  '步骤规划': 'Step planning',
  '接口匹配': 'API matching',
  '依赖规划': 'Dependency planning',
  '断言规划': 'Assertion planning',
  '模型正在拆解目标并识别业务步骤': 'The model is splitting the goal and identifying business steps',
  '已生成业务步骤': 'Business steps generated',
  '模型正在从候选接口中选择匹配项': 'The model is selecting APIs from candidates',
  '已完成接口匹配': 'API matching completed',
  '模型正在规划上下游参数传递': 'The model is planning upstream/downstream parameters',
  '已生成参数依赖规划': 'Parameter dependency plan generated',
  '正在根据响应结构和依赖字段生成断言': 'Generating assertions from response structure and dependency fields',
  '已生成断言规则': 'Assertion rules generated',
  '正在编排链路': 'Planning chain',
  '编排失败，请查看校验结果': 'Planning failed. Check validation details.',
  '编排完成': 'Planning completed',
  '规则引擎': 'Rule engine',
  '第': 'Step',
  '步：': ': ',
  'Step': 'Step',
  '{count} 个步骤未匹配到接口，请在编辑器中手动选择接口后再运行': '{count} step(s) are not matched. Select APIs in the editor before running.',
  '{count} 个参数需确认': '{count} parameter(s) need review',
  '{count} 条断言': '{count} assertion(s)',
  '该步骤暂未规划断言': 'No assertions planned for this step',
  '默认启用': 'Enabled by default',
  '建议确认': 'Needs review',
  '置信度': 'Confidence',
  '提取': 'Extract',
  '打开已保存链路': 'Open saved chain',
  '未选择接口': 'No API selected',
  '已匹配 {count} 个接口': '{count} API(s) matched',
  '缺少参数：': 'Missing parameter: ',
  '条断言默认启用': 'assertion(s) enabled by default',
  '存在': 'exists',
  '不存在': 'does not exist',
  '基础断言': 'Base assertion',
  '响应结构': 'Response schema',
  '依赖字段': 'Dependency field',
  '业务语义': 'Business semantic',
  '模型补充': 'Model suggestion',
  '用户记忆': 'User memory',
  '规则': 'Rule',
  '请输入要编排的目标': 'Please enter a goal to plan',
  '任务已提交，正在编排中...': 'Task submitted. Planning...',
  '提交任务失败': 'Failed to submit task',
  '已生成链路草稿': 'Chain draft generated',
  '由 Agent 生成的链路草稿': 'Chain draft generated by Agent',
  '链路已保存，正在执行...': 'Chain saved. Running...',
  '链路执行完成，{count} 个节点失败': 'Chain run completed. {count} node(s) failed.',
  '执行链路失败': 'Failed to run chain',
  '保存匹配记忆失败': 'Failed to save match memory',
  '已记住该匹配，下次同类步骤会优先推荐': 'Match remembered. Similar steps will prefer it next time.',
  '耗时': 'Duration',
  '完成': 'Done',
  '进行中': 'Running',
  '失败': 'Failed',
  '等待开始': 'Waiting',
  '已映射': 'Mapped',
  '默认值': 'Default',
  '建议映射': 'Suggested',
  '需补充': 'Missing',
  '总分': 'Total',
  '名称完全匹配': 'Exact name',
  '名称相似': 'Name similarity',
  '语义相似': 'Semantic similarity',
  '描述命中': 'Description hit',
  'URL 命中': 'URL hit',
  '路径命中': 'Path hit',
  '请求字段': 'Request fields',
  '响应字段': 'Response fields',
  '分组命中': 'Group hit',
  '接口名称与步骤完全一致': 'API name exactly matches the step',
  '接口名称与步骤完全一致，且 pre_score 较高': 'API name exactly matches the step and pre_score is high',
  '接口名称与步骤完全匹配，基础分 0.85': 'API name exactly matches the step, base score 0.85',
  '基础成功断言：HTTP 状态码小于 400': 'Base success assertion: HTTP status code is less than 400',
  '真实响应中 code 为 0，符合常见成功码结构': 'The real response has code = 0, matching a common success-code schema',
  '真实响应中存在 data 字段，作为业务数据结构断言': 'The real response contains data, used as a business data schema assertion',
  '来源基础分(base)': 'Source base score (base)',
  '来源基础分(schema)': 'Source base score (schema)',
  '来源基础分(semantic)': 'Source base score (semantic)',
  '真实响应存在该字段': 'Field exists in real response',
  '常见关键字段': 'Common key field',
  '用户显式校验意图': 'Explicit user assertion intent',
  '来自接口已有响应字段': 'From existing API response fields',
  '缺少真实响应证据': 'Missing real response evidence',
  '后续节点使用该字段': 'Used by downstream node',
  '动态字段不适合固定值断言': 'Dynamic field is not suitable for fixed-value assertion',
  '对话式编排': 'Conversational planning',
  '执行到哪个阶段，就展示哪个阶段的规划细节': 'Show each planning detail as its stage runs',
  '待开始': 'Not started',
  '提交中': 'Submitting',
  '编排中': 'Planning',
  '已完成': 'Completed',
  '已取消': 'Cancelled',
  '你': 'You',
  '描述你的链路目标': 'Describe your chain goal',
  'Agent 会按规划阶段逐步展示步骤、接口匹配、参数依赖、断言和草稿。': 'The agent will progressively show steps, API matching, parameter dependencies, assertions, and the draft.',
  '等待步骤规划输出': 'Waiting for step planning output',
  '等待接口匹配输出': 'Waiting for API matching output',
  '没有选择接口，请查看候选或进入编辑器处理': 'No API selected. Review candidates or handle it in the editor.',
  '候选接口与确认': 'API candidates and confirmation',
  '确认': 'Confirm',
  '候选': 'Candidate',
  '暂无参数依赖': 'No parameter dependencies',
  '暂无断言规划': 'No assertion planning yet',
  '展开查看识别到的业务步骤': 'Expand to view recognized business steps',
  '展开查看接口选择原因': 'Expand to view API selection reasons',
  '展开查看参数如何传递': 'Expand to view parameter passing',
  '展开查看生成的断言': 'Expand to view generated assertions',
  '展开查看完整草稿和模型信息': 'Expand to view the full draft and model info',
  '我正在拆解你的目标，识别需要执行的业务步骤。': 'I am breaking down your goal and identifying the business steps to run.',
  '我正在从项目接口中为每个步骤选择最合适的接口。': 'I am selecting the best API for each step from this project.',
  '我正在规划步骤之间的参数传递和缺失参数。': 'I am planning parameter passing and missing inputs between steps.',
  '我正在根据响应结构和业务目标生成断言规则。': 'I am generating assertion rules from the response structure and business goal.',
  '识别到 {count} 个业务步骤：': 'Recognized {count} business step(s): ',
  '已完成步骤规划。': 'Step planning completed.',
  '已完成接口匹配：{matched}/{total} 个步骤匹配到接口。': 'API matching completed: {matched}/{total} step(s) matched.',
  '已完成参数依赖规划，暂无跨步骤参数依赖。': 'Parameter dependency planning completed. No cross-step dependencies.',
  '已规划 {count} 条参数依赖': 'Planned {count} parameter dependenc(ies)',
  '仍有 {count} 个参数需确认': '{count} parameter(s) still need review',
  '已完成断言规划，暂无默认断言。': 'Assertion planning completed. No default assertions.',
  '已生成 {count} 条断言规则。': 'Generated {count} assertion rule(s).',
  '该阶段执行失败': 'This stage failed',
  '编排已取消': 'Planning cancelled',
  '任务已取消，你可以调整目标后重新编排。': 'Task cancelled. You can adjust the goal and plan again.',
  '链路草稿': 'Chain draft',
  '链路草稿已生成。': 'Chain draft generated.',
  '链路草稿已生成，但有写接口需要授权调试后继续补充响应字段。': 'Chain draft generated, but write APIs need debugging authorization to collect response fields.',
  '链路草稿已生成，所有步骤已匹配接口，可保存或直接运行。': 'Chain draft generated. All steps are matched, so you can save or run directly.',
  '重新编排': 'Replan',
  '开始编排': 'Start planning',
  '取消任务': 'Cancel task',
  '任务已取消': 'Task cancelled',
  '正在取消任务...': 'Cancelling task...',
  '取消任务失败': 'Failed to cancel task',
  '从断点恢复中，重新获取授权接口的响应...': 'Resuming from checkpoint and collecting authorized API responses...',
  '恢复任务失败': 'Failed to resume task',
}

const messages = { zh, en }
const currentLocale = ref(localStorage.getItem(STORAGE_KEY) || 'zh')
const originalText = new WeakMap()
const originalAttrs = new WeakMap()

export const locale = computed(() => currentLocale.value)

export function setLocale(value) {
  currentLocale.value = value === 'en' ? 'en' : 'zh'
  localStorage.setItem(STORAGE_KEY, currentLocale.value)
}

export function toggleLocale() {
  setLocale(currentLocale.value === 'zh' ? 'en' : 'zh')
}

export function t(key, fallback = key) {
  if (currentLocale.value === 'zh') return fallback
  return messages.en[key] || fallback
}

export function translateText(value) {
  const text = String(value ?? '')
  if (currentLocale.value === 'zh') return text
  const trimmed = text.trim()
  const translated = messages.en[trimmed] || translatePattern(trimmed)
  if (!translated) return text
  return text.replace(trimmed, translated)
}

function translatePattern(text) {
  const rules = [
    [/^第 (\d+) 步：(.+)$/, (_, n, name) => `Step ${n}: ${name}`],
    [/^第 (\d+) 步$/, (_, n) => `Step ${n}`],
    [/^(\d+) 个参数需确认$/, (_, n) => `${n} parameter(s) need review`],
    [/^耗时 (.+)$/, (_, v) => `Duration ${v}`],
    [/^置信度 (\d+)%$/, (_, v) => `Confidence ${v}%`],
    [/^已匹配 (\d+) 个接口$/, (_, n) => `${n} API(s) matched`],
    [/^打开已保存链路 #(.+)$/, (_, id) => `Open saved chain #${id}`],
    [/^提取 (.+) ← (.+)$/, (_, k, p) => `Extract ${k} <- ${p}`],
    [/^置信度 (\d+)%：(.+)$/, (_, v, reason) => `Confidence ${v}%: ${translateText(reason)}`],
    [/^第 (\d+) 步：(.+)（(\d+)%） - (.+)$/, (_, n, name, confidence, reason) => `Step ${n}: ${translateText(name)} (${confidence}%) - ${translateText(reason)}`],
    [/^第 (\d+) 步：(.+)$/, (_, n, value) => `Step ${n}: ${translateText(value)}`],
    [/^根据用户校验意图“(.+)”生成业务断言$/, (_, intent) => `Generated business assertion from user assertion intent "${translateText(intent)}"`],
    [/^根据用户校验意图“(.+)”和接口已有响应字段生成断言；试运行未获取真实响应，建议确认环境后运行$/, (_, intent) => `Generated assertion from user assertion intent "${translateText(intent)}" and existing API response fields; no real response was collected, confirm the environment before running.`],
    [/^根据接口语义和真实响应字段补充业务字段“(.+)”存在性断言$/, (_, field) => `Added existence assertion for business field "${field}" from API semantics and real response fields`],
    [/^后续第 (\d+) 步需要使用 (.+)，因此需要确认响应中存在该字段$/, (_, n, field) => `Step ${n} uses ${field}, so this field must exist in the response`],
    [/^缺少参数：(.+)$/, (_, field) => `Missing parameter: ${field}`],
  ]
  for (const [pattern, render] of rules) {
    const match = text.match(pattern)
    if (match) return render(...match)
  }
  return ''
}

export function installDomI18n(root = document.body) {
  const apply = () => translateDom(root)
  nextTick(apply)
  const observer = new MutationObserver(() => nextTick(apply))
  observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label'] })
  watch(currentLocale, () => nextTick(apply))
  return () => observer.disconnect()
}

function translateDom(root) {
  if (!root) return
  translateNode(root)
}

function translateNode(node) {
  if (!node) return
  if (node.nodeType === Node.TEXT_NODE) {
    translateTextNode(node)
    return
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return
  const tag = node.tagName?.toLowerCase()
  if (['script', 'style', 'textarea', 'input', 'pre', 'code'].includes(tag)) return
  translateAttrs(node)
  for (const child of Array.from(node.childNodes)) translateNode(child)
}

function translateTextNode(node) {
  const raw = originalText.get(node) ?? node.nodeValue
  if (!originalText.has(node)) originalText.set(node, raw)
  const next = currentLocale.value === 'zh' ? raw : translateText(raw)
  if (node.nodeValue !== next) node.nodeValue = next
}

function translateAttrs(el) {
  for (const attr of ['placeholder', 'title', 'aria-label']) {
    if (!el.hasAttribute?.(attr)) continue
    let stored = originalAttrs.get(el)
    if (!stored) {
      stored = {}
      originalAttrs.set(el, stored)
    }
    if (!stored[attr]) stored[attr] = el.getAttribute(attr)
    const raw = stored[attr]
    const next = currentLocale.value === 'zh' ? raw : translateText(raw)
    if (el.getAttribute(attr) !== next) el.setAttribute(attr, next)
  }
}
