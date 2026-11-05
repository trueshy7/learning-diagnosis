<script setup lang="ts">
import { config } from '../../config';
import type { Evidence } from '../../api/contracts';
defineProps<{ evidences: Evidence[]; back: string }>();
</script>
<template>
  <section class="panel">
    <h2>引用与来源</h2>
    <p v-if="!evidences.length" class="notice">
      暂无检索证据。测验统计仍有效，解释所需的资料依据不足。
    </p>
    <details v-for="e in evidences" :key="e.evidence_id" class="evidence">
      <summary>
        {{ e.document_title }} ·
        {{
          e.location.section ||
          (e.location.page_start === null
            ? '原文片段（未提供页码）'
            : `第 ${e.location.page_start} 页`)
        }}
        <span class="muted">展开引用</span>
      </summary>
      <p class="muted">
        生成报告时的引用片段 · {{ e.source_label }} ·
        {{
          e.availability === 'removed'
            ? '来源当前已移除'
            : e.availability === 'available'
              ? '来源可访问'
              : '来源状态待确认'
        }}
      </p>
      <blockquote>{{ e.text }}</blockquote>
      <p v-if="config.debug" class="mono">
        {{ e.resource_id }} / {{ e.document_id }} / {{ e.chunk_id }}
      </p>
      <router-link
        :to="{
          path: `/resources/${encodeURIComponent(e.resource_id)}`,
          query: {
            document_id: e.document_id,
            chunk_id: e.chunk_id,
            resource_version: e.resource_version,
            back,
          },
        }"
        >查看原资料与章节 →</router-link
      >
    </details>
  </section>
</template>
