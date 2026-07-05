<template>
  <div class="agent-page">
    <div class="agent-toolbar">
      <div>
        <h2>Agent 编排</h2>
        <p>根据自然语言目标生成链路草稿，确认后可保存到编辑器或直接运行调试。</p>
      </div>
    </div>

    <a-row :gutter="16" class="agent-content">
      <a-col :span="9">
        <div class="codex-prompt-box">
          <div class="codex-prompt-header">
            <span class="codex-prompt-icon">⟩</span>
            <span class="codex-prompt-label">目标描述</span>
          </div>
          <textarea
            v-model="form.goal"
            class="codex-prompt-input"
            :disabled="submitting || polling"
            placeholder="描述你要自动化执行的业务链路…"
            rows="6"
          ></textarea>
          <div class="codex-prompt-footer">
            <span class="active-env">环境：{{ envStore.activeEnvName }}</span>
            <a-button
              type="primary"
              :loading="submitting || polling"
              @click="handleSubmit"
              class="codex-submit-btn"
            >
              <ThunderboltOutlined />
              生成链路草稿
            </a-button>
          </div>
        </div>

        <!-- 校验结果 + 操作按钮 -->
        <a-card title="校验结果" :bordered="false" class="mt16">
          <a-empty v-if="!result && !taskError" description="暂无结果" />
          <template v-else>
            <a-alert v-if="taskError" type="error" :message="taskError" show-icon />
            <template v-else-if="result">
              <a-alert
                v-if="result.error_code || resultStatus === 'failed' || resultStatus === 'timeout'"
                type="error"
                :message="result.error_message || result.message || '编排失败'"
                show-icon
              />
              <a-alert
                v-else-if="unmatchedStepCount > 0"
                type="warning"
                :message="`${unmatchedStepCount} 个步骤未匹配到接口，请在编辑器中手动选择接口后再运行`"
                show-icon
              />
              <a-alert
                v-else
                type="success"
                message="所有步骤已匹配接口，可保存或运行"
                show-icon
              />
              <div v-if="llmTrace.length" class="llm-trace">
                <a-tag v-for="item in llmTrace" :key="item.key" color="purple">
                  {{ item.label }}: {{ item.provider }} / {{ item.model }}
                </a-tag>
              </div>
              <a-list v-if="allWarnings.length" size="small" :data-source="allWarnings" class="mt12">
                <template #renderItem="{ item }">
                  <a-list-item>{{ item }}</a-list-item>
                </template>
              </a-list>

              <!-- 操作按钮 -->
              <div v-if="result.chain_draft?.nodes?.length && unmatchedStepCount < totalInterfaceStepCount" class="action-bar mt12">
                <a-button type="primary" :loading="savingChain" @click="saveAndOpenEditor">
                  <EditOutlined /> 保存并打开编辑器
                </a-button>
                <a-button v-if="unmatchedStepCount === 0" :loading="runningChain" @click="saveAndRun">
                  <PlayCircleOutlined /> 直接运行
                </a-button>
              </div>

              <a-button v-if="result.saved_chain_id" type="link" @click="goChain(result.saved_chain_id)">
                打开已保存链路 #{{ result.saved_chain_id }}
              </a-button>
            </template>
          </template>
        </a-card>
      </a-col>

      <a-col :span="15">
        <a-card title="编排进度" :bordered="false">
          <a-empty v-if="!polling && !result && !taskError" description="生成时展示进度" />
          <template v-else>
            <div class="progress-summary">
              <a-progress :percent="progressPercent" :status="progressStatus" />
              <span class="progress-text">{{ progressText }}</span>
            </div>
            <div class="stage-row">
              <a-tag v-for="stage in progressStages" :key="stage.key" :color="stageColor(stage.status)">
                {{ stage.label }}
              </a-tag>
            </div>
            <div v-if="modelStageDetails.length" class="model-stage-panel">
              <div v-for="stage in modelStageDetails" :key="stage.key" class="model-stage-item">
                <div class="model-stage-head">
                  <div>
                    <strong>{{ stage.title }}</strong>
                    <span class="stage-detail-text">{{ stage.detail }}</span>
                  </div>
                  <a-tag :color="stageColor(stage.status)">{{ stage.statusText }}</a-tag>
                </div>
                <a-progress
                  :percent="stage.percent"
                  size="small"
                  :show-info="false"
                  :status="stage.status === 'error' ? 'exception' : 'normal'"
                />
                <div v-if="stage.model" class="stage-meta">{{ stage.model }}</div>
                <div v-if="stage.summary.length" class="stage-summary">
                  <div v-for="line in stage.summary" :key="line" class="stage-summary-line">{{ line }}</div>
                </div>
                <a-collapse v-if="stage.raw" ghost class="stage-json-collapse">
                  <a-collapse-panel key="raw" header="查看规划内容 JSON">
                    <pre class="stage-json">{{ stage.raw }}</pre>
                  </a-collapse-panel>
                </a-collapse>
              </div>
            </div>
          </template>
        </a-card>

        <!-- 识别步骤 — 带匹配状态 -->
        <a-card title="识别步骤" :bordered="false" class="mt16">
          <a-empty v-if="!displaySteps.length" description="生成后展示步骤" />
          <a-steps v-else direction="vertical" size="small" :current="currentStepIndex">
            <a-step
              v-for="step in displaySteps"
              :key="step.index"
              :title="step.resolved_text || step.text"
              :status="step.stepStatus"
            >
              <template #description>
                <div class="step-desc">
                  <a-tag v-if="step.matchedInterface" color="green">
                    {{ step.matchedInterface.method || '' }} {{ step.matchedInterface.name || step.matchedInterface.url || '' }}
                  </a-tag>
                  <a-tag v-else color="orange">未匹配到接口</a-tag>
                  <span v-if="step.matchReason" class="step-detail-inline">{{ step.matchReason }}</span>
                </div>
                <div v-if="step.extractions?.length" class="step-extractions">
                  <span v-for="ext in step.extractions" :key="ext.var_name" class="extraction-preview">
                    提取 {{ ext.var_name }} ← {{ ext.jsonpath }}
                  </span>
                </div>
              </template>
            </a-step>
          </a-steps>
        </a-card>

        <!-- 接口候选 — 含未匹配提示 -->
        <a-card title="接口候选" :bordered="false" class="mt16">
          <a-empty v-if="!candidates.length" description="暂无候选接口" />
          <a-collapse v-else>
            <a-collapse-panel v-for="item in candidates" :key="item.step_index">
              <template #header>
                <span>
                  第 {{ item.step_index }} 步：{{ item.resolved_text || item.step_text }}
                  <a-tag v-if="!getStepMatch(item.step_index)" color="orange" style="margin-left: 6px">未匹配接口</a-tag>
                  <a-tag v-else color="green" style="margin-left: 6px">已匹配</a-tag>
                </span>
              </template>
              <!-- 有候选接口时展示表格 -->
              <template v-if="item.candidates?.length">
                <a-table size="small" row-key="interface_id" :pagination="false" :data-source="item.candidates">
                  <a-table-column title="分数" data-index="pre_score" width="70">
                    <template #default="{ text }">{{ text?.toFixed?.(2) ?? text }}</template>
                  </a-table-column>
                  <a-table-column title="方法" data-index="method" width="70" />
                  <a-table-column title="接口" data-index="name" />
                  <a-table-column title="地址" data-index="url" />
                </a-table>
              </template>
              <!-- 无候选接口时展示提示 -->
              <a-alert
                v-else
                type="warning"
                message="未找到相关候选接口"
                description="项目中没有与该步骤语义匹配的接口，请在链路编辑器中手动创建或选择接口"
                show-icon
                style="margin-top: 4px"
              />
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <!-- 执行结果面板 -->
        <a-card v-if="runResult" title="运行结果" :bordered="false" class="mt16">
          <div class="run-summary">
            <a-tag :color="runResult.status === 'completed' ? 'green' : runResult.status === 'failed' ? 'red' : 'orange'" style="font-size: 13px">
              {{ runResult.status === 'completed' ? '执行完成' : runResult.status === 'failed' ? '执行失败' : runResult.status }}
            </a-tag>
            <span v-if="runResult.finished_at" class="run-time">
              耗时 {{ formatDuration(runResult.started_at, runResult.finished_at) }}
            </span>
          </div>
          <a-steps direction="vertical" size="small" class="run-steps">
            <a-step
              v-for="(step, idx) in runResult.step_results || []"
              :key="idx"
              :title="step.node_label || step.node_id"
              :status="step.status === 'success' ? 'finish' : step.status === 'failed' ? 'error' : 'process'"
            >
              <template #description>
                <div class="run-step-detail">
                  <template v-if="step.response">
                    <span :style="{ color: step.response.status_code < 400 ? '#52c41a' : '#ff4d4f', fontWeight: 600 }">
                      {{ step.response.status_code }}
                    </span>
                    <span v-if="step.response.elapsed_ms" style="margin-left: 8px; color: #8c8c8c">
                      {{ step.response.elapsed_ms }}ms
                    </span>
                  </template>
                  <span v-if="step.error" style="color: #ff4d4f">{{ step.error }}</span>
                  <!-- 变量提取 -->
                  <div v-if="step.extractions?.length" class="run-extractions">
                    <span v-for="ext in step.extractions" :key="ext.var_name" class="extraction-tag">
                      {{ ext.var_name }} = {{ truncate(String(ext.value ?? ''), 80) }}
                    </span>
                  </div>
                  <!-- 断言结果 -->
                  <div v-if="step.assertion_results?.length" class="run-assertions">
                    <span
                      v-for="(ar, ai) in step.assertion_results"
                      :key="ai"
                      :class="['assertion-tag', ar.pass ? 'assertion-pass' : 'assertion-fail']"
                    >
                      {{ ar.pass ? '✓' : '✗' }} {{ ar.rule?.jsonpath || '断言' }}
                    </span>
                  </div>
                  <!-- 响应体（可折叠） -->
                  <template v-if="step.response?.body">
                    <a-button type="link" size="small" @click="toggleStepBody(idx)">
                      {{ expandedSteps.has(idx) ? '收起响应' : '查看响应' }}
                    </a-button>
                    <pre v-if="expandedSteps.has(idx)" class="run-body-pre">{{ formatBody(step.response.body) }}</pre>
                  </template>
                </div>
              </template>
            </a-step>
          </a-steps>
        </a-card>

        <a-card title="链路草稿 JSON" :bordered="false" class="mt16">
          <pre class="json-preview">{{ chainJson }}</pre>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ThunderboltOutlined,
  EditOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons-vue'
import { agentApi } from '../../api/agent'
import { chainApi } from '../../api/chain'
import { useProjectStore } from '../../stores/project'
import { useEnvironmentStore } from '../../stores/environment'

const router = useRouter()
const projectStore = useProjectStore()
const envStore = useEnvironmentStore()

// State
const submitting = ref(false)
const polling = ref(false)
const taskId = ref(null)
const taskData = ref(null)
const result = ref(null)
const resultStatus = ref(null)
const taskError = ref(null)
let pollTimer = null

// Save & run state
const savingChain = ref(false)
const runningChain = ref(false)
const runResult = ref(null)
const expandedSteps = ref(new Set())
const savedChainId = ref(null)

const form = reactive({ goal: '提交发票，审批，下载发票' })

// Build match lookup: step_index → match
const matchesByStep = computed(() => {
  const map = {}
  for (const m of result.value?.matches || []) {
    map[m.step_index] = m
  }
  return map
})

// Count steps with no matched interface
const unmatchedStepCount = computed(() => {
  if (!result.value?.chain_draft?.nodes) return 0
  return result.value.chain_draft.nodes.filter(
    n => n.type === 'interface' && !n.data?.interface_id
  ).length
})

// Total interface-type steps
const totalInterfaceStepCount = computed(() => {
  if (!result.value?.chain_draft?.nodes) return 0
  return result.value.chain_draft.nodes.filter(n => n.type === 'interface').length
})

// Computed from poll data
const currentStep = computed(() => taskData.value?.current_step || '')
const progressPercent = computed(() => taskData.value?.progress || 0)

const progressStages = computed(() => {
  const stepResults = taskData.value?.step_results || {}
  const keys = ['parse', 'index', 'match', 'dependency', 'draft', 'validate']
  const labels = ['解析步骤', '检索接口', '匹配接口', '规划依赖', '生成草稿', '校验结果']
  const stageStatuses = [
    stepResults.step_planning?.status,
    stepResults.step_planning?.status === 'completed' ? 'done' : null,
    stepResults.interface_matching?.status,
    stepResults.dependency_planning?.status,
    stepResults.draft_and_validate?.status || (result.value ? 'completed' : null),
    result.value ? 'completed' : null,
  ]
  return keys.map((key, i) => {
    const rawStatus = stageStatuses[i]
    let status = 'wait'
    if (rawStatus === 'completed') status = 'finish'
    else if (rawStatus === 'running') status = 'process'
    else if (rawStatus === 'failed') status = 'error'
    return { key, label: labels[i], status }
  })
})

const modelStageDetails = computed(() => {
  const stepResults = taskData.value?.step_results || {}
  const finalResult = result.value || {}
  return [
    buildModelStage({
      key: 'step_planning',
      title: '步骤规划',
      range: [5, 33],
      result: stepResults.step_planning,
      trace: finalResult.llm_trace?.step_planning,
      fallbackOutput: finalResult.step_plan,
      summaryBuilder: summarizeStepPlan,
      runningDetail: '模型正在拆解目标并识别业务步骤',
      completedDetail: '已生成业务步骤',
    }),
    buildModelStage({
      key: 'interface_matching',
      title: '接口匹配',
      range: [38, 66],
      result: stepResults.interface_matching,
      trace: finalResult.llm_trace?.interface_matching,
      fallbackOutput: { matches: finalResult.matches },
      summaryBuilder: summarizeInterfaceMatch,
      runningDetail: '模型正在从候选接口中选择匹配项',
      completedDetail: '已完成接口匹配',
    }),
    buildModelStage({
      key: 'dependency_planning',
      title: '依赖规划',
      range: [71, 95],
      result: stepResults.dependency_planning,
      trace: finalResult.llm_trace?.dependency_planning,
      fallbackOutput: finalResult.dependency_plan,
      summaryBuilder: summarizeDependencyPlan,
      runningDetail: '模型正在规划上下游参数传递',
      completedDetail: '已生成参数依赖规划',
    }),
  ].filter(stage => stage.visible)
})

const progressStatus = computed(() => {
  const s = resultStatus.value
  if (s === 'failed' || s === 'timeout') return 'exception'
  if (s === 'completed') return 'normal'
  return 'active'
})

const progressText = computed(() => {
  if (polling.value) return currentStep.value || '正在编排链路'
  if (resultStatus.value === 'failed' || resultStatus.value === 'timeout') return '编排失败，请查看校验结果'
  if (resultStatus.value === 'completed') return '编排完成'
  return ''
})

const steps = computed(() => result.value?.steps || [])
const candidates = computed(() => result.value?.candidates_by_step || [])
const allWarnings = computed(() => result.value?.warnings || [])
const chainJson = computed(() => result.value?.chain_draft ? JSON.stringify(result.value.chain_draft, null, 2) : '{}')
const llmTrace = computed(() => {
  const trace = result.value?.llm_trace || {}
  return [
    { key: 'step', label: '步骤规划', ...trace.step_planning },
    { key: 'match', label: '接口匹配', ...trace.interface_matching },
    { key: 'dependency', label: '依赖规划', ...trace.dependency_planning },
  ].filter(item => item.provider)
})

const displaySteps = computed(() => {
  if (!result.value) {
    const stepPlanning = taskData.value?.step_results?.step_planning?.output
    if (stepPlanning?.steps) {
      return stepPlanning.steps.map(step => ({
        ...step,
        stepStatus: 'process',
        matchedInterface: null,
        matchReason: '',
        extractions: [],
      }))
    }
    return []
  }
  return steps.value.map(step => {
    const match = matchesByStep.value[step.index]
    const selected = match?.selected_interface
    // Also look for extractions from chain_draft node
    const draftNode = result.value?.chain_draft?.nodes?.find(
      n => n.id === `agent_step_${step.index}`
    )
    const extractions = draftNode?.data?.extractions || []
    return {
      ...step,
      stepStatus: selected ? 'finish' : 'finish',
      matchedInterface: selected || null,
      matchReason: match?.reason || (selected ? '' : '未匹配到接口'),
      extractions,
    }
  })
})

const currentStepIndex = computed(() => {
  const processingIndex = displaySteps.value.findIndex(step => step.stepStatus === 'process')
  return processingIndex >= 0 ? processingIndex : displaySteps.value.length
})

function getStepMatch(stepIndex) {
  return matchesByStep.value[stepIndex]?.selected_interface || null
}

function buildModelStage({ key, title, range, result: stageResult, trace, fallbackOutput, summaryBuilder, runningDetail, completedDetail }) {
  const status = stageResult?.status || (fallbackOutput ? 'completed' : 'wait')
  const output = stageResult?.output || fallbackOutput
  const visible = status !== 'wait' || Boolean(output) || polling.value || result.value
  const statusText = status === 'completed' ? '完成' : status === 'running' ? '进行中' : status === 'failed' ? '失败' : '等待'
  const normalizedStatus = status === 'completed' ? 'finish' : status === 'running' ? 'process' : status === 'failed' ? 'error' : 'wait'
  const percent = stagePercent(range, status)
  const model = trace?.provider ? `${trace.provider} / ${trace.model || '-'}` : ''
  return {
    key,
    title,
    visible,
    status: normalizedStatus,
    statusText,
    percent,
    detail: status === 'running' ? runningDetail : status === 'completed' ? completedDetail : stageResult?.error || '等待开始',
    model,
    summary: output ? summaryBuilder(output) : [],
    raw: output ? JSON.stringify(output, null, 2) : '',
  }
}

function stagePercent([start, end], status) {
  if (status === 'completed') return 100
  if (status === 'running') {
    const current = progressPercent.value || start
    return Math.max(5, Math.min(99, Math.round(((current - start) / (end - start)) * 100)))
  }
  if (status === 'failed') return 100
  return 0
}

function summarizeStepPlan(output) {
  const steps = output.steps || []
  return steps.map(step => `第 ${step.index} 步：${step.text || step.resolved_text || ''}`)
}

function summarizeInterfaceMatch(output) {
  const matches = output.matches || []
  if (!matches.length && output.match_count !== undefined) return [`已匹配 ${output.match_count} 个接口`]
  return matches.map(match => {
    const selected = match.selected_interface
    const name = selected ? `${selected.method || ''} ${selected.name || selected.url || ''}`.trim() : '未选择接口'
    const confidence = Math.round((match.confidence || 0) * 100)
    return `第 ${match.step_index} 步：${name}（${confidence}%）${match.reason ? ` - ${match.reason}` : ''}`
  })
}

function summarizeDependencyPlan(output) {
  const mappings = output.mappings || []
  const missing = output.missing_inputs || []
  const lines = mappings.map(item => `第 ${item.from_step} 步 ${item.from_key || item.from_var} → 第 ${item.to_step} 步 ${item.to_key || item.to_field}`)
  return lines.concat(missing.map(item => item.message || `缺少参数：${item.field || '-'}`))
}

// ---- Submit & Poll ----

async function handleSubmit() {
  if (!form.goal.trim()) { message.warning('请输入要编排的目标'); return }
  result.value = null
  resultStatus.value = null
  taskData.value = null
  taskError.value = null
  taskId.value = null
  runResult.value = null
  savedChainId.value = null

  submitting.value = true
  try {
    const response = await agentApi.submitPlan({
      goal: form.goal,
      project_id: projectStore.activeProjectId,
      auto_save: false,
      auto_execute: false,
      environment_id: envStore.activeEnvironmentId,
    })
    taskId.value = response.task_id
    message.info('任务已提交，正在编排中...')
    startPolling()
  } catch (error) {
    const msg = error?.response?.data?.detail || error?.message || '提交任务失败'
    taskError.value = msg
    message.error(msg)
  } finally {
    submitting.value = false
  }
}

function startPolling() {
  stopPolling()
  polling.value = true
  pollStatus()
  pollTimer = window.setInterval(pollStatus, 2000)
}

async function pollStatus() {
  if (!taskId.value) { stopPolling(); return }
  try {
    const data = await agentApi.getPlanStatus(taskId.value)
    taskData.value = data
    resultStatus.value = data.status
    if (data.status === 'completed') {
      result.value = data.result
      if (data.result?.saved_chain_id) savedChainId.value = data.result.saved_chain_id
      stopPolling()
      if (result.value?.error_code) message.error(result.value.message || '编排失败')
      else message.success('已生成链路草稿')
    } else if (data.status === 'failed' || data.status === 'timeout') {
      result.value = data.result
      taskError.value = data.error_message || '编排失败'
      stopPolling()
      message.error(taskError.value)
    }
  } catch { /* transient error, keep polling */ }
}

function stopPolling() {
  if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null }
  polling.value = false
}

// ---- Save & Run ----

function buildChainData(status = 'ready') {
  const draft = result.value.chain_draft
  return {
    name: draft.name || form.goal.substring(0, 80),
    description: draft.description || '由 Agent 生成的链路草稿',
    nodes: draft.nodes,
    edges: draft.edges,
    globals: draft.globals || [],
    status,
    project: projectStore.activeProjectId,
  }
}

async function saveChain() {
  const existingId = savedChainId.value || result.value?.saved_chain_id
  if (existingId) {
    await chainApi.patchChain(existingId, { ...buildChainData('ready'), status: 'ready' })
    return existingId
  }
  const created = await chainApi.createChain(buildChainData('ready'))
  savedChainId.value = created.id
  return created.id
}

async function saveAndOpenEditor() {
  savingChain.value = true
  try {
    const chainId = await saveChain()
    message.success('链路已保存')
    router.push({ path: '/chain-test', query: { id: chainId } })
  } catch (e) {
    message.error(e?.response?.data?.detail || '保存链路失败')
  } finally {
    savingChain.value = false
  }
}

async function saveAndRun() {
  runningChain.value = true
  runResult.value = null
  try {
    const chainId = await saveChain()
    message.info('链路已保存，正在执行...')
    const execResult = await chainApi.executeChain(chainId, envStore.activeEnvironmentId)
    runResult.value = execResult
    const failCount = execResult.step_results?.filter(s => s.status === 'failed').length || 0
    if (execResult.status === 'completed' && !failCount) message.success('链路执行完成，全部通过')
    else if (failCount) message.warning(`链路执行完成，${failCount} 个节点失败`)
    else message.error(`链路执行失败: ${execResult.error_message || '未知错误'}`)
  } catch (e) {
    message.error(e?.response?.data?.detail || '执行链路失败')
  } finally {
    runningChain.value = false
  }
}

// ---- Helper functions ----

function goChain(chainId) {
  router.push({ path: '/chain-test', query: { id: chainId } })
}

function stageColor(status) {
  if (status === 'finish') return 'green'
  if (status === 'process') return 'blue'
  if (status === 'error') return 'red'
  return 'default'
}

function toggleStepBody(idx) {
  const s = new Set(expandedSteps.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  expandedSteps.value = s
}

function formatBody(body) {
  if (!body) return ''
  if (typeof body === 'object') { try { return JSON.stringify(body, null, 2) } catch { return String(body) } }
  try { return JSON.stringify(JSON.parse(body), null, 2) } catch { return String(body) }
}

function formatDuration(start, end) {
  if (!start || !end) return ''
  const ms = new Date(end) - new Date(start)
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function truncate(str, len) {
  return str.length > len ? str.substring(0, len) + '…' : str
}

onBeforeUnmount(stopPolling)
</script>

<style scoped>
.agent-page { padding: 16px; }
.agent-toolbar {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 16px;
}
.agent-toolbar h2 { margin: 0 0 4px; font-size: 20px; }
.agent-toolbar p { margin: 0; color: #667085; }
.agent-content :deep(.ant-card) { border-radius: 8px; }
.mt16 { margin-top: 16px; }
.mt12 { margin-top: 12px; }

/* ===== Codex 风格目标描述框 ===== */
.codex-prompt-box {
  display: flex;
  flex-direction: column;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.codex-prompt-box:focus-within {
  border-color: #58a6ff;
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}
.codex-prompt-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px 0;
}
.codex-prompt-icon {
  color: #58a6ff;
  font-size: 20px;
  font-weight: 700;
  font-family: 'Courier New', monospace;
  line-height: 1;
}
.codex-prompt-label {
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
}
.codex-prompt-input {
  flex: 1;
  width: 100%;
  padding: 10px 16px;
  background: transparent;
  border: none;
  outline: none;
  resize: vertical;
  color: #e6edf3;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.6;
  min-height: 96px;
}
.codex-prompt-input::placeholder {
  color: #484f58;
}
.codex-prompt-input:disabled {
  color: #484f58;
  cursor: not-allowed;
}
.codex-prompt-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 10px;
  gap: 8px;
}
.codex-char-count {
  color: #484f58;
  font-size: 11px;
  font-family: 'SF Mono', monospace;
  flex-shrink: 0;
}
.codex-submit-btn {
  border-radius: 8px !important;
  font-weight: 500;
}
.active-env {
  color: #8b949e;
  font-size: 12px;
}

/* ===== 原有样式 ===== */
.progress-summary { display: flex; flex-direction: column; gap: 6px; }
.progress-text { color: #667085; font-size: 13px; }
.stage-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.model-stage-panel { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.model-stage-item {
  padding: 10px 12px; border: 1px solid #eaecf0; border-radius: 6px; background: #fcfcfd;
}
.model-stage-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 6px;
}
.model-stage-head strong { font-size: 13px; color: #1f2937; }
.stage-detail-text { display: block; margin-top: 2px; color: #667085; font-size: 12px; }
.stage-meta { margin-top: 6px; color: #6941c6; font-size: 12px; }
.stage-summary { margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }
.stage-summary-line {
  color: #344054; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere;
}
.stage-json-collapse { margin-top: 2px; }
.stage-json-collapse :deep(.ant-collapse-header) { padding: 4px 0 !important; font-size: 12px; color: #667085 !important; }
.stage-json-collapse :deep(.ant-collapse-content-box) { padding: 0 !important; }
.stage-json {
  max-height: 220px; overflow: auto; margin: 4px 0 0; padding: 8px;
  background: #101828; color: #f2f4f7; border-radius: 6px;
  font-size: 11px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
}
.step-desc { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.step-detail-inline { color: #8c8c8c; font-size: 12px; }
.step-extractions { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.extraction-preview {
  display: inline-block; font-size: 11px; padding: 1px 6px;
  background: #f0f5ff; color: #2f54eb; border: 1px solid #adc6ff;
  border-radius: 3px; font-family: monospace;
}
.llm-trace { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.json-preview {
  max-height: 360px; overflow: auto; margin: 0; padding: 12px;
  background: #101828; color: #f2f4f7; border-radius: 6px;
  font-size: 12px; line-height: 1.6;
}
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; }

/* Run result styles */
.run-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.run-time { color: #8c8c8c; font-size: 13px; }
.run-steps { margin-top: 8px; }
.run-step-detail { font-size: 12px; }
.run-extractions { margin-top: 4px; }
.extraction-tag {
  display: inline-block; font-size: 11px; padding: 1px 6px; margin: 2px 4px 2px 0;
  background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; border-radius: 3px;
  max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.run-assertions { margin-top: 4px; }
.assertion-tag {
  display: inline-block; font-size: 11px; padding: 1px 6px; margin: 2px 4px 2px 0;
  border-radius: 3px;
}
.assertion-pass { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
.assertion-fail { background: #fff2f0; color: #cf1322; border: 1px solid #ffa39e; }
.run-body-pre {
  margin: 4px 0 0; padding: 8px; background: #1e1e1e; color: #d4d4d4;
  border-radius: 6px; font-size: 11px; line-height: 1.5;
  max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
}
</style>
