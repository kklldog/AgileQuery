import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const HomeView = () => import('@/views/Home.vue')
const DatabaseChatView = () => import('@/views/DatabaseChat.vue')
const SpaceDetailView = () => import('@/views/SpaceDetail.vue')

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomeView },
  {
    path: '/databases/:databaseId',
    name: 'database-chat',
    component: DatabaseChatView,
    props: true,
  },
  {
    path: '/databases/:databaseId/spaces/:spaceId',
    name: 'space-detail',
    component: SpaceDetailView,
    props: true,
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
