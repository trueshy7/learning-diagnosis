<script setup lang="ts">
import { config } from '../../config';
import type { Comparison } from '../../api/contracts';
import { deltaText, percent } from '../../utils';
import BarChart from './BarChart.vue';
defineProps<{ comparison: Comparison | null }>();
</script>
<template>
  <section class="panel">
    <h2>前后测比较</h2>
    <p v-if="!comparison" class="notice">
      当前报告没有复测对比。可从本报告创建复测，以本次测验为基准。
    </p>
    <template v-else
      ><p v-if="config.debug" class="mono">
        基准 {{ comparison.baseline_attempt_id }} → 本次
        {{ comparison.current_attempt_id }}
      </p>
      <p>
        {{
          comparison.overall_comparable
            ? `总分变化：${deltaText(comparison.overall_delta_percentage_points)}`
            : `整卷不可比较：${comparison.overall_reason}`
        }}
      </p>
      <BarChart
        v-if="comparison.knowledge_points.some((p) => p.comparable)"
        :items="
          comparison.knowledge_points
            .filter((p) => p.comparable)
            .map((p) => ({ name: p.name, value: p.delta_percentage_points! }))
        "
        comparison
      />
      <div class="table-scroll">
        <table data-testid="comparison-table">
          <thead>
            <tr>
              <th>知识点</th>
              <th>前测（题量）</th>
              <th>复测（题量）</th>
              <th>变化</th>
              <th>可比条件与限制</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in comparison.knowledge_points"
              :key="p.knowledge_point_id"
            >
              <td>{{ p.name }}</td>
              <td>
                {{ percent(p.baseline_correct_rate) }}（{{
                  p.baseline_question_count
                }}
                题）
              </td>
              <td>
                {{ percent(p.current_correct_rate) }}（{{
                  p.current_question_count
                }}
                题）
              </td>
              <td>
                {{
                  p.comparable
                    ? deltaText(p.delta_percentage_points)
                    : '不可比较'
                }}
              </td>
              <td>{{ p.reason || p.difficulty_note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted">
        正确率变化受题目及覆盖范围影响，不能据此断言教学因果效果。
      </p></template
    >
  </section>
</template>
