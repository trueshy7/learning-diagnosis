<script setup lang="ts">
import { api } from '../../api/services';
import { useLoad } from '../../composables/useLoad';
import PageState from '../../components/common/PageState.vue';
const { data, loading, error, reload } = useLoad(() => 'courses', api.courses);
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">MY LEARNING</span>
    <h1>我的课程</h1>
    <p>从课程出发，完成测验、理解诊断，再安排下一步学习。</p>
  </div>
  <PageState
    empty-title="暂无课程"
    empty-text="请联系教师配置课程后再开始学习。"
    :loading="loading"
    :error="error"
    :empty="!!data && !data.length"
    @retry="reload"
  />
  <div v-if="data?.length" class="course-grid">
    <router-link
      v-for="c in data"
      :key="c.course_id"
      :to="`/courses/${encodeURIComponent(c.course_id)}`"
      class="course-entry"
      ><span class="course-glyph">{ }</span
      ><span class="eyebrow">COURSE WORKSPACE</span>
      <h2>{{ c.title }}</h2>
      <p>{{ c.description }}</p>
      <div class="course-entry-bottom">
        <span>{{ c.knowledge_points.length }} 个知识点</span
        ><strong>进入课程 →</strong>
      </div></router-link
    >
  </div>
</template>
