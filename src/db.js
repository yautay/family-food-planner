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
    calories_per_100g INTEGER,
    carbohydrates_per_100g REAL,
    sugars_per_100g REAL,
    fat_per_100g REAL,
    protein_per_100g REAL,
    fiber_per_100g REAL,
    FOREIGN KEY (unit_id) REFERENCES units(id)
  )
`)

export default db
