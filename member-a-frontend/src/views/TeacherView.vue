<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, errorText, useMock } from '../services/api'
import type { TeacherOverview } from '../types/api'
import StateNotice from '../components/StateNotice.vue'
const overview = ref<TeacherOverview | null>(null), loading = ref(true), error = ref('')
async function load() { loading.value = true; error.value = ''; try { overview.value = await api.teacherOverview() } catch (e) { error.value = errorText(e) } finally { loading.value = false } }
onMounted(load)
</script>
<template><div class="page-heading"><p class="eyebrow">教师工作台</p><h1>系统概况</h1><p class="muted">教师权限由后端校验；前端导航控制仅用于交互。</p></div><StateNotice :loading="loading" :error="error" @retry="load" /><div v-if="overview && !error" class="stat-grid"><div class="card"><span>用户</span><strong>{{ overview.user_count }}</strong></div><div class="card"><span>题目</span><strong>{{ overview.question_count }}</strong></div><div class="card"><span>测验记录</span><strong>{{ overview.attempt_count }}</strong></div><div class="card"><span>学习资源</span><strong>{{ overview.resource_count }}</strong></div></div><p v-if="useMock" class="hint">本地模式的测验数量仅统计当前教师账号在当前浏览器的样例记录，其他数量为固定样例。</p><section class="card"><h2>后续开发入口</h2><p>按成员 A 的任务书逐步增加课程管理、题目编辑与资源管理界面，并先与 B 确认对应接口。初始骨架仅提供概况页。</p></section></template>
