<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorText } from '../services/api'
import type { Question, SubmitAttempt } from '../types/api'
import StateNotice from '../components/StateNotice.vue'
const route = useRoute(), router = useRouter()
const questions = ref<Question[]>([]), selected = ref<Record<string, string>>({}), loading = ref(true), submitting = ref(false), error = ref(''), submitError = ref('')
const baseline = computed(() => typeof route.query.baseline === 'string' ? route.query.baseline : undefined)
// 一次进入测验对应一个提交键；失败后重试沿用相同答案快照和键。
const idempotencyKey = ref(crypto.randomUUID())
const pendingSubmission = ref<SubmitAttempt | null>(null)
const completed = computed(() => questions.value.filter(q => !!selected.value[q.id]).length)
async function load() { loading.value = true; error.value = ''; submitError.value = ''; selected.value = {}; pendingSubmission.value = null; idempotencyKey.value = crypto.randomUUID(); try { questions.value = (await api.questions(String(route.params.courseId))).questions } catch (e) { error.value = errorText(e) } finally { loading.value = false } }
async function submit() {
  if (submitting.value || completed.value !== questions.value.length) return
  submitting.value = true; submitError.value = ''
  pendingSubmission.value ??= {
    course_id: String(route.params.courseId),
    answers: questions.value.map(q => ({ question_id: q.id, selected_option_ids: [selected.value[q.id]!] })),
    ...(baseline.value ? { baseline_attempt_id: baseline.value } : {}),
  }
  try {
    const result = await api.submitAttempt(pendingSubmission.value, idempotencyKey.value)
    await router.push(`/report/${result.id}`)
  } catch (e) { submitError.value = errorText(e) }
  finally { submitting.value = false }
}
watch(() => [route.params.courseId, route.query.baseline], load, { immediate: true })
</script>
<template><div class="page-heading"><p class="eyebrow">02 / 作答</p><h1>{{ baseline ? '复测' : '课程测验' }}</h1><p class="muted">已完成 {{ completed }} / {{ questions.length }} 题。当前骨架只展示单选题。</p><p v-if="baseline" class="hint">本次将与基线测验 {{ baseline }} 比较；比较数据由后端提供。</p></div><StateNotice :loading="loading" :error="error" :empty="!questions.length" empty-text="该课程暂时没有题目。" @retry="load" /><form v-if="!loading && !error && questions.length" @submit.prevent="submit"><fieldset v-for="(question, index) in questions" :key="question.id" class="card question" :disabled="submitting || pendingSubmission !== null"><legend>{{ index + 1 }}. {{ question.stem }}</legend><label v-for="option in question.options" :key="option.id" class="option"><input v-model="selected[question.id]" type="radio" :name="question.id" :value="option.id" required /><span>{{ option.id }}. {{ option.text }}</span></label></fieldset><p v-if="submitError" class="error" role="alert">{{ submitError }}</p><p v-if="submitError && pendingSubmission" class="hint">答案已锁定。点击重试会沿用原答案和提交编号，避免网络超时造成重复测验。请勿刷新页面；重新进入测验会视为新一轮。</p><button :disabled="submitting || completed !== questions.length">{{ submitting ? '正在提交并生成报告……' : pendingSubmission ? '重试提交' : '提交测验' }}</button></form></template>
