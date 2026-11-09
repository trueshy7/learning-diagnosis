<script setup lang="ts">
import { validationMessage } from '../../utils/presentation';
import { userError } from '../../utils/presentation';
import { reactive, ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { confirmDisable } from '../../utils/confirm';
import { api } from '../../api/services';
import { knowledgeWriteSchema, type Knowledge } from '../../api/contracts';
import { useCourse } from '../../composables/useCourse';
import { useLoad } from '../../composables/useLoad';
import PageState from '../../components/common/PageState.vue';
const course = useCourse(),
  q = ref(''),
  active = ref(''),
  page = ref(1),
  opened = ref(false),
  busy = ref(false),
  editId = ref<string | null>(null),
  saveError = ref(''),
  message = ref('');
const originalActive = ref(false);
const form = reactive({
  name: '',
  description: '',
  sort_order: 1,
  active: true,
});
const list = useLoad(
  () =>
    `${course.data.value?.course_id}:${q.value}:${active.value}:${page.value}`,
  async () =>
    course.data.value
      ? api.knowledge({
          course_id: course.data.value.course_id,
          q: q.value,
          ...(active.value ? { active: active.value } : {}),
          page: page.value,
          page_size: 10,
        })
      : null,
);
function edit(k?: Knowledge) {
  originalActive.value = k?.active || false;
  editId.value = k?.knowledge_point_id || null;
  Object.assign(
    form,
    k || {
      name: '',
      description: '',
      sort_order: (course.data.value?.knowledge_points.length || 0) + 1,
      active: true,
    },
  );
  saveError.value = '';
  opened.value = true;
}
async function save() {
  if (!course.data.value || busy.value) return;
  const parsed = knowledgeWriteSchema.safeParse({
    ...form,
    course_id: course.data.value.course_id,
  });
  if (!parsed.success) {
    saveError.value = validationMessage(parsed.error);
    return;
  }
  busy.value = true;
  if (
    originalActive.value &&
    !parsed.data.active &&
    !(await confirmDisable(parsed.data.name))
  ) {
    busy.value = false;
    return;
  }
  try {
    await api.saveKnowledge(editId.value, parsed.data);
    opened.value = false;
    message.value = '知识点已保存';
    await Promise.all([course.reload(), list.reload()]);
  } catch (e) {
    saveError.value = userError(e);
  } finally {
    busy.value = false;
  }
}
async function disable(k: Knowledge) {
  if (busy.value) return;
  try {
    await ElMessageBox.confirm(
      `停用“${k.name}”会影响新题目关联，历史报告仍保留。确认继续？`,
      '确认停用',
      { confirmButtonText: '确认停用', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    await api.saveKnowledge(k.knowledge_point_id, { ...k, active: false });
    message.value = '知识点已停用';
    await list.reload();
  } catch (e) {
    message.value = userError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">KNOWLEDGE CATALOG</span>
    <h1>知识点管理</h1>
    <p>维护名称、说明和课程内顺序。已有历史记录保留原报告快照。</p>
  </div>
  <section class="panel">
    <div class="toolbar">
      <label>搜索名称<input v-model="q" @input="page = 1" /></label
      ><label
        >启用状态<select v-model="active" @change="page = 1">
          <option value="">全部</option>
          <option value="true">启用</option>
          <option value="false">停用</option>
        </select></label
      ><el-button
        type="primary"
        :disabled="!course.data.value || busy"
        @click="edit()"
        >新增知识点</el-button
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
            <th>顺序</th>
            <th>名称</th>
            <th>说明</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in list.data.value.items" :key="k.knowledge_point_id">
            <td>{{ k.sort_order }}</td>
            <td>{{ k.name }}</td>
            <td>{{ k.description }}</td>
            <td>{{ k.active ? '启用' : '停用' }}</td>
            <td>
              <el-button text @click="edit(k)">编辑</el-button
              ><el-button
                v-if="k.active"
                text
                type="danger"
                :disabled="busy"
                @click="disable(k)"
                >停用</el-button
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-pagination
      v-if="list.data.value && list.data.value.total > 10"
      v-model:current-page="page"
      :total="list.data.value.total"
      :page-size="10"
      layout="prev, pager, next"
    />
  </section>
  <el-dialog
    v-model="opened"
    :title="editId ? '编辑知识点' : '新增知识点'"
    width="600px"
    :close-on-click-modal="false"
    ><form class="stacked-form" @submit.prevent="save">
      <label for="kp-name">知识点名称</label
      ><el-input id="kp-name" v-model="form.name" maxlength="100" /><label
        for="kp-description"
        >知识点说明</label
      ><el-input
        id="kp-description"
        v-model="form.description"
        type="textarea"
        :rows="4"
        maxlength="3000"
      /><label for="kp-order">显示顺序</label
      ><el-input-number
        id="kp-order"
        v-model="form.sort_order"
        :min="0"
      /><el-checkbox v-model="form.active">启用</el-checkbox>
      <p v-if="saveError" role="alert" class="inline-error">{{ saveError }}</p>
      <div class="actions">
        <el-button :disabled="busy" @click="opened = false">取消</el-button
        ><el-button type="primary" native-type="submit" :loading="busy"
          >保存知识点</el-button
        >
      </div>
    </form></el-dialog
  >
</template>
