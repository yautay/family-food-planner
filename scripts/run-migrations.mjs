import Database from 'better-sqlite3'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const migrationsDir = path.join(projectRoot, 'db', 'migrations')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

db.exec(`
  CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )
`)

const applied = new Set(
  db
    .prepare('SELECT filename FROM schema_migrations ORDER BY filename')
    .all()
    .map((row) => row.filename),
)

const migrationFiles = readdirSync(migrationsDir)
  .filter((filename) => filename.endsWith('.sql'))
  .sort((left, right) => left.localeCompare(right))

if (migrationFiles.length === 0) {
  console.log('No migration files found.')
  db.close()
  process.exit(0)
}

const recordMigration = db.prepare('INSERT INTO schema_migrations (filename) VALUES (?)')

for (const filename of migrationFiles) {
  if (applied.has(filename)) {
    console.log(`Skipping ${filename} (already applied)`)
    continue
  }

  const migrationPath = path.join(migrationsDir, filename)
  const sql = readFileSync(migrationPath, 'utf8')

  const applyMigration = db.transaction(() => {
    db.exec(sql)
    recordMigration.run(filename)
  })

  applyMigration()
  console.log(`Applied migration: ${filename}`)
}

db.close()
console.log('Migrations finished successfully.')
