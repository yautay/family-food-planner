import db from '../db.js'

export function getTags() {
  return db.prepare('SELECT * FROM tags').all()
}

export function addTag(tag) {
  const stmt = db.prepare('INSERT INTO tags (name) VALUES (?)')
  stmt.run(tag.name)
}

export function updateTag(tag) {
  const stmt = db.prepare('UPDATE tags SET name = ? WHERE id = ?')
  stmt.run(tag.name, tag.id)
}

export function deleteTag(id) {
  const stmt = db.prepare('DELETE FROM tags WHERE id = ?')
  stmt.run(id)
}
