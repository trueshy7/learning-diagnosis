<script setup lang="ts">
import {
  taskText,
  taskError as taskFailureText,
} from '../../utils/presentation';
import { ref, shallowRef, watch } from 'vue';
import { useRoute } from 'vue-router';
import type { Report, Task } from '../../api/contracts';
import { api } from '../../api/services';
import { generation } from '../../api/client';
import { useLoad } from '../../composables/useLoad';
import { useTaskPolling } from '../../composables/useTaskPolling';
import { statusLabels } from '../../config';
import PageState from '../../components/common/PageState.vue';
import ScoreCard from '../../components/reports/ScoreCard.vue';
import KnowledgeTable from '../../components/reports/KnowledgeTable.vue';
import EvidenceList from '../../components/reports/EvidenceList.vue';
import { sameScore } from '../../api/mappers';
const route = useRoute();
const {
  data: attempt,
  error,
  loading,
  reload,
} = useLoad(
  () => String(route.params.attemptId),
  () => api.attempt(String(route.params.attemptId)),
);
const report = shallowRef<Report | null>(null),
  reportError = shallowRef<Error | null>(null),
  retrying = ref(false);
let loadSeq = 0;
async function loadReport(id: string) {
  reportError.value = null;
  report.value = null;
  const n = ++loadSeq,
    epoch = generation;
  try {
    const r = await api.report(id);
    if (
      n === loadSeq &&
      epoch === generation &&
      r.attempt_id === attempt.value?.attempt_id &&
      r.user_id === attempt.value?.user_id &&
      attempt.value?.result &&
      sameScore(r.score, attempt.value.result.score)
    )
      report.value = r;
    else if (n === loadSeq && epoch === generation)
      reportError.value = new Error('报告与本次测验或成绩不一致');
  } catch (e) {
    if (n === loadSeq && epoch === generation) reportError.value = e as Error;
  }
}
async function completed(t: Task) {
  if (t.report_id) await loadReport(t.report_id);
}
const {
  task,
  error: taskError,
  reason,
  restart,
} = useTaskPolling(() => attempt.value?.diagnosis_task_id || null, completed);
watch(attempt, (a) => {
  report.value = null;
  reportError.value = null;
  if (a?.report_id) void loadReport(a.report_id);
});
async function retry() {
  if (!task.value || retrying.value) return;
  retrying.value = true;
  try {
    await api.retry(task.value.task_id, crypto.randomUUID());
    restart();
  } catch (e) {
    reportError.value = e as Error;
  } finally {
    retrying.value = false;
  }
}
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">ASSESSMENT RESULT</span>
    <h1>本次学习诊断</h1>
    <p>先确认成绩，再结合知识点与资料理解本次表现。</p>
  </div>
  <PageState :loading="loading" :error="error" @retry="reload" /><template
    v-if="attempt"
    ><ScoreCard v-if="attempt.result" :score="attempt.result.score" />
    <section v-else class="panel">
      <p>本次测验尚未提交。</p>
      <router-link :to="`/attempts/${attempt.attempt_id}`"
        >继续作答 →</router-link
      >
    </section>
    <section v-if="attempt.diagnosis_task_id" class="panel">
      <h2>诊断处理状态</h2>
      <p role="status">
        {{ task ? statusLabels[task.status] : '正在查询任务' }} ·
        {{ taskText(task) }}
      </p>
      <p v-if="task?.progress !== null && task?.progress !== undefined">
        服务进度：{{ Math.round(task.progress * 100) }}%
      </p>
      <p v-if="task?.status === 'failed'" class="inline-error" role="alert">
        {{ taskFailureText(task.error_code) }}
      </p>
      <p v-if="reason === 'limit'" class="notice">
        仍在处理，已达本轮等待上限，可稍后查询。
      </p>
      <PageState :error="taskError" @retry="restart" />
      <div class="actions">
        <el-button v-if="reason !== 'polling'" @click="restart"
          >手动刷新状态</el-button
        ><el-button v-if="task?.can_retry" :loading="retrying" @click="retry"
          >重试诊断</el-button
        ><router-link to="/reports">历史记录</router-link>
      </div>
    </section>
    <PageState
      :error="reportError"
      @retry="task?.report_id && loadReport(task.report_id)"
    /><template v-if="report"
      ><div class="notice">
        {{ report.source_mode === 'mock' ? '示例数据报告' : '本次学习分析' }}
        ·
        {{
          report.explanation_mode === 'rule_template'
            ? '规则模板解释'
            : report.explanation_mode === 'llm'
              ? '智能分析建议'
              : '历史分析结果'
        }}
        <p v-if="report.is_degraded">
          分析提示：{{ '智能分析暂不可用，当前展示基础学习建议' }}
        </p>
        <p v-if="report.retrieval_status === 'empty'">
          检索无证据：成绩和规则诊断仍然保留。
        </p>
      </div>
      <KnowledgeTable :points="report.knowledge_points" /><EvidenceList
        :evidences="report.evidences"
        :back="$route.fullPath"
      />
      <div class="actions">
        <router-link
          class="button-link"
          :to="`/reports/${report.report_id}/recommendations`"
          >查看学习推荐 →</router-link
        ><router-link :to="`/reports/${report.report_id}`"
          >本次完整报告</router-link
        >
      </div></template
    ><router-link :to="`/courses/${attempt.course_id}`"
      >← 返回课程</router-link
    ></template
  >
</template>
