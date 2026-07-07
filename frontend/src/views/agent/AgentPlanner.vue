<template>
  <div class="agent-page">
    <div class="agent-toolbar">
      <div>
        <h2>{{ t('Agent 编排') }}</h2>
        <p>{{ t('根据自然语言目标生成链路草稿，确认后可保存到编辑器或直接运行调试。') }}</p>
      </div>
    </div>

    <a-row :gutter="16" class="agent-content">
      <a-col :span="24">
        <div class="agent-chat-panel">
          <div class="agent-chat-header">
            <div>
              <strong>{{ t('对话式编排') }}</strong>
              <span>{{ t('执行到哪个阶段，就展示哪个阶段的规划细节') }}</span>
            </div>
            <a-tag :color="polling ? 'blue' : effectiveResultStatus === 'completed' ? 'green' : taskError ? 'red' : 'default'">
              {{ chatStatusText }}
            </a-tag>
          </div>

          <div class="agent-chat-stream">
            <div v-if="!conversationMessages.length" class="agent-chat-empty">
              <div class="agent-chat-empty-title">{{ t('描述你的链路目标') }}</div>
              <div class="agent-chat-empty-desc">{{ t('Agent 会按规划阶段逐步展示步骤、接口匹配、参数依赖、断言和草稿。') }}</div>
            </div>

            <div
              v-for="msg in conversationMessages"
              :key="msg.renderKey || msg.id"
              :class="['chat-message', msg.role === 'user' ? 'chat-message-user' : 'chat-message-agent']"
            >
              <div class="chat-avatar">{{ msg.role === 'user' ? t('你') : 'AI' }}</div>
              <div class="chat-bubble">
                <div class="chat-bubble-head">
                  <strong>{{ msg.title }}</strong>
                  <a-tag v-if="msg.statusText" :color="msg.statusColor">{{ msg.statusText }}</a-tag>
                </div>
                <div class="chat-summary">{{ msg.summary }}</div>
                <a-progress
                  v-if="msg.progress !== undefined"
                  :percent="msg.progress"
                  size="small"
                  :status="msg.status === 'failed' ? 'exception' : 'normal'"
                  class="chat-progress"
                />

                <a-collapse v-if="msg.detailType" ghost class="chat-detail-collapse">
                  <a-collapse-panel key="detail" :header="msg.detailTitle">
                    <template v-if="msg.detailType === 'step_planning'">
                      <a-empty v-if="!chatStepPlanSteps.length" :description="t('等待步骤规划输出')" />
                      <a-steps v-else direction="vertical" size="small">
                        <a-step
                          v-for="step in chatStepPlanSteps"
                          :key="step.index"
                          :title="localize(step.resolved_text || step.text)"
                          status="finish"
                        />
                      </a-steps>
                    </template>

                    <template v-else-if="msg.detailType === 'interface_matching'">
                      <a-empty v-if="!chatInterfaceMatches.length" :description="t('等待接口匹配输出')" />
                      <div v-else class="chat-detail-list">
                        <div v-for="match in chatInterfaceMatches" :key="match.step_index" class="chat-detail-item">
                          <div class="chat-detail-main">
                            <a-tag :color="match.selected_interface ? 'green' : 'orange'">
                              {{ match.selected_interface ? t('已匹配') : t('未匹配') }}
                            </a-tag>
                            <span>{{ t('第') }} {{ match.step_index }} {{ t('步') }}</span>
                          </div>
                          <div class="chat-detail-text">
                            <template v-if="match.selected_interface">
                              {{ match.selected_interface.method || '' }} {{ translateText(match.selected_interface.name || match.selected_interface.url || '') }}
                              <span v-if="match.confidence"> · {{ t('置信度') }} {{ Math.round(match.confidence * 100) }}%</span>
                            </template>
                            <template v-else>{{ t('没有选择接口，请查看候选或进入编辑器处理') }}</template>
                          </div>
                          <div v-if="match.reason" class="chat-detail-reason">{{ localize(match.reason) }}</div>
                        </div>
                      </div>

                      <a-divider v-if="chatCandidates.length" class="chat-divider">{{ t('候选接口与确认') }}</a-divider>
                      <a-collapse v-if="chatCandidates.length" ghost class="chat-nested-collapse">
                        <a-collapse-panel v-for="item in chatCandidates" :key="item.step_index">
                          <template #header>
                            <span>
                              {{ t('第') }} {{ item.step_index }} {{ t('步：') }}{{ localize(item.resolved_text || item.step_text) }}
                              <a-tag v-if="!getStepMatch(item.step_index)" color="orange" style="margin-left: 6px">{{ t('未匹配接口') }}</a-tag>
                              <a-tag v-else color="green" style="margin-left: 6px">{{ t('已匹配') }}</a-tag>
                            </span>
                          </template>
                          <template v-if="item.candidates?.length">
                            <a-table
                              size="small"
                              row-key="interface_id"
                              :pagination="false"
                              :data-source="item.candidates"
                              table-layout="fixed"
                              class="candidate-table chat-candidate-table"
                            >
                              <a-table-column :title="t('分数')" data-index="pre_score" width="70">
                                <template #default="{ text }">{{ text?.toFixed?.(2) ?? text }}</template>
                              </a-table-column>
                              <a-table-column :title="t('方法')" data-index="method" width="70" />
                              <a-table-column :title="t('接口')" data-index="name" width="180">
                                <template #default="{ record }">
                                  <a-tooltip :title="record.name">
                                    <span class="candidate-cell-text">{{ translateText(record.name) }}</span>
                                  </a-tooltip>
                                </template>
                              </a-table-column>
                              <a-table-column :title="t('地址')" data-index="url">
                                <template #default="{ record }">
                                  <a-tooltip :title="record.url">
                                    <span class="candidate-cell-text candidate-url">{{ record.url }}</span>
                                  </a-tooltip>
                                </template>
                              </a-table-column>
                              <a-table-column :title="t('确认')" width="120">
                                <template #default="{ record }">
                                  <div class="candidate-reason-cell">
                                    <a-tag v-if="isSelectedCandidate(item.step_index, record.interface_id)" color="green">{{ t('最终选择') }}</a-tag>
                                    <a-tag v-else color="blue">{{ t('候选') }}</a-tag>
                                    <a-button
                                      type="link"
                                      size="small"
                                      class="remember-btn"
                                      :loading="feedbackSavingKey === feedbackKey(item.step_index, record.interface_id)"
                                      @click="rememberCandidate(item, record)"
                                    >
                                      {{ t('记住') }}
                                    </a-button>
                                  </div>
                                </template>
                              </a-table-column>
                              <template #expandedRowRender="{ record }">
                                <div class="candidate-explain">
                                  <div v-if="candidateModelReason(item.step_index, record.interface_id)" class="candidate-explain-block">
                                    <div class="candidate-explain-title">{{ t('模型判断') }}</div>
                                    <div class="candidate-explain-text">
                                      {{ localize(candidateModelReason(item.step_index, record.interface_id)) }}
                                    </div>
                                  </div>
                                  <div class="candidate-explain-block">
                                    <div class="candidate-explain-title">{{ t('规则评分') }}</div>
                                    <a-space size="small" wrap>
                                      <a-tag v-for="part in candidateScoreParts(record)" :key="part.key" color="purple">
                                        {{ localize(part.label) }} {{ part.value }}
                                      </a-tag>
                                    </a-space>
                                  </div>
                                  <div v-if="candidateReasons(record).length" class="candidate-explain-block">
                                    <div class="candidate-explain-title">{{ t('命中原因') }}</div>
                                    <ul class="candidate-reasons">
                                      <li v-for="reason in candidateReasons(record)" :key="reason">{{ localize(reason) }}</li>
                                    </ul>
                                  </div>
                                </div>
                              </template>
                            </a-table>
                          </template>
                          <a-alert
                            v-else
                            type="warning"
                            :message="t('未找到相关候选接口')"
                            :description="t('项目中没有与该步骤语义匹配的接口，请在链路编辑器中手动创建或选择接口')"
                            show-icon
                            style="margin-top: 4px"
                          />
                        </a-collapse-panel>
                      </a-collapse>
                    </template>

                    <template v-else-if="msg.detailType === 'dependency_planning'">
                      <a-empty v-if="!chatDependencyLines.length" :description="t('暂无参数依赖')" />
                      <div v-else class="chat-detail-list">
                        <div v-for="line in chatDependencyLines" :key="line" class="chat-detail-item">
                          {{ line }}
                        </div>
                      </div>
                    </template>

                    <template v-else-if="msg.detailType === 'assertion_planning'">
                      <a-empty v-if="!assertionPlan.length" :description="t('暂无断言规划')" />
                      <div v-else class="chat-detail-list">
                        <div v-for="item in assertionPlan" :key="item.step_index" class="chat-detail-item">
                          <div class="chat-detail-main">
                            <a-tag color="blue">{{ t('第') }} {{ item.step_index }} {{ t('步') }}</a-tag>
                            <span>{{ localize(item.step_text) }}</span>
                          </div>
                          <div class="chat-assertion-tags">
                            <span v-for="rule in item.assertions || []" :key="assertionKey(item.step_index, rule)" class="assertion-tag assertion-pass">
                              {{ rule.jsonpath }} {{ assertionOperatorText(rule.operator) }} {{ formatAssertionExpected(rule.expected) }}
                            </span>
                          </div>
                        </div>
                      </div>
                    </template>

                    <template v-else-if="msg.detailType === 'draft'">
                      <div v-if="planStageBadges.length" class="llm-trace">
                        <a-tag v-for="item in planStageBadges" :key="item.key" :color="item.color || 'purple'">
                          {{ item.label }}: {{ item.text }}
                        </a-tag>
                      </div>
                      <a-list v-if="allWarnings.length" size="small" :data-source="allWarnings" class="mt12">
                        <template #renderItem="{ item }">
                          <a-list-item>{{ localize(item) }}</a-list-item>
                        </template>
                      </a-list>
                      <pre class="chat-json-preview">{{ chainJson }}</pre>
                    </template>
                  </a-collapse-panel>
                </a-collapse>

                <div v-if="msg.showTrialQuestions && trialAuthorizationQuestions.length" class="trial-auth-panel mt12">
                  <div v-for="item in trialAuthorizationQuestions" :key="trialQuestionKey(item)" class="trial-auth-item">
                    <div class="trial-auth-main">
                      <strong>{{ t('需要调试确认') }}</strong>
                      <span>{{ trialDebugText(item) }}</span>
                      <div class="trial-auth-meta">
                        <a-tag color="orange">{{ item.method }}</a-tag>
                        <span>{{ item.interface_name }}</span>
                        <span class="trial-auth-url">{{ item.url }}</span>
                      </div>
                    </div>
                    <div v-if="resultStatus === 'completed'" class="trial-auth-actions">
                      <a-button size="small" type="primary" :loading="submitting || polling" @click="authorizeTrialRun(item)">
                        {{ t('授权调试并重新规划') }}
                      </a-button>
                    </div>
                  </div>
                </div>

                <div v-if="msg.showActions" class="action-bar mt12">
                  <a-button v-if="canUseDraftActions" type="primary" :loading="savingChain" @click="saveAndOpenEditor">
                    <EditOutlined /> {{ t('保存并打开编辑器') }}
                  </a-button>
                  <a-button v-if="canUseDraftActions && unmatchedStepCount === 0" :loading="runningChain" @click="saveAndRun">
                    <PlayCircleOutlined /> {{ t('直接运行') }}
                  </a-button>
                  <a-button v-if="result?.saved_chain_id" type="link" @click="goChain(result.saved_chain_id)">
                    {{ t('打开已保存链路') }} #{{ result.saved_chain_id }}
                  </a-button>
                </div>
              </div>
            </div>
          </div>

          <div class="agent-chat-composer">
            <textarea
              v-model="form.goal"
              class="agent-chat-input"
              :disabled="submitting || polling || cancelling"
              :placeholder="t('描述你要自动化执行的业务链路…')"
              rows="3"
              @keydown.meta.enter.prevent="handleSubmit"
              @keydown.ctrl.enter.prevent="handleSubmit"
            ></textarea>
            <div class="agent-chat-footer">
              <span class="active-env">{{ t('环境：') }}{{ translateText(envStore.activeEnvName) }}</span>
              <a-button
                v-if="!polling"
                type="primary"
                :loading="submitting"
                @click="handleSubmit"
                class="codex-submit-btn"
              >
                <ThunderboltOutlined />
                {{ conversationMessages.length ? t('重新编排') : t('开始编排') }}
              </a-button>
              <a-button
                v-else
                danger
                :loading="cancelling"
                :disabled="cancelling"
                @click="handleCancel"
                class="codex-submit-btn"
              >
                {{ t('取消任务') }}
              </a-button>
            </div>
          </div>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
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
import { locale, t, translateText } from '../../i18n'

const router = useRouter()
const projectStore = useProjectStore()
const envStore = useEnvironmentStore()

// State
const submitting = ref(false)
const polling = ref(false)
const cancelling = ref(false)
const taskId = ref(null)
const taskData = ref(null)
const result = ref(null)
const resultStatus = ref(null)
const taskError = ref(null)
let pollTimer = null
let pollingInFlight = false

// Save & run state
const savingChain = ref(false)
const runningChain = ref(false)
const runResult = ref(null)
const expandedSteps = ref(new Set())
const savedChainId = ref(null)
const feedbackSavingKey = ref('')

const DEFAULT_GOAL_ZH = '创建订单，查询订单'
const DEFAULT_GOAL_EN = 'Create order, query order'
const defaultGoal = () => t(DEFAULT_GOAL_ZH)
const form = reactive({ goal: defaultGoal() })
const submittedGoal = ref('')
const chatResumeSnapshot = ref(null)

watch(locale, (nextLocale, prevLocale) => {
  const previousDefault = prevLocale === 'en' ? DEFAULT_GOAL_EN : DEFAULT_GOAL_ZH
  if (!form.goal || form.goal === previousDefault) {
    form.goal = nextLocale === 'en' ? DEFAULT_GOAL_EN : DEFAULT_GOAL_ZH
  }
})

// Build match lookup: step_index → match
const matchesByStep = computed(() => {
  const map = {}
  for (const m of chatInterfaceMatches.value || []) {
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
const hasDraftResult = computed(() => {
  const finalResult = result.value || taskData.value?.result
  const status = resultStatus.value || taskData.value?.status
  if (!finalResult || taskError.value) return false
  if (['failed', 'timeout', 'cancelled'].includes(status)) return false
  return Boolean(
    status === 'completed' ||
    finalResult.chain_draft ||
    finalResult.saved_chain_id ||
    (result.value && (
      finalResult.steps ||
      finalResult.matches ||
      finalResult.dependency_plan ||
      finalResult.assertion_plan
    ))
  )
})
const effectiveResultStatus = computed(() => {
  if (resultStatus.value) return resultStatus.value
  if (taskData.value?.status) return taskData.value.status
  if (hasDraftResult.value) return 'completed'
  return null
})

const progressStages = computed(() => {
  const stepResults = taskData.value?.step_results || {}
  const keys = ['parse', 'index', 'match', 'dependency', 'assertion', 'draft', 'validate']
  const labels = ['解析步骤', '检索接口', '匹配接口', '规划依赖', '断言规划', '生成草稿', '校验结果']
  const stageStatuses = [
    stepResults.step_planning?.status,
    stepResults.index_init?.status,
    stepResults.interface_matching?.status,
    stepResults.dependency_planning?.status,
    stepResults.assertion_planning?.status,
    stepResults.draft_and_validate?.status || (result.value ? 'completed' : null),
    result.value ? 'completed' : null,
  ]
  return keys.map((key, i) => {
    const rawStatus = stageStatuses[i]
    let status = 'wait'
    if (rawStatus === 'completed') status = 'finish'
    else if (rawStatus === 'running') status = 'process'
    else if (rawStatus === 'failed') status = 'error'
    else if (rawStatus === 'cancelled') status = 'error'
    return { key, label: t(labels[i]), status }
  })
})

const modelStageDetails = computed(() => {
  const stepResults = taskData.value?.step_results || {}
  const finalResult = result.value || {}
  return [
    buildModelStage({
      key: 'step_planning',
      title: t('步骤规划'),
      range: [5, 33],
      result: withStageOutput(stepResults.step_planning, finalResult.step_plan),
      trace: finalResult.llm_trace?.step_planning,
      fallbackOutput: finalResult.step_plan,
      summaryBuilder: summarizeStepPlan,
      runningDetail: t('模型正在拆解目标并识别业务步骤'),
      completedDetail: t('已生成业务步骤'),
    }),
    buildModelStage({
      key: 'interface_matching',
      title: t('接口匹配'),
      range: [38, 66],
      result: withStageOutput(stepResults.interface_matching, buildInterfaceMatchOutput(finalResult.matches)),
      trace: finalResult.llm_trace?.interface_matching,
      fallbackOutput: { matches: finalResult.matches },
      summaryBuilder: summarizeInterfaceMatch,
      runningDetail: t('模型正在从候选接口中选择匹配项'),
      completedDetail: t('已完成接口匹配'),
    }),
    buildModelStage({
      key: 'dependency_planning',
      title: t('依赖规划'),
      range: [71, 95],
      result: withStageOutput(stepResults.dependency_planning, finalResult.dependency_plan),
      trace: finalResult.llm_trace?.dependency_planning,
      fallbackOutput: finalResult.dependency_plan,
      summaryBuilder: summarizeDependencyPlan,
      runningDetail: t('模型正在规划上下游参数传递'),
      completedDetail: t('已生成参数依赖规划'),
    }),
    buildModelStage({
      key: 'assertion_planning',
      title: t('断言规划'),
      range: [84, 94],
      result: withStageOutput(stepResults.assertion_planning, buildAssertionPlanOutput(finalResult.assertion_plan)),
      trace: finalResult.llm_trace?.assertion_planning,
      fallbackOutput: { items: finalResult.assertion_plan },
      summaryBuilder: summarizeAssertionPlan,
      runningDetail: t('正在根据响应结构和依赖字段生成断言'),
      completedDetail: t('已生成断言规则'),
    }),
  ].filter(stage => stage.visible)
})

const progressStatus = computed(() => {
  const s = effectiveResultStatus.value
  if (s === 'failed' || s === 'timeout') return 'exception'
  if (s === 'cancelled') return 'exception'
  if (s === 'completed') return 'normal'
  return 'active'
})

const progressText = computed(() => {
  if (polling.value) return localize(currentStep.value || '正在编排链路')
  if (effectiveResultStatus.value === 'cancelled') return t('任务已取消')
  if (effectiveResultStatus.value === 'failed' || effectiveResultStatus.value === 'timeout') return t('编排失败，请查看校验结果')
  if (effectiveResultStatus.value === 'completed') return t('编排完成')
  return ''
})

const chatStatusText = computed(() => {
  if (submitting.value) return t('提交中')
  if (polling.value) return t('编排中')
  if (effectiveResultStatus.value === 'completed') return t('已完成')
  if (effectiveResultStatus.value === 'failed' || effectiveResultStatus.value === 'timeout') return t('失败')
  if (effectiveResultStatus.value === 'cancelled') return t('已取消')
  return t('待开始')
})

const steps = computed(() => result.value?.steps || [])
const candidates = computed(() => result.value?.candidates_by_step || [])
const chatCandidates = computed(() => {
  return result.value?.candidates_by_step ||
    taskData.value?.result?.candidates_by_step ||
    chatResumeSnapshot.value?.candidates_by_step ||
    []
})
const parameterRequirements = computed(() => result.value?.parameter_requirements || [])
const assertionPlan = computed(() => result.value?.assertion_plan || [])
const allWarnings = computed(() => result.value?.warnings || [])
const trialAuthorizationQuestions = computed(() => {
  return (result.value?.questions || []).filter(item => item?.type === 'trial_run_authorization')
})
const canUseDraftActions = computed(() => {
  return Boolean(
    effectiveResultStatus.value === 'completed' &&
    result.value?.chain_draft?.nodes?.length &&
    unmatchedStepCount.value < totalInterfaceStepCount.value &&
    trialAuthorizationQuestions.value.length === 0
  )
})
const chainJson = computed(() => result.value?.chain_draft ? JSON.stringify(result.value.chain_draft, null, 2) : '{}')

const chatStepPlanSteps = computed(() => {
  return result.value?.steps ||
    taskData.value?.step_results?.step_planning?.output?.steps ||
    chatResumeSnapshot.value?.steps ||
    []
})

const chatInterfaceMatches = computed(() => {
  return result.value?.matches ||
    taskData.value?.step_results?.interface_matching?.output?.matches ||
    chatResumeSnapshot.value?.matches ||
    []
})

const chatDependencyLines = computed(() => {
  const plan = result.value?.dependency_plan || taskData.value?.step_results?.dependency_planning?.output || {}
  const mappings = plan.mappings || []
  const missing = plan.missing_inputs || []
  const lines = mappings.map(item => {
    const fromStep = item.from_step || '-'
    const toStep = item.to_step || '-'
    const fromKey = item.from_key || item.from_var || item.source || '-'
    const toKey = item.to_key || item.to_field || item.target || '-'
    return `${t('第')} ${fromStep} ${t('步')} ${fromKey} → ${t('第')} ${toStep} ${t('步')} ${toKey}`
  })
  return lines.concat(missing.map(item => localize(item.message || `${t('缺少参数：')}${item.field || '-'}`)))
})

const conversationMessages = computed(() => {
  const messages = []
  const goal = submittedGoal.value || form.goal
  if (goal?.trim()) {
    messages.push({
      id: 'user-goal',
      role: 'user',
      title: t('目标描述'),
      summary: goal.trim(),
    })
  }

  const stepResults = taskData.value?.step_results || {}
  const finalResult = result.value || taskData.value?.result || {}
  const restoredStepPlanning = chatResumeSnapshot.value?.step_plan
    ? {
        status: 'completed',
        progress: 100,
        output: chatResumeSnapshot.value.step_plan,
        restored: true,
      }
    : null
  const restoredInterfaceMatching = chatResumeSnapshot.value?.matches
    ? {
        status: 'completed',
        progress: 100,
        output: {
          matches: chatResumeSnapshot.value.matches,
          match_count: chatResumeSnapshot.value.matches.filter(match => match.selected_interface_id || match.selected_interface).length,
        },
        restored: true,
      }
    : null
  const indexInitStage = stepResults.index_init
  const stepPlanningStage = withStageOutput(
    stepResults.step_planning || restoredStepPlanning || fallbackCompletedStage(finalResult.step_plan),
    finalResult.step_plan || stepResults.step_planning?.output || restoredStepPlanning?.output,
  )
  const interfaceMatchingStage = withStageOutput(
    stepResults.interface_matching || restoredInterfaceMatching || fallbackCompletedStage(finalResult.matches),
    buildInterfaceMatchOutput(finalResult.matches) || stepResults.interface_matching?.output || restoredInterfaceMatching?.output,
  )
  const dependencyPlanningStage = withStageOutput(
    stepResults.dependency_planning || fallbackCompletedStage(finalResult.dependency_plan),
    finalResult.dependency_plan || stepResults.dependency_planning?.output,
  )
  const assertionPlanningStage = withStageOutput(
    stepResults.assertion_planning || fallbackCompletedStage(finalResult.assertion_plan),
    buildAssertionPlanOutput(finalResult.assertion_plan) || stepResults.assertion_planning?.output,
  )
  const stageMessages = [
    buildChatStageMessage({
      key: 'index_init',
      title: t('接口索引初始化'),
      stage: indexInitStage,
      runningSummary: t('我正在读取项目接口画像并构建检索索引。'),
      completedSummary: indexInitChatSummary,
      progress: 5,
    }),
    buildChatStageMessage({
      key: 'step_planning',
      title: t('步骤规划'),
      detailType: 'step_planning',
      detailTitle: t('展开查看识别到的业务步骤'),
      stage: stepPlanningStage,
      runningSummary: t('我正在拆解你的目标，识别需要执行的业务步骤。'),
      completedSummary: stepPlanChatSummary,
      progress: 25,
    }),
    buildChatStageMessage({
      key: 'interface_matching',
      title: t('接口匹配'),
      detailType: 'interface_matching',
      detailTitle: t('展开查看接口选择原因'),
      stage: interfaceMatchingStage,
      runningSummary: t('我正在从项目接口中为每个步骤选择最合适的接口。'),
      completedSummary: interfaceMatchChatSummary,
      progress: 55,
    }),
    buildChatStageMessage({
      key: 'dependency_planning',
      title: t('参数依赖规划'),
      detailType: 'dependency_planning',
      detailTitle: t('展开查看参数如何传递'),
      stage: dependencyPlanningStage,
      runningSummary: t('我正在规划步骤之间的参数传递和缺失参数。'),
      completedSummary: dependencyChatSummary,
      progress: 82,
    }),
    buildChatStageMessage({
      key: 'assertion_planning',
      title: t('断言规划'),
      detailType: 'assertion_planning',
      detailTitle: t('展开查看生成的断言'),
      stage: assertionPlanningStage,
      runningSummary: t('我正在根据响应结构和业务目标生成断言规则。'),
      completedSummary: assertionChatSummary,
      progress: 94,
    }),
  ].filter(Boolean)

  messages.push(...stageMessages)

  if (result.value || taskError.value || effectiveResultStatus.value === 'cancelled') {
    messages.push(buildFinalChatMessage())
  }

  return messages
})
const runDiagnostics = computed(() => {
  const items = []
  for (const step of runResult.value?.step_results || []) {
    for (const diag of step.diagnostics || []) {
      items.push({
        ...diag,
        step_label: step.label || step.node_label || step.node_id,
      })
    }
  }
  return items
})
const planStageBadges = computed(() => {
  const trace = result.value?.llm_trace || {}
  const modelStages = [
    { key: 'step', label: t('步骤规划'), trace: trace.step_planning },
    { key: 'match', label: t('接口匹配'), trace: trace.interface_matching },
    { key: 'dependency', label: t('依赖规划'), trace: trace.dependency_planning },
    { key: 'assertion', label: t('断言规划'), trace: trace.assertion_planning },
  ]
    .filter(item => item.trace?.provider)
    .map(item => ({
      key: item.key,
      label: item.label,
      text: `${item.trace.provider} / ${item.trace.model || '-'}`,
      color: 'purple',
    }))

  if (!trace.assertion_planning && (result.value?.assertion_plan || taskData.value?.step_results?.assertion_planning)) {
    modelStages.push({
      key: 'assertion',
      label: t('断言规划'),
      text: t('规则引擎'),
      color: 'blue',
    })
  }
  return modelStages
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
      matchReason: match?.reason || (selected ? '' : t('未匹配到接口')),
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

function isSelectedCandidate(stepIndex, interfaceId) {
  return matchesByStep.value[stepIndex]?.selected_interface_id === interfaceId
}

function selectedMatchForCandidate(stepIndex, interfaceId) {
  const match = matchesByStep.value[stepIndex]
  return match?.selected_interface_id === interfaceId ? match : null
}

function candidateReasons(record) {
  return record?.score_reasons || record?.pre_reason || []
}

function candidateModelReason(stepIndex, interfaceId) {
  const match = selectedMatchForCandidate(stepIndex, interfaceId)
  if (!match) return ''
  const confidence = Math.round((match.confidence || 0) * 100)
  const reason = match.reason || match.selected_interface?.llm_reason || ''
  return `${t('置信度')} ${confidence}%${reason ? `：${localize(reason)}` : ''}`
}

function candidateScoreParts(record) {
  const labels = {
    exact_name: '名称完全匹配',
    name_similarity: '名称相似',
    semantic_name_similarity: '语义相似',
    description: '描述命中',
    url: 'URL 命中',
    path: '路径命中',
    request_fields: '请求字段',
    response_fields: '响应字段',
    group: '分组命中',
    total: '总分',
  }
  const breakdown = record?.score_breakdown || {}
  const parts = []
  for (const [key, label] of Object.entries(labels)) {
    const value = Number(breakdown[key] || 0)
    if (value > 0 || key === 'total') {
      parts.push({ key, label: t(label), value: value.toFixed(2) })
    }
  }
  if (!parts.length && record?.pre_score !== undefined) {
    parts.push({ key: 'total', label: t('总分'), value: Number(record.pre_score || 0).toFixed(2) })
  }
  return parts
}

function feedbackKey(stepIndex, interfaceId) {
  return `${stepIndex}:${interfaceId}`
}

async function rememberCandidate(stepItem, record) {
  const stepText = stepItem.resolved_text || stepItem.step_text
  const key = feedbackKey(stepItem.step_index, record.interface_id)
  feedbackSavingKey.value = key
  try {
    await agentApi.saveInterfaceFeedback({
      project_id: projectStore.activeProjectId,
      step_text: stepText,
      interface_id: record.interface_id,
      reason: `用户确认「${stepText}」使用接口「${record.name || record.url}」`,
    })
    message.success(t('已记住该匹配，下次同类步骤会优先推荐'))
  } catch (e) {
    message.error(localize(e?.response?.data?.detail || '保存匹配记忆失败'))
  } finally {
    feedbackSavingKey.value = ''
  }
}

function countMissingFields(item) {
  return (item.fields || []).filter(field => ['missing', 'suggested'].includes(field.status)).length
}

function paramStatusColor(status) {
  const colors = { mapped: 'green', default: 'blue', suggested: 'gold', missing: 'orange' }
  return colors[status] || 'default'
}

function paramStatusText(status) {
  const labels = { mapped: '已映射', default: '默认值', suggested: '建议映射', missing: '需补充' }
  return t(labels[status] || status)
}

function diagnosticKey(item) {
  return `${item.node_id || ''}:${item.type || ''}:${item.message || ''}:${item.jsonpath || ''}`
}

function diagnosticColor(level) {
  const colors = { error: 'red', warning: 'orange', info: 'blue' }
  return colors[level] || 'blue'
}

function diagnosticLevelText(level) {
  const labels = { error: '错误', warning: '警告', info: '提示' }
  return t(labels[level] || '提示')
}

function buildModelStage({ key, title, range, result: stageResult, trace, fallbackOutput, summaryBuilder, runningDetail, completedDetail }) {
  const status = stageResult?.status || (fallbackOutput ? 'completed' : 'wait')
  const output = stageResult?.output || fallbackOutput
  const visible = status !== 'wait' || Boolean(output) || polling.value || result.value
  const statusText = status === 'completed' ? t('完成') : status === 'running' ? t('进行中') : status === 'failed' ? t('失败') : t('等待')
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
    detail: status === 'running' ? runningDetail : status === 'completed' ? completedDetail : localize(stageResult?.error || '等待开始'),
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
  return steps.map(step => `${t('Step')} ${step.index}: ${localize(step.text || step.resolved_text || '')}`)
}

function summarizeInterfaceMatch(output) {
  const matches = output.matches || []
  if (!matches.length && output.match_count !== undefined) return [t('已匹配 {count} 个接口').replace('{count}', output.match_count)]
  return matches.map(match => {
    const selected = match.selected_interface
    const name = selected ? `${selected.method || ''} ${translateText(selected.name || selected.url || '')}`.trim() : t('未选择接口')
    const confidence = Math.round((match.confidence || 0) * 100)
    return `${t('Step')} ${match.step_index}: ${name} (${confidence}%)${match.reason ? ` - ${localize(match.reason)}` : ''}`
  })
}

function summarizeDependencyPlan(output) {
  const mappings = output.mappings || []
  const missing = output.missing_inputs || []
  const lines = mappings.map(item => `${t('Step')} ${item.from_step} ${item.from_key || item.from_var} → ${t('Step')} ${item.to_step} ${item.to_key || item.to_field}`)
  return lines.concat(missing.map(item => localize(item.message || `${t('缺少参数：')}${item.field || '-'}`)))
}

function summarizeAssertionPlan(output) {
  const items = output.items || []
  return items.map(item => {
    const count = item.assertions?.length || 0
    const enabled = (item.assertions || []).filter(rule => rule.enabled).length
    return `${t('Step')} ${item.step_index}: ${enabled}/${count} ${t('条断言默认启用')}`
  })
}

function completeChatStageWhen(stage, shouldComplete, output) {
  if (!stage && !shouldComplete) return null
  if (!shouldComplete) return stage
  return {
    ...(stage || {}),
    status: 'completed',
    progress: 100,
    output: output || stage?.output || {},
  }
}

function withStageOutput(stage, output) {
  if (!stage) return null
  if (output === undefined || output === null || stage.output) return stage
  return {
    ...stage,
    output,
  }
}

function fallbackCompletedStage(output) {
  if (output === undefined || output === null) return null
  return {
    status: 'completed',
    progress: 100,
    output,
  }
}

function buildInterfaceMatchOutput(matches) {
  if (!matches) return null
  return {
    matches,
    match_count: matches.filter(match => match.selected_interface_id || match.selected_interface).length,
  }
}

function buildAssertionPlanOutput(items) {
  if (!items) return null
  return { items }
}

function buildChatStageMessage({ key, title, detailType, detailTitle, stage, runningSummary, completedSummary, progress }) {
  if (!stage) return null
  const displayStage = normalizeStageForDisplay(key, stage)
  const status = displayStage.status || 'running'
  const failed = status === 'failed'
  const cancelled = status === 'cancelled'
  const completed = status === 'completed'
  const fallbackProgress = completed || failed || cancelled ? 100 : progress
  const stageProgress = Math.max(0, Math.min(100, Number(displayStage.progress ?? fallbackProgress ?? 5)))
  const summary = completed
    ? completedSummary(displayStage.output || displayStage.checkpoint || displayStage || {})
    : failed
      ? localize(displayStage.error || '该阶段执行失败')
      : cancelled
        ? localize(displayStage.error || '该阶段已取消')
        : runningSummary

  return {
    id: `stage-${key}`,
    renderKey: buildStageRenderKey(key, displayStage, status, stageProgress),
    role: 'agent',
    title,
    summary,
    status,
    statusText: completed ? t('完成') : failed ? t('失败') : cancelled ? t('已取消') : t('进行中'),
    statusColor: completed ? 'green' : failed ? 'red' : cancelled ? 'orange' : 'blue',
    progress: stageProgress,
    detailType,
    detailTitle,
  }
}

function normalizeStageForDisplay(key, stage) {
  const backendStage = taskData.value?.step_results?.[key]
  const sourceStage = backendStage || stage
  const displayStage = {
    ...sourceStage,
    output: backendStage?.output || stage?.output || sourceStage?.output,
    checkpoint: backendStage?.checkpoint || stage?.checkpoint || sourceStage?.checkpoint,
  }

  if (['completed', 'failed', 'cancelled'].includes(displayStage.status)) {
    return {
      ...displayStage,
      progress: 100,
    }
  }

  return displayStage
}

function buildStageRenderKey(key, stage, status, progress) {
  return [
    'stage',
    key,
    status || 'unknown',
    progress ?? 'na',
    stage?.completed_at || '',
    stage?.updated_at || '',
    stage?.checkpoint?.completed_at || '',
    taskData.value?.status || '',
  ].join(':')
}

function buildFinalChatMessage() {
  if (resultStatus.value === 'cancelled') {
    return {
      id: 'final-cancelled',
      role: 'agent',
      title: t('编排已取消'),
      summary: t('任务已取消，你可以调整目标后重新编排。'),
      status: 'cancelled',
      statusText: t('已取消'),
      statusColor: 'orange',
    }
  }

  if (taskError.value || resultStatus.value === 'failed' || resultStatus.value === 'timeout') {
    return {
      id: 'final-error',
      role: 'agent',
      title: t('编排失败'),
      summary: localize(taskError.value || result.value?.error_message || result.value?.message || '编排失败'),
      status: 'failed',
      statusText: t('失败'),
      statusColor: 'red',
    }
  }

  const hasQuestions = trialAuthorizationQuestions.value.length > 0
  const unmatched = unmatchedStepCount.value
  let summary = t('链路草稿已生成。')
  if (hasQuestions) {
    summary = t('链路草稿已生成，但有写接口需要授权调试后继续补充响应字段。')
  } else if (unmatched > 0) {
    summary = t('{count} 个步骤未匹配到接口，请在编辑器中手动选择接口后再运行').replace('{count}', unmatched)
  } else {
    summary = t('链路草稿已生成，所有步骤已匹配接口，可保存或直接运行。')
  }

  return {
    id: 'final-result',
    role: 'agent',
    title: t('链路草稿'),
    summary,
    status: 'completed',
    statusText: t('完成'),
    statusColor: hasQuestions || unmatched > 0 ? 'orange' : 'green',
    detailType: 'draft',
    detailTitle: t('展开查看完整草稿和模型信息'),
    showActions: true,
    showTrialQuestions: hasQuestions,
  }
}

function stepPlanChatSummary(output) {
  const steps = output.steps || chatStepPlanSteps.value || []
  if (!steps.length) return t('已完成步骤规划。')
  const names = steps.map(step => localize(step.resolved_text || step.text)).filter(Boolean)
  return t('识别到 {count} 个业务步骤：').replace('{count}', steps.length) + names.join(' → ')
}

function indexInitChatSummary(output) {
  const count = output.profile_count ?? output.checkpoint?.profile_count
  if (count !== undefined) return t('已读取 {count} 个接口画像，索引初始化完成。').replace('{count}', count)
  return t('接口索引初始化完成。')
}

function interfaceMatchChatSummary(output) {
  const matches = output.matches || chatInterfaceMatches.value || []
  if (!matches.length) return t('已完成接口匹配。')
  const matched = matches.filter(match => match.selected_interface_id || match.selected_interface).length
  return t('已完成接口匹配：{matched}/{total} 个步骤匹配到接口。')
    .replace('{matched}', matched)
    .replace('{total}', matches.length)
}

function dependencyChatSummary(output) {
  const mappings = output.mappings || []
  const missing = output.missing_inputs || []
  if (!mappings.length && !missing.length) return t('已完成参数依赖规划，暂无跨步骤参数依赖。')
  const prefix = t('已规划 {count} 条参数依赖').replace('{count}', mappings.length)
  if (!missing.length) return `${prefix}。`
  return `${prefix}，${t('仍有 {count} 个参数需确认').replace('{count}', missing.length)}。`
}

function assertionChatSummary(output) {
  const items = output.items || assertionPlan.value || []
  const count = items.reduce((sum, item) => sum + (item.assertions?.length || 0), 0)
  if (!count) return t('已完成断言规划，暂无默认断言。')
  return t('已生成 {count} 条断言规则。').replace('{count}', count)
}

function buildChatResumeSnapshot() {
  const stepPlan = result.value?.step_plan ||
    taskData.value?.step_results?.step_planning?.output ||
    chatResumeSnapshot.value?.step_plan ||
    {}
  const steps = result.value?.steps ||
    stepPlan.steps ||
    chatResumeSnapshot.value?.steps ||
    []
  const matches = result.value?.matches ||
    taskData.value?.step_results?.interface_matching?.output?.matches ||
    chatResumeSnapshot.value?.matches ||
    []
  const candidatesByStep = result.value?.candidates_by_step ||
    taskData.value?.result?.candidates_by_step ||
    chatResumeSnapshot.value?.candidates_by_step ||
    []

  return {
    step_plan: {
      ...stepPlan,
      steps,
    },
    steps,
    matches,
    candidates_by_step: candidatesByStep,
  }
}

function assertionKey(stepIndex, rule) {
  return `${stepIndex}:${rule.jsonpath}:${rule.operator}:${rule.expected}`
}

function assertionNeedsExpected(operator) {
  return !['exists', 'not_exists'].includes(operator)
}

function assertionOperatorText(operator) {
  const labels = {
    equals: '=',
    not_equals: '!=',
    contains: 'contains',
    not_contains: 'not contains',
    greater_than: '>',
    less_than: '<',
    exists: t('存在'),
    not_exists: t('不存在'),
  }
  return labels[operator] || operator
}

function assertionSourceText(source) {
  const labels = {
    base: t('基础断言'),
    schema: t('响应结构'),
    dependency: t('依赖字段'),
    semantic: t('业务语义'),
    model: t('模型补充'),
    user_memory: t('用户记忆'),
  }
  return labels[source] || source || t('规则')
}

function formatAssertionExpected(value) {
  if (value === true) return 'true'
  if (value === false) return 'false'
  if (value === null || value === undefined) return ''
  return String(value)
}

function signedScore(value) {
  const n = Number(value || 0)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function localize(value) {
  return translateText(value == null ? '' : String(value))
}

// ---- Submit & Poll ----

async function handleSubmit(options = {}) {
  if (!form.goal.trim()) { message.warning(t('请输入要编排的目标')); return }
  submittedGoal.value = form.goal.trim()
  if (!options.keepChatSnapshot) chatResumeSnapshot.value = null
  result.value = null
  resultStatus.value = null
  taskData.value = null
  taskError.value = null
  taskId.value = null
  runResult.value = null
  savedChainId.value = null
  cancelling.value = false

  submitting.value = true
  try {
    const response = await agentApi.submitPlan({
      goal: form.goal,
      project_id: projectStore.activeProjectId,
      auto_save: false,
      auto_execute: false,
      environment_id: envStore.activeEnvironmentId,
      trial_policy: options.trialPolicy || {},
    })
    taskId.value = response.task_id
    message.info(t('任务已提交，正在编排中...'))
    startPolling()
  } catch (error) {
    const msg = localize(error?.response?.data?.detail || error?.message || '提交任务失败')
    taskError.value = msg
    message.error(msg)
  } finally {
    submitting.value = false
  }
}

function trialQuestionKey(item) {
  return `${item.step_index || ''}-${item.interface_id || ''}`
}

function trialDebugText(item) {
  return t(
    '第 {step} 步「{name}」是写接口，链路规划完成后请进入编辑器授权调试以补充响应字段'
  )
    .replace('{step}', item.step_index || '-')
    .replace('{name}', translateText(item.interface_name || item.url || ''))
}

async function authorizeTrialRun(item) {
  const trialPolicy = {
    authorized_step_indexes: item.step_index ? [item.step_index] : [],
    authorized_interface_ids: item.interface_id ? [item.interface_id] : [],
  }
  chatResumeSnapshot.value = buildChatResumeSnapshot()

  // If we have a current taskId from a completed task, use the resume API
  // to continue from the checkpoint instead of starting from scratch
  if (taskId.value && resultStatus.value === 'completed') {
    submitting.value = true
    resultStatus.value = null
    taskError.value = null
    try {
      const response = await agentApi.resumePlan(taskId.value, trialPolicy)
      taskId.value = response.task_id
      message.info(t('从断点恢复中，重新获取授权接口的响应...'))
      startPolling()
    } catch (error) {
      const msg = localize(error?.response?.data?.detail || error?.message || '恢复任务失败')
      taskError.value = msg
      message.error(msg)
    } finally {
      submitting.value = false
    }
  } else {
    // Fallback: no completed task to resume from, submit a new plan
    handleSubmit({ trialPolicy, keepChatSnapshot: true })
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
  if (pollingInFlight) return
  pollingInFlight = true
  try {
    const data = await agentApi.getPlanStatus(taskId.value)
    taskData.value = mergeTaskData(taskData.value, data)
    resultStatus.value = data.status
    if (data.status === 'completed') {
      result.value = data.result
      if (data.result?.saved_chain_id) savedChainId.value = data.result.saved_chain_id
      stopPolling()
      if (result.value?.error_code) message.error(localize(result.value.message || '编排失败'))
      else message.success(t('已生成链路草稿'))
    } else if (data.status === 'failed' || data.status === 'timeout') {
      result.value = data.result
      taskError.value = localize(data.error_message || '编排失败')
      stopPolling()
      message.error(taskError.value)
    } else if (data.status === 'cancelled') {
      resultStatus.value = 'cancelled'
      taskError.value = t('任务已取消')
      stopPolling()
      message.warning(t('任务已取消'))
    }
  } catch { /* transient error, keep polling */ }
  finally {
    pollingInFlight = false
  }
}

function stopPolling() {
  if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null }
  polling.value = false
}

function mergeTaskData(previous, next) {
  if (!previous) return next
  if (!next) return previous

  const merged = {
    ...previous,
    ...next,
    progress: Math.max(Number(previous.progress || 0), Number(next.progress || 0)),
    step_results: mergeStepResults(previous.step_results, next.step_results),
  }

  if (isFinalStatus(previous.status) && !isFinalStatus(next.status)) {
    merged.status = previous.status
    merged.current_step = previous.current_step
    merged.result = previous.result || next.result
  }

  return merged
}

function mergeStepResults(previous = {}, next = {}) {
  const merged = { ...previous, ...next }
  for (const key of Object.keys(merged)) {
    merged[key] = mergeStageResult(previous[key], next[key])
  }
  return merged
}

function mergeStageResult(previous, next) {
  if (!previous) return normalizeFinalStageProgress(next)
  if (!next) return normalizeFinalStageProgress(previous)

  const previousFinal = isFinalStatus(previous.status)
  const nextFinal = isFinalStatus(next.status)
  const preferred = previousFinal && !nextFinal ? previous : next
  const secondary = preferred === next ? previous : next
  const progress = Math.max(Number(previous.progress || 0), Number(next.progress || 0))

  return normalizeFinalStageProgress({
    ...secondary,
    ...preferred,
    output: preferred.output || secondary.output,
    checkpoint: preferred.checkpoint || secondary.checkpoint,
    progress,
  })
}

function normalizeFinalStageProgress(stage) {
  if (!stage) return stage
  if (!isFinalStatus(stage.status)) return stage
  return {
    ...stage,
    progress: 100,
  }
}

function isFinalStatus(status) {
  return ['completed', 'failed', 'timeout', 'cancelled'].includes(status)
}

async function handleCancel() {
  if (!taskId.value) return
  cancelling.value = true
  try {
    await agentApi.cancelPlan(taskId.value)
    message.info(t('正在取消任务...'))
  } catch (e) {
    const msg = localize(e?.response?.data?.detail || e?.message || '取消任务失败')
    message.error(msg)
  } finally {
    cancelling.value = false
  }
}

// ---- Save & Run ----

function buildChainData(status = 'ready') {
  const draft = result.value.chain_draft
  return {
    name: draft.name || form.goal.substring(0, 80),
    description: draft.description || t('由 Agent 生成的链路草稿'),
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
    message.success(t('链路已保存'))
    router.push({ path: '/chain-test', query: { id: chainId } })
  } catch (e) {
    message.error(localize(e?.response?.data?.detail || '保存链路失败'))
  } finally {
    savingChain.value = false
  }
}

async function saveAndRun() {
  runningChain.value = true
  runResult.value = null
  try {
    const chainId = await saveChain()
    message.info(t('链路已保存，正在执行...'))
    const execResult = await chainApi.executeChain(chainId, envStore.activeEnvironmentId)
    runResult.value = execResult
    const failCount = execResult.step_results?.filter(s => s.status === 'failed').length || 0
    if (execResult.status === 'completed' && !failCount) message.success(t('链路执行完成，全部通过'))
    else if (failCount) message.warning(t('链路执行完成，{count} 个节点失败').replace('{count}', failCount))
    else message.error(`${t('链路执行失败')}: ${localize(execResult.error_message || '未知错误')}`)
  } catch (e) {
    message.error(localize(e?.response?.data?.detail || '执行链路失败'))
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

/* ===== 阶段式对话流 ===== */
.agent-chat-panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 132px);
  min-height: 640px;
  max-width: 1180px;
  margin: 0 auto;
  background: #f8fafc;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  overflow: hidden;
}
.agent-chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: #ffffff;
  border-bottom: 1px solid #eaecf0;
}
.agent-chat-header strong {
  display: block;
  color: #101828;
  font-size: 15px;
}
.agent-chat-header span {
  display: block;
  margin-top: 2px;
  color: #667085;
  font-size: 12px;
}
.agent-chat-stream {
  flex: 1;
  overflow: auto;
  padding: 16px;
}
.agent-chat-empty {
  padding: 28px 16px;
  text-align: center;
  color: #667085;
}
.agent-chat-empty-title {
  color: #344054;
  font-weight: 600;
  margin-bottom: 6px;
}
.agent-chat-empty-desc {
  font-size: 12px;
  line-height: 1.6;
}
.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}
.chat-message-user {
  flex-direction: row-reverse;
}
.chat-avatar {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #155eef;
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
}
.chat-message-user .chat-avatar {
  background: #101828;
}
.chat-bubble {
  max-width: min(920px, calc(100% - 38px));
  padding: 11px 12px;
  background: #ffffff;
  border: 1px solid #eaecf0;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.chat-message-user .chat-bubble {
  background: #155eef;
  border-color: #155eef;
  color: #ffffff;
  max-width: min(720px, calc(100% - 38px));
}
.chat-bubble-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 5px;
}
.chat-bubble-head strong {
  font-size: 13px;
  color: #101828;
}
.chat-message-user .chat-bubble-head strong {
  color: #ffffff;
}
.chat-summary {
  color: #475467;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.chat-message-user .chat-summary {
  color: #ffffff;
}
.chat-progress {
  margin-top: 8px;
}
.chat-detail-collapse {
  margin-top: 8px;
  border-top: 1px solid #f2f4f7;
}
.chat-detail-collapse :deep(.ant-collapse-header) {
  padding: 8px 0 0 !important;
  color: #475467 !important;
  font-size: 12px;
}
.chat-detail-collapse :deep(.ant-collapse-content-box) {
  padding: 8px 0 0 !important;
}
.chat-nested-collapse {
  margin-top: 8px;
}
.chat-nested-collapse :deep(.ant-collapse-header) {
  padding: 8px 0 !important;
  font-size: 12px;
  color: #344054 !important;
}
.chat-nested-collapse :deep(.ant-collapse-content-box) {
  padding: 0 0 8px !important;
}
.chat-divider {
  margin: 12px 0 4px;
  color: #667085;
  font-size: 12px;
}
.chat-candidate-table {
  overflow-x: auto;
}
.chat-candidate-table :deep(.ant-table) {
  min-width: 760px;
}
.chat-detail-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chat-detail-item {
  padding: 8px 10px;
  background: #fcfcfd;
  border: 1px solid #eaecf0;
  border-radius: 6px;
  color: #344054;
  font-size: 12px;
  line-height: 1.5;
}
.chat-detail-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.chat-detail-text {
  color: #1d2939;
  overflow-wrap: anywhere;
}
.chat-detail-reason {
  margin-top: 4px;
  color: #667085;
}
.chat-assertion-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.chat-json-preview {
  max-height: 260px;
  overflow: auto;
  margin: 10px 0 0;
  padding: 10px;
  background: #101828;
  color: #f2f4f7;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.agent-chat-composer {
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #eaecf0;
}
.agent-chat-input {
  width: 100%;
  min-height: 72px;
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  resize: vertical;
  outline: none;
  color: #101828;
  font-size: 14px;
  line-height: 1.5;
}
.agent-chat-input:focus {
  border-color: #155eef;
  box-shadow: 0 0 0 3px rgba(21, 94, 239, 0.12);
}
.agent-chat-input:disabled {
  background: #f2f4f7;
  color: #98a2b3;
  cursor: not-allowed;
}
.agent-chat-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

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
.candidate-table :deep(.ant-table-cell) { vertical-align: middle; }
.candidate-cell-text {
  display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.candidate-url { color: #475467; font-size: 12px; }
.candidate-reason-cell {
  min-height: 24px; display: flex; align-items: center; justify-content: flex-start; gap: 4px; flex-wrap: wrap;
}
.remember-btn { padding: 0 !important; height: 20px !important; font-size: 12px; }
.candidate-explain {
  display: flex; flex-direction: column; gap: 8px;
  padding: 8px 10px; background: #fcfcfd; border: 1px solid #eaecf0; border-radius: 6px;
}
.candidate-explain-block { display: flex; flex-direction: column; gap: 4px; }
.candidate-explain-title { color: #344054; font-size: 12px; font-weight: 600; }
.candidate-explain-text { color: #475467; font-size: 12px; line-height: 1.5; }
.candidate-reasons {
  margin: 0; padding-left: 18px; color: #475467; font-size: 12px; line-height: 1.6;
}
.param-requirement-list { display: flex; flex-direction: column; gap: 8px; }
.param-requirement-item {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 8px; background: #fcfcfd; border: 1px solid #eaecf0; border-radius: 6px;
}
.param-field { font-family: monospace; color: #1d2939; font-weight: 600; }
.param-message { color: #475467; font-size: 12px; }
.param-source { color: #2f54eb; font-size: 12px; }
.assertion-plan-list { display: flex; flex-direction: column; gap: 8px; }
.assertion-plan-item {
  padding: 8px 10px; background: #fcfcfd; border: 1px solid #eaecf0; border-radius: 6px;
}
.assertion-plan-main {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.assertion-path {
  font-family: monospace; color: #1d2939; font-weight: 600; overflow-wrap: anywhere;
}
.assertion-op { color: #475467; font-size: 12px; }
.assertion-expected {
  font-family: monospace; color: #1d2939; font-size: 12px; overflow-wrap: anywhere;
}
.assertion-plan-meta {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-top: 6px; color: #475467; font-size: 12px; line-height: 1.5;
}
.assertion-score-parts {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;
}
.llm-trace { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.trial-auth-panel {
  display: flex; flex-direction: column; gap: 8px;
}
.trial-auth-item {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 10px 12px; border: 1px solid #ffd591; border-radius: 6px; background: #fff7e6;
}
.trial-auth-main {
  display: flex; flex-direction: column; gap: 4px; min-width: 0;
  color: #1f2937; font-size: 12px; line-height: 1.5;
}
.trial-auth-main strong { color: #ad6800; font-size: 13px; }
.trial-auth-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; color: #475467;
}
.trial-auth-url {
  max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; font-size: 11px;
}
.trial-auth-actions {
  display: flex; gap: 6px; flex-shrink: 0;
}
.json-preview {
  max-height: 360px; overflow: auto; margin: 0; padding: 12px;
  background: #101828; color: #f2f4f7; border-radius: 6px;
  font-size: 12px; line-height: 1.6;
}
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; }

/* Run result styles */
.run-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.run-time { color: #8c8c8c; font-size: 13px; }
.diagnostic-panel {
  display: flex; flex-direction: column; gap: 8px;
  margin: 10px 0 14px; padding: 10px 12px;
  background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px;
}
.diagnostic-title { color: #ad6800; font-size: 13px; font-weight: 600; }
.diagnostic-item { display: flex; align-items: flex-start; gap: 8px; }
.diagnostic-content { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.diagnostic-message { color: #1f2937; font-size: 12px; line-height: 1.5; }
.diagnostic-suggestion { color: #475467; font-size: 12px; line-height: 1.5; }
.diagnostic-confidence { color: #8c8c8c; font-size: 11px; }
.run-steps { margin-top: 8px; }
.run-step-detail { font-size: 12px; }
.run-diagnostics-inline { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
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
