<script setup lang="ts">
import { ref } from 'vue';
import { useCourse } from '../../composables/useCourse';
import { useLoad } from '../../composables/useLoad';
import { api } from '../../api/services';
import { numberText, dateText } from '../../utils';
import PageState from '../../components/common/PageState.vue';
const course = useCourse();
const q = ref(''),
  page = ref(1),
  selectedUser = ref(''),
  recordPage = ref(1),
  recordsOpen = ref(false);
const overview = useLoad(
  () => course.data.value?.course_id || '',
  async () =>
    course.data.value ? api.overview(course.data.value.course_id) : null,
);
const students = useLoad(
  () => `${course.data.value?.course_id}:${q.value}:${page.value}`,
  async () =>
    course.data.value
      ? api.students({
          course_id: course.data.value.course_id,
          q: q.value,
          page: page.value,
          page_size: 10,
        })
      : null,
);
const records = useLoad(
  () =>
    `${recordsOpen.value}:${selectedUser.value}:${recordPage.value}:${course.data.value?.course_id}`,
  async () =>
    recordsOpen.value && selectedUser.value && course.data.value
      ? api.studentAttempts(selectedUser.value, {
          course_id: course.data.value.course_id,
          page: recordPage.value,
          page_size: 10,
        })
      : null,
);
function showRecords(uid: string) {
  selectedUser.value = uid;
  recordPage.value = 1;
  recordsOpen.value = true;
}
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">TEACHING OVERVIEW</span>
    <h1>教学概况</h1>
    <p>查看课程范围内的学习记录，了解需要支持的学生。</p>
  </div>
  <PageState
    empty-title="暂无匹配记录"
    empty-text="请调整查询条件，或等待相关内容更新。"
    :loading="course.loading.value || overview.loading.value"
    :error="course.error.value || overview.error.value"
    @retry="
      course.reload();
      overview.reload();
    "
  />
  <div v-if="overview.data.value" class="metric-grid">
    <article class="panel">
      <span class="eyebrow">学生人数</span
      ><strong>{{ overview.data.value.student_count }}</strong>
    </article>
    <article class="panel">
      <span class="eyebrow">已提交测验</span
      ><strong>{{ overview.data.value.submitted_attempt_count }}</strong>
    </article>
    <article class="panel">
      <span class="eyebrow">课程平均分</span
      ><strong
        >{{ numberText(overview.data.value.average_percentage)
        }}<small> /100</small></strong
      >
    </article>
  </div>
  <section class="panel">
    <div class="section-head">
      <h2>学生学习记录</h2>
      <label
        >查找学生<input v-model="q" placeholder="姓名或账号" @input="page = 1"
      /></label>
    </div>
    <PageState
      empty-title="暂无匹配记录"
      empty-text="请调整查询条件，或等待相关内容更新。"
      :loading="students.loading.value"
      :error="students.error.value"
      :empty="students.data.value?.total === 0"
      @retry="students.reload"
    />
    <div v-if="students.data.value?.items.length" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>学生</th>
            <th>提交次数</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in students.data.value.items" :key="s.user_id">
            <td>{{ s.display_name }}</td>
            <td>{{ s.submitted_attempt_count }}</td>
            <td>
              <el-button text @click="showRecords(s.user_id)"
                >查看全部记录</el-button
              ><router-link
                v-if="s.latest_report_id"
                :to="`/teacher/students/${s.user_id}/reports/${s.latest_report_id}`"
                >最新报告 →</router-link
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-pagination
      v-if="students.data.value && students.data.value.total > 10"
      v-model:current-page="page"
      :total="students.data.value.total"
      :page-size="10"
      layout="prev, pager, next"
    />
  </section>
  <el-dialog v-model="recordsOpen" title="学生测验记录" width="760px">
    <PageState
      empty-title="暂无匹配记录"
      empty-text="请调整查询条件，或等待相关内容更新。"
      :loading="records.loading.value"
      :error="records.error.value"
      :empty="records.data.value?.total === 0"
      @retry="records.reload"
    />
    <div
      v-for="a in records.data.value?.items"
      :key="a.attempt_id"
      class="record-row"
    >
      <span
        >{{ dateText(a.submitted_at) }} ·
        {{
          a.score ? `${a.score.raw_score}/${a.score.max_score} 分` : '暂无成绩'
        }}</span
      ><router-link
        v-if="a.report_id"
        :to="`/teacher/students/${selectedUser}/reports/${a.report_id}`"
        @click="recordsOpen = false"
        >查看报告</router-link
      ><span v-else>{{
        a.diagnosis_status === 'failed' ? '报告生成未完成' : '报告处理中'
      }}</span>
    </div>
    <el-pagination
      v-if="records.data.value && records.data.value.total > 10"
      v-model:current-page="recordPage"
      :total="records.data.value.total"
      :page-size="10"
      layout="total, prev, pager, next"
    />
  </el-dialog>
</template>
