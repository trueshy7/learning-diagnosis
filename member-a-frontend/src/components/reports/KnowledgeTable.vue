<script setup lang="ts">
import type { PointResult } from '../../api/contracts';
import { percent, masteryChartData } from '../../utils';
import { statusLabels } from '../../config';
import BarChart from './BarChart.vue';
defineProps<{ points: PointResult[] }>();
</script>
<template>
  <section class="panel">
    <div class="section-head">
      <div>
        <span class="eyebrow">KNOWLEDGE CHECK</span>
        <h2>知识点诊断</h2>
      </div>
      <span class="muted">仅表示本次测验表现</span>
    </div>
    <BarChart
      v-if="masteryChartData(points).length"
      :items="masteryChartData(points)"
    />
    <p v-else class="notice">本次测验覆盖不足，暂无可绘制的掌握度。</p>
    <div class="table-scroll">
      <table data-testid="knowledge-table">
        <thead>
          <tr>
            <th>知识点</th>
            <th>正确 / 有效题</th>
            <th>本次正确率</th>
            <th>掌握状态</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in points" :key="point.knowledge_point_id">
            <td>{{ point.name }}</td>
            <td>{{ point.correct_count }} / {{ point.question_count }}</td>
            <td>{{ percent(point.correct_rate) }}</td>
            <td>
              <span class="status" :class="point.mastery_status">{{
                statusLabels[point.mastery_status]
              }}</span>
            </td>
            <td>
              {{
                point.coverage_reason === 'not_tested'
                  ? '本次未覆盖'
                  : point.coverage_reason === 'too_few_questions'
                    ? '有效不同题少于 3 道，暂不判断掌握'
                    : point.explanation
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
