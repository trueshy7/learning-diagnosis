<script setup lang="ts">
import { userError } from '../../utils/presentation';
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from '../../stores/auth';
import { safeRedirect } from '../../utils';
const username = ref(''),
  password = ref(''),
  loading = ref(false),
  error = ref('');
const auth = useAuth(),
  router = useRouter(),
  route = useRoute();
async function submit() {
  if (loading.value) return;
  if (!username.value.trim() || !password.value) {
    error.value = '请输入账号和密码';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    await auth.login(username.value.trim(), password.value);
    await router.replace(safeRedirect(route.query.redirect, auth.user!.role));
  } catch (e) {
    error.value = userError(e);
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story">
      <div class="brand">
        <span class="brand-mark">L</span>
        <div>LearnMate<small>个性化学习诊断与推荐</small></div>
      </div>
      <div class="login-copy">
        <span class="eyebrow">YOUR NEXT LEARNING STEP</span>
        <h1>看见薄弱点，<br />找到学习的<br /><em>下一步。</em></h1>
        <p>
          从一次测验出发，让诊断有数据，<br />让建议有依据，让进步可以回看。
        </p>
        <div class="learning-path">
          <span>01 测验</span><i></i><span>02 诊断</span><i></i
          ><span>03 复习</span><i></i><span>04 复测</span>
        </div>
      </div>
      <small>基于课程资料与本次测验记录</small>
    </section>
    <section class="login-form-area">
      <form class="login-form" @submit.prevent="submit">
        <span class="eyebrow">WELCOME BACK</span>
        <h2>登录学习空间</h2>
        <p class="muted">使用课程账号继续你的学习与教学。</p>
        <p v-if="route.query.expired" class="notice" role="status">
          登录已过期，请重新登录。
        </p>
        <p v-if="route.query.error" role="alert" class="notice">
          {{ route.query.error }}
        </p>
        <label for="username">账号</label
        ><el-input
          id="username"
          v-model="username"
          autocomplete="username"
          placeholder="请输入账号"
          size="large"
          :disabled="loading"
        /><label for="password">密码</label
        ><el-input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
          show-password
          size="large"
          :disabled="loading"
        />
        <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
        <el-button
          type="primary"
          native-type="submit"
          size="large"
          :loading="loading"
          class="login-submit"
          >登录</el-button
        >
        <p class="login-hint">成绩与诊断由服务返回，掌握状态仅反映本次测验。</p>
      </form>
    </section>
  </div>
</template>
