<script setup lang="ts">
import type { Report } from '../../api/contracts';
import { config } from '../../config';
import { dateText } from '../../utils';
defineProps<{ report: Report }>();
</script>
<template>
  <section class="report-meta panel">
    <span v-if="report.source_mode === 'mock'" class="status"
      >示例数据报告</span
    >
    <span class="status">{{
      report.explanation_mode === 'rule_template'
        ? '基础分析建议'
        : report.explanation_mode === 'cached'
          ? '历史分析结果'
          : '智能学习建议'
    }}</span>
    <p>{{ report.summary }}</p>
    <p v-if="report.is_degraded" class="notice" role="status">
      智能分析暂不可用，当前展示基础学习建议。已保存的测验成绩不受影响。
    </p>
    <p
      v-if="
        report.retrieval_status === 'empty' ||
        report.retrieval_status === 'failed'
      "
      class="notice"
    >
      资料依据不足：暂未取得匹配的课程内容。本次测验统计仍然保留。
    </p>
    <p class="muted">报告生成于 {{ dateText(report.generated_at) }}</p>
    <p
      v-if="report.explanation_mode === 'cached' && report.cached_from"
      class="muted"
    >
      原分析生成于 {{ dateText(report.cached_from.generated_at) }}
    </p>
    <details v-if="config.debug">
      <summary>联调信息</summary>
      <p class="mono">
        测验 {{ report.attempt_id }} · 规则 {{ report.rule_version }} / 报告
        {{ report.report_version }} / 数据 {{ report.data_version }}
      </p>
      <p>{{ report.degraded_reasons.join('；') }}</p>
    </details>
  </section>
</template>
