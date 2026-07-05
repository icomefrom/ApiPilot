<template>
  <a-drawer
    :open="visible"
    :title="drawerTitle"
    :width="420"
    placement="right"
    @close="handleClose"
  >
    <template v-if="node">
      <!-- 公共：标签名 -->
      <a-form layout="vertical" size="small">
        <a-form-item label="节点标签">
          <a-input v-model:value="node.data.label" @change="emitChange" />
        </a-form-item>
      </a-form>

      <a-divider style="margin: 8px 0" />

      <!-- ========== 接口节点 ========== -->
      <template v-if="node.type === 'interface'">
        <a-form layout="vertical" size="small">
          <a-form-item label="选择接口">
            <a-select
              v-model:value="node.data.interface_id"
              placeholder="请选择已保存的接口"
              show-search
              option-filter-prop="label"
              @change="onInterfaceSelect"
            >
              <a-select-option
                v-for="iface in interfaces"
                :key="iface.id"
                :value="iface.id"
                :label="`${iface.method} ${iface.name}`"
              >
                <span class="method-tag" :class="'method-' + (iface.method || 'GET').toLowerCase()">
                  {{ iface.method || 'GET' }}
                </span>
                {{ iface.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-form>

        <!-- 变量引用（参数覆盖） -->
        <div class="panel-section" v-if="selectedInterface">
          <div class="panel-section-header">
            <span>变量引用</span>
            <a-tooltip title="用 {{vars.变量名}} 引用上游提取值，{{globals.变量名}} 引用全局参数">
              <QuestionCircleOutlined style="color: #8c8c8c; font-size: 13px" />
            </a-tooltip>
          </div>
          <a-form layout="vertical" size="small">
            <!-- URL -->
            <a-form-item label="URL" class="compact-form-item">
              <div class="kv-row">
                <a-input v-model:value="node.data.overrides.url" :placeholder="selectedInterface.url" style="flex: 1" @change="emitChange" />
                <a-dropdown :trigger="['click']">
                  <a-button type="text" size="small" class="var-btn"><VarDirectiveOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key }) => insertVar('url', key)">
                      <a-menu-item v-for="v in availableVars" :key="`vars.${v}`">上游变量: {{ v }}</a-menu-item>
                      <a-menu-divider v-if="availableVars.length && globalKeys.length" />
                      <a-menu-item v-for="g in globalKeys" :key="`globals.${g}`">全局参数: {{ g }}</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </a-form-item>
            <!-- Headers -->
            <a-form-item label="请求头" class="compact-form-item">
              <div v-for="(val, key) in overrideHeaders" :key="key" class="kv-row">
                <a-input :value="key" disabled style="width: 30%" />
                <a-input v-model:value="overrideHeaders[key]" :placeholder="String(selectedInterface.headers?.[key] ?? '')" style="flex: 1" @change="syncOverridesFromKv('headers'); emitChange()" />
                <a-dropdown :trigger="['click']">
                  <a-button type="text" size="small" class="var-btn"><VarDirectiveOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key: varKey }) => insertVarToKv('headers', key, varKey)">
                      <a-menu-item v-for="v in availableVars" :key="`vars.${v}`">上游变量: {{ v }}</a-menu-item>
                      <a-menu-divider v-if="availableVars.length && globalKeys.length" />
                      <a-menu-item v-for="g in globalKeys" :key="`globals.${g}`">全局参数: {{ g }}</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
                <a-button type="text" danger size="small" @click="removeOverrideKv('headers', key)"><DeleteOutlined /></a-button>
              </div>
              <KeyPicker
                :interfaceData="selectedInterface"
                sourceField="headers"
                :existingKeys="Object.keys(overrideHeaders)"
                addLabel="添加请求头"
                @select="({ key }) => addOverrideKvKey('headers', key)"
              />
            </a-form-item>
            <!-- Query Params -->
            <a-form-item label="参数" class="compact-form-item">
              <div v-for="(val, key) in overrideQueryParams" :key="key" class="kv-row">
                <a-input :value="key" disabled style="width: 30%" />
                <a-input v-model:value="overrideQueryParams[key]" :placeholder="String(selectedInterface.query_params?.[key] ?? '')" style="flex: 1" @change="syncOverridesFromKv('query_params'); emitChange()" />
                <a-dropdown :trigger="['click']">
                  <a-button type="text" size="small" class="var-btn"><VarDirectiveOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key: varKey }) => insertVarToKv('query_params', key, varKey)">
                      <a-menu-item v-for="v in availableVars" :key="`vars.${v}`">上游变量: {{ v }}</a-menu-item>
                      <a-menu-divider v-if="availableVars.length && globalKeys.length" />
                      <a-menu-item v-for="g in globalKeys" :key="`globals.${g}`">全局参数: {{ g }}</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
                <a-button type="text" danger size="small" @click="removeOverrideKv('query_params', key)"><DeleteOutlined /></a-button>
              </div>
              <KeyPicker
                :interfaceData="selectedInterface"
                sourceField="query_params"
                :existingKeys="Object.keys(overrideQueryParams)"
                addLabel="添加参数"
                @select="({ key }) => addOverrideKvKey('query_params', key)"
              />
            </a-form-item>
            <!-- Body Fields KV 模式（JSON body 且有可解析 key） -->
            <a-form-item
              v-if="selectedInterface.body_type === 'json' && hasBodyFieldKeys"
              label="请求体字段"
              class="compact-form-item"
            >
              <div v-for="(val, key) in overrideBodyFields" :key="key" class="kv-row">
                <a-input :value="key" disabled style="width: 30%" />
                <a-input
                  v-model:value="overrideBodyFields[key]"
                  :placeholder="formatBodyValuePlaceholder(_getByPath(originalBodyValues, key))"
                  style="flex: 1"
                  @change="syncOverridesFromKv('body_fields'); emitChange()"
                />
                <a-dropdown :trigger="['click']">
                  <a-button type="text" size="small" class="var-btn"><VarDirectiveOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key: varKey }) => insertVarToKv('body_fields', key, varKey)">
                      <a-menu-item v-for="v in availableVars" :key="`vars.${v}`">上游变量: {{ v }}</a-menu-item>
                      <a-menu-divider v-if="availableVars.length && globalKeys.length" />
                      <a-menu-item v-for="g in globalKeys" :key="`globals.${g}`">全局参数: {{ g }}</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
                <a-button type="text" danger size="small" @click="removeOverrideKv('body_fields', key)"><DeleteOutlined /></a-button>
              </div>
              <KeyPicker
                :interfaceData="selectedInterface"
                sourceField="body_fields"
                :existingKeys="Object.keys(overrideBodyFields)"
                addLabel="添加字段"
                @select="({ key }) => addOverrideKvKey('body_fields', key)"
              />
              <div class="body-mode-hint">
                <a-button type="link" size="small" @click="bodyEditMode = 'textarea'">切换为完整请求体</a-button>
              </div>
            </a-form-item>
            <!-- Body Textarea 模式（非 JSON / 无可解析 key / 用户主动切换） -->
            <a-form-item
              v-else-if="selectedInterface.body_type !== 'none'"
              label="请求体"
              class="compact-form-item"
            >
              <a-textarea
                v-model:value="node.data.overrides.body"
                :placeholder="selectedInterface.body || '请求体内容，可使用 {{vars.xxx}} 引用变量'"
                :auto-size="{ minRows: 2, maxRows: 8 }"
                class="script-editor"
                @change="emitChange"
              />
              <div v-if="selectedInterface.body_type === 'json'" class="body-mode-hint">
                <a-button type="link" size="small" @click="bodyEditMode = 'kv'">切换为字段编辑</a-button>
              </div>
            </a-form-item>
            <!-- WS Message -->
            <a-form-item v-if="selectedInterface.protocol === 'websocket'" label="WS 消息" class="compact-form-item">
              <a-textarea
                v-model:value="node.data.overrides.ws_message"
                :placeholder="selectedInterface.ws_message || 'WebSocket 发送消息'"
                :auto-size="{ minRows: 2, maxRows: 6 }"
                class="script-editor"
                @change="emitChange"
              />
            </a-form-item>
            <!-- RPC Method -->
            <a-form-item v-if="selectedInterface.protocol === 'rpc'" label="RPC 方法" class="compact-form-item">
              <a-input v-model:value="node.data.overrides.rpc_method" :placeholder="selectedInterface.rpc_method || '方法名'" @change="emitChange" />
            </a-form-item>
          </a-form>
        </div>

        <!-- 提取规则 -->
        <div class="panel-section">
          <div class="panel-section-header">
            <span>提取规则</span>
            <a-button type="link" size="small" @click="addExtraction"><PlusOutlined /> 添加</a-button>
          </div>
          <div v-for="(ext, idx) in node.data.extractions" :key="idx" class="extraction-item">
            <a-input v-model:value="ext.var_name" placeholder="变量名" style="width: 30%" @change="emitChange" />
            <JsonPathPicker
              v-model:modelValue="ext.jsonpath"
              :responseData="stepResult?.response || lastExecuteResult"
              class="extraction-jsonpath-picker"
              @change="emitChange"
            />
            <a-button type="text" danger size="small" @click="removeExtraction(idx)"><DeleteOutlined /></a-button>
          </div>
          <a-empty v-if="!node.data.extractions?.length" :image="simpleImage" description="暂无提取规则" />
        </div>

        <!-- 断言规则（支持 JSONPath + 脚本） -->
        <div class="panel-section">
          <div class="panel-section-header">
            <span>断言规则</span>
            <a-button type="link" size="small" @click="addAssertion"><PlusOutlined /> 添加</a-button>
          </div>
          <div v-for="(rule, idx) in node.data.assertions" :key="idx" class="assertion-rule-block">
            <!-- 类型切换 -->
            <div class="assertion-type-row">
              <a-segmented
                v-model:value="rule.type"
                :options="ASSERT_TYPE_OPTIONS"
                size="small"
                @change="emitChange"
              />
              <a-button type="text" danger size="small" @click="removeAssertion(idx)"><DeleteOutlined /></a-button>
            </div>

            <!-- JSONPath 断言 -->
            <template v-if="rule.type === 'jsonpath'">
              <div class="assertion-jsonpath-row">
                <JsonPathPicker
                  v-model:modelValue="rule.jsonpath"
                  :responseData="stepResult?.response || lastExecuteResult"
                  class="assertion-jsonpath-picker"
                  @change="emitChange"
                />
                <a-select v-model:value="rule.operator" style="width: 100px; flex-shrink:0" @change="emitChange">
                  <a-select-option v-for="op in ASSERT_OPERATORS" :key="op.value" :value="op.value">{{ op.label }}</a-select-option>
                </a-select>
              </div>
              <a-input
                v-if="opNeedsExpected(rule.operator)"
                v-model:value="rule.expected"
                placeholder="期望值"
                size="small"
                @change="emitChange"
                style="margin-top: 4px"
              />
            </template>

            <!-- 脚本断言 -->
            <template v-if="rule.type === 'script'">
              <a-textarea
                v-model:value="rule.script"
                class="script-editor"
                :auto-size="{ minRows: 3, maxRows: 12 }"
                :placeholder="SCRIPT_PLACEHOLDER"
                @change="emitChange"
              />
              <div class="script-timeout-row">
                <span>超时</span>
                <a-input-number v-model:value="rule.timeout" :min="1" :max="30" size="small" style="width: 70px" @change="emitChange" />
                <span>秒</span>
              </div>
            </template>
          </div>
          <a-empty v-if="!node.data.assertions?.length" :image="simpleImage" description="暂无断言规则" />
        </div>

        <!-- 执行配置 -->
        <div class="panel-section">
          <div class="panel-section-header">
            <span>执行配置</span>
          </div>
          <a-form layout="inline" size="small">
            <a-form-item label="失败重试" tooltip="节点执行失败后的最大重试次数">
              <a-input-number v-model:value="node.data.retry_count" :min="0" :max="10" style="width: 80px" @change="emitChange" />
            </a-form-item>
            <a-form-item label="重试间隔(秒)">
              <a-input-number v-model:value="node.data.retry_interval" :min="0.5" :max="60" :step="0.5" style="width: 80px" @change="emitChange" />
            </a-form-item>
          </a-form>
        </div>
      </template>

      <!-- ========== 脚本节点 ========== -->
      <template v-if="node.type === 'script'">
        <a-form layout="vertical" size="small">
          <a-form-item label="脚本">
            <a-textarea
              v-model:value="node.data.script"
              class="script-editor"
              :auto-size="{ minRows: 6, maxRows: 20 }"
              placeholder="assert vars['token'] != ''"
              @change="emitChange"
            />
          </a-form-item>
          <a-form-item label="超时(秒)">
            <a-input-number v-model:value="node.data.timeout" :min="1" :max="30" @change="emitChange" />
          </a-form-item>
        </a-form>
      </template>

      <!-- ========== 定时器节点 ========== -->
      <template v-if="node.type === 'timer'">
        <a-form layout="vertical" size="small">
          <a-form-item label="延迟(秒)">
            <a-input-number v-model:value="node.data.delay" :min="0.1" :max="300" :step="0.5" @change="emitChange" />
          </a-form-item>
        </a-form>
      </template>

      <!-- ========== 条件分支节点 ========== -->
      <template v-if="node.type === 'condition'">
        <a-form layout="vertical" size="small">
          <a-form-item label="条件类型">
            <a-segmented
              v-model:value="node.data.condition_type"
              :options="CONDITION_TYPE_OPTIONS"
              size="small"
              @change="onConditionTypeChange"
            />
          </a-form-item>
        </a-form>

        <!-- 变量模式（原有） -->
        <template v-if="node.data.condition_type === 'variable' || !node.data.condition_type">
          <a-form layout="vertical" size="small">
            <a-form-item label="变量来源">
              <a-select v-model:value="node.data.source_var" placeholder="选择变量" @change="emitChange">
                <a-select-option v-for="v in availableVars" :key="v" :value="v">{{ v }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="比较符">
              <a-select v-model:value="node.data.operator" @change="emitChange">
                <a-select-option value="equals">等于</a-select-option>
                <a-select-option value="not_equals">不等于</a-select-option>
                <a-select-option value="contains">包含</a-select-option>
                <a-select-option value="greater_than">大于</a-select-option>
                <a-select-option value="less_than">小于</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="期望值">
              <a-input v-model:value="node.data.expected" @change="emitChange" />
            </a-form-item>
          </a-form>
        </template>

        <!-- JSONPath 模式 -->
        <template v-if="node.data.condition_type === 'jsonpath'">
          <div class="assertion-rule-block">
            <div class="assertion-jsonpath-row">
              <JsonPathPicker
                v-model:modelValue="node.data.jsonpath"
                :responseData="lastExecuteResult"
                class="assertion-jsonpath-picker"
                @change="emitChange"
              />
              <a-select v-model:value="node.data.operator" style="width: 100px; flex-shrink:0" @change="emitChange">
                <a-select-option v-for="op in CONDITION_OPERATORS" :key="op.value" :value="op.value">{{ op.label }}</a-select-option>
              </a-select>
            </div>
            <a-input
              v-if="opNeedsExpected(node.data.operator)"
              v-model:value="node.data.expected"
              placeholder="期望值"
              size="small"
              @change="emitChange"
              style="margin-top: 4px"
            />
          </div>
          <div class="condition-jsonpath-hint" v-if="!lastExecuteResult">
            <a-alert type="info" message="请先运行链路后，可通过 JSONPath 选择上游接口响应字段" show-icon />
          </div>
        </template>

        <!-- 脚本模式 -->
        <template v-if="node.data.condition_type === 'script'">
          <div class="assertion-rule-block">
            <a-textarea
              v-model:value="node.data.script"
              class="script-editor"
              :auto-size="{ minRows: 3, maxRows: 12 }"
              :placeholder="CONDITION_SCRIPT_PLACEHOLDER"
              @change="emitChange"
            />
            <div class="script-timeout-row">
              <span>超时</span>
              <a-input-number v-model:value="node.data.timeout" :min="1" :max="30" size="small" style="width: 70px" @change="emitChange" />
              <span>秒</span>
            </div>
          </div>
        </template>
      </template>

      <!-- ========== 执行结果 ========== -->
      <template v-if="stepResult">
        <a-divider style="margin: 8px 0" />
        <div class="panel-section">
          <div class="panel-section-header"><span>执行结果</span></div>
          <a-alert
            v-if="stepResult.error"
            :message="stepResult.error"
            type="error"
            show-icon
            style="margin-bottom: 8px"
          />
          <a-alert
            v-else
            message="通过"
            type="success"
            show-icon
            style="margin-bottom: 8px"
          />
          <div v-if="stepResult.elapsed_ms" class="result-meta">耗时: {{ stepResult.elapsed_ms }}ms</div>
          <div v-if="stepResult.extractions?.length" class="result-meta">
            <div v-for="ext in stepResult.extractions" :key="ext.var_name">
              提取 {{ ext.var_name }} = {{ JSON.stringify(ext.value) }}
            </div>
          </div>
          <div v-if="stepResult.assertion_results?.length" class="result-meta">
            <div v-for="(ar, aidx) in stepResult.assertion_results" :key="aidx" :class="ar.pass ? 'result-pass' : 'result-fail'">
              <template v-if="ar.rule?.type === 'script'">
                脚本: {{ ar.pass ? '通过' : '失败' }}
                <span v-if="ar.error" style="margin-left: 4px; color: #ff4d4f">{{ ar.error }}</span>
              </template>
              <template v-else-if="ar.rule">
                {{ ar.rule.jsonpath }} {{ ar.rule.operator }} {{ ar.rule.expected }} => {{ ar.pass ? '通过' : '失败' }}
              </template>
            </div>
          </div>
          <div v-if="stepResult.script_result" class="result-meta">
            <div :class="stepResult.script_result.pass ? 'result-pass' : 'result-fail'">
              脚本: {{ stepResult.script_result.pass ? '通过' : '失败' }}
            </div>
            <pre v-if="stepResult.script_result.output" class="script-output">{{ stepResult.script_result.output }}</pre>
          </div>
          <div v-if="stepResult.condition_detail" class="result-meta">
            <template v-if="stepResult.condition_detail.condition_type === 'variable' || !stepResult.condition_detail.condition_type">
              <div :class="stepResult.condition_detail.result ? 'result-pass' : 'result-fail'">
                {{ stepResult.condition_detail.source_var }} {{ stepResult.condition_detail.operator }} {{ stepResult.condition_detail.expected }} => {{ stepResult.condition_detail.result ? 'True' : 'False' }}
              </div>
            </template>
            <template v-else-if="stepResult.condition_detail.condition_type === 'jsonpath'">
              <div :class="stepResult.condition_detail.result ? 'result-pass' : 'result-fail'">
                {{ stepResult.condition_detail.jsonpath }} {{ stepResult.condition_detail.operator }} {{ stepResult.condition_detail.expected }}
              </div>
              <div>实际值: {{ JSON.stringify(stepResult.condition_detail.actual) }} => {{ stepResult.condition_detail.result ? 'True' : 'False' }}</div>
            </template>
            <template v-else-if="stepResult.condition_detail.condition_type === 'script'">
              <div :class="stepResult.condition_detail.pass ? 'result-pass' : 'result-fail'">
                脚本: {{ stepResult.condition_detail.pass ? 'True' : 'False' }}
              </div>
              <div v-if="stepResult.condition_detail.error" style="color: #ff4d4f">{{ stepResult.condition_detail.error }}</div>
              <pre v-if="stepResult.condition_detail.output" class="script-output">{{ stepResult.condition_detail.output }}</pre>
            </template>
          </div>

          <!-- 接口返回结果 -->
          <template v-if="stepResult.response">
            <a-divider style="margin: 8px 0" />
            <div class="panel-section-header"><span>接口返回</span></div>
            <!-- Status -->
            <div class="result-meta" style="margin-bottom: 4px">
              <span style="font-weight: 600">Status:</span>
              <span :style="{ color: stepResult.response.status_code < 400 ? '#52c41a' : '#ff4d4f', marginLeft: '6px' }">
                {{ stepResult.response.status_code }}
              </span>
              <span v-if="stepResult.response.elapsed_ms" style="margin-left: 12px; color: #8c8c8c">
                {{ stepResult.response.elapsed_ms }}ms
              </span>
            </div>
            <!-- Headers -->
            <template v-if="stepResult.response.headers && Object.keys(stepResult.response.headers).length">
              <div class="result-meta result-section-toggle" @click="showRespHeaders = !showRespHeaders">
                <span style="font-weight: 600">Headers</span>
                <span style="color: #8c8c8c; font-size: 10px">{{ showRespHeaders ? '▾' : '▸' }} ({{ Object.keys(stepResult.response.headers).length }})</span>
              </div>
              <div v-if="showRespHeaders" class="result-headers">
                <div v-for="(v, k) in stepResult.response.headers" :key="k" class="result-header-row">
                  <span class="result-header-key">{{ k }}</span>
                  <span class="result-header-val">{{ v }}</span>
                </div>
              </div>
            </template>
            <!-- Body -->
            <template v-if="stepResult.response.body">
              <div class="result-meta result-section-toggle" @click="showRespBody = !showRespBody">
                <span style="font-weight: 600">Body</span>
                <span style="color: #8c8c8c; font-size: 10px">{{ showRespBody ? '▾' : '▸' }}</span>
              </div>
              <div v-if="showRespBody" class="result-body-wrap">
                <a-segmented v-model:value="bodyViewFormat" :options="[{ value: 'pretty', label: '格式化' }, { value: 'raw', label: '原始' }]" size="small" style="margin-bottom: 6px" />
                <pre v-if="bodyViewFormat === 'pretty'" class="result-body-pre">{{ formatResponseBody(stepResult.response.body) }}</pre>
                <pre v-else class="result-body-pre">{{ stepResult.response.body }}</pre>
              </div>
            </template>
          </template>
        </div>
      </template>
    </template>
  </a-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Empty } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, QuestionCircleOutlined, DollarOutlined } from '@ant-design/icons-vue'

// 变量插入图标组件
const VarDirectiveOutlined = DollarOutlined
import { debugApi } from '../../api/debug'
import JsonPathPicker from '../debug/JsonPathPicker.vue'
import KeyPicker from './KeyPicker.vue'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const props = defineProps({
  visible: Boolean,
  node: Object,
  chainResult: Object,
  globals: Array,
  nodes: Array,
})

const emit = defineEmits(['update:visible', 'change'])

const interfaces = ref([])
const lastExecuteResult = ref(null)
const selectedInterface = ref(null)
const bodyEditMode = ref('kv')  // 'kv' | 'textarea'
const showRespHeaders = ref(false)
const showRespBody = ref(true)
const bodyViewFormat = ref('pretty')

const ASSERT_TYPE_OPTIONS = [
  { value: 'jsonpath', label: 'JSONPath' },
  { value: 'script', label: '脚本' },
]

const ASSERT_OPERATORS = [
  { value: 'equals', label: '等于' },
  { value: 'not_equals', label: '不等于' },
  { value: 'contains', label: '包含' },
  { value: 'greater_than', label: '大于' },
  { value: 'less_than', label: '小于' },
  { value: 'exists', label: '存在' },
  { value: 'not_exists', label: '不存在' },
]

const CONDITION_TYPE_OPTIONS = [
  { value: 'variable', label: '变量' },
  { value: 'jsonpath', label: 'JSONPath' },
  { value: 'script', label: '脚本' },
]

const CONDITION_OPERATORS = [
  { value: 'equals', label: '等于' },
  { value: 'not_equals', label: '不等于' },
  { value: 'contains', label: '包含' },
  { value: 'not_contains', label: '不包含' },
  { value: 'greater_than', label: '大于' },
  { value: 'less_than', label: '小于' },
  { value: 'exists', label: '存在' },
  { value: 'not_exists', label: '不存在' },
]

const SCRIPT_PLACEHOLDER = `# 可用变量: vars, globals, response
# vars - 上游提取的变量
# response.status_code / .body / .headers
assert vars.get('token') is not None`

const CONDITION_SCRIPT_PLACEHOLDER = `# 可用变量: vars, globals, response
# 脚本执行通过(True) 走 True 分支，断言失败走 False 分支
# response.status_code / .body / .headers
assert response.status_code == 200`

function opNeedsExpected(operator) {
  return !['exists', 'not_exists'].includes(operator)
}

function onConditionTypeChange() {
  if (!props.node?.data) return
  const ctype = props.node.data.condition_type
  if (ctype === 'jsonpath') {
    if (!props.node.data.jsonpath) props.node.data.jsonpath = ''
    if (!props.node.data.operator) props.node.data.operator = 'equals'
    if (!props.node.data.expected) props.node.data.expected = ''
  } else if (ctype === 'script') {
    if (!props.node.data.script) props.node.data.script = ''
    if (!props.node.data.timeout) props.node.data.timeout = 10
  }
  emitChange()
}

const drawerTitle = computed(() => {
  if (!props.node) return '节点属性'
  const typeLabels = { interface: '接口节点', script: '脚本节点', timer: '定时器', condition: '条件分支' }
  return typeLabels[props.node.type] || '节点属性'
})

// 上游可用的变量列表（从链路节点提取规则静态收集 + 执行结果中已提取的 + 全局参数 key）
const availableVars = computed(() => {
  const vars = new Set()

  // 1. 从链路所有接口节点的提取规则中静态收集变量名
  if (props.nodes) {
    for (const n of props.nodes) {
      const extractions = n.data?.extractions || n.data?.extractions
      if (extractions) {
        for (const ext of extractions) {
          if (ext.var_name) vars.add(ext.var_name)
        }
      }
    }
  }

  // 2. 从链路执行结果中收集已实际提取的变量名（补充运行后出现的变量）
  if (props.chainResult?.step_results) {
    for (const step of props.chainResult.step_results) {
      if (step.extractions) {
        for (const ext of step.extractions) {
          if (ext.var_name) vars.add(ext.var_name)
        }
      }
    }
  }

  return Array.from(vars)
})

// 全局参数 key 列表
const globalKeys = computed(() => {
  if (!props.globals) return []
  return props.globals.filter(g => g.key).map(g => g.key)
})

/**
 * 插入变量占位符到指定覆盖字段（简单 string 字段如 url, body）
 * 直接替换为 {{scope.key}}，如果已有内容则追加
 */
function insertVar(field, varKey) {
  if (!props.node?.data?.overrides) return
  const placeholder = `{{${varKey}}}`
  const current = props.node.data.overrides[field] || ''
  props.node.data.overrides[field] = current ? `${current}${placeholder}` : placeholder
  emitChange()
}

/**
 * 插入变量占位符到 KV dict 的指定 key（headers / query_params）
 * 替换该 key 的值为 {{scope.key}}
 */
function insertVarToKv(dictField, itemKey, varKey) {
  if (!props.node?.data?.overrides) return
  const dict = props.node.data.overrides[dictField]
  if (!dict || !(itemKey in dict)) return
  const placeholder = `{{${varKey}}}`
  dict[itemKey] = dict[itemKey] ? `${dict[itemKey]}${placeholder}` : placeholder
  emitChange()
}

// 当前节点的执行结果
const stepResult = computed(() => {
  if (!props.chainResult?.step_results || !props.node) return null
  const result = props.chainResult.step_results.find(s => s.node_id === props.node.id)
  if (result?.response) {
    lastExecuteResult.value = result.response
  }
  return result
})

// 加载接口列表
async function loadInterfaces() {
  try {
    const data = await debugApi.getInterfaces({ limit: 200 })
    interfaces.value = data.results || data
  } catch { /* ignore */ }
}

watch(() => props.visible, async (v) => {
  if (v) {
    await loadInterfaces()
    // 面板打开时，如果已有选中接口，加载详情并初始化 overrides KV
    if (props.node?.data?.interface_id) {
      try {
        const detail = await debugApi.getInterface(props.node.data.interface_id)
        selectedInterface.value = detail
        if (!props.node.data.overrides || Object.keys(props.node.data.overrides).length <= 1) {
          if (!props.node.data.overrides) props.node.data.overrides = {}
          initOverrideKv('headers', detail.headers || {})
          initOverrideKv('query_params', detail.query_params || {})
          const bodyKeys = _parseBodyKeys(detail.body, detail.body_type)
          initOverrideKv('body_fields', bodyKeys)
        }
        if (!props.node.data.overrides.body_fields) {
          props.node.data.overrides.body_fields = {}
        }
      } catch { /* ignore */ }
    } else {
      selectedInterface.value = null
    }
  }
})

// 当 node 切换（如点击不同节点）时，重新加载接口详情
watch(() => props.node?.id, async (newId, oldId) => {
  if (!props.visible || newId === oldId) return
  selectedInterface.value = null
  bodyEditMode.value = 'kv'
  if (props.node?.data?.interface_id) {
    try {
      const detail = await debugApi.getInterface(props.node.data.interface_id)
      if (props.node?.data?.interface_id !== detail.id) return  // 防过期
      selectedInterface.value = detail
    } catch { /* ignore */ }
  }
})

async function onInterfaceSelect(val) {
  if (!val) { selectedInterface.value = null; return }
  const fetchId = val
  try {
    const detail = await debugApi.getInterface(val)
    if (props.node?.data?.interface_id !== fetchId) return  // 防过期响应
    selectedInterface.value = detail
    props.node.data.interface_name = `${detail.method} ${detail.name}`
    if (!props.node.data.label || props.node.data.label === '接口节点') {
      props.node.data.label = detail.name
    }
    // 确保 overrides 结构完整
    if (!props.node.data.overrides) props.node.data.overrides = {}
    const ov = props.node.data.overrides
    if (!ov.headers) ov.headers = {}
    if (!ov.query_params) ov.query_params = {}
    if (ov.body === undefined) ov.body = ''
    if (!ov.body_fields) ov.body_fields = {}
    if (ov.ws_message === undefined) ov.ws_message = ''
    if (ov.rpc_method === undefined) ov.rpc_method = ''
    if (ov.url === undefined) ov.url = ''
    // 从接口原始参数初始化 KV 行
    initOverrideKv('headers', detail.headers || {})
    initOverrideKv('query_params', detail.query_params || {})
    const bodyKeys = _parseBodyKeys(detail.body, detail.body_type)
    initOverrideKv('body_fields', bodyKeys)
    bodyEditMode.value = 'kv'
    emitChange()
  } catch (e) {
    console.error('加载接口详情失败', e)
  }
}

// 初始化覆盖 KV（从接口原始参数创建 key 列表，值为空表示使用原始值）
function initOverrideKv(field, original) {
  const overrides = props.node.data.overrides || {}
  const existing = overrides[field] || {}
  const merged = {}
  // 保留接口原始 key（值为空 → 执行时用原始值）
  for (const key of Object.keys(original || {})) {
    merged[key] = existing[key] !== undefined ? existing[key] : ''
  }
  // 保留用户加的额外 key
  for (const key of Object.keys(existing)) {
    if (!(key in merged)) merged[key] = existing[key]
  }
  props.node.data.overrides[field] = merged
}

// 响应式 KV 代理：headers / query_params
const overrideHeaders = computed({
  get() { return props.node?.data?.overrides?.headers || {} },
  set(v) { if (props.node?.data?.overrides) props.node.data.overrides.headers = v },
})
const overrideQueryParams = computed({
  get() { return props.node?.data?.overrides?.query_params || {} },
  set(v) { if (props.node?.data?.overrides) props.node.data.overrides.query_params = v },
})

function syncOverridesFromKv(field) {
  // Vue 响应式已自动同步到 node.data.overrides[field]
  // 此函数仅作为显式触发点
}

/**
 * 从 KeyPicker 选中 key 后，添加到指定 override dict 字段
 * @param {string} field - 'headers' | 'query_params' | 'body_fields'
 * @param {string} key - 从接口 JSON 中选出的 key
 */
function addOverrideKvKey(field, key) {
  if (!key) return
  if (!props.node.data.overrides) props.node.data.overrides = {}
  if (!props.node.data.overrides[field]) props.node.data.overrides[field] = {}
  // 如果 key 已存在则跳过
  if (key in props.node.data.overrides[field]) return
  props.node.data.overrides[field][key] = ''
  // 触发响应式更新
  props.node.data.overrides[field] = { ...props.node.data.overrides[field] }
  emitChange()
}

function removeOverrideKv(field, key) {
  if (!props.node?.data?.overrides?.[field]) return
  delete props.node.data.overrides[field][key]
  // 触发响应式更新
  props.node.data.overrides[field] = { ...props.node.data.overrides[field] }
  emitChange()
}

// ---- body_fields 字段级覆盖辅助 ----

/** 解析 body JSON 的顶层 key，返回 { key: '' } 用于初始化 KV 行 */
function _parseBodyKeys(bodyStr, bodyType) {
  if (bodyType !== 'json' || !bodyStr) return {}
  try {
    const parsed = JSON.parse(bodyStr)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const keys = {}
    for (const k of Object.keys(parsed)) keys[k] = ''
    return keys
  } catch { return {} }
}

/** 按点号路径从对象中取值（如 'user.name' → obj.user.name） */
function _getByPath(obj, path) {
  if (!obj || !path) return undefined
  const parts = path.split('.')
  let current = obj
  for (const p of parts) {
    if (current === null || current === undefined || typeof current !== 'object') return undefined
    current = current[p]
  }
  return current
}

/** 原始 body 的解析后完整对象 */
const _parsedBody = computed(() => {
  if (!selectedInterface.value?.body || selectedInterface.value?.body_type !== 'json') return null
  try {
    const parsed = JSON.parse(selectedInterface.value.body)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
    return parsed
  } catch { return null }
})

/** 原始 body 的顶层 key 和值（用于 placeholder 显示） */
const originalBodyValues = computed(() => {
  return _parsedBody.value || {}
})

/** 当前是否应显示 body KV 编辑模式 */
const hasBodyFieldKeys = computed(() => {
  if (bodyEditMode.value !== 'kv') return false
  return Object.keys(originalBodyValues.value).length > 0
})

/** 格式化 body 字段值的 placeholder */
function formatBodyValuePlaceholder(val) {
  if (val === undefined || val === null) return ''
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

/** 格式化接口返回 body（尝试美化 JSON） */
function formatResponseBody(body) {
  if (!body) return ''
  if (typeof body === 'object') {
    try { return JSON.stringify(body, null, 2) } catch { return String(body) }
  }
  try {
    const parsed = JSON.parse(body)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return String(body)
  }
}

// body_fields 响应式代理
const overrideBodyFields = computed({
  get() { return props.node?.data?.overrides?.body_fields || {} },
  set(v) { if (props.node?.data?.overrides) props.node.data.overrides.body_fields = v },
})

function addExtraction() {
  if (!props.node.data.extractions) props.node.data.extractions = []
  props.node.data.extractions.push({ var_name: '', jsonpath: '' })
  emitChange()
}

function removeExtraction(idx) {
  props.node.data.extractions.splice(idx, 1)
  emitChange()
}

function addAssertion() {
  if (!props.node.data.assertions) props.node.data.assertions = []
  props.node.data.assertions.push({
    type: 'jsonpath',
    jsonpath: '',
    operator: 'equals',
    expected: '',
    // 脚本断言字段
    script: '',
    timeout: 10,
  })
  emitChange()
}

function removeAssertion(idx) {
  props.node.data.assertions.splice(idx, 1)
  emitChange()
}

function handleClose() {
  emit('update:visible', false)
}

function emitChange() {
  emit('change')
}
</script>

<style scoped>
.panel-section {
  margin-bottom: 12px;
}

.panel-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.extraction-item {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.extraction-jsonpath-picker {
  flex: 1;
  min-width: 0;
}

.extraction-jsonpath-picker :deep(.ant-input) {
  font-size: 12px;
}

/* 变量引用 KV 行 */
.kv-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.kv-row .ant-input {
  font-size: 12px;
}

/* 变量插入按钮 */
.var-btn {
  flex-shrink: 0;
  color: #1677ff;
  font-size: 13px;
  padding: 0 4px;
}

.var-btn:hover {
  color: #4096ff;
}

.compact-form-item {
  margin-bottom: 8px;
}

.compact-form-item :deep(.ant-form-item-label) {
  padding-bottom: 2px;
}

.compact-form-item :deep(.ant-form-item-label > label) {
  font-size: 12px;
  color: #8c8c8c;
}

/* body 编辑模式切换提示 */
.body-mode-hint {
  margin-top: 4px;
  text-align: right;
}
.body-mode-hint .ant-btn {
  font-size: 11px;
  padding: 0;
  height: auto;
}

/* 断言规则块 */
.assertion-rule-block {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
}

.assertion-type-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.assertion-jsonpath-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.assertion-jsonpath-picker {
  flex: 1;
  min-width: 0;
}

.assertion-jsonpath-picker :deep(.ant-input) {
  font-size: 12px;
}

.script-timeout-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: #8c8c8c;
}

.condition-jsonpath-hint {
  margin-top: 8px;
}

.method-tag {
  display: inline-block;
  padding: 0 4px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  margin-right: 6px;
  color: #fff;
}

.method-get { background: #61affe; }
.method-post { background: #49cc90; }
.method-put { background: #fca130; }
.method-delete { background: #f93e3e; }
.method-patch { background: #50e3c2; }

.script-editor :deep(.ant-input) {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
  background: #1e1e1e !important;
  color: #d4d4d4 !important;
  border: 1px solid #434343 !important;
  border-radius: 6px !important;
  padding: 12px !important;
}

.script-editor :deep(.ant-input)::placeholder {
  color: #6a6a6a !important;
}

.result-meta {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
}

.result-pass { color: #52c41a; }
.result-fail { color: #ff4d4f; }

.script-output {
  max-height: 120px;
  overflow-y: auto;
  padding: 6px 8px;
  background: #f5f5f5;
  border-radius: 4px;
  font-family: monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 4px 0 0;
}

/* 接口返回结果区域 */
.result-section-toggle {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
}
.result-section-toggle:hover {
  background: #f5f5f5;
  border-radius: 3px;
}
.result-headers {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  padding: 4px 6px;
  max-height: 160px;
  overflow-y: auto;
  margin-top: 4px;
}
.result-header-row {
  display: flex;
  gap: 6px;
  font-size: 11px;
  line-height: 1.6;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}
.result-header-key {
  color: #8c8c8c;
  flex-shrink: 0;
  min-width: 0;
  word-break: break-all;
}
.result-header-key::after { content: ':'; }
.result-header-val {
  color: #262626;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-body-wrap {
  margin-top: 4px;
}
.result-body-pre {
  margin: 0;
  padding: 8px 10px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>