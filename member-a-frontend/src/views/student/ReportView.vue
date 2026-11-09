<script setup lang="ts">
import { useRoute } from 'vue-router';
import { api } from '../../api/services';
import { useLoad } from '../../composables/useLoad';
import PageState from '../../components/common/PageState.vue';
import ReportContent from '../../components/reports/ReportContent.vue';
import { useAuth } from '../../stores/auth';
import { ApiError } from '../../api/client';
import { verifyReport } from '../../api/mappers';
const auth = useAuth();
const route = useRoute();
const { data, loading, error, reload } = useLoad(
  () => route.fullPath,
  async () => {
    const report = await api.report(
      String(route.params.reportId),
      route.params.userId ? String(route.params.userId) : undefined,
    );
    if (route.params.userId) return report;
    if (report.user_id !== auth.user?.user_id)
      throw new ApiError('INVALID_RESPONSE', '报告归属与当前用户不一致');
    return verifyReport(report, await api.attempt(report.attempt_id));
  },
);
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">LEARNING INSIGHTS</span>
    <h1>{{ route.meta.recommendations ? '学习推荐' : '学习报告' }}</h1>
    <p>结合有效题量阅读诊断，沿着真实来源继续学习。</p>
  </div>
  <PageState :loading="loading" :error="error" @retry="reload" /><ReportContent
    v-if="data"
    :report="data"
    :read-only="!!route.params.userId"
    :recommendations-only="!!route.meta.recommendations"
  />
  <div class="actions">
    <router-link :to="route.params.userId ? '/teacher/overview' : '/reports'"
      >← 返回{{ route.params.userId ? '教学概况' : '历史报告' }}</router-link
    ><router-link
      v-if="data && !route.params.userId"
      :to="`/attempts/${data.attempt_id}/diagnosis`"
      >本次诊断</router-link
    ><router-link
      v-if="data && !route.params.userId"
      :to="
        route.meta.recommendations
          ? `/reports/${data.report_id}`
          : `/reports/${data.report_id}/recommendations`
      "
      >{{
        route.meta.recommendations ? '查看完整报告' : '查看学习推荐'
      }}
      →</router-link
    >
  </div>
</template>
