<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { api, errorText } from '../services/api';
import {
  draftKey,
  restoreDraft,
  writeDraft,
  submission,
} from '../services/draft';
import { getSession } from '../services/session';
import type { Question, SubmitAttempt } from '../types/api';
import StateNotice from '../components/StateNotice.vue';
const route = useRoute(),
  router = useRouter();
const questions = ref<Question[]>([]),
  selected = ref<Record<string, string>>({}),
  loading = ref(true),
  submitting = ref(false),
  error = ref(''),
  submitError = ref(''),
  notice = ref('');
const course = computed(() => String(route.params.courseId)),
  baseline = computed(() =>
    typeof route.query.baseline === 'string' ? route.query.baseline : undefined,
  );
const idempotencyKey = ref<string>(crypto.randomUUID()),
  pendingSubmission = ref<SubmitAttempt | null>(null);
const completed = computed(
  () => questions.value.filter((q) => !!selected.value[q.id]).length,
);
let revision = 0,
  finished = false;
const storageKey = computed(() => draftKey(course.value, baseline.value));
function persist() {
  if (loading.value || finished || !getSession()) return true;
  const ok = writeDraft(storageKey.value, {
    key: idempotencyKey.value,
    questions: questions.value.map((q) => JSON.stringify(q)),
    selected: selected.value,
    pending: pendingSubmission.value,
  });
  if (!ok)
    notice.value =
      '浏览器无法保存草稿，请勿关闭页面；提交失败后可在当前页面重试。';
  return ok;
}
watch(selected, persist, { deep: true });
async function load() {
  const rev = ++revision;
  loading.value = true;
  error.value = '';
  submitError.value = '';
  selected.value = {};
  questions.value = [];
  pendingSubmission.value = null;
  notice.value = '';
  finished = false;
  idempotencyKey.value = crypto.randomUUID();
  try {
    const [result, base] = await Promise.all([
      api.questions(course.value),
      baseline.value ? api.attempt(baseline.value) : Promise.resolve(null),
    ]);
    if (rev !== revision) return;
    if (base && base.course_id !== course.value)
      throw new Error('基准课程不匹配');
    questions.value = result.questions;
    const restored = restoreDraft(
      storageKey.value,
      course.value,
      baseline.value,
      questions.value,
    );
    if (restored) {
      idempotencyKey.value = restored.key;
      selected.value = restored.selected;
      pendingSubmission.value = restored.pending;
      notice.value = restored.pending
        ? '已恢复未确认提交，重试将沿用原答案和提交编号。'
        : '已恢复本次作答草稿。';
    }
  } catch (e) {
    if (rev === revision) error.value = errorText(e);
  } finally {
    if (rev === revision) loading.value = false;
  }
}
async function submit() {
  if (
    submitting.value ||
    completed.value !== questions.value.length ||
    !questions.value.length
  )
    return;
  submitting.value = true;
  submitError.value = '';
  pendingSubmission.value ??= submission(
    course.value,
    baseline.value,
    questions.value,
    selected.value,
  );
  persist();
  const rev = revision;
  const submittedDraftKey = storageKey.value;
  try {
    const result = await api.submitAttempt(
      pendingSubmission.value,
      idempotencyKey.value,
    );
    if (rev !== revision) return;
    finished = true;
    sessionStorage.removeItem(submittedDraftKey);
    await router.push('/report/' + result.id);
  } catch (e) {
    submitError.value = errorText(e);
  } finally {
    submitting.value = false;
  }
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (!finished && (completed.value || pendingSubmission.value)) {
    event.preventDefault();
    event.returnValue = '';
  }
}
window.addEventListener('beforeunload', beforeUnload);
onBeforeUnmount(() => {
  revision++;
  window.removeEventListener('beforeunload', beforeUnload);
});
onBeforeRouteLeave(
  (to) =>
    !getSession() ||
    finished ||
    (!completed.value && !pendingSubmission.value) ||
    to.path === route.path ||
    window.confirm('离开本次作答？草稿会在当前登录会话中保留。'),
);
watch(() => [route.params.courseId, route.query.baseline], load, {
  immediate: true,
});
</script>
<template>
  <div class="page-heading">
    <p class="eyebrow">02 / 作答</p>
    <h1>{{ baseline ? '复测' : '课程测验' }}</h1>
    <p class="muted">
      已完成 {{ completed }} /
      {{ questions.length }} 题。本次为单选题，请选择最合适的答案。
    </p>
    <p v-if="baseline" class="hint">
      本次将与选定的历史测验比较，比较结果以服务返回为准。
    </p>
    <p v-if="notice" class="hint" role="status">{{ notice }}</p>
  </div>
  <StateNotice
    :loading="loading"
    :error="error"
    :empty="!questions.length"
    empty-text="该课程暂时没有题目。"
    @retry="load"
  />
  <form v-if="!loading && !error && questions.length" @submit.prevent="submit">
    <fieldset
      v-for="(question, index) in questions"
      :key="question.id"
      class="card question"
      :disabled="submitting || pendingSubmission !== null"
    >
      <legend>{{ index + 1 }}. {{ question.stem }}</legend>
      <label v-for="option in question.options" :key="option.id" class="option"
        ><input
          v-model="selected[question.id]"
          type="radio"
          :name="question.id"
          :value="option.id"
          required
        /><span>{{ option.id }}. {{ option.text }}</span></label
      >
    </fieldset>
    <p v-if="submitError" class="error" role="alert">{{ submitError }}</p>
    <p v-if="pendingSubmission" class="hint">
      答案已锁定。重试和刷新恢复均使用原答案与同一提交编号；成绩可能已保存，也可从历史核对。
    </p>
    <button :disabled="submitting || completed !== questions.length">
      {{
        submitting ? '正在提交……' : pendingSubmission ? '重试提交' : '提交测验'
      }}
    </button>
  </form>
</template>
