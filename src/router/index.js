import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import IngredientsView from '../views/ingredientView.vue'
import MealsView from '../views/MealsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import UnitsView from '@/views/UnitsView.vue'

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
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
    },
    {
      path: '/settings/units',
      name: 'units',
      component: UnitsView,
    },
  ],
})

export default router
