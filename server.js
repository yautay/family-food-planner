import express from 'express'
import cors from 'cors'
import routes from './src/routes/index.js'

const app = express()
const port = 3000

app.use(cors())
app.use(express.json())

app.use('/api/units', routes.units)
app.use('/api/tags', routes.tags)
app.use('/api/ingredients', routes.ingredients)

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`)
})
