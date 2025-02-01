import db from '../db.js'

export function addFoodItem(item) {
  const stmt = db.prepare(`
    INSERT INTO food_items (name, comment, unit_id, quantity_per_package, calories_per_100g, carbohydrates_per_100g, sugars_per_100g, fat_per_100g, protein_per_100g, fiber_per_100g)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)
  stmt.run(item.name, item.comment, item.unit_id, item.quantity_per_package, item.calories, item.carbohydrates, item.sugars, item.fat, item.protein, item.fiber)
}
