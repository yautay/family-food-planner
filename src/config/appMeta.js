import packageJson from '../../package.json'

const fallbackRepositoryUrl = 'https://github.com/yautay/family-food-planner'
const fallbackCodename = 'Harvest Orbit'

export const appMeta = {
  name: packageJson.name ?? 'family-food-planner',
  version: packageJson.version ?? '0.0.0',
  codename: import.meta.env.VITE_APP_CODENAME?.trim() || fallbackCodename,
  author: import.meta.env.VITE_APP_AUTHOR?.trim() || 'yautay',
  repositoryUrl: import.meta.env.VITE_APP_REPOSITORY_URL?.trim() || fallbackRepositoryUrl,
}
