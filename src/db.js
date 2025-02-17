import Database from 'better-sqlite3'

const db = new Database('database.db', { verbose: console.log })

// Create tables if they don't exist
db.exec(`
  CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS ingredients (
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
  );
  CREATE TABLE IF NOT EXISTS ingredients_tags (
    ingredient_id INTEGER,
    tag_id INTEGER,
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
  );
`)

export default db
