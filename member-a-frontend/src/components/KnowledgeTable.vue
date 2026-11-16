<script setup lang="ts">
import type { KnowledgePointResult, KnowledgeStatus } from '../types/api'
defineProps<{ items: KnowledgePointResult[] }>()
const labels: Record<KnowledgeStatus, string> = { insufficient_evidence: '证据不足', weak: '需要重点复习', needs_practice: '需要巩固', mastered: '当前表现良好' }
const percent = (value: number | null) => value === null ? '证据不足' : `${(value * 100).toFixed(0)}%`
</script>
<template><div class="table-scroll"><table><thead><tr><th>知识点</th><th>本次答对 / 题数</th><th>正确率</th><th>诊断状态</th></tr></thead><tbody><tr v-for="item in items" :key="item.knowledge_point_id"><td>{{ item.name }}</td><td>{{ item.correct_count }} / {{ item.sample_count }}</td><td>{{ percent(item.accuracy) }}</td><td>{{ labels[item.status] ?? item.status }}</td></tr></tbody></table></div></template>
