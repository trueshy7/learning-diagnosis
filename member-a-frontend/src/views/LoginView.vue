<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { errorText } from '../services/api'
const username = ref('student'), password = ref('demo12345'), busy = ref(false), error = ref('')
const auth = useAuthStore(), router = useRouter()
async function submit() { busy.value = true; error.value = ''; try { await auth.login(username.value, password.value); await router.push('/courses') } catch (e) { error.value = errorText(e) } finally { busy.value = false } }
</script>
<template><section class="card login-card"><p class="eyebrow">开始学习诊断</p><h1>登录学习工作台</h1><p class="muted">先完成一次测验，再查看知识点表现与复习建议。</p><form @submit.prevent="submit"><label>用户名<input v-model.trim="username" autocomplete="username" required /></label><label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label><p v-if="error" class="error" role="alert">{{ error }}</p><button :disabled="busy">{{ busy ? '正在登录……' : '登录' }}</button></form><p class="hint">演示账号：student 或 teacher；密码均为 demo12345。<br />这些账号仅供本地课程设计演示。</p></section></template>
