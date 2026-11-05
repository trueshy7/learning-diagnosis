<script setup lang="ts">
import { validationMessage } from '../../utils/presentation';
import { userError } from '../../utils/presentation';
import { ref, watch } from 'vue';
import { api } from '../../api/services';
import { courseWriteSchema } from '../../api/contracts';
import { useCourse } from '../../composables/useCourse';
import PageState from '../../components/common/PageState.vue';
const { data, error, loading, reload } = useCourse();
const title = ref(''),
  description = ref(''),
  busy = ref(false),
  message = ref(''),
  saveError = ref('');
watch(data, (c) => {
  if (c) {
    title.value = c.title;
    description.value = c.description;
  }
});
async function save() {
  if (!data.value || busy.value) return;
  message.value = '';
  saveError.value = '';
  const parsed = courseWriteSchema.safeParse({
    title: title.value,
    description: description.value,
  });
  if (!parsed.success) {
    saveError.value = validationMessage(parsed.error);
    return;
  }
  busy.value = true;
  try {
    data.value = await api.saveCourse(data.value.course_id, parsed.data);
    message.value = '课程信息已保存';
  } catch (e) {
    saveError.value = userError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">COURSE SETTINGS</span>
    <h1>课程设置</h1>
    <p>维护当前课程的标题和简介。</p>
  </div>
  <PageState :loading="loading" :error="error" @retry="reload" />
  <form v-if="data" class="panel form-panel" @submit.prevent="save">
    <label for="course-title">课程标题</label
    ><el-input
      id="course-title"
      v-model="title"
      maxlength="100"
      show-word-limit
    /><label for="course-description">课程简介</label
    ><el-input
      id="course-description"
      v-model="description"
      type="textarea"
      :rows="5"
      maxlength="3000"
      show-word-limit
    />
    <p v-if="saveError" class="inline-error" role="alert">{{ saveError }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <el-button type="primary" native-type="submit" :loading="busy"
      >保存课程</el-button
    >
  </form>
</template>
