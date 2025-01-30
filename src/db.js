// src/db.js
import Database from 'better-sqlite3'

const db = new Database('database.db', { verbose: console.log })

// Create a table if it doesn't exist
db.exec(`
  CREATE TABLE IF NOT EXISTS counter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    count INTEGER
  )
`)

export function getCount() {
  const row = db.prepare('SELECT count FROM counter WHERE id = 1').get()
  return row ? row.count : 0
}

export function setCount(count) {
  const row = db.prepare('SELECT count FROM counter WHERE id = 1').get()
  if (row) {
    db.prepare('UPDATE counter SET count = ? WHERE id = 1').run(count)
  } else {
    db.prepare('INSERT INTO counter (count) VALUES (?)').run(count)
  }
}
