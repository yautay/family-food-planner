ALTER TABLE day_plan_meals
ADD COLUMN portions REAL NOT NULL DEFAULT 1;

UPDATE day_plan_meals
SET portions = CASE
  WHEN servings IS NOT NULL AND servings > 0 THEN servings
  ELSE 1
END;

UPDATE day_plan_meals
SET servings = NULL;

ALTER TABLE meal_plan_day_slot_meals
ADD COLUMN portions REAL NOT NULL DEFAULT 1;

UPDATE meal_plan_day_slot_meals
SET portions = CASE
  WHEN servings IS NOT NULL AND servings > 0 THEN servings
  ELSE 1
END;
