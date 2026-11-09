<script setup lang="ts">
import type { Evidence } from '../types/api';
defineProps<{ items: Evidence[] }>();
function locationLabel(value: Evidence['location']) {
  if (typeof value === 'string') return value || '未提供';
  return (
    Object.values(value)
      .filter((v) => typeof v === 'string' || typeof v === 'number')
      .join(' · ') || '未提供'
  );
}
</script>
<template>
  <p v-if="!items.length" class="muted">
    本次没有可引用的资料，请结合课程材料复习。
  </p>
  <article v-for="item in items" :key="item.evidence_id" class="evidence">
    <h3>{{ item.title || '课程资料' }}</h3>
    <blockquote>{{ item.text }}</blockquote>
    <p class="muted">
      来源：{{ item.source || '未提供' }} · 位置：{{
        locationLabel(item.location)
      }}
    </p>
  </article>
</template>
