<template>
  <a-config-provider :locale="antdLocale">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import enUS from 'ant-design-vue/es/locale/en_US'
import { installDomI18n, locale } from './i18n'

const antdLocale = computed(() => locale.value === 'en' ? enUS : zhCN)
let stopI18n = null

onMounted(() => {
  stopI18n = installDomI18n()
})

onBeforeUnmount(() => {
  stopI18n?.()
})
</script>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}
</style>
