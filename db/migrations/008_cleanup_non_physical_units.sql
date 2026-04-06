INSERT OR IGNORE INTO package_types(name, normalized_name)
SELECT DISTINCT
  u.name,
  lower(trim(u.name))
FROM units u
WHERE COALESCE(u.unit_type, 'custom') NOT IN ('mass', 'volume')
  AND trim(COALESCE(u.name, '')) <> '';

INSERT OR IGNORE INTO units(name, symbol, unit_type, to_grams_factor, to_ml_factor)
VALUES ('g', 'g', 'mass', 1.0, NULL);

CREATE TABLE IF NOT EXISTS ingredients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT '',
  unit_id INTEGER NOT NULL,
  FOREIGN KEY (unit_id) REFERENCES units(id)
);

INSERT INTO ingredient_package_conversions(
  product_id,
  package_type_id,
  grams_per_package,
  source,
  samples_count
)
SELECT
  ri.product_id,
  pt.id,
  ROUND(AVG(ri.grams / ri.quantity), 2) AS grams_per_package,
  'migration:cleanup-units',
  COUNT(*) AS samples_count
FROM recipe_ingredients ri
INNER JOIN units u ON u.id = ri.unit_id
INNER JOIN package_types pt ON pt.normalized_name = lower(trim(u.name))
WHERE COALESCE(u.unit_type, 'custom') NOT IN ('mass', 'volume')
  AND ri.quantity IS NOT NULL
  AND ri.quantity > 0
  AND ri.grams IS NOT NULL
  AND ri.grams > 0
GROUP BY ri.product_id, pt.id
ON CONFLICT(product_id, package_type_id)
DO UPDATE SET
  grams_per_package = excluded.grams_per_package,
  source = excluded.source,
  samples_count = excluded.samples_count,
  updated_at = CURRENT_TIMESTAMP;

UPDATE recipe_ingredients
SET ingredient_package_conversion_id = (
  SELECT ipc.id
  FROM units u
  INNER JOIN package_types pt ON pt.normalized_name = lower(trim(u.name))
  INNER JOIN ingredient_package_conversions ipc
    ON ipc.product_id = recipe_ingredients.product_id
   AND ipc.package_type_id = pt.id
  WHERE u.id = recipe_ingredients.unit_id
  LIMIT 1
)
WHERE ingredient_package_conversion_id IS NULL
  AND unit_id IN (
    SELECT id
    FROM units
    WHERE COALESCE(unit_type, 'custom') NOT IN ('mass', 'volume')
  );

UPDATE recipe_ingredients
SET unit_id = NULL
WHERE unit_id IN (
  SELECT id
  FROM units
  WHERE COALESCE(unit_type, 'custom') NOT IN ('mass', 'volume')
);

UPDATE ingredients
SET unit_id = (
  SELECT id
  FROM units
  WHERE lower(name) = 'g'
  LIMIT 1
)
WHERE unit_id IN (
  SELECT id
  FROM units
  WHERE COALESCE(unit_type, 'custom') NOT IN ('mass', 'volume')
);

UPDATE packages
SET unit_id = (
  SELECT id
  FROM units
  WHERE lower(name) = 'g'
  LIMIT 1
)
WHERE unit_id IN (
  SELECT id
  FROM units
  WHERE COALESCE(unit_type, 'custom') NOT IN ('mass', 'volume')
);

DELETE FROM units
WHERE COALESCE(unit_type, 'custom') NOT IN ('mass', 'volume');
