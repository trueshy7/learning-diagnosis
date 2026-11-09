<script setup lang="ts">
import type { Report } from '../../api/contracts';
import ScoreCard from './ScoreCard.vue';
import KnowledgeTable from './KnowledgeTable.vue';
import EvidenceList from './EvidenceList.vue';
import ComparisonPanel from './ComparisonPanel.vue';
import RecommendationList from './RecommendationList.vue';
import AnalysisNotice from './AnalysisNotice.vue';
import { config } from '../../config';
defineProps<{
  report: Report;
  readOnly?: boolean;
  recommendationsOnly?: boolean;
}>();
</script>
<template>
  <AnalysisNotice :report="report" />
  <ScoreCard v-if="!recommendationsOnly" :score="report.score" /><KnowledgeTable
    v-if="!recommendationsOnly"
    :points="report.knowledge_points"
  /><RecommendationList :report="report" :read-only="readOnly" /><EvidenceList
    :evidences="report.evidences"
    :back="$route.fullPath"
  /><ComparisonPanel
    v-if="!recommendationsOnly"
    :comparison="report.comparison"
  />
  <section
    v-if="config.debug && !recommendationsOnly && report.agent_steps.length"
    class="panel"
  >
    <h2>服务执行摘要</h2>
    <p v-if="!report.agent_steps.length" class="muted">
      服务未提供智能体执行摘要。本地模拟不代表真实智能体执行。
    </p>
    <p v-for="s in report.agent_steps" :key="s.step">
      {{ s.step }} · {{ s.status }} · {{ s.summary }}
      {{ s.duration_ms === null ? '' : `${s.duration_ms} ms` }}
    </p>
  </section>
</template>
