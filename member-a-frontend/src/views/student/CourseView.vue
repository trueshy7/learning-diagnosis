<script setup lang="ts">
import { userError } from '../../utils/presentation';
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../../api/services';
import { useLoad } from '../../composables/useLoad';
import PageState from '../../components/common/PageState.vue';
import { statusLabels } from '../../config';
const route = useRoute(),
  router = useRouter();
const { data, loading, error, reload } = useLoad(
  () => String(route.params.courseId),
  () => api.course(String(route.params.courseId)),
);
const latest = useLoad(
  () => data.value?.latest_report_id || '',
  async () =>
    data.value?.latest_report_id
      ? api.report(data.value.latest_report_id)
      : null,
);
const busy = ref(false),
  createError = ref('');
let creationKey = crypto.randomUUID();
async function start() {
  if (busy.value || !data.value) return;
  busy.value = true;
  createError.value = '';
  try {
    const a = await api.createAttempt({
      course_id: data.value.course_id,
      kind: 'initial',
      client_request_id: creationKey,
    });
    creationKey = crypto.randomUUID();
    await router.push(`/attempts/${a.attempt_id}`);
  } catch (e) {
    createError.value = userError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <PageState :loading="loading" :error="error" @retry="reload" /><template
    v-if="data"
    ><section class="course-hero">
      <div>
        <span class="eyebrow">COURSE / 学习工作台</span>
        <h1>{{ data.title }}</h1>
        <p>{{ data.description }}</p>
        <div class="actions">
          <el-button type="primary" size="large" :loading="busy" @click="start"
            >开始新测验</el-button
          ><router-link
            v-if="data.active_attempt_id"
            :to="`/attempts/${data.active_attempt_id}`"
            >继续未完成测验 →</router-link
          ><router-link to="/reports">历史报告</router-link>
        </div>
        <p v-if="createError" class="inline-error" role="alert">
          {{ createError }}
        </p>
      </div>
      <div class="hero-number">
        {{ String(data.knowledge_points.length).padStart(2, '0')
        }}<span>个知识点，逐步掌握</span>
      </div>
    </section>
    <div class="section-head">
      <h2>本课程知识点</h2>
      <span class="muted">先测验，再了解本次掌握情况</span>
    </div>
    <div class="knowledge-grid">
      <article
        v-for="(p, i) in data.knowledge_points"
        :key="p.knowledge_point_id"
        class="panel knowledge-card"
      >
        <span class="card-index">{{ String(i + 1).padStart(2, '0') }}</span>
        <h3>{{ p.name }}</h3>
        <p>{{ p.description }}</p>
        <span class="muted">{{
          !data.latest_report_id
            ? '未测评'
            : latest.loading.value
              ? '加载最近诊断…'
              : latest.error.value
                ? '最近诊断加载失败'
                : statusLabels[
                    latest.data.value?.knowledge_points.find(
                      (k) => k.knowledge_point_id === p.knowledge_point_id,
                    )?.mastery_status || ''
                  ] || '最近测验未覆盖'
        }}</span>
      </article>
    </div>
    <section class="panel latest">
      <div>
        <h2>回看最近一次学习</h2>
        <p>
          {{
            data.latest_attempt_id
              ? '成绩和报告可按测验记录恢复。'
              : '尚未参加测验，完成后将在这里保存结果。'
          }}
        </p>
      </div>
      <router-link
        v-if="data.latest_report_id"
        :to="`/reports/${data.latest_report_id}`"
        >查看最新报告 →</router-link
      ><router-link
        v-else-if="data.latest_attempt_id"
        :to="`/attempts/${data.latest_attempt_id}/diagnosis`"
        >查看成绩与处理状态 →</router-link
      >
    </section></template
  >
</template>
