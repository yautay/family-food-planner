import express from 'express'
import cors from 'cors'
import unitRoutes from "./src/apiroutes/unitsApi.js"
import ingredientsRoutes from './src/apiroutes/ingredientsApi.js'
import tagRoutes from './src/apiroutes/tagsApi.js'

const app = express()
const port = 3000

app.use(cors())
app.use(express.json())

app.use('/api/units', unitRoutes)
app.use('/api/tags', tagRoutes)
app.use('/api/ingredients', ingredientsRoutes)

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`)
})
