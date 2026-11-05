<script setup lang="ts">
import { userError } from '../../utils/presentation';
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import type { Report } from '../../api/contracts';
import { api } from '../../api/services';
const props = defineProps<{ report: Report; readOnly?: boolean }>();
const router = useRouter(),
  busy = ref(false),
  error = ref('');
let creationKey = crypto.randomUUID();
let creationSignature = '';
async function create(kind: 'retest' | 'practice', ids?: string[]) {
  if (busy.value) return;
  const signature = JSON.stringify([
    props.report.report_id,
    kind,
    [...(ids || [])].sort(),
  ]);
  if (creationSignature !== signature) {
    creationKey = crypto.randomUUID();
    creationSignature = signature;
  }
  busy.value = true;
  error.value = '';
  try {
    const a = await api.createAttempt({
      course_id: props.report.course_id,
      kind,
      source_report_id: props.report.report_id,
      client_request_id: creationKey,
      ...(kind === 'retest'
        ? { baseline_attempt_id: props.report.attempt_id }
        : { question_ids: ids }),
    });
    creationKey = crypto.randomUUID();
    await router.push(`/attempts/${a.attempt_id}`);
  } catch (e) {
    error.value = userError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="panel">
    <div class="section-head">
      <div>
        <span class="eyebrow">NEXT STEPS</span>
        <h2>你的下一步学习</h2>
      </div>
      <el-button
        v-if="!readOnly"
        type="primary"
        :disabled="!report.actions.can_retest || busy"
        :loading="busy"
        @click="create('retest')"
        >以本次为基准复测</el-button
      >
    </div>
    <p class="muted">按建议顺序阅读资料并完成练习，再通过复测了解本次变化。</p>
    <p v-if="!report.recommendations.length" class="notice">
      当前没有匹配资源或练习。可返回课程，联系教师补充资料。
    </p>
    <article
      v-for="rec in report.recommendations"
      :key="rec.recommendation_id"
      class="recommendation"
    >
      <div class="rec-number">{{ String(rec.priority).padStart(2, '0') }}</div>
      <div class="rec-body">
        <h3>
          {{
            report.knowledge_points.find(
              (k) => k.knowledge_point_id === rec.knowledge_point_id,
            )?.name
          }}
        </h3>
        <p>{{ rec.reason }}</p>
        <p>{{ rec.next_step }}</p>
        <small class="muted">{{
          rec.estimated_minutes === null
            ? '未提供预计用时'
            : `建议用时 ${rec.estimated_minutes} 分钟`
        }}</small>
        <div class="resource-links">
          <router-link
            v-for="r in rec.resources"
            :key="r.resource_id"
            :to="{
              path: `/resources/${encodeURIComponent(r.resource_id)}`,
              query: { back: $route.fullPath },
            }"
            >↗ {{ r.title }}
            <small>{{
              r.availability === 'available' ? '阅读资料' : '当前不可用'
            }}</small></router-link
          >
          <p v-if="!rec.resources.length">当前没有匹配资料。</p>
        </div>
        <el-button
          v-if="!readOnly"
          :disabled="
            busy ||
            !report.actions.can_practice ||
            !rec.practice_questions.length
          "
          @click="
            create(
              'practice',
              rec.practice_questions.map((q) => q.question_id),
            )
          "
          >开始推荐练习（{{ rec.practice_questions.length }} 题）</el-button
        >
        <p v-if="!rec.practice_questions.length" class="muted">
          当前没有匹配练习。
        </p>
      </div>
    </article>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
  </section>
</template>
