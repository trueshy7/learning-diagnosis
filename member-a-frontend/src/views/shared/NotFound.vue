<script setup lang="ts">
import { useRoute } from 'vue-router';
const route = useRoute();
</script>
<template>
  <section class="panel state">
    <span class="eyebrow">{{ route.path === '/403' ? '403' : '404' }}</span>
    <h1>{{ route.path === '/403' ? '无权访问此页面' : '没有找到这个页面' }}</h1>
    <p>请返回当前账号的工作空间。</p>
    <router-link to="/">返回本人首页 →</router-link>
  </section>
</template>
