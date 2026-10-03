<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useFormValidation, required } from '@/composables/useFormValidation'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')

const { touched, errors, isValid, touch, touchAll } = useFormValidation({
  username: { value: username, rules: [required()] },
  password: { value: password, rules: [required()] },
})

async function onSubmit() {
  touchAll()
  if (!isValid.value) return
  error.value = ''
  const result = await auth.login(username.value, password.value)
  if (result.ok) {
    // Role-aware landing — CASHIER -> the live working screen, ACCOUNTANT/
    // OWNER -> the read-only back-office dashboard (mirrors router's
    // homeRouteFor; kept inline here since this is the only other spot
    // that needs it).
    router.push(auth.user?.role === 'CASHIER' ? '/game-day' : '/dashboard')
  } else {
    error.value = result.error
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card card" novalidate @submit.prevent="onSubmit">
      <div class="login-brand">
        <div class="login-logo">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8">
            <circle cx="12" cy="12" r="8" /><path d="M12 8v8M8 12h8" />
          </svg>
        </div>
        <div class="login-title">Staff Login</div>
        <div class="login-subtitle">Player Payment Tracking — Staff Access</div>
      </div>

      <label class="field">
        <span class="eyebrow">Username</span>
        <input
          v-model="username" type="text" autocomplete="username" autofocus
          :class="{ 'input--invalid': touched.username && errors.username }" @blur="touch('username')"
        />
        <p v-if="touched.username && errors.username" class="field-error">{{ errors.username }}</p>
      </label>

      <label class="field">
        <span class="eyebrow">Password</span>
        <input
          v-model="password" type="password" autocomplete="current-password"
          :class="{ 'input--invalid': touched.password && errors.password }" @blur="touch('password')"
        />
        <p v-if="touched.password && errors.password" class="field-error">{{ errors.password }}</p>
      </label>

      <p v-if="error" class="form-error">{{ error }}</p>

      <button class="btn btn--primary" type="submit" :disabled="auth.loading">
        {{ auth.loading ? 'Signing in…' : 'Sign In' }}
      </button>

      <p class="login-help">Trouble logging in? Ask the Owner to reset your password.</p>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 20px;
}
.login-card {
  width: 480px;
  max-width: 100%;
  padding: 48px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  margin-bottom: 8px;
}
.login-logo {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}
.login-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field input {
  height: 52px;
}
.field input[type='password'] {
  font-family: var(--font-mono);
  letter-spacing: 0.12em;
}
.login-help {
  text-align: center;
  font-size: 12.5px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
</style>
