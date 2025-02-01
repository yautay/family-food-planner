import db from '../db.js'

export function getUnits() {
  return db.prepare('SELECT * FROM units').all()
}

export function addUnit(unit) {
  const stmt = db.prepare('INSERT INTO units (name) VALUES (?)')
  stmt.run(unit.name)
}

export function updateUnit(unit) {
  console.log('updateUnit called with:', unit) // Log the unit object
  const stmt = db.prepare('UPDATE units SET name = ? WHERE id = ?')
  const result = stmt.run(unit.name, unit.id)
  console.log('SQL query executed:', stmt) // Log the SQL statement
  console.log('Result:', result) // Log the result of the query
}

export function deleteUnit(id) {
  const stmt = db.prepare('DELETE FROM units WHERE id = ?')
  stmt.run(id)
}
