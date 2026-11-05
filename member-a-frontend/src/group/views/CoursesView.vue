<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, errorText } from '../services/api';
import type { Course } from '../types/api';
import StateNotice from '../components/StateNotice.vue';
const courses = ref<Course[]>([]),
  loading = ref(true),
  error = ref('');
async function load() {
  loading.value = true;
  error.value = '';
  try {
    courses.value = await api.courses();
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <p class="eyebrow">01 / 课程与测验</p>
    <h1>选择一门课程</h1>
    <p class="muted">选择课程完成测验，查看本次表现与复习建议。</p>
  </div>
  <StateNotice
    :loading="loading"
    :error="error"
    :empty="!courses.length"
    @retry="load"
  />
  <div v-if="!loading && !error" class="card-grid">
    <article v-for="course in courses" :key="course.id" class="card">
      <h2>{{ course.name }}</h2>
      <p>{{ course.description }}</p>
      <RouterLink class="button" :to="`/quiz/${course.id}`"
        >开始测验</RouterLink
      >
    </article>
  </div>
</template>
