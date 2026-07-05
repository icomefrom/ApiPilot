<template>
  <div class="assertion-panel">
    <!-- Tab 切换 -->
    <a-segmented v-model:value="activeTab" :options="TAB_OPTIONS" class="tab-switch" />

    <!-- ===== JSONPath 断言 Tab ===== -->
    <template v-if="activeTab === 'jsonpath'">
      <!-- 断言规则列表 -->
      <div class="assertion-rules" v-if="rules.length">
        <div class="rule-item" v-for="(rule, index) in rules" :key="rule.id"
          :class="{ 'rule-body-not-json': rule.result?.error?.includes('非 JSON') }">
          <!-- 第一行：JSONPath + 比较符 + 结果 + 删除 -->
          <div class="rule-row">
            <JsonPathPicker
              v-model:modelValue="rule.jsonpath"
              :responseData="props.result"
              class="rule-jsonpath"
              @change="onRuleChange"
            />
            <a-select
              v-model:value="rule.operator"
              class="rule-operator"
              @change="onRuleChange"
            >
              <a-select-option v-for="op in ASSERT_OPERATORS" :key="op.value" :value="op.value">
                {{ op.label }}
              </a-select-option>
            </a-select>
            <a-tooltip :title="ruleTooltip(rule)" v-if="rule.result">
              <span v-if="rule.result.pass" class="rule-badge badge-pass">
                <CheckCircleOutlined /> 通过
              </span>
              <span v-else class="rule-badge badge-fail">
                <CloseCircleOutlined /> 失败
              </span>
            </a-tooltip>
            <span v-else class="rule-badge badge-pending">--</span>
            <a-button type="text" danger size="small" @click="removeRule(index)">
              <DeleteOutlined />
            </a-button>
          </div>
          <!-- 第二行：期望值 -->
          <div class="rule-row-expected" v-if="needsExpected(rule.operator)">
            <span class="expected-label">期望值</span>
            <a-input
              v-model:value="rule.expected"
              placeholder="输入期望值"
              class="rule-expected"
              @blur="onRuleChange"
            />
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="assertion-empty">
        <a-empty :image="simpleImage" description="暂无断言规则，点击下方添加" />
      </div>

      <!-- 非 JSON 响应提示（仅 JSONPath Tab） -->
      <a-alert
        v-if="props.result && !isBodyJson && props.result.response_body"
        type="warning"
        show-icon
        message="响应体非 JSON 格式"
        closable
        style="margin-bottom: 12px"
      >
        <template #description>
          <span>仅 $.status_code、$.elapsed_ms、$.headers 可用于 JSONPath 断言，推荐使用</span>
          <a-button type="link" size="small" style="padding: 0; vertical-align: baseline;" @click="activeTab = 'script'">脚本断言</a-button>
          <span>处理非 JSON 内容。</span>
        </template>
      </a-alert>

      <!-- 添加按钮 -->
      <a-button type="dashed" block size="small" @click="addRule" class="add-rule-btn">
        <PlusOutlined /> 添加断言
      </a-button>
    </template>

    <!-- ===== 脚本断言 Tab ===== -->
    <template v-if="activeTab === 'script'">
      <!-- 非 JSON 响应提示（脚本 Tab） -->
      <a-alert
        v-if="props.result && !isBodyJson && props.result.response_body"
        type="info"
        show-icon
        message="响应体非 JSON 格式"
        description="使用 response.body 在脚本中访问原始响应内容。"
        style="margin-bottom: 12px"
        closable
      />

      <!-- 脚本编辑器 -->
      <div class="script-editor-wrap">
        <a-textarea
          v-model:value="scriptRule.script"
          class="script-editor"
          :auto-size="{ minRows: 8, maxRows: 24 }"
          :placeholder="SCRIPT_PLACEHOLDER"
        />
      </div>

      <!-- 超时与运行 -->
      <div class="script-actions">
        <div class="script-timeout">
          <span class="timeout-label">超时</span>
          <a-input-number
            v-model:value="scriptRule.timeout"
            :min="1"
            :max="30"
            size="small"
            style="width: 80px"
          />
          <span class="timeout-unit">秒</span>
        </div>
        <a-button
          type="primary"
          size="small"
          :loading="scriptRule.result?.loading"
          :disabled="!props.result || !scriptRule.script.trim()"
          @click="runScriptAssertion"
        >
          <PlayCircleOutlined v-if="!scriptRule.result?.loading" /> 运行脚本
        </a-button>
      </div>

      <!-- 脚本结果 -->
      <div class="script-result" v-if="scriptRule.result && !scriptRule.result.loading">
        <div class="script-result-header">
          <span v-if="scriptRule.result.pass" class="rule-badge badge-pass">
            <CheckCircleOutlined /> 通过
          </span>
          <span v-else class="rule-badge badge-fail">
            <CloseCircleOutlined /> 失败
          </span>
        </div>
        <a-alert
          v-if="scriptRule.result.error"
          type="error"
          :message="scriptRule.result.error"
          show-icon
          style="margin-top: 8px"
        />
        <div v-if="scriptRule.result.output" class="script-result-output-wrap">
          <div class="script-result-output-label">输出</div>
          <pre class="script-result-output">{{ scriptRule.result.output }}</pre>
        </div>
      </div>

      <!-- 加载中 -->
      <div class="script-loading" v-if="scriptRule.result?.loading">
        <a-spin tip="执行中..." />
      </div>
    </template>

    <!-- 保存断言按钮（两个 Tab 共享） -->
    <div class="save-bar">
      <a-tooltip v-if="!store.currentInterface.id" title="请先保存接口后再保存断言">
        <a-button type="primary" size="small" :disabled="true" class="save-assertion-btn">
          <SaveOutlined /> 保存断言
        </a-button>
      </a-tooltip>
      <a-button v-else type="primary" size="small" :loading="saving" :disabled="!dirty" @click="handleSave" class="save-assertion-btn">
        <SaveOutlined /> 保存断言
      </a-button>
    </div>

    <!-- 摘要 -->
    <div class="assertion-summary" v-if="hasRunResults">
      <span :class="summaryClass">
        校验结果: {{ passCount }} 通过 <span v-if="failCount">/ {{ failCount }} 失败</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Empty } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  DeleteOutlined,
  SaveOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons-vue'
import JsonPathPicker from './JsonPathPicker.vue'
import { useDebugStore } from '../../stores/debug'
import { debugApi } from '../../api/debug'
import { JSONPath } from 'jsonpath-plus'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE
const store = useDebugStore()

const props = defineProps({
  result: { type: Object, default: null },
})
const emit = defineEmits(['summary-change'])

// ============ Tab 切换 ============

const TAB_OPTIONS = [
  { value: 'jsonpath', label: 'JSONPath 断言' },
  { value: 'script', label: '脚本断言' },
]
const activeTab = ref('jsonpath')

// ============ 响应体解析 ============

// 响应体是否为合法 JSON
const isBodyJson = computed(() => {
  if (!props.result?.response_body) return false
  try {
    JSON.parse(props.result.response_body)
    return true
  } catch {
    return false
  }
})

// 解析后的响应体（仅 isBodyJson 时解析）
const parsedBody = computed(() => {
  if (!isBodyJson.value) return null
  return JSON.parse(props.result.response_body)
})

// 判断 JSONPath 是否引用 $.body 路径
function pathReferencesBody(jsonpath) {
  const p = jsonpath.trim()
  if (!p.startsWith('$')) return false
  const afterRoot = p.slice(1)
  return /^\.body/.test(afterRoot) || /^\['body'\]/.test(afterRoot) || /^\["body"\]/.test(afterRoot)
}

// ============ JSONPath 断言 ============

// 比较符定义
const ASSERT_OPERATORS = [
  { value: 'equals', label: '等于', needsExpected: true },
  { value: 'not_equals', label: '不等于', needsExpected: true },
  { value: 'contains', label: '包含', needsExpected: true },
  { value: 'not_contains', label: '不包含', needsExpected: true },
  { value: 'greater_than', label: '大于', needsExpected: true },
  { value: 'less_than', label: '小于', needsExpected: true },
  { value: 'type_is', label: '类型为', needsExpected: true },
  { value: 'exists', label: '存在', needsExpected: false },
  { value: 'not_exists', label: '不存在', needsExpected: false },
]

function needsExpected(operator) {
  const op = ASSERT_OPERATORS.find(o => o.value === operator)
  return op ? op.needsExpected : true
}

let ruleIdCounter = 0

// 断言规则列表（工作副本，含 id 和 result）
const rules = ref([])

// ============ 脚本断言 ============

const SCRIPT_PLACEHOLDER = `# 可用变量: response
# response.status_code  HTTP 状态码
# response.headers      响应头 (dict)
# response.body         响应体 (原始字符串)
# response.elapsed_ms   耗时(ms)
# response.json()       解析 JSON 响应体

assert response.status_code == 200`

const scriptRule = ref({
  script: '',
  timeout: 10,
  result: null, // { pass: bool|null, error: str|null, output: str, loading: bool }
})

// ============ 与 store 双向同步 ============

let syncing = false

// 从 store.assertions 填充 rules 和 scriptRule（加载接口时调用）
function syncFromStore() {
  const assertions = store.currentInterface.assertions
  if (!assertions || !assertions.length) {
    rules.value = []
    scriptRule.value = { script: '', timeout: 10, result: null }
    dirty.value = false
    return
  }
  syncing = true

  // JSONPath 断言 → rules 数组（无 type 字段视为 jsonpath，向后兼容）
  rules.value = assertions
    .filter(a => !a.type || a.type === 'jsonpath')
    .map(a => ({
      id: ++ruleIdCounter,
      type: 'jsonpath',
      jsonpath: a.jsonpath || '',
      operator: a.operator || 'equals',
      expected: a.expected || '',
      result: null,
    }))

  // 脚本断言 → scriptRule（取最后一个 script 条目）
  const scriptEntry = [...assertions].reverse().find(a => a.type === 'script')
  scriptRule.value = scriptEntry
    ? { script: scriptEntry.script || '', timeout: scriptEntry.timeout || 10, result: null }
    : { script: '', timeout: 10, result: null }

  // 自动切换到有内容的 tab
  if (scriptEntry && !rules.value.length) {
    activeTab.value = 'script'
  }

  nextTick(() => {
    syncing = false
    dirty.value = false
  })
}

// 当接口 id 变化时（切换接口 / 新建），从 store 同步断言
watch(() => store.currentInterface.id, () => {
  syncFromStore()
})

// rules 和 scriptRule 变化时写回 store
watch([rules, scriptRule], () => {
  if (syncing) return
  const jsonPathAssertions = rules.value.map(r => ({
    type: 'jsonpath',
    jsonpath: r.jsonpath,
    operator: r.operator,
    expected: r.expected,
  }))
  const scriptAssertions = scriptRule.value.script.trim()
    ? [{ type: 'script', script: scriptRule.value.script, timeout: scriptRule.value.timeout }]
    : []
  store.currentInterface.assertions = [...jsonPathAssertions, ...scriptAssertions]
}, { deep: true })

// ============ 保存断言到数据库 ============

const saving = ref(false)

// 当前断言是否有未保存的变更
const dirty = ref(false)

// rules 和 scriptRule 变化时标记为脏
watch([rules, scriptRule], () => {
  if (syncing) return
  dirty.value = true
}, { deep: true })

// 保存断言到数据库
async function handleSave() {
  const ifaceId = store.currentInterface.id
  if (!ifaceId) {
    message.warning('请先保存接口后再保存断言')
    return
  }
  saving.value = true
  const jsonPathAssertions = rules.value.map(r => ({
    type: 'jsonpath',
    jsonpath: r.jsonpath,
    operator: r.operator,
    expected: r.expected,
  }))
  const scriptAssertions = scriptRule.value.script.trim()
    ? [{ type: 'script', script: scriptRule.value.script, timeout: scriptRule.value.timeout }]
    : []
  const assertions = [...jsonPathAssertions, ...scriptAssertions]
  try {
    await debugApi.patchInterface(ifaceId, { assertions })
    dirty.value = false
    message.success('断言已保存')
  } catch (e) {
    console.error('[AssertionPanel] 保存失败:', e?.response?.status, e?.response?.data)
    message.error('断言保存失败')
  } finally {
    saving.value = false
  }
}

// ============ 规则操作 ============

function addRule() {
  rules.value.push({
    id: ++ruleIdCounter,
    type: 'jsonpath',
    jsonpath: '',
    operator: 'equals',
    expected: '',
    result: null,
  })
}

function removeRule(index) {
  rules.value.splice(index, 1)
}

function onRuleChange() {
  if (props.result) {
    runJsonPathAssertions()
  }
}

// ============ 断言执行 ============

// JSONPath 断言执行（同步，客户端）
function runJsonPathAssertions() {
  if (!props.result) {
    rules.value.forEach(r => { r.result = null })
    return
  }

  const wrapper = {
    status_code: props.result.status_code,
    elapsed_ms: props.result.elapsed_ms,
    headers: props.result.response_headers || {},
    body: parsedBody.value,
  }

  rules.value.forEach(rule => {
    if (!rule.jsonpath.trim()) {
      rule.result = null
      return
    }

    // 非 JSON 响应时拦截 $.body 路径
    if (!isBodyJson.value && pathReferencesBody(rule.jsonpath)) {
      rule.result = { pass: false, actual: undefined, error: '响应体非 JSON 格式，无法使用 $.body 路径' }
      return
    }

    let actual
    try {
      const matches = JSONPath({ path: rule.jsonpath, json: wrapper })
      actual = matches.length > 0 ? matches[0] : undefined
    } catch (e) {
      rule.result = { pass: false, actual: undefined, error: `JSONPath 语法错误: ${e.message}` }
      return
    }

    let pass = false
    const expected = rule.expected

    switch (rule.operator) {
      case 'equals':
        pass = String(actual) === String(expected)
        break
      case 'not_equals':
        pass = String(actual) !== String(expected)
        break
      case 'contains':
        pass = String(actual).includes(String(expected))
        break
      case 'not_contains':
        pass = !String(actual).includes(String(expected))
        break
      case 'greater_than':
        pass = Number(actual) > Number(expected)
        break
      case 'less_than':
        pass = Number(actual) < Number(expected)
        break
      case 'exists':
        pass = actual !== undefined
        break
      case 'not_exists':
        pass = actual === undefined
        break
      case 'type_is': {
        const actualType = Array.isArray(actual) ? 'array' : typeof actual
        pass = actualType === expected
        break
      }
      default:
        pass = false
    }

    rule.result = { pass, actual, error: null }
  })
}

// 脚本断言执行（异步，后端）
async function runScriptAssertion() {
  if (!props.result || !scriptRule.value.script.trim()) {
    scriptRule.value.result = null
    return
  }

  scriptRule.value.result = { pass: null, error: null, output: null, loading: true }

  // 构建与 script_executor._ResponseProxy 匹配的上下文
  const context = {
    status_code: props.result.status_code,
    headers: props.result.response_headers || {},
    body: props.result.response_body || '',
    elapsed_ms: props.result.elapsed_ms,
  }

  try {
    const result = await debugApi.runAssertScript({
      script: scriptRule.value.script,
      context,
      timeout: scriptRule.value.timeout,
    })
    scriptRule.value.result = {
      pass: result.pass,
      error: result.error,
      output: result.output,
      loading: false,
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.response?.data?.error || e?.message || '未知错误'
    scriptRule.value.result = {
      pass: false,
      error: `请求失败: ${detail}`,
      output: '',
      loading: false,
    }
  }

  emit('summary-change', getSummary())
}

// 全部断言执行（JSONPath 同步 + 脚本异步）
async function runAllAssertions() {
  if (!props.result) {
    rules.value.forEach(r => { r.result = null })
    scriptRule.value.result = null
    emit('summary-change', { total: 0, pass: 0, fail: 0 })
    return
  }

  // 1. JSONPath 同步执行，立即可用
  runJsonPathAssertions()
  emit('summary-change', getSummary())

  // 2. 脚本异步执行，完成后更新
  if (scriptRule.value.script.trim()) {
    await runScriptAssertion()
  }
}

// 响应到达时触发全部断言
watch(() => props.result, () => {
  runAllAssertions()
}, { deep: true })

// ============ 统计 ============

const hasRunResults = computed(() => {
  const jsonPathHasResults = rules.value.some(r => r.result !== null)
  const scriptHasResult = scriptRule.value.result !== null && !scriptRule.value.result.loading
  return jsonPathHasResults || scriptHasResult
})

const passCount = computed(() => {
  let count = rules.value.filter(r => r.result?.pass === true).length
  if (scriptRule.value.result?.pass === true && !scriptRule.value.result.loading) count++
  return count
})

const failCount = computed(() => {
  let count = rules.value.filter(r => r.result?.pass === false).length
  if (scriptRule.value.result?.pass === false && !scriptRule.value.result.loading) count++
  return count
})

const summaryClass = computed(() => failCount.value > 0 ? 'summary-fail' : 'summary-pass')

function ruleTooltip(rule) {
  if (!rule.result) return ''
  if (rule.result.error) return rule.result.error
  const actualStr = rule.result.actual === undefined ? '(未匹配)' : JSON.stringify(rule.result.actual)
  return `实际值: ${actualStr}`
}

function getSummary() {
  return {
    total: rules.value.filter(r => r.result !== null).length +
      (scriptRule.value.result !== null && !scriptRule.value.result.loading ? 1 : 0),
    pass: passCount.value,
    fail: failCount.value,
  }
}

defineExpose({ getSummary })
</script>

<style scoped>
.assertion-panel {
  padding: 0 4px;
}

/* Tab 切换 */
.tab-switch {
  margin-bottom: 12px;
}

/* JSONPath 断言规则 */
.assertion-rules {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.rule-item {
  padding: 8px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}

.rule-body-not-json {
  background: #fff7e6;
  border-color: #ffd591;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-row-expected {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 0;
  margin-bottom: 8px;
}

.expected-label {
  flex-shrink: 0;
  width: 54px;
  font-size: 12px;
  color: #8c8c8c;
  text-align: right;
}

.rule-jsonpath {
  flex: 1;
}

.rule-operator {
  width: 110px;
  flex-shrink: 0;
}

.rule-expected {
  flex: 1;
}

.rule-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: 64px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
}

.badge-pass {
  color: #52c41a;
}

.badge-fail {
  color: #ff4d4f;
}

.badge-pending {
  color: #bfbfbf;
}

.assertion-empty {
  padding: 40px 0;
}

.add-rule-btn {
  margin-top: 4px;
}

/* 脚本断言 */
.script-editor-wrap {
  margin-bottom: 8px;
}

.script-editor :deep(.ant-input) {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
  background: #1e1e1e !important;
  color: #d4d4d4 !important;
  border: 1px solid #434343 !important;
  border-radius: 6px !important;
  padding: 12px !important;
  resize: vertical;
}

.script-editor :deep(.ant-input)::placeholder {
  color: #6a6a6a !important;
}

.script-editor :deep(.ant-input):hover {
  border-color: #595959 !important;
}

.script-editor :deep(.ant-input):focus {
  border-color: #4096ff !important;
  box-shadow: 0 0 0 2px rgba(64, 150, 255, 0.2) !important;
}

.script-editor :deep(.ant-input-affix-wrapper) {
  background: #1e1e1e !important;
  border-color: #434343 !important;
  border-radius: 6px !important;
}

.script-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.script-timeout {
  display: flex;
  align-items: center;
  gap: 6px;
}

.timeout-label {
  font-size: 12px;
  color: #8c8c8c;
}

.timeout-unit {
  font-size: 12px;
  color: #8c8c8c;
}

.script-result {
  padding: 8px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  margin-bottom: 12px;
}

.script-result-header {
  display: flex;
  align-items: center;
}

.script-result-output-wrap {
  margin-top: 8px;
}

.script-result-output-label {
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 4px;
}

.script-result-output {
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.script-loading {
  display: flex;
  justify-content: center;
  padding: 24px 0;
  margin-bottom: 12px;
}

/* 保存按钮 */
.save-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.save-assertion-btn {
  /* ensure same width across tabs */
}

/* 摘要 */
.assertion-summary {
  margin-top: 16px;
  padding: 8px 16px;
  background: #fafafa;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
  font-size: 13px;
}

.summary-pass {
  color: #52c41a;
  font-weight: 500;
}

.summary-fail {
  color: #ff4d4f;
  font-weight: 500;
}
</style>