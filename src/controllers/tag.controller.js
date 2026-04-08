import { literal } from 'sequelize'
import models from '../models/index.js'

async function getTags() {
  return models.tag.findAll({
    attributes: ['id', 'name'],
    order: [[literal('name COLLATE NOCASE'), 'ASC']],
    raw: true,
  })
}

async function addTag(tag) {
  const name = typeof tag?.name === 'string' ? tag.name.trim() : ''
  if (!name) {
    throw new Error('Tag name is required')
  }

  const created = await models.tag.create({ name })
  return {
    id: created.id,
    name: created.name,
  }
}

async function updateTag(tag) {
  const tagId = Number(tag?.id)
  if (!Number.isInteger(tagId) || tagId <= 0) {
    throw new Error('Tag id is invalid')
  }

  const existing = await models.tag.findByPk(tagId, { attributes: ['id'] })
  if (!existing) {
    return 0
  }

  const name = typeof tag?.name === 'string' ? tag.name.trim() : ''
  if (!name) {
    throw new Error('Tag name is required')
  }

  const [changes] = await models.tag.update({ name }, { where: { id: tagId } })
  return changes
}

async function deleteTag(id) {
  const tagId = Number(id)
  if (!Number.isInteger(tagId) || tagId <= 0) {
    throw new Error('Tag id is invalid')
  }

  return models.tag.destroy({ where: { id: tagId } })
}

export default {
  getTags,
  addTag,
  updateTag,
  deleteTag,
}
