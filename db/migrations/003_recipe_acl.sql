ALTER TABLE recipes ADD COLUMN owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE recipes ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0;
ALTER TABLE recipes ADD COLUMN is_editable INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_recipes_owner_user_id ON recipes(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_recipes_is_system ON recipes(is_system);

UPDATE recipes
SET is_system = CASE
  WHEN source_file IS NOT NULL AND source_file LIKE '%dieta%' THEN 1
  ELSE 0
END,
is_editable = CASE
  WHEN source_file IS NOT NULL AND source_file LIKE '%dieta%' THEN 0
  ELSE 1
END
WHERE is_system = 0 AND is_editable = 1;
