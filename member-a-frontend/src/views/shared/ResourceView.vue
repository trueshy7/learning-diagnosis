<script setup lang="ts">
import { userError } from '../../utils/presentation';
import { ref, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { api } from '../../api/services';
import { useLoad } from '../../composables/useLoad';
import { safeUrl, safeRedirect, cleanFilename } from '../../utils';
import { config } from '../../config';
import { useAuth } from '../../stores/auth';
import PageState from '../../components/common/PageState.vue';
const route = useRoute(),
  auth = useAuth();
const { data, loading, error, reload } = useLoad(
  () => route.fullPath,
  () =>
    api.resource(String(route.params.resourceId), {
      ...(route.query.document_id
        ? { document_id: route.query.document_id }
        : {}),
      ...(route.query.chunk_id ? { chunk_id: route.query.chunk_id } : {}),
      ...(route.query.resource_version
        ? { resource_version: route.query.resource_version }
        : {}),
    }),
);
const fileUrl = ref(''),
  downloadName = ref(''),
  fileError = ref(''),
  busy = ref(false);
let alive = true;
async function download() {
  if (!data.value || busy.value) return;
  busy.value = true;
  fileError.value = '';
  try {
    const blob = await api.file(data.value.resource_id);
    if (!alive) return;
    if (fileUrl.value) URL.revokeObjectURL(fileUrl.value);
    const extension = blob.type.includes('pdf')
      ? '.pdf'
      : blob.type.includes('markdown')
        ? '.md'
        : blob.type.includes('text/plain')
          ? '.txt'
          : '.bin';
    const name = data.value.filename || data.value.title;
    downloadName.value = cleanFilename(
      /\.(pdf|txt|md)$/i.test(name) ? name : `${name}${extension}`,
    );
    fileUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    fileError.value = userError(e);
  } finally {
    busy.value = false;
  }
}
onBeforeUnmount(() => {
  alive = false;
  if (fileUrl.value) URL.revokeObjectURL(fileUrl.value);
});
</script>
<template>
  <div class="actions">
    <router-link
      :to="safeRedirect(route.query.back, auth.user?.role || 'student')"
      >← 返回来源页面</router-link
    >
  </div>
  <PageState :loading="loading" :error="error" @retry="reload" />
  <article v-if="data" class="panel reader">
    <span class="eyebrow">COURSE MATERIAL</span>
    <h1>{{ data.title }}</h1>
    <p class="muted">
      {{ data.source_label }}
      <span v-if="config.debug">· {{ data.resource_version }}</span>
    </p>
    <p>{{ data.description }}</p>
    <p v-if="data.location?.section" class="notice">
      定位章节：{{ data.location.section }}
    </p>
    <pre v-if="data.text_content" class="resource-content">{{
      data.text_content
    }}</pre>
    <template v-else-if="data.external_url"
      ><a
        v-if="safeUrl(data.external_url)"
        :href="safeUrl(data.external_url)!"
        target="_blank"
        rel="noopener noreferrer"
        >打开外部学习资源 ↗</a
      >
      <p v-else class="inline-error">
        资源链接协议不受支持，已阻止打开。
      </p></template
    >
    <p v-else class="notice">
      无可直接显示的正文，可通过授权文件接口查看原文件。
    </p>
    <el-button v-if="data.file_available" :loading="busy" @click="download"
      >获取原文件</el-button
    ><a v-if="fileUrl" :href="fileUrl" :download="downloadName">下载原文件</a>
    <p v-if="fileError" role="alert" class="inline-error">{{ fileError }}</p>
  </article>
</template>
