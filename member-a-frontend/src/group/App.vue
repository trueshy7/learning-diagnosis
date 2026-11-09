<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from './stores/auth';
import { errorText } from './services/api';
const auth = useAuthStore(),
  router = useRouter(),
  busy = ref(false),
  logoutError = ref('');
const sync = () => auth.sync();
window.addEventListener('group-session-changed', sync);
onBeforeUnmount(() =>
  window.removeEventListener('group-session-changed', sync),
);
async function logout() {
  if (busy.value) return;
  busy.value = true;
  logoutError.value = '';
  try {
    await auth.logout();
  } catch (e) {
    logoutError.value = errorText(e) + ' 本机已退出，服务端会话撤销未确认。';
  } finally {
    busy.value = false;
    await router.push('/login');
  }
}
</script>
<template>
  <header class="site-header">
    <div class="container header-inner">
      <RouterLink class="brand" to="/courses"
        ><strong>LearnMate · 学习诊断</strong
        ><small>让下一步学习更清晰</small></RouterLink
      >
      <nav v-if="auth.user" aria-label="主导航">
        <RouterLink to="/courses">课程测验</RouterLink
        ><RouterLink to="/history">测验历史</RouterLink
        ><RouterLink v-if="auth.user.role === 'teacher'" to="/teacher"
          >教师工作台</RouterLink
        ><button class="text-button" :disabled="busy" @click="logout">
          退出 {{ auth.user.username }}
        </button>
      </nav>
    </div>
  </header>
  <main class="container main">
    <p v-if="logoutError" class="error" role="alert">{{ logoutError }}</p>
    <RouterView />
  </main>
  <footer class="container footer">LearnMate · 课程学习诊断与推荐</footer>
</template>
