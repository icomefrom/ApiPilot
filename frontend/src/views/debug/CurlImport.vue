<template>
  <a-modal
    v-model:open="visible"
    title="导入 cURL"
    width="640px"
    @ok="handleParse"
    :confirmLoading="parsing"
    okText="解析"
    cancelText="取消"
  >
    <a-textarea
      v-model:value="curlText"
      placeholder="粘贴 cURL 命令，例如：&#10;curl -X POST https://api.example.com/login -H 'Content-Type: application/json' -d '{&quot;username&quot;:&quot;admin&quot;}'"
      :auto-size="{ minRows: 6, maxRows: 16 }"
      style="font-family: monospace; font-size: 12px;"
    />
    <div v-if="parseError" style="color: #ff4d4f; margin-top: 8px; font-size: 12px;">
      {{ parseError }}
    </div>
  </a-modal>
</template>

<script setup>
import { ref } from 'vue'
import { useDebugStore } from '../../stores/debug'
import { message } from 'ant-design-vue'

const emit = defineEmits(['parsed'])
const debugStore = useDebugStore()

const visible = ref(false)
const curlText = ref('')
const parsing = ref(false)
const parseError = ref('')

function open() {
  visible.value = true
  curlText.value = ''
  parseError.value = ''
}

async function handleParse() {
  if (!curlText.value.trim()) {
    parseError.value = '请输入 cURL 命令'
    return
  }
  parsing.value = true
  parseError.value = ''
  try {
    const result = await debugStore.parseCurl(curlText.value)
    debugStore.fillFromCurl(result)
    visible.value = false
    message.success('cURL 解析成功')
    emit('parsed', result)
  } catch (err) {
    parseError.value = err?.response?.data?.detail || err?.message || '解析失败，请检查 cURL 命令格式'
  } finally {
    parsing.value = false
  }
}

defineExpose({ open })
</script>