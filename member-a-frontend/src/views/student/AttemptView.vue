<script setup lang="ts">
import { config } from '../../config';
import { userError } from '../../utils/presentation';
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router';
import { ElMessageBox } from 'element-plus';
import { api } from '../../api/services';
import type { SubmitAttempt } from '../../api/contracts';
import { useLoad } from '../../composables/useLoad';
import {
  draftKey,
  restoreDraft,
  restoreSubmitIntent,
  submitIntentKey,
} from '../../composables/draft';
import { serializeAnswers } from '../../utils';
import PageState from '../../components/common/PageState.vue';
import QuestionCard from '../../components/quiz/QuestionCard.vue';
import { useAuth } from '../../stores/auth';
const auth = useAuth();
const route = useRoute(),
  router = useRouter();
const {
  data: attempt,
  loading,
  error,
  reload,
} = useLoad(
  () => String(route.params.attemptId),
  () => api.attempt(String(route.params.attemptId)),
);
const choices = ref<Record<string, string[]>>({}),
  index = ref(0),
  busy = ref(false),
  pending = ref(false),
  message = ref(''),
  submittingError = ref(''),
  stale = ref(false);
let complete = false;
let intent: { key: string; data: SubmitAttempt } | null = null;
const intentKey = () => submitIntentKey(attempt.value!);
const answered = computed(
  () => Object.values(choices.value).filter((x) => x.length).length,
);
const question = computed(() => attempt.value?.questions[index.value]);
watch(attempt, (a) => {
  if (!a) return;
  if (a.status === 'submitted') {
    complete = true;
    sessionStorage.removeItem(draftKey(a));
    sessionStorage.removeItem(intentKey());
    void router.replace(`/attempts/${a.attempt_id}/diagnosis`);
    return;
  }
  const draft = restoreDraft(a);
  choices.value = draft.choices;
  stale.value = draft.stale;
  intent = restoreSubmitIntent(a);
  pending.value = !!intent;
});
watch(
  choices,
  (c) => {
    if (attempt.value?.status === 'in_progress' && !pending.value)
      sessionStorage.setItem(draftKey(attempt.value), JSON.stringify(c));
  },
  { deep: true },
);
async function confirmState() {
  if (!attempt.value || busy.value) return;
  busy.value = true;
  try {
    const a = await api.attempt(attempt.value.attempt_id);
    if (a.status === 'submitted') {
      complete = true;
      pending.value = false;
      sessionStorage.removeItem(intentKey());
      sessionStorage.removeItem(draftKey(a));
      await router.replace(`/attempts/${a.attempt_id}/diagnosis`);
    } else
      message.value = '服务确认当前仍未提交。可用原提交内容重试，或返回编辑。';
  } catch (e) {
    submittingError.value = `提交结果仍待确认：${userError(e)}`;
  } finally {
    busy.value = false;
  }
}
async function submit() {
  if (!attempt.value || busy.value) return;
  busy.value = true;
  if (!intent) {
    try {
      await ElMessageBox.confirm(
        `已答 ${answered.value} 题，未答 ${attempt.value.questions.length - answered.value} 题；提交后未答按规则计零分，且不能修改本次答案。`,
        '确认提交测验',
        { confirmButtonText: '确认提交', cancelButtonText: '继续作答' },
      );
    } catch {
      busy.value = false;
      return;
    }
    intent = {
      key: crypto.randomUUID(),
      data: {
        snapshot_version: attempt.value.snapshot_version,
        answers: serializeAnswers(attempt.value, choices.value),
      },
    };
    sessionStorage.setItem(intentKey(), JSON.stringify(intent));
  }
  pending.value = true;
  busy.value = true;
  submittingError.value = '';
  try {
    await api.submit(attempt.value.attempt_id, intent.data, intent.key);
    complete = true;
    sessionStorage.removeItem(draftKey(attempt.value));
    sessionStorage.removeItem(intentKey());
    await router.replace(`/attempts/${attempt.value.attempt_id}/diagnosis`);
  } catch (e) {
    submittingError.value = `提交结果待确认：${userError(e)}`;
    busy.value = false;
    await confirmState();
  } finally {
    busy.value = false;
  }
}
async function editAgain() {
  if (!attempt.value || busy.value) return;
  busy.value = true;
  try {
    const a = await api.attempt(attempt.value.attempt_id);
    if (a.status === 'submitted') {
      complete = true;
      await router.replace(`/attempts/${a.attempt_id}/diagnosis`);
    } else {
      intent = null;
      pending.value = false;
      message.value = '';
      submittingError.value = '';
      sessionStorage.removeItem(intentKey());
    }
  } catch (e) {
    submittingError.value = userError(e);
  } finally {
    busy.value = false;
  }
}
async function leaving() {
  if (!auth.user || complete || (!answered.value && !pending.value))
    return true;
  try {
    await ElMessageBox.confirm(
      '本次作答尚未完成。草稿仅保留在当前标签页，确认离开？',
      '离开测验',
      { confirmButtonText: '确认离开', cancelButtonText: '继续作答' },
    );
    return true;
  } catch {
    return false;
  }
}
onBeforeRouteLeave(leaving);
function beforeUnload(e: BeforeUnloadEvent) {
  if (!complete && (answered.value || pending.value)) {
    e.preventDefault();
    e.returnValue = '';
  }
}
window.addEventListener('beforeunload', beforeUnload);
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
</script>
<template>
  <PageState :loading="loading" :error="error" @retry="reload" /><template
    v-if="attempt && attempt.status === 'in_progress'"
    ><div class="page-heading">
      <span class="eyebrow">ASSESSMENT</span>
      <h1>
        {{
          attempt.kind === 'retest'
            ? '复测'
            : attempt.kind === 'practice'
              ? '推荐练习'
              : '课程测验'
        }}
      </h1>
      <p>客观题每题 1 分，多选完全匹配得分。按你的理解作答。</p>
      <p v-if="config.debug && attempt.baseline_attempt_id" class="mono">
        复测基准：{{ attempt.baseline_attempt_id }}
      </p>
      <p v-if="attempt.kind === 'retest' && attempt.source_report_id">
        <router-link :to="`/reports/${attempt.source_report_id}`"
          >查看本次复测的基准报告 →</router-link
        >
      </p>
    </div>
    <p v-if="stale" class="notice">草稿版本已变化，已清理不兼容选项。</p>
    <div class="quiz-layout">
      <section>
        <QuestionCard
          v-if="question"
          :question="question"
          :index="index"
          :model-value="choices[question.question_id] || []"
          :disabled="busy || pending"
          @update:model-value="choices[question!.question_id] = $event"
        />
        <div class="actions quiz-actions">
          <el-button :disabled="index === 0" @click="index--">上一题</el-button
          ><span>{{ index + 1 }} / {{ attempt.questions.length }}</span
          ><el-button
            :disabled="index === attempt.questions.length - 1"
            @click="index++"
            >下一题</el-button
          >
        </div>
      </section>
      <aside class="panel quiz-aside">
        <h2>答题进度</h2>
        <p>已答 {{ answered }} / {{ attempt.questions.length }} 题</p>
        <div class="question-nav">
          <button
            v-for="(q, i) in attempt.questions"
            :key="q.question_id"
            :data-testid="`question-nav-${i}`"
            :aria-label="`跳到第 ${i + 1} 题`"
            :class="{
              current: index === i,
              answered: choices[q.question_id]?.length,
            }"
            @click="index = i"
          >
            {{ i + 1 }}
          </button>
        </div>
        <p class="muted">选项自动保存为当前标签页草稿。</p>
        <el-button
          type="primary"
          :loading="busy"
          :disabled="busy"
          @click="submit"
          >{{ pending ? '用原内容重试提交' : '提交测验' }}</el-button
        ><template v-if="pending"
          ><p class="notice">提交结果待确认，答案已锁定。</p>
          <el-button :disabled="busy" @click="confirmState"
            >确认服务端状态</el-button
          ><el-button :disabled="busy" @click="editAgain"
            >确认后返回编辑</el-button
          ></template
        >
        <p v-if="message" role="status">{{ message }}</p>
        <p v-if="submittingError" class="inline-error" role="alert">
          {{ submittingError }}
        </p>
      </aside>
    </div></template
  >
</template>
