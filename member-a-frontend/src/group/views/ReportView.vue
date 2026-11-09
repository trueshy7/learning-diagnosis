<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, errorText } from '../services/api';
import type { Attempt } from '../types/api';
import StateNotice from '../components/StateNotice.vue';
import KnowledgeTable from '../components/KnowledgeTable.vue';
import EvidenceList from '../components/EvidenceList.vue';
const route = useRoute(),
  attempt = ref<Attempt | null>(null),
  loading = ref(true),
  error = ref(''),
  busy = ref(false),
  actionError = ref('');
let revision = 0;
const courseName = ref('课程测验');
const explanation = computed(
  () =>
    attempt.value?.report?.explanation.replace(
      /mode=rule_template_demo[，,]?\s*/g,
      '',
    ) || '',
);
const date = computed(() =>
  attempt.value
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(attempt.value.created_at * 1000))
    : '',
);
const percent = (v: number | null) =>
  v === null ? '证据不足' : (v * 100).toFixed(1) + '%';
const delta = (v: number | null) =>
  v === null
    ? '无法比较'
    : (v > 0 ? '+' : '') + (v * 100).toFixed(1) + ' 个百分点';
function kpName(id: string) {
  return (
    attempt.value?.report?.knowledge_points.find(
      (k) => k.knowledge_point_id === id,
    )?.name || '课程知识点'
  );
}
async function load() {
  const rev = ++revision;
  loading.value = true;
  error.value = '';
  actionError.value = '';
  attempt.value = null;
  try {
    const result = await api.attempt(String(route.params.attemptId));
    if (rev !== revision) return;
    attempt.value = result;
    const courses = await api.courses();
    if (rev === revision)
      courseName.value =
        courses.find((c) => c.id === result.course_id)?.name || '课程测验';
  } catch (e) {
    if (rev === revision) error.value = errorText(e);
  } finally {
    if (rev === revision) loading.value = false;
  }
}
async function regenerate() {
  if (busy.value || !attempt.value) return;
  busy.value = true;
  actionError.value = '';
  const id = attempt.value.id,
    rev = revision;
  try {
    const result = await api.regenerate(id);
    if (rev === revision) attempt.value = result;
  } catch (e) {
    if (rev === revision) actionError.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
watch(() => route.params.attemptId, load, { immediate: true });
onBeforeUnmount(() => revision++);
</script>
<template>
  <div class="page-heading">
    <p class="eyebrow">03 / 学习报告</p>
    <h1>查看本次表现</h1>
  </div>
  <StateNotice :loading="loading" :error="error" @retry="load" /><template
    v-if="attempt && !error && !loading"
    ><section class="card">
      <div class="report-top">
        <div>
          <h2>{{ courseName }}</h2>
          <p class="muted">{{ date }}</p>
          <span>本次得分</span>
          <p class="score">
            {{ attempt.score }} <small>/ {{ attempt.max_score }}</small>
          </p>
          <p>测验得分率 {{ attempt.percentage }}%</p>
        </div>
        <RouterLink
          class="button"
          :to="{
            path: '/quiz/' + attempt.course_id,
            query: { baseline: attempt.id },
          }"
          >基于本次结果复测</RouterLink
        >
      </div>
    </section>
    <section v-if="!attempt.report" class="card">
      <h2>
        {{
          attempt.ai_status === 'processing'
            ? '报告准备中'
            : attempt.ai_status === 'disabled'
              ? '诊断功能未启用'
              : '诊断服务暂不可用'
        }}
      </h2>
      <p>
        本次成绩已保存，诊断未完成不会影响计分。您可以稍后重新查看，或重新生成报告。
      </p>
      <div class="actions">
        <button class="secondary" @click="load">刷新报告</button
        ><button :disabled="busy" @click="regenerate">
          {{ busy ? '正在生成……' : '重新生成报告' }}
        </button>
      </div>
      <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
    </section>
    <template v-else
      ><section class="card">
        <p class="hint">规则与模板分析 · 未调用大语言模型</p>
        <p v-if="attempt.report.fallback_status" class="hint">
          本次部分分析能力受限；请结合知识点统计和已有资料学习。
        </p>
        <p class="explanation">{{ explanation }}</p>
      </section>
      <section class="card">
        <h2>知识点表现</h2>
        <KnowledgeTable :items="attempt.report.knowledge_points" />
      </section>
      <section class="card">
        <h2>复习建议</h2>
        <p v-if="!attempt.report.recommendations.length" class="muted">
          本次暂无复习建议，可继续学习以积累更多诊断证据。
        </p>
        <article
          v-for="(item, index) in attempt.report.recommendations"
          :key="item.resource_id + index"
          class="list-item"
        >
          <h3>{{ item.title }}</h3>
          <p>{{ item.reason }}</p>
          <p class="muted">关联知识点：{{ kpName(item.knowledge_point_id) }}</p>
        </article>
      </section>
      <section class="card">
        <h2>报告引用与证据</h2>
        <EvidenceList :items="attempt.report.evidence" />
      </section>
      <section v-if="attempt.baseline_attempt_id" class="card">
        <h2>与基线测验比较</h2>
        <p v-if="!attempt.report.comparison.length" class="muted">
          暂无可比较的知识点。双方都需要足够样本和有效报告。
        </p>
        <div v-else class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>知识点</th>
                <th>基线正确率</th>
                <th>本次正确率</th>
                <th>变化</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in attempt.report.comparison"
                :key="item.knowledge_point_id"
              >
                <td>{{ kpName(item.knowledge_point_id) }}</td>
                <td>{{ percent(item.before_accuracy) }}</td>
                <td>{{ percent(item.after_accuracy) }}</td>
                <td>{{ delta(item.delta) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">
          前后测差异用于回顾本次表现，不代表学习效果的因果结论。
        </p>
      </section></template
    ></template
  >
</template>
