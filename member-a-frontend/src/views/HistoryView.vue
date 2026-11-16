<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, errorText } from '../services/api'
import type { Attempt } from '../types/api'
import StateNotice from '../components/StateNotice.vue'
const attempts = ref<Attempt[]>([]), loading = ref(true), error = ref('')
async function load() { loading.value = true; error.value = ''; try { attempts.value = await api.attempts() } catch (e) { error.value = errorText(e) } finally { loading.value = false } }
onMounted(load)
</script>
<template><div class="page-heading"><p class="eyebrow">04 / 学习记录</p><h1>测验历史</h1><p class="muted">从已有报告开始复测。当前展示课程、得分与记录编号；后端同时保留提交时间。</p></div><StateNotice :loading="loading" :error="error" :empty="!attempts.length" empty-text="还没有测验记录，先前往课程页面完成一次测验。" @retry="load" /><div v-if="!loading && !error" class="card-grid"><article v-for="item in attempts" :key="item.id" class="card"><p class="muted">{{ item.course_id }}</p><h2>{{ item.score }} / {{ item.max_score }} 分</h2><p v-if="!item.report" class="hint">{{ item.ai_status === 'processing' ? '报告准备中；成绩已保存。' : item.ai_status === 'disabled' ? '诊断功能未启用；成绩已保存。' : '诊断服务尚未可用；成绩已保存。' }}</p><p class="identifier">测验编号：{{ item.id }}</p><div class="actions"><RouterLink class="button" :to="`/report/${item.id}`">查看报告</RouterLink><RouterLink class="button secondary" :to="{ path: `/quiz/${item.course_id}`, query: { baseline: item.id } }">复测</RouterLink></div></article></div></template>
