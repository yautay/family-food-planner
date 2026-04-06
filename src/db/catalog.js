import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '../..')

function resolveDatabasePath() {
  return path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')
}

const catalogDb = new Database(resolveDatabasePath())
catalogDb.pragma('foreign_keys = ON')

export default catalogDb
