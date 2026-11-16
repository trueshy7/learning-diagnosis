<script setup lang="ts">
defineProps<{ loading?: boolean; error?: string; empty?: boolean; emptyText?: string }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <p v-if="loading" class="notice" role="status">正在加载，请稍候……</p>
  <div v-else-if="error" class="notice error" role="alert"><p>{{ error }}</p><button class="secondary" @click="$emit('retry')">重新加载</button></div>
  <p v-else-if="empty" class="notice">{{ emptyText || '暂无数据。' }}</p>
</template>
