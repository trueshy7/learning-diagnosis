<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useMock } from './services/api'
const auth = useAuthStore()
const router = useRouter()
function logout() { auth.logout(); router.push('/login') }
</script>
<template>
  <header class="site-header"><div class="container header-inner">
    <RouterLink class="brand" to="/courses"><strong>学习诊断与推荐</strong><small>基于 RAG 与多智能体协作 · 课程设计初始骨架</small></RouterLink>
    <nav v-if="auth.user" aria-label="主导航"><RouterLink to="/courses">课程测验</RouterLink><RouterLink to="/history">测验历史</RouterLink><RouterLink v-if="auth.user.role === 'teacher'" to="/teacher">教师概况</RouterLink><button class="text-button" @click="logout">退出 {{ auth.user.username }}</button></nav>
  </div></header>
  <main class="container main"><div class="mode-banner" :class="{ live: !useMock }">{{ useMock ? '本地样例数据：固定规则演示，未连接检索或大模型。' : '后端接口模式：结果以服务返回的运行模式与状态为准。' }}</div><RouterView /></main>
  <footer class="container footer">《基于 RAG 与多智能体协作的个性化学习诊断与推荐系统》 · 成员 A 前端起步工程</footer>
</template>
