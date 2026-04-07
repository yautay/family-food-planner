INSERT INTO meal_plan_day_slot_meals(day_slot_id, recipe_id, servings, note, meal_order)
SELECT
  s.id,
  m.recipe_id,
  m.servings,
  m.note,
  m.meal_order
FROM meal_plan_day_slots s
INNER JOIN day_plan_meals m ON m.day_plan_id = s.day_plan_id
WHERE s.day_plan_id IS NOT NULL;

UPDATE meal_plan_day_slots
SET day_plan_id = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE day_plan_id IS NOT NULL;
