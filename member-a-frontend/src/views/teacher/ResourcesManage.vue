<script setup lang="ts">
import { taskText, taskError } from '../../utils/presentation';
import { validationMessage } from '../../utils/presentation';
import { userError } from '../../utils/presentation';
import { reactive, ref, watch, onBeforeUnmount } from 'vue';
import { ElMessageBox } from 'element-plus';
import { confirmDisable } from '../../utils/confirm';
import { api } from '../../api/services';
import { ApiError } from '../../api/client';
import {
  resourceWriteSchema,
  type ResourceWrite,
  type Task,
} from '../../api/contracts';
import { useCourse } from '../../composables/useCourse';
import { useLoad } from '../../composables/useLoad';
import { useTaskPolling } from '../../composables/useTaskPolling';
import { validateFile } from '../../utils';
import { config, statusLabels } from '../../config';
import PageState from '../../components/common/PageState.vue';
const isDemo = import.meta.env.VITE_API_MODE === 'mock';
const course = useCourse(),
  page = ref(1),
  kind = ref(''),
  kp = ref(''),
  active = ref(''),
  opened = ref(false),
  editId = ref<string | null>(null),
  busy = ref(false),
  message = ref(''),
  error = ref('');
const originalActive = ref(false);
const form = reactive<ResourceWrite>({
  course_id: '',
  title: '',
  description: '',
  kind: 'note',
  knowledge_point_ids: [],
  difficulty: 'easy',
  active: true,
  text_content: '',
  external_url: null,
});
const list = useLoad(
  () =>
    `${course.data.value?.course_id}:${page.value}:${kind.value}:${kp.value}:${active.value}`,
  async () =>
    course.data.value
      ? api.resources({
          course_id: course.data.value.course_id,
          page: page.value,
          page_size: 10,
          ...(kind.value ? { kind: kind.value } : {}),
          ...(kp.value ? { knowledge_point_id: kp.value } : {}),
          ...(active.value ? { active: active.value } : {}),
        })
      : null,
);
const taskId = ref<string | null>(null),
  documentId = ref(''),
  uploadTitle = ref(''),
  uploadKps = ref<string[]>([]),
  selectedFile = ref<File | null>(null),
  uploading = ref(false),
  uploadError = ref(''),
  retrying = ref(false);
let controller: AbortController | null = null;
const fileInput = ref<HTMLInputElement | null>(null);
async function completed(_task: Task) {
  await list.reload();
}
const polling = useTaskPolling(() => taskId.value, completed);
watch(
  () => list.data.value,
  (value) => {
    if (!taskId.value) {
      const p = value?.items.find((r) => r.availability === 'processing');
      if (p?.ingestion_task_id) {
        taskId.value = p.ingestion_task_id;
        documentId.value = p.document_id || '';
      }
    }
  },
);
async function edit(id?: string) {
  if (busy.value) return;
  error.value = '';
  editId.value = id || null;
  if (id) {
    busy.value = true;
    try {
      const r = await api.teacherResource(id);
      originalActive.value = r.active;
      Object.assign(form, r);
      opened.value = true;
    } catch (e) {
      message.value = userError(e);
    } finally {
      busy.value = false;
    }
  } else {
    originalActive.value = false;
    Object.assign(form, {
      course_id: course.data.value?.course_id || '',
      title: '',
      description: '',
      kind: 'note',
      knowledge_point_ids: [],
      difficulty: 'easy',
      active: true,
      text_content: '',
      external_url: null,
    });
    opened.value = true;
  }
}
async function save() {
  if (busy.value) return;
  const parsed = resourceWriteSchema.safeParse(form);
  if (!parsed.success) {
    error.value = validationMessage(parsed.error);
    return;
  }
  busy.value = true;
  if (
    originalActive.value &&
    !parsed.data.active &&
    !(await confirmDisable(parsed.data.title))
  ) {
    busy.value = false;
    return;
  }
  try {
    await api.saveResource(editId.value, parsed.data);
    opened.value = false;
    message.value = '资源已保存';
    await list.reload();
  } catch (e) {
    error.value = userError(e);
  } finally {
    busy.value = false;
  }
}
async function disable(id: string, title: string) {
  if (busy.value) return;
  try {
    await ElMessageBox.confirm(
      `停用“${title}”后不再进入新推荐，历史引用片段仍保留。确认继续？`,
      '确认停用资源',
      { confirmButtonText: '确认停用', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    const r = await api.teacherResource(id);
    await api.saveResource(id, { ...r, active: false });
    message.value = '资源已停用';
    await list.reload();
  } catch (e) {
    message.value = userError(e);
  } finally {
    busy.value = false;
  }
}
function selectFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null;
  uploadError.value = selectedFile.value
    ? validateFile(selectedFile.value) || ''
    : '已取消选择文件';
}
async function upload() {
  if (uploading.value || !course.data.value) return;
  if (
    !selectedFile.value ||
    validateFile(selectedFile.value) ||
    !uploadTitle.value.trim() ||
    uploadTitle.value.trim().length > 100 ||
    !uploadKps.value.length
  ) {
    uploadError.value = selectedFile.value
      ? validateFile(selectedFile.value) || '请填写 1—100 字标题并关联知识点'
      : '请选择文件';
    return;
  }
  const body = new FormData();
  body.set('course_id', course.data.value.course_id);
  body.set('title', uploadTitle.value.trim());
  body.set('knowledge_point_ids', JSON.stringify(uploadKps.value));
  body.set('file', selectedFile.value);
  uploading.value = true;
  uploadError.value = '';
  controller = new AbortController();
  try {
    const response = await api.upload(body, controller.signal);
    taskId.value = response.task.task_id;
    documentId.value = response.document.document_id;
    message.value = '文件已受理，等待处理；尚未成为可用学习资料';
    await list.reload();
  } catch (e) {
    uploadError.value =
      e instanceof ApiError && e.code === 'REQUEST_CANCELLED'
        ? '上传已取消；若服务已受理，请刷新资源列表确认'
        : userError(e);
  } finally {
    uploading.value = false;
    controller = null;
  }
}
async function retryTask() {
  if (!taskId.value || retrying.value) return;
  retrying.value = true;
  try {
    await api.retry(taskId.value, crypto.randomUUID());
    polling.restart();
  } catch (e) {
    uploadError.value = userError(e);
  } finally {
    retrying.value = false;
  }
}
onBeforeUnmount(() => controller?.abort());
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">LEARNING MATERIALS</span>
    <h1>资料与资源</h1>
    <p>管理可阅读资料与知识点关联，上传后跟踪处理状态。</p>
  </div>
  <section class="panel">
    <div class="toolbar">
      <label
        >资源类型<select
          v-model="kind"
          aria-label="资源类型"
          @change="page = 1"
        >
          <option value="">全部</option>
          <option value="note">文本资料</option>
          <option value="document">上传文档</option>
          <option value="external">外部链接</option>
        </select></label
      ><label
        >知识点<select v-model="kp" aria-label="知识点" @change="page = 1">
          <option value="">全部</option>
          <option
            v-for="k in course.data.value?.knowledge_points"
            :key="k.knowledge_point_id"
            :value="k.knowledge_point_id"
          >
            {{ k.name }}
          </option>
        </select></label
      ><label
        >状态<select v-model="active" aria-label="状态" @change="page = 1">
          <option value="">全部</option>
          <option value="true">启用</option>
          <option value="false">停用</option>
        </select></label
      ><el-button
        type="primary"
        :disabled="!course.data.value || busy"
        @click="edit()"
        >新建学习资源</el-button
      >
    </div>
    <p v-if="message" role="status">{{ message }}</p>
    <PageState
      empty-title="暂无匹配记录"
      empty-text="请调整查询条件，或等待相关内容更新。"
      :loading="course.loading.value || list.loading.value"
      :error="course.error.value || list.error.value"
      :empty="list.data.value?.total === 0"
      @retry="
        course.reload();
        list.reload();
      "
    />
    <div v-if="list.data.value" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>资料名称</th>
            <th>类型 / 关联知识点</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in list.data.value.items" :key="r.resource_id">
            <td>
              {{ r.title }}
              <p v-if="r.error_message" class="inline-error">
                {{ taskError(r.error_code) }}
              </p>
            </td>
            <td>
              {{ statusLabels[r.kind] }} /
              {{
                r.knowledge_point_ids
                  .map(
                    (id) =>
                      course.data.value?.knowledge_points.find(
                        (k) => k.knowledge_point_id === id,
                      )?.name || '知识点待确认',
                  )
                  .join('、')
              }}
            </td>
            <td>
              {{ r.active ? '启用' : '停用' }} ·
              {{ statusLabels[r.availability] }}
            </td>
            <td>
              <el-button text :disabled="busy" @click="edit(r.resource_id)"
                >编辑</el-button
              ><el-button
                v-if="r.ingestion_task_id"
                text
                @click="
                  taskId = r.ingestion_task_id;
                  documentId = r.document_id || '';
                  polling.restart();
                "
                >查看处理</el-button
              ><router-link
                v-if="r.availability === 'available'"
                :to="{
                  path: `/resources/${r.resource_id}`,
                  query: { back: $route.fullPath },
                }"
                >阅读</router-link
              ><el-button
                v-if="r.active && r.availability === 'available'"
                text
                type="danger"
                :disabled="busy"
                @click="disable(r.resource_id, r.title)"
                >停用</el-button
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-pagination
      v-if="list.data.value"
      v-model:current-page="page"
      :total="list.data.value.total"
      :page-size="10"
      layout="total, prev, pager, next"
    />
  </section>
  <section class="panel">
    <h2>上传课程资料</h2>
    <p class="muted">
      TXT、MD、文本型 PDF，单文件不超过 10 MiB。上传后请等待资料处理完成。
    </p>
    <p v-if="isDemo" class="notice">
      演示环境仅保存文件并展示处理状态，暂不提供文档内容解析。
    </p>
    <form class="stacked-form upload-form" @submit.prevent="upload">
      <label for="upload-title">上传资料标题</label
      ><el-input
        id="upload-title"
        v-model="uploadTitle"
        maxlength="100"
        :disabled="uploading"
      /><label for="upload-kps">上传关联知识点</label
      ><select
        id="upload-kps"
        v-model="uploadKps"
        multiple
        size="3"
        :disabled="uploading"
      >
        <option
          v-for="k in course.data.value?.knowledge_points.filter(
            (k) => k.active,
          )"
          :key="k.knowledge_point_id"
          :value="k.knowledge_point_id"
        >
          {{ k.name }}
        </option></select
      ><label for="upload-file">选择文件</label>
      <div class="file-picker">
        <el-button :disabled="uploading" @click="fileInput?.click()"
          >选择文件</el-button
        ><span role="status">{{ selectedFile?.name || '未选择文件' }}</span>
      </div>
      <input
        ref="fileInput"
        class="visually-hidden-file"
        tabindex="-1"
        id="upload-file"
        type="file"
        accept=".txt,.md,.pdf"
        :disabled="uploading"
        @change="selectFile"
      />
      <div class="actions">
        <el-button type="primary" native-type="submit" :loading="uploading"
          >上传并处理</el-button
        ><el-button v-if="uploading" @click="controller?.abort()"
          >取消上传</el-button
        >
      </div>
      <p v-if="uploadError" class="inline-error" role="alert">
        {{ uploadError }}
      </p>
    </form>
    <div v-if="taskId" class="notice">
      <p v-if="config.debug" class="mono">
        文档 {{ documentId }}<br />任务 {{ taskId }}
      </p>
      <p role="status">
        {{
          polling.task.value
            ? statusLabels[polling.task.value.status]
            : '查询中'
        }}
        · {{ taskText(polling.task.value) }}
      </p>
      <p
        v-if="polling.task.value?.error_message"
        role="alert"
        class="inline-error"
      >
        {{ taskError(polling.task.value.error_code) }}
      </p>
      <p v-if="polling.reason.value === 'limit'">
        仍在处理，已达等待上限，可稍后查询。
      </p>
      <PageState
        empty-title="暂无匹配记录"
        empty-text="请调整查询条件，或等待相关内容更新。"
        :error="polling.error.value"
        @retry="polling.restart"
      /><el-button @click="polling.restart">刷新处理状态</el-button
      ><el-button
        v-if="polling.task.value?.can_retry"
        :loading="retrying"
        @click="retryTask"
        >重试资料处理</el-button
      >
    </div>
  </section>
  <el-dialog
    v-model="opened"
    :title="editId ? '编辑学习资源' : '新建学习资源'"
    width="700px"
    :close-on-click-modal="false"
    ><form class="stacked-form" @submit.prevent="save">
      <label for="resource-title">资源标题</label
      ><el-input
        id="resource-title"
        v-model="form.title"
        maxlength="100"
      /><label
        >资源类型<select v-model="form.kind" :disabled="!!editId">
          <option value="note">自编文本</option>
          <option value="external">外部链接</option>
          <option v-if="form.kind === 'document'" value="document">
            上传文档
          </option>
        </select></label
      ><label for="resource-description">资源说明</label
      ><el-input
        id="resource-description"
        v-model="form.description"
        type="textarea"
        maxlength="3000"
      /><template v-if="form.kind === 'note'"
        ><label for="resource-text">资料正文</label
        ><el-input
          id="resource-text"
          v-model="form.text_content"
          type="textarea"
          :rows="6" /></template
      ><template v-if="form.kind === 'external'"
        ><label for="resource-url">外部链接（http/https）</label
        ><el-input id="resource-url" v-model="form.external_url" /></template
      ><label for="resource-kps">关联知识点</label
      ><select
        id="resource-kps"
        v-model="form.knowledge_point_ids"
        multiple
        size="4"
      >
        <option
          v-for="k in course.data.value?.knowledge_points.filter(
            (k) => k.active,
          )"
          :key="k.knowledge_point_id"
          :value="k.knowledge_point_id"
        >
          {{ k.name }}
        </option></select
      ><label
        >难度<select v-model="form.difficulty">
          <option value="easy">基础</option>
          <option value="medium">中等</option>
          <option value="hard">较难</option>
        </select></label
      ><el-checkbox v-model="form.active">启用资源</el-checkbox>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div class="actions">
        <el-button :disabled="busy" @click="opened = false">取消</el-button
        ><el-button type="primary" native-type="submit" :loading="busy"
          >保存资源</el-button
        >
      </div>
    </form></el-dialog
  >
</template>
