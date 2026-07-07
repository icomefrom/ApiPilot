<template>
  <div class="forbidden-page">
    <a-segmented class="public-lang-switch" :value="locale" size="small" :options="languageOptions" @change="setLocale" />
    <a-result
      status="403"
      title="403"
      sub-title="抱歉，您没有权限访问此页面。"
    >
      <template #extra>
        <a-button type="primary" @click="$router.push('/')">返回首页</a-button>
      </template>
    </a-result>
  </div>
</template>

<script setup>
import { locale, setLocale } from '../i18n'

const languageOptions = [
  { label: '中', value: 'zh' },
  { label: 'EN', value: 'en' },
]
</script>

<style scoped>
.forbidden-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}

.public-lang-switch {
  position: fixed;
  top: 18px;
  right: 18px;
}
</style>
