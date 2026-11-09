<script setup lang="ts">
import { ref } from 'vue';
import { api } from '../../api/services';
import { useLoad } from '../../composables/useLoad';
import { dateText, numberText } from '../../utils';
import { config, statusLabels } from '../../config';
import PageState from '../../components/common/PageState.vue';
const page = ref(1),
  kind = ref('');
const { data, loading, error, reload } = useLoad(
  () => `${page.value}:${kind.value}`,
  () =>
    api.history({
      page: page.value,
      page_size: 10,
      ...(kind.value ? { kind: kind.value } : {}),
    }),
);
</script>
<template>
  <div class="page-heading">
    <span class="eyebrow">LEARNING HISTORY</span>
    <h1>学习报告</h1>
    <p>每一次作答都有对应记录。复测比较以报告保存的基准为准。</p>
  </div>
  <section class="panel">
    <div class="toolbar">
      <label
        >测验类型<select v-model="kind" @change="page = 1">
          <option value="">全部</option>
          <option value="initial">前测</option>
          <option value="practice">练习</option>
          <option value="retest">复测</option>
        </select></label
      ><el-button @click="reload">刷新记录</el-button>
    </div>
    <PageState
      :loading="loading"
      :error="error"
      :empty="data?.total === 0"
      @retry="reload"
    />
    <div v-if="data?.items.length" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>提交时间</th>
            <th>类型</th>
            <th>成绩</th>
            <th>诊断状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in data.items" :key="a.attempt_id">
            <td>
              {{ dateText(a.submitted_at)
              }}<small v-if="config.debug" class="mono block">{{
                a.attempt_id
              }}</small>
            </td>
            <td>{{ statusLabels[a.kind] }}</td>
            <td>
              {{
                a.score
                  ? `${a.score.raw_score}/${a.score.max_score} · ${numberText(a.score.percentage)} 分`
                  : '暂无成绩'
              }}
            </td>
            <td>
              {{
                a.diagnosis_status
                  ? statusLabels[a.diagnosis_status]
                  : '尚未诊断'
              }}
            </td>
            <td>
              <router-link v-if="a.report_id" :to="`/reports/${a.report_id}`"
                >查看报告</router-link
              ><router-link v-else :to="`/attempts/${a.attempt_id}/diagnosis`"
                >查看成绩与状态</router-link
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-pagination
      v-if="data && data.total > 10"
      v-model:current-page="page"
      :page-size="10"
      :total="data.total"
      layout="prev, pager, next"
    />
  </section>
</template>
