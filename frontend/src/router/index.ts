import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
          meta: { title: '监测总览' },
        },
        {
          path: 'creators',
          name: 'creators',
          component: () => import('../views/CreatorsView.vue'),
          meta: { title: '监控账号' },
        },
        {
          path: 'creators/:id',
          name: 'creator-detail',
          component: () => import('../views/CreatorDetailView.vue'),
          meta: { title: '账号详情' },
        },
        {
          path: 'feed',
          name: 'feed',
          component: () => import('../views/FeedView.vue'),
          meta: { title: '内容动态' },
        },
        {
          path: 'alerts',
          name: 'alerts',
          component: () => import('../views/AlertsView.vue'),
          meta: { title: '预警中心' },
        },
      ],
    },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '创作者监测')} - Creator Monitor`
})

export default router
