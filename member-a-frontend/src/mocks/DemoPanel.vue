<script setup lang="ts">
import { ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useRouter } from 'vue-router';
import { scenarios } from './browser';
import { useAuth } from '../stores/auth';
const scenario = ref('normal'),
  delay = ref(0),
  message = ref(''),
  opened = ref(false);
const auth = useAuth(),
  router = useRouter();
async function setDelay() {
  await window.__LEARNMATE_DEMO__!.setDelay(delay.value);
  message.value = `响应延迟已设为 ${delay.value} ms`;
}
async function apply() {
  await window.__LEARNMATE_DEMO__!.setScenario(scenario.value);
  message.value = `已应用 ${scenario.value}，重新加载目标页面生效`;
  const preset: Record<string, string> = {
    'weak-profile': 'report-a-001',
    'balanced-profile': 'report-a-003',
    'insufficient-coverage': 'report-a-004',
  };
  if (preset[scenario.value] && auth.user?.user_id === 'student-a')
    await router.push(`/reports/${preset[scenario.value]}`);
}
async function reset() {
  try {
    await ElMessageBox.confirm(
      '仅重置本应用的本地演示数据和当前演示会话，确认继续？',
      '重置演示数据',
      { confirmButtonText: '确认重置', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  await window.__LEARNMATE_DEMO__!.reset();
  auth.clear();
  location.assign('/login');
}
</script>
<template>
  <div class="demo-dock">
    <button class="demo-badge" @click="opened = !opened">
      ◉ 演示数据 / 模拟服务 <span>{{ opened ? '收起' : '场景控制' }}</span>
    </button>
    <section v-if="opened" class="demo-panel" aria-label="演示场景面板">
      <strong>本地模拟控制</strong>
      <p>未连接真实后端、模型或向量库。</p>
      <p class="mono">
        demo_student_a / demo_student_b / demo_teacher<br />统一口令：Demo123!
      </p>
      <label
        >演示场景<select v-model="scenario" aria-label="演示场景">
          <option v-for="s in scenarios" :key="s">{{ s }}</option>
        </select></label
      ><el-button @click="apply">应用场景</el-button
      ><label
        >响应延迟（毫秒）<input
          v-model.number="delay"
          type="number"
          min="0"
          max="15000" /></label
      ><el-button @click="setDelay">设置延迟</el-button>
      <p role="status">{{ message }}</p>
      <el-button type="danger" plain @click="reset">重置演示数据</el-button>
    </section>
  </div>
</template>
