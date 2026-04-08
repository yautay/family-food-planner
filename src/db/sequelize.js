import sequelize from './client.js'
import '../models/index.js'

export async function initDatabase() {
  await sequelize.authenticate()
}

export default sequelize
