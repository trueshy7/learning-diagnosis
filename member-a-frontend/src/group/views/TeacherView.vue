<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, errorText } from '../services/api';
import type { TeacherOverview, Course } from '../types/api';
import StateNotice from '../components/StateNotice.vue';
const overview = ref<TeacherOverview | null>(null),
  loading = ref(true),
  error = ref(''),
  courses = ref<Course[]>([]),
  course = ref(''),
  knowledge = ref<string[]>([]),
  selected = ref<string[]>([]),
  title = ref(''),
  text = ref(''),
  source = ref('课程教师自编材料'),
  busy = ref(false),
  formError = ref(''),
  success = ref('');
let resourceId = 'res-' + crypto.randomUUID(),
  documentId = 'doc-' + crypto.randomUUID(),
  revision = 0;
const kpError = ref('');
const labels: Record<string, string> = { 'kp-stack': '栈', 'kp-queue': '队列' };
const points = computed(() =>
  knowledge.value.map((id) => ({ id, name: labels[id] || id })),
);
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [stats, list] = await Promise.all([
      api.teacherOverview(),
      api.courses(),
    ]);
    overview.value = stats;
    courses.value = list;
    if (!course.value) course.value = list[0]?.id || '';
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
watch(course, async (id) => {
  const rev = ++revision;
  knowledge.value = [];
  selected.value = [];
  kpError.value = '';
  try {
    const result = await api.questions(id);
    if (rev === revision)
      knowledge.value = [
        ...new Set(result.questions.flatMap((q) => q.knowledge_point_ids)),
      ];
  } catch (e) {
    if (rev === revision) kpError.value = errorText(e);
  }
});
async function submit() {
  if (busy.value) return;
  formError.value = '';
  success.value = '';
  if (
    !title.value.trim() ||
    !text.value.trim() ||
    !source.value.trim() ||
    !selected.value.length
  ) {
    formError.value = '请填写标题、正文、来源，并至少选择一个知识点。';
    return;
  }
  busy.value = true;
  try {
    const result = await api.ingest({
      resource_id: resourceId,
      document_id: documentId,
      course_id: course.value,
      title: title.value.trim(),
      text: text.value.trim(),
      knowledge_point_ids: [...selected.value],
      source: source.value.trim(),
    });
    success.value =
      '文本已导入，生成 ' +
      result.chunks +
      ' 个资料片段。课程资源计数可能暂未更新。';
    title.value = '';
    text.value = '';
    selected.value = [];
    resourceId = 'res-' + crypto.randomUUID();
    documentId = 'doc-' + crypto.randomUUID();
  } catch (e) {
    formError.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <p class="eyebrow">教师工作台</p>
    <h1>教学概况与资料导入</h1>
  </div>
  <StateNotice :loading="loading" :error="error" @retry="load" /><template
    v-if="overview && !error && !loading"
    ><div class="stat-grid">
      <div class="card">
        <span>用户</span><strong>{{ overview.user_count }}</strong>
      </div>
      <div class="card">
        <span>题目</span><strong>{{ overview.question_count }}</strong>
      </div>
      <div class="card">
        <span>测验记录</span><strong>{{ overview.attempt_count }}</strong>
      </div>
      <div class="card">
        <span>学习资源</span><strong>{{ overview.resource_count }}</strong>
      </div>
    </div>
    <section class="card">
      <h2>导入课程文本</h2>
      <p class="muted">
        填写可供学生引用的课程材料。请确认内容准确并标注来源。
      </p>
      <form @submit.prevent="submit">
        <fieldset :disabled="busy">
          <label
            >课程<select v-model="course" required>
              <option v-for="item in courses" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select></label
          ><label
            >资料标题<input v-model="title" required maxlength="200" /></label
          ><label
            >资料正文<textarea
              v-model="text"
              required
              maxlength="200000"
              rows="8"
            /></label
          ><label>来源<input v-model="source" required /></label>
          <fieldset>
            <legend>关联知识点</legend>
            <p v-if="kpError" class="error">{{ kpError }}</p>
            <p v-else-if="!points.length" class="muted">暂无可关联的知识点。</p>
            <label v-for="point in points" :key="point.id" class="option"
              ><input
                v-model="selected"
                type="checkbox"
                :value="point.id"
              /><span>{{ point.name }}</span></label
            >
          </fieldset>
        </fieldset>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <p v-if="success" class="hint" role="status">{{ success }}</p>
        <button :disabled="busy || !points.length">
          {{ busy ? '正在导入……' : '导入文本' }}
        </button>
      </form>
    </section>
    <section class="card">
      <h2>更多课程维护功能</h2>
      <p class="muted">题库编辑、课程设置、文件上传和学生明细暂未开放。</p>
    </section></template
  >
</template>
