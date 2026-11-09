<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, errorText } from '../services/api';
import type { Attempt } from '../types/api';
import StateNotice from '../components/StateNotice.vue';
const attempts = ref<Attempt[]>([]),
  loading = ref(true),
  error = ref(''),
  page = ref(1),
  names = ref<Record<string, string>>({});
const pages = computed(() =>
  Math.max(1, Math.ceil(attempts.value.length / 10)),
);
const visible = computed(() =>
  attempts.value.slice((page.value - 1) * 10, page.value * 10),
);
function date(time: number) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(time * 1000));
}
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [records, courses] = await Promise.all([
      api.attempts(),
      api.courses(),
    ]);
    attempts.value = records;
    names.value = Object.fromEntries(courses.map((c) => [c.id, c.name]));
    page.value = 1;
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
    <p class="eyebrow">04 / 学习记录</p>
    <h1>测验历史</h1>
    <p class="muted">回顾本次表现，或选择一份记录作为复测基准。</p>
  </div>
  <StateNotice
    :loading="loading"
    :error="error"
    :empty="!attempts.length"
    empty-text="还没有测验记录，先前往课程页面完成一次测验。"
    @retry="load"
  /><template v-if="!loading && !error"
    ><div class="card-grid">
      <article v-for="item in visible" :key="item.id" class="card">
        <h2>{{ names[item.course_id] || '课程测验' }}</h2>
        <p class="muted">{{ date(item.created_at) }}</p>
        <p class="score">
          {{ item.score }} <small>/ {{ item.max_score }}</small>
        </p>
        <p v-if="!item.report" class="hint">
          成绩已保存，{{
            item.ai_status === 'processing'
              ? '报告准备中'
              : item.ai_status === 'disabled'
                ? '诊断功能未启用'
                : '诊断暂不可用'
          }}。
        </p>
        <div class="actions">
          <RouterLink class="button" :to="'/report/' + item.id"
            >查看报告</RouterLink
          ><RouterLink
            class="button secondary"
            :to="{
              path: '/quiz/' + item.course_id,
              query: { baseline: item.id },
            }"
            >复测</RouterLink
          >
        </div>
      </article>
    </div>
    <div v-if="attempts.length" class="actions">
      <button class="secondary" :disabled="page <= 1" @click="page--">
        上一页</button
      ><span role="status"
        >第 {{ page }} / {{ pages }} 页，共 {{ attempts.length }} 条</span
      ><button class="secondary" :disabled="page >= pages" @click="page++">
        下一页
      </button>
    </div></template
  >
</template>
