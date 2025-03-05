import models from '../models/index.js';

async function getTags() {
  return await models.tag.findAll();
}

async function addTag(tag) {
  return models.tag.create(tag);
}

async function updateTag(tag) {
  return await models.tag.update(tag, {
    where: { id: tag.id }
  });
}

async function deleteTag(id) {
  return await models.tag.destroy({
    where: { id }
  });
}

export default {
  getTags,
  addTag,
  updateTag,
  deleteTag,
}
