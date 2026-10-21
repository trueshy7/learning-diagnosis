<script setup lang="ts">
import type { Evidence } from '../types/api'
defineProps<{ items: Evidence[] }>()
</script>
<template>
  <p v-if="!items.length" class="muted">服务未返回可引用的材料。</p>
  <article v-for="item in items" :key="item.evidence_id" class="evidence">
    <h3>{{ item.title || '未提供标题' }}</h3><blockquote>{{ item.text }}</blockquote>
    <p class="muted">来源：{{ item.source || '未提供' }} · 位置：{{ item.location || '未提供' }}</p>
    <details><summary>查看引用标识</summary><dl class="identifier-list"><dt>证据</dt><dd>{{ item.evidence_id }}</dd><dt>文档 / 分块</dt><dd>{{ item.document_id }} / {{ item.chunk_id }}</dd><dt>资源</dt><dd>{{ item.resource_id }}</dd><dt>关联知识点</dt><dd>{{ item.knowledge_point_ids.join('、') || '未提供' }}</dd><dt>检索得分</dt><dd>{{ item.score }}</dd></dl></details>
  </article>
</template>
