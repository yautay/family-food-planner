import { createApp } from './src/app.js'
import { initDatabase } from './src/db/sequelize.js'

const port = Number(process.env.PORT ?? 3000)

async function startServer() {
  const app = createApp()
  await initDatabase()

  app.listen(port, () => {
    console.log(`Server is running on http://localhost:${port}`)
  })
}

startServer().catch((error) => {
  console.error('Server startup failed:', error)
  process.exit(1)
})
