import { createRouter, createWebHistory } from 'vue-router';
import { useAuth } from '../stores/auth';
import { safeRedirect } from '../utils';
export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      component: () => import('../views/auth/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      redirect: () =>
        useAuth().user?.role === 'teacher' ? '/teacher/overview' : '/courses',
    },
    {
      path: '/courses',
      component: () => import('../views/student/CoursesView.vue'),
      meta: { title: '我的课程', role: 'student' },
    },
    {
      path: '/courses/:courseId',
      component: () => import('../views/student/CourseView.vue'),
      meta: { title: '课程学习', role: 'student' },
    },
    {
      path: '/attempts/:attemptId',
      component: () => import('../views/student/AttemptView.vue'),
      meta: { title: '测验作答', role: 'student' },
    },
    {
      path: '/attempts/:attemptId/diagnosis',
      component: () => import('../views/student/DiagnosisView.vue'),
      meta: { title: '学习诊断', role: 'student' },
    },
    {
      path: '/reports',
      component: () => import('../views/student/HistoryView.vue'),
      meta: { title: '学习报告', role: 'student' },
    },
    {
      path: '/reports/:reportId',
      component: () => import('../views/student/ReportView.vue'),
      meta: { title: '完整报告', role: 'student' },
    },
    {
      path: '/reports/:reportId/recommendations',
      component: () => import('../views/student/ReportView.vue'),
      meta: { title: '学习推荐', role: 'student', recommendations: true },
    },
    {
      path: '/resources/:resourceId',
      component: () => import('../views/shared/ResourceView.vue'),
      meta: { title: '课程资料' },
    },
    {
      path: '/teacher/overview',
      component: () => import('../views/teacher/OverviewView.vue'),
      meta: { title: '教学概况', role: 'teacher' },
    },
    {
      path: '/teacher/course',
      component: () => import('../views/teacher/CourseManage.vue'),
      meta: { title: '课程设置', role: 'teacher' },
    },
    {
      path: '/teacher/knowledge-points',
      component: () => import('../views/teacher/KnowledgeManage.vue'),
      meta: { title: '知识点管理', role: 'teacher' },
    },
    {
      path: '/teacher/questions',
      component: () => import('../views/teacher/QuestionsManage.vue'),
      meta: { title: '题库管理', role: 'teacher' },
    },
    {
      path: '/teacher/resources',
      component: () => import('../views/teacher/ResourcesManage.vue'),
      meta: { title: '资料与上传', role: 'teacher' },
    },
    {
      path: '/teacher/students/:userId/reports/:reportId',
      component: () => import('../views/student/ReportView.vue'),
      meta: { title: '学生报告', role: 'teacher' },
    },
    {
      path: '/403',
      component: () => import('../views/shared/NotFound.vue'),
      meta: { title: '无权访问' },
    },
    {
      path: '/:pathMatch(.*)*',
      component: () => import('../views/shared/NotFound.vue'),
      meta: { title: '页面不存在' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
router.beforeEach(async (to) => {
  const auth = useAuth();
  try {
    await auth.bootstrap();
  } catch {
    if (to.path !== '/login')
      return { path: '/login', query: { error: '身份验证失败，请重新登录' } };
  }
  if (!to.meta.public && !auth.user)
    return {
      path: '/login',
      query: {
        redirect: to.fullPath,
        ...(sessionStorage.getItem('learnmate-expired')
          ? { expired: '1' }
          : {}),
      },
    };
  if (to.meta.role && auth.user?.role !== to.meta.role) return '/403';
  if (to.path === '/login' && auth.user)
    return safeRedirect(to.query.redirect, auth.user.role);
});
