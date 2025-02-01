import db from './database.js'

export function getUnits() {
  return db.prepare('SELECT * FROM units').all()
}

export function addUnit(unit) {
  const stmt = db.prepare('INSERT INTO units (name) VALUES (?)')
  stmt.run(unit.name)
}

export function updateUnit(unit) {
  const stmt = db.prepare('UPDATE units SET name = ? WHERE id = ?')
  stmt.run(unit.name, unit.id)
}

export function deleteUnit(unit) {
  const stmt = db.prepare('DELETE FROM units WHERE id = ?')
  stmt.run(unit.id)
}
