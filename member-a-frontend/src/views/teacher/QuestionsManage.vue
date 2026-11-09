<script setup lang="ts">
import { validationMessage } from '../../utils/presentation';
import { userError } from '../../utils/presentation';
import { reactive, ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { confirmDisable } from '../../utils/confirm';
import {
  questionWriteSchema,
  type QuestionWrite,
  type TeacherQuestion,
} from '../../api/contracts';
import { statusLabels } from '../../config';
import { api } from '../../api/services';
import { questionToWrite } from '../../api/mappers/teacher';
import { useCourse } from '../../composables/useCourse';
import { useLoad } from '../../composables/useLoad';
import PageState from '../../components/common/PageState.vue';
const course = useCourse(),
  type = ref(''),
  kp = ref(''),
  active = ref(''),
  page = ref(1),
  opened = ref(false),
  busy = ref(false),
  editId = ref<string | null>(null),
  error = ref(''),
  message = ref('');
const empty = (): QuestionWrite => ({
  course_id: course.data.value?.course_id || '',
  type: 'single_choice',
  stem: '',
  options: ['A', 'B', 'C', 'D'].map((label) => ({
    option_id: null,
    client_key: crypto.randomUUID(),
    label,
    text: '',
  })),
  correct_option_keys: [],
  knowledge_point_ids: [],
  difficulty: 'easy',
  explanation: '',
  active: true,
});
const form = reactive<QuestionWrite>(empty());
const originalActive = ref(false);
function addOption() {
  form.options.push({
    option_id: null,
    client_key: crypto.randomUUID(),
    label: String.fromCharCode(65 + form.options.length),
    text: '',
  });
}
const list = useLoad(
  () =>
    `${course.data.value?.course_id}:${type.value}:${kp.value}:${active.value}:${page.value}`,
  async () =>
    course.data.value
      ? api.questions({
          course_id: course.data.value.course_id,
          page: page.value,
          page_size: 10,
          ...(type.value ? { type: type.value } : {}),
          ...(kp.value ? { knowledge_point_id: kp.value } : {}),
          ...(active.value ? { active: active.value } : {}),
        })
      : null,
);
function edit(q?: TeacherQuestion) {
  originalActive.value = q?.active || false;
  editId.value = q?.question_id || null;
  Object.assign(form, q ? questionToWrite(q) : empty());
  error.value = '';
  opened.value = true;
}
function removeOption(i: number) {
  const key = form.options[i].client_key;
  form.options.splice(i, 1);
  form.options.forEach(
    (option, index) => (option.label = String.fromCharCode(65 + index)),
  );
  if (form.correct_option_keys.includes(key)) {
    form.correct_option_keys = form.correct_option_keys.filter(
      (k) => k !== key,
    );
    error.value = '已移除该选项及对应标准答案，请重新确认答案集合';
  }
}
async function save() {
  if (busy.value) return;
  const parsed = questionWriteSchema.safeParse(form);
  if (!parsed.success) {
    error.value = validationMessage(parsed.error);
    return;
  }
  busy.value = true;
  error.value = '';
  if (
    originalActive.value &&
    !parsed.data.active &&
    !(await confirmDisable(parsed.data.stem))
  ) {
    busy.value = false;
    return;
  }
  try {
    await api.saveQuestion(editId.value, parsed.data);
    opened.value = false;
    message.value = '题目已保存，历史试卷快照保持原内容';
    await list.reload();
  } catch (e) {
    error.value = userError(e);
  } finally {
    busy.value = false;
  }
}
async function disable(q: TeacherQuestion) {
  if (busy.value) return;
  try {
    await ElMessageBox.confirm(
      `停用“${q.stem}”？新测验不再选用，历史快照仍保留。`,
      '确认停用题目',
      { confirmButtonText: '确认停用', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    await api.saveQuestion(q.question_id, {
      ...questionToWrite(q),
      active: false,
    });
    message.value = '题目已停用';
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
    <span class="eyebrow">QUESTION BANK</span>
    <h1>题库管理</h1>
    <p>题目及标准答案仅限教师维护。编辑不会追改已有测验快照。</p>
  </div>
  <section class="panel">
    <div class="toolbar">
      <label
        >题型<select v-model="type" aria-label="题型" @change="page = 1">
          <option value="">全部</option>
          <option value="single_choice">单选</option>
          <option value="multiple_choice">多选</option>
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
        >新增题目</el-button
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
            <th>题干</th>
            <th>类型 / 难度</th>
            <th>标准答案</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="q in list.data.value.items" :key="q.question_id">
            <td class="question-cell">{{ q.stem }}</td>
            <td>
              {{ q.type === 'single_choice' ? '单选' : '多选' }} /
              {{ statusLabels[q.difficulty] }}
            </td>
            <td>
              {{
                q.options
                  .filter((o) => q.correct_option_ids.includes(o.option_id))
                  .map((o) => o.label)
                  .join('、')
              }}
            </td>
            <td>{{ q.active ? '启用' : '停用' }}</td>
            <td class="nowrap">
              <el-button text @click="edit(q)">编辑</el-button
              ><el-button
                v-if="q.active"
                text
                type="danger"
                :disabled="busy"
                @click="disable(q)"
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
  <el-dialog
    v-model="opened"
    :title="editId ? '编辑题目' : '新增题目'"
    width="780px"
    :close-on-click-modal="false"
    ><form class="stacked-form" @submit.prevent="save">
      <label for="question-stem">题干</label
      ><el-input
        id="question-stem"
        v-model="form.stem"
        type="textarea"
        :rows="3"
        maxlength="2000"
      />
      <div class="form-row">
        <label
          >题目类型<select v-model="form.type" aria-label="题目类型">
            <option value="single_choice">单选</option>
            <option value="multiple_choice">多选</option>
          </select></label
        ><label
          >难度<select v-model="form.difficulty">
            <option value="easy">基础</option>
            <option value="medium">中等</option>
            <option value="hard">较难</option>
          </select></label
        >
      </div>
      <fieldset>
        <legend>选项与标准答案（勾选正确项）</legend>
        <div
          v-for="(o, i) in form.options"
          :key="o.client_key"
          class="option-editor"
        >
          <label
            ><input
              v-model="form.correct_option_keys"
              type="checkbox"
              :value="o.client_key"
              :aria-label="`正确选项 ${o.label}`"
            />{{ o.label }}</label
          ><input
            v-model="o.text"
            :aria-label="`选项 ${o.label} 内容`"
            maxlength="500"
          /><el-button
            :disabled="form.options.length <= 2"
            @click="removeOption(i)"
            >移除</el-button
          >
        </div>
        <el-button :disabled="form.options.length >= 6" @click="addOption"
          >增加选项</el-button
        >
      </fieldset>
      <label for="question-kps">关联知识点（可多选）</label
      ><select
        id="question-kps"
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
      ><label for="question-explanation">解析</label
      ><el-input
        id="question-explanation"
        v-model="form.explanation"
        type="textarea"
        maxlength="3000"
      /><el-checkbox v-model="form.active">启用题目</el-checkbox>
      <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
      <div class="actions">
        <el-button :disabled="busy" @click="opened = false">取消</el-button
        ><el-button type="primary" native-type="submit" :loading="busy"
          >保存题目</el-button
        >
      </div>
    </form></el-dialog
  >
</template>
