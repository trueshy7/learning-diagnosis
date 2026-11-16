import { createRouter, createWebHashHistory } from 'vue-router'
import { getSession } from '../services/session'
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/courses' },
    { path: '/login', component: () => import('../views/LoginView.vue') },
    { path: '/courses', component: () => import('../views/CoursesView.vue'), meta: { auth: true } },
    { path: '/quiz/:courseId', component: () => import('../views/QuizView.vue'), meta: { auth: true } },
    { path: '/report/:attemptId', component: () => import('../views/ReportView.vue'), meta: { auth: true } },
    { path: '/history', component: () => import('../views/HistoryView.vue'), meta: { auth: true } },
    { path: '/teacher', component: () => import('../views/TeacherView.vue'), meta: { auth: true, teacher: true } },
    { path: '/:pathMatch(.*)*', redirect: '/courses' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.beforeEach(to => {
  const session = getSession()
  if (to.meta.auth && !session) return '/login'
  if (to.meta.teacher && session?.user.role !== 'teacher') return '/courses'
})
