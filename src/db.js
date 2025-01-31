// src/db.js
import Database from 'better-sqlite3'

const db = new Database('database.db', { verbose: console.log })

// Create tables if they don't exist
db.exec(`
  CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS food_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    comment TEXT,
    unit_id INTEGER NOT NULL,
    quantity_per_package INTEGER,
    calories INTEGER,
    carbohydrates INTEGER,
    sugars INTEGER,
    fat INTEGER,
    protein INTEGER,
    fiber INTEGER,
    g INTEGER,
    FOREIGN KEY (unit_id) REFERENCES units(id)
  )
`)

export function addFoodItem(item) {
  const stmt = db.prepare(`
    INSERT INTO food_items (name, comment, unit_id, quantity_per_package, calories, carbohydrates, sugars, fat, protein, fiber, g)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)
  stmt.run(item.name, item.comment, item.unit_id, item.quantity_per_package, item.calories, item.carbohydrates, item.sugars, item.fat, item.protein, item.fiber, item.g)
}

export function getUnits() {
  return db.prepare('SELECT * FROM units').all()
}

export function addUnit(unit) {
  const stmt = db.prepare('INSERT INTO units (name) VALUES (?)')
  stmt.run(unit.name)
}

export function updateUnit(id, unit) {
  const stmt = db.prepare('UPDATE units SET name = ? WHERE id = ?')
  stmt.run(unit.name, id)
}

export function deleteUnit(id) {
  const stmt = db.prepare('DELETE FROM units WHERE id = ?')
  stmt.run(id)
}
