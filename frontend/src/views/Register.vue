<template>
  <div class="register-container">
    <div class="register-card">
      <div class="register-header">
        <h1>缺陷猎手</h1>
        <p>Bug Shoot</p>
      </div>
      <a-form
        :model="formState"
        :rules="rules"
        @finish="handleRegister"
        class="register-form"
      >
        <a-form-item name="username">
          <a-input
            v-model:value="formState.username"
            size="large"
            placeholder="用户名"
          >
            <template #prefix>
              <UserOutlined style="color: rgba(0,0,0,.25)" />
            </template>
          </a-input>
        </a-form-item>
        <a-form-item name="email">
          <a-input
            v-model:value="formState.email"
            size="large"
            placeholder="邮箱（可选）"
          >
            <template #prefix>
              <MailOutlined style="color: rgba(0,0,0,.25)" />
            </template>
          </a-input>
        </a-form-item>
        <a-form-item name="password">
          <a-input-password
            v-model:value="formState.password"
            size="large"
            placeholder="密码（至少6位）"
          >
            <template #prefix>
              <LockOutlined style="color: rgba(0,0,0,.25)" />
            </template>
          </a-input-password>
        </a-form-item>
        <a-form-item name="password_confirm">
          <a-input-password
            v-model:value="formState.password_confirm"
            size="large"
            placeholder="确认密码"
          >
            <template #prefix>
              <LockOutlined style="color: rgba(0,0,0,.25)" />
            </template>
          </a-input-password>
        </a-form-item>
        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            size="large"
            :loading="loading"
            block
          >
            注 册
          </a-button>
        </a-form-item>
      </a-form>
      <div class="register-footer">
        已有账号？
        <router-link to="/login">去登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useUserStore } from '../stores/user'
import { authApi } from '../api/auth'

const router = useRouter()
const loading = ref(false)

const formState = reactive({
  username: '',
  email: '',
  password: '',
  password_confirm: '',
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少3个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  password_confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_, value) => {
        if (value && value !== formState.password) {
          return Promise.reject('两次密码不一致')
        }
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
}

async function handleRegister() {
  loading.value = true
  try {
    const res = await authApi.register({
      username: formState.username,
      email: formState.email,
      password: formState.password,
      password_confirm: formState.password_confirm,
    })
    // 注册成功，自动登录
    const userStore = useUserStore()
    userStore.token = res.access
    userStore.refreshToken = res.refresh
    userStore.userInfo = res.user
    localStorage.setItem('access_token', res.access)
    localStorage.setItem('refresh_token', res.refresh)
    message.success('注册成功')
    router.push('/')
  } catch (error) {
    // error handled by interceptor
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.register-card {
  width: 400px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
}

.register-header {
  text-align: center;
  margin-bottom: 24px;
}

.register-header h1 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #333;
}

.register-header p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

.register-form {
  max-width: 320px;
  margin: 0 auto;
}

.register-footer {
  text-align: center;
  color: #666;
  font-size: 13px;
  margin-top: 16px;
}
</style>