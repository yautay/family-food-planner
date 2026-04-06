import { Sequelize } from 'sequelize'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '../..')

function resolveDatabasePath() {
  return path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')
}

const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: resolveDatabasePath(),
  logging: false,
})

export default sequelize
