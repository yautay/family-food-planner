import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { QueryTypes } from 'sequelize'
import sequelize from '../src/db/client.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const migrationsDir = path.join(projectRoot, 'db', 'migrations')

function splitSqlStatements(sql) {
  const statements = []
  let current = ''
  let inSingle = false
  let inDouble = false
  let inLineComment = false
  let inBlockComment = false

  for (let index = 0; index < sql.length; index += 1) {
    const char = sql[index]
    const next = sql[index + 1] ?? ''

    if (inLineComment) {
      current += char
      if (char === '\n') {
        inLineComment = false
      }
      continue
    }

    if (inBlockComment) {
      current += char
      if (char === '*' && next === '/') {
        current += next
        index += 1
        inBlockComment = false
      }
      continue
    }

    if (!inSingle && !inDouble) {
      if (char === '-' && next === '-') {
        current += char
        inLineComment = true
        continue
      }

      if (char === '/' && next === '*') {
        current += char
        inBlockComment = true
        continue
      }
    }

    if (char === "'" && !inDouble) {
      inSingle = !inSingle
      current += char
      continue
    }

    if (char === '"' && !inSingle) {
      inDouble = !inDouble
      current += char
      continue
    }

    if (char === ';' && !inSingle && !inDouble) {
      const trimmed = current.trim()
      if (trimmed.length > 0) {
        statements.push(trimmed)
      }
      current = ''
      continue
    }

    current += char
  }

  const trailing = current.trim()
  if (trailing.length > 0) {
    statements.push(trailing)
  }

  return statements
}

await sequelize.authenticate()

await sequelize.query(
  `
  CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )
  `,
)

const appliedRows = await sequelize.query(
  'SELECT filename FROM schema_migrations ORDER BY filename',
  { type: QueryTypes.SELECT },
)

const applied = new Set(appliedRows.map((row) => row.filename))

const migrationFiles = readdirSync(migrationsDir)
  .filter((filename) => filename.endsWith('.sql'))
  .sort((left, right) => left.localeCompare(right))

if (migrationFiles.length === 0) {
  console.log('No migration files found.')
  await sequelize.close()
  process.exit(0)
}

for (const filename of migrationFiles) {
  if (applied.has(filename)) {
    console.log(`Skipping ${filename} (already applied)`)
    continue
  }

  const migrationPath = path.join(migrationsDir, filename)
  const sql = readFileSync(migrationPath, 'utf8')
  const statements = splitSqlStatements(sql)

  await sequelize.transaction(async (transaction) => {
    for (const statement of statements) {
      await sequelize.query(statement, { transaction })
    }

    await sequelize.query('INSERT INTO schema_migrations (filename) VALUES (?)', {
      replacements: [filename],
      transaction,
    })
  })

  console.log(`Applied migration: ${filename}`)
}

await sequelize.close()
console.log('Migrations finished successfully.')
