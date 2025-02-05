import db from '../db.js'

export function getIngredients() {
  const query = `
    SELECT fi.*, u.id as unit_id, GROUP_CONCAT(t.id, ',') as tag_id
    FROM ingredients fi
    LEFT JOIN units u ON fi.unit_id = u.id
    LEFT JOIN ingredients_tags fit ON fi.id = fit.ingredient_id
    LEFT JOIN tags t ON fit.tag_id = t.id
    GROUP BY fi.id
  `
  const stmt = db.prepare(query)
  return stmt.all()
}

export function addIngredient(item) {
  const stmt = db.prepare(`
    INSERT INTO ingredients (name, comment, unit_id, quantity_per_package, calories_per_100g, carbohydrates_per_100g, sugars_per_100g, fat_per_100g, protein_per_100g, fiber_per_100g)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)
  const info = stmt.run(item.name, item.comment, item.unit_id, item.quantity_per_package, item.calories, item.carbohydrates, item.sugars, item.fat, item.protein, item.fiber)

  if (item.tags && item.tags.length > 0) {
    const tagStmt = db.prepare('INSERT INTO ingredients_tags (ingredient_id, tag_id) VALUES (?, ?)')
    for (const tagId of item.tags) {
      tagStmt.run(info.lastInsertRowid, tagId)
    }
  }
}

export function updateIngredient(item) {
  const stmt = db.prepare(`
    UPDATE ingredients
    SET name = ?, comment = ?, unit_id = ?, quantity_per_package = ?, calories_per_100g = ?, carbohydrates_per_100g = ?, sugars_per_100g = ?, fat_per_100g = ?, protein_per_100g, fiber_per_100g = ?
    WHERE id = ?
  `)
  stmt.run(item.name, item.comment, item.unit_id, item.quantity_per_package, item.calories, item.carbohydrates, item.sugars, item.fat, item.protein, item.fiber)

  const deleteTagsStmt = db.prepare('DELETE FROM ingredients_tags WHERE ingredient_id = ?')
  deleteTagsStmt.run(item.id)

  if (item.tags && item.tags.length > 0) {
    const tagStmt = db.prepare('INSERT INTO ingredients_tags (ingredient_id, tag_id) VALUES (?, ?)')
    for (const tagId of item.tags) {
      tagStmt.run(item.id, tagId)
    }
  }
}

export function deleteIngredient(id) {
  const deleteTagsStmt = db.prepare('DELETE FROM ingredients_tags WHERE ingredient_id = ?')
  deleteTagsStmt.run(id)

  const stmt = db.prepare('DELETE FROM ingredients WHERE id = ?')
  stmt.run(id)
}
