<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from './stores/auth';
const DemoPanel =
  import.meta.env.VITE_API_MODE === 'mock' &&
  import.meta.env.VITE_SHOW_DEV_TOOLS === 'true'
    ? defineAsyncComponent(() => import('./mocks/DemoPanel.vue'))
    : null;
const auth = useAuth(),
  route = useRoute(),
  router = useRouter();
const isDemo = import.meta.env.VITE_API_MODE === 'mock';
const teacher = computed(() => auth.user?.role === 'teacher');
const links = computed(() =>
  teacher.value
    ? [
        ['/teacher/overview', '教学概况'],
        ['/teacher/course', '课程设置'],
        ['/teacher/knowledge-points', '知识点管理'],
        ['/teacher/questions', '题库管理'],
        ['/teacher/resources', '资料与上传'],
      ]
    : [
        ['/courses', '我的课程'],
        ['/reports', '学习报告'],
      ],
);
const isLogin = computed(() => route.path === '/login');
async function logout() {
  try {
    await auth.logout();
  } catch {
    /* local logout always completes */
  }
  await router.replace('/login');
}
function expired() {
  auth.clear();
  void router.replace({
    path: '/login',
    query: { expired: '1', redirect: route.fullPath },
  });
}
window.addEventListener('learnmate-expired', expired);
onBeforeUnmount(() => window.removeEventListener('learnmate-expired', expired));
</script>
<template>
  <div class="app-shell" :class="{ 'login-shell': isLogin }">
    <aside v-if="!isLogin && auth.user" class="sidebar">
      <router-link class="brand" to="/"
        ><span class="brand-mark">L</span>
        <div>LearnMate<small>让下一步学习更清晰</small></div></router-link
      >
      <div class="workspace-label">
        {{ teacher ? '教师工作台' : '学习空间' }}
      </div>
      <nav aria-label="主导航">
        <router-link v-for="[path, label] in links" :key="path" :to="path"
          ><span class="nav-dot"></span>{{ label }}</router-link
        >
      </nav>
      <div class="sidebar-note">
        <span class="eyebrow">LEARN · REFLECT · GROW</span>
        <p>一次测验是起点。<br />理解过程，比一个分数更重要。</p>
      </div>
    </aside>
    <div class="workspace">
      <header v-if="!isLogin" class="topbar">
        <span
          >学习与诊断 / <strong>{{ route.meta.title }}</strong></span
        >
        <div v-if="auth.user" class="userbar">
          <span class="avatar">{{ auth.user.display_name.slice(0, 1) }}</span
          ><span
            >{{ auth.user.display_name
            }}<small>{{ teacher ? '教师' : '学生' }}</small></span
          ><el-button text @click="logout">退出登录</el-button>
        </div>
      </header>
      <main :class="{ 'main-content': !isLogin }">
        <router-view :key="route.path" />
      </main>
      <footer v-if="!isLogin" class="footer">
        LearnMate · 课程学习诊断与推荐系统<span>以本次测验数据为依据</span>
      </footer>
    </div>
  </div>
  <component :is="DemoPanel" v-if="DemoPanel" />
  <div v-else-if="isDemo" class="demo-dock">
    <span class="demo-badge" role="status">演示环境 · 示例数据</span>
  </div>
</template>
