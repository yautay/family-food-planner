import sequelize from './client.js'
import '../models/index.js'

export async function initDatabase() {
  await sequelize.authenticate()
  await sequelize.sync()
}

export default sequelize
