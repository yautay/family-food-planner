import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import IngredientsView from '../views/IngredientsView.vue'
import MealsView from '../views/MealsView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/ingredients',
      name: 'ingredients',
      component: IngredientsView,
    },
    {
      path: '/meals',
      name: 'meals',
      component: MealsView,
    },
  ],
})

export default router
