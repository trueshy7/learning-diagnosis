<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { errorText } from '../services/api';
const username = ref(''),
  password = ref(''),
  busy = ref(false),
  error = ref(''),
  auth = useAuthStore(),
  router = useRouter();
async function submit() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await auth.login(username.value, password.value);
    password.value = '';
    await router.push('/courses');
  } catch (e) {
    error.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="card login-card">
    <p class="eyebrow">开始学习诊断</p>
    <h1>登录学习工作台</h1>
    <p class="muted">完成测验，了解本次表现，找到下一步复习方向。</p>
    <form @submit.prevent="submit">
      <label
        >用户名<input
          v-model.trim="username"
          autocomplete="username"
          required
          maxlength="64" /></label
      ><label
        >密码<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          maxlength="128"
      /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button :disabled="busy">{{ busy ? '正在登录……' : '登录' }}</button>
    </form>
    <p class="hint">请使用教师或管理员提供的账号。</p>
  </section>
</template>
