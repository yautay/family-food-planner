import catalogDb from '../db/catalog.js'

async function getTags() {
  return catalogDb.prepare('SELECT id, name FROM tags ORDER BY name COLLATE NOCASE ASC').all()
}

async function addTag(tag) {
  const name = typeof tag?.name === 'string' ? tag.name.trim() : ''
  if (!name) {
    throw new Error('Tag name is required')
  }

  const result = catalogDb.prepare('INSERT INTO tags(name) VALUES (?)').run(name)
  return catalogDb
    .prepare('SELECT id, name FROM tags WHERE id = ?')
    .get(Number(result.lastInsertRowid))
}

async function updateTag(tag) {
  const tagId = Number(tag?.id)
  if (!Number.isInteger(tagId) || tagId <= 0) {
    throw new Error('Tag id is invalid')
  }

  const existing = catalogDb.prepare('SELECT id FROM tags WHERE id = ?').get(tagId)
  if (!existing) {
    return 0
  }

  const name = typeof tag?.name === 'string' ? tag.name.trim() : ''
  if (!name) {
    throw new Error('Tag name is required')
  }

  return catalogDb.prepare('UPDATE tags SET name = ? WHERE id = ?').run(name, tagId).changes
}

async function deleteTag(id) {
  const tagId = Number(id)
  if (!Number.isInteger(tagId) || tagId <= 0) {
    throw new Error('Tag id is invalid')
  }

  return catalogDb.prepare('DELETE FROM tags WHERE id = ?').run(tagId).changes
}

export default {
  getTags,
  addTag,
  updateTag,
  deleteTag,
}
