<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { init, use, type EChartsType } from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);
const props = defineProps<{
  items: { name: string; value: number }[];
  comparison?: boolean;
}>();
const element = ref<HTMLElement>();
let chart: EChartsType | undefined, observer: ResizeObserver | undefined;
const chartError = ref(false);
async function draw() {
  await nextTick();
  if (!element.value) return;
  try {
    chart ||= init(element.value);
    chart.setOption(
      {
        animation: false,
        grid: { left: 180, right: 45, top: 12, bottom: 30 },
        tooltip: {
          trigger: 'axis',
          valueFormatter: (v: number) =>
            `${v.toFixed(2)}${props.comparison ? ' 个百分点' : '%'}`,
        },
        xAxis: {
          type: 'value',
          min: props.comparison ? -100 : 0,
          max: 100,
          axisLabel: { formatter: `{value}${props.comparison ? '' : '%'}` },
          splitLine: { lineStyle: { color: '#e9ece8' } },
        },
        yAxis: {
          type: 'category',
          inverse: true,
          data: props.items.map((x) => x.name),
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { width: 165, overflow: 'truncate' },
        },
        series: [
          {
            type: 'bar',
            barMaxWidth: 18,
            itemStyle: { color: '#287a65', borderRadius: [0, 4, 4, 0] },
            data: props.items.map((x) => x.value),
          },
        ],
      },
      true,
    );
  } catch {
    chartError.value = true;
  }
}
onMounted(() => {
  void draw();
  observer = new ResizeObserver(() => chart?.resize());
  if (element.value) observer.observe(element.value);
});
watch(() => props.items, draw);
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <p v-if="chartError">图表暂不可用，请查看下方数值表格。</p>
  <div
    v-show="!chartError"
    ref="element"
    role="img"
    :aria-label="
      comparison
        ? '可比知识点正确率变化，详见数值表'
        : '知识点掌握度，详见数值表'
    "
    :style="{ height: `${Math.max(160, items.length * 38 + 45)}px` }"
  ></div>
</template>
