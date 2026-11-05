<script setup lang="ts">
import { ApiError } from '../../api/client';
import { userError } from '../../utils/presentation';
import { config } from '../../config';
withDefaults(
  defineProps<{
    loading?: boolean;
    error?: Error | null;
    empty?: boolean;
    emptyTitle?: string;
    emptyText?: string;
  }>(),
  {
    emptyTitle: '暂无记录',
    emptyText: '完成一次测验后，可以在这里查阅学习结果。',
  },
);
defineEmits<{ retry: [] }>();
</script>
<template>
  <div v-if="loading" class="state" role="status">
    <span class="spinner"></span>正在加载数据…
  </div>
  <div v-else-if="error" class="state error-state" role="alert">
    <strong>{{
      error instanceof ApiError && error.httpStatus === 403
        ? '无权访问'
        : error instanceof ApiError && error.httpStatus === 410
          ? '来源已移除'
          : '暂时无法加载'
    }}</strong>
    <p>{{ userError(error) }}</p>
    <small v-if="config.debug && error instanceof ApiError"
      >{{ error.code }} · {{ error.requestId || '无请求标识' }}</small
    >
    <el-button @click="$emit('retry')">重新加载</el-button>
  </div>
  <div v-else-if="empty" class="state">
    <strong>{{ emptyTitle }}</strong>
    <p>{{ emptyText }}</p>
    <router-link to="/">返回首页</router-link>
  </div>
</template>
