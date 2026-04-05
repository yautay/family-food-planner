import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@views/HomeView.vue'
import IngredientsView from '@views/ingredientView.vue'
import MealsView from '@views/MealsView.vue'
import SettingsView from '@views/SettingsView.vue'
import UnitsView from '@views/UnitsView.vue'
import TagView from '@views/TagView.vue'
import CatalogView from '@views/CatalogView.vue'
import LoginView from '@views/LoginView.vue'
import RegisterView from '@views/RegisterView.vue'
import ForgotPasswordView from '@views/ForgotPasswordView.vue'
import ResetPasswordView from '@views/ResetPasswordView.vue'
import AccountView from '@views/AccountView.vue'
import AccessControlView from '@views/AccessControlView.vue'

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
    {
      path: '/settings/tags',
      name: 'tags',
      component: TagView,
    },
    {
      path: '/catalog',
      name: 'catalog',
      component: CatalogView,
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: ForgotPasswordView,
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: ResetPasswordView,
    },
    {
      path: '/account',
      name: 'account',
      component: AccountView,
      meta: { requiresAuth: true },
    },
    {
      path: '/access-control',
      name: 'access-control',
      component: AccessControlView,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const hasToken = Boolean(localStorage.getItem('ffp_auth_token'))

  if (to.meta.requiresAuth && !hasToken) {
    return {
      name: 'login',
      query: {
        redirect: to.fullPath,
      },
    }
  }

  return true
})

export default router
