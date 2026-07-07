<template>
  <div class="profile">
    <h2 style="margin-bottom: 24px">个人信息</h2>

    <a-row :gutter="24">
      <a-col :span="12">
        <a-card title="基本信息">
          <a-form :model="profileForm" :label-col="{ span: 6 }" :wrapper-col="{ span: 16 }">
            <a-form-item label="用户名">
              <a-input :value="userStore.userInfo?.username" disabled />
            </a-form-item>
            <a-form-item label="邮箱">
              <a-input v-model:value="profileForm.email" />
            </a-form-item>
            <a-form-item label="手机号">
              <a-input v-model:value="profileForm.phone" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 16 }">
              <a-button type="primary" :loading="saving" @click="handleSaveProfile">保存</a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>

      <a-col :span="12">
        <a-card title="修改密码">
          <a-form :model="pwdForm" :label-col="{ span: 6 }" :wrapper-col="{ span: 16 }">
            <a-form-item label="旧密码">
              <a-input-password v-model:value="pwdForm.old_password" />
            </a-form-item>
            <a-form-item label="新密码">
              <a-input-password v-model:value="pwdForm.new_password" />
            </a-form-item>
            <a-form-item label="确认密码">
              <a-input-password v-model:value="pwdForm.confirm_password" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 16 }">
              <a-button type="primary" :loading="changingPwd" @click="handleChangePassword">修改密码</a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useUserStore } from '../stores/user'
import { authApi } from '../api/auth'

const userStore = useUserStore()
const saving = ref(false)
const changingPwd = ref(false)

const profileForm = reactive({
  email: '',
  phone: '',
})

const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

onMounted(() => {
  if (userStore.userInfo) {
    profileForm.email = userStore.userInfo.email || ''
    profileForm.phone = userStore.userInfo.phone || ''
  }
})

async function handleSaveProfile() {
  saving.value = true
  try {
    await authApi.updateProfile({
      email: profileForm.email,
      phone: profileForm.phone,
    })
    await userStore.fetchProfile()
    message.success('保存成功')
  } catch (e) {
    // 已在拦截器处理
  } finally {
    saving.value = false
  }
}

async function handleChangePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    message.error('请填写旧密码和新密码')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    message.error('两次输入的密码不一致')
    return
  }
  if (pwdForm.new_password.length < 6) {
    message.error('密码至少6位')
    return
  }
  changingPwd.value = true
  try {
    await authApi.changePassword(pwdForm.old_password, pwdForm.new_password)
    message.success('密码修改成功，请重新登录')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch (e) {
    // 已在拦截器处理
  } finally {
    changingPwd.value = false
  }
}
</script>