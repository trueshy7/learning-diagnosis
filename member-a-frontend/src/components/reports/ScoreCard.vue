<script setup lang="ts">
import type { Score } from '../../api/contracts';
import { numberText } from '../../utils';
defineProps<{ score: Score }>();
</script>
<template>
  <section class="score-card" aria-label="测验成绩">
    <div>
      <span class="eyebrow">本次测验成绩</span>
      <div class="big-score" data-testid="percentage">
        {{ numberText(score.percentage) }}<small> / 100 分</small>
      </div>
    </div>
    <div class="score-meta">
      <strong>{{ score.raw_score }} / {{ score.max_score }} 分</strong
      ><span
        >答对 {{ score.correct_count }} / {{ score.total_count }} 道有效题</span
      >
    </div>
    <p>成绩已保存。知识点题量可能重叠，不能相加作为总成绩。</p>
  </section>
</template>
