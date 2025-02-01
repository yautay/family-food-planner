import express from 'express'
import cors from 'cors'
import unitRoutes from "./src/apiroutes/units.js"
import foodItemRoutes from './src/apiroutes/fooditems.js'
import tagRoutes from './src/apiroutes/tags.js'

const app = express()
const port = 3000

app.use(cors())
app.use(express.json())

app.use('/api/units', unitRoutes)
app.use('/api/tags', tagRoutes)
app.use('/api/food-items', foodItemRoutes)

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`)
})
