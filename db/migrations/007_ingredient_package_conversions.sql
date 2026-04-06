CREATE TABLE IF NOT EXISTS package_types (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_package_types_name_unique
  ON package_types(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS ingredient_package_conversions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  package_type_id INTEGER NOT NULL,
  grams_per_package REAL NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  samples_count INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (product_id, package_type_id),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  FOREIGN KEY (package_type_id) REFERENCES package_types(id) ON DELETE CASCADE,
  CHECK (grams_per_package > 0),
  CHECK (samples_count > 0)
);

CREATE INDEX IF NOT EXISTS idx_ing_pkg_conv_product_id
  ON ingredient_package_conversions(product_id);

CREATE INDEX IF NOT EXISTS idx_ing_pkg_conv_package_type_id
  ON ingredient_package_conversions(package_type_id);

ALTER TABLE recipe_ingredients
  ADD COLUMN ingredient_package_conversion_id INTEGER
  REFERENCES ingredient_package_conversions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ing_pkg_conv_id
  ON recipe_ingredients(ingredient_package_conversion_id);

INSERT OR IGNORE INTO package_types(name, normalized_name)
SELECT DISTINCT
  u.name,
  lower(trim(u.name))
FROM units u
WHERE trim(COALESCE(u.name, '')) <> ''
  AND COALESCE(u.unit_type, 'custom') IN ('custom', 'count');

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
  'migration:derived-from-recipes' AS source,
  COUNT(*) AS samples_count
FROM recipe_ingredients ri
INNER JOIN units u ON u.id = ri.unit_id
INNER JOIN package_types pt ON pt.normalized_name = lower(trim(u.name))
WHERE ri.quantity IS NOT NULL
  AND ri.quantity > 0
  AND ri.grams IS NOT NULL
  AND ri.grams > 0
  AND COALESCE(u.unit_type, 'custom') IN ('custom', 'count')
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
  AND unit_id IS NOT NULL;

DROP VIEW IF EXISTS recipe_nutrition_summary;

CREATE VIEW recipe_nutrition_summary AS
WITH ingredient_mass AS (
  SELECT
    ri.id AS recipe_ingredient_id,
    ri.recipe_id,
    ri.product_id,
    COALESCE(
      ri.grams,
      CASE
        WHEN ri.quantity IS NOT NULL AND ipc.grams_per_package IS NOT NULL
          THEN ri.quantity * ipc.grams_per_package
        ELSE NULL
      END,
      CASE
        WHEN ri.quantity IS NOT NULL AND ri.package_id IS NOT NULL AND pkg.grams IS NOT NULL
          THEN ri.quantity * pkg.grams
        ELSE NULL
      END,
      CASE
        WHEN ri.quantity IS NOT NULL AND u.to_grams_factor IS NOT NULL
          THEN ri.quantity * u.to_grams_factor
        ELSE NULL
      END
    ) AS effective_grams
  FROM recipe_ingredients ri
  LEFT JOIN ingredient_package_conversions ipc ON ipc.id = ri.ingredient_package_conversion_id
  LEFT JOIN packages pkg ON pkg.id = ri.package_id
  LEFT JOIN units u ON u.id = ri.unit_id
)
SELECT
  r.id AS recipe_id,
  r.name AS recipe_name,
  COUNT(im.recipe_ingredient_id) AS ingredients_count,
  ROUND(SUM(COALESCE(im.effective_grams, 0)), 2) AS total_grams,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.calories_per_100g, 0) / 100.0), 2) AS calories,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.carbohydrates_per_100g, 0) / 100.0), 2) AS carbohydrates,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.sugars_per_100g, 0) / 100.0), 2) AS sugars,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.fat_per_100g, 0) / 100.0), 2) AS fat,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.protein_per_100g, 0) / 100.0), 2) AS protein,
  ROUND(SUM(COALESCE(im.effective_grams, 0) * COALESCE(p.fiber_per_100g, 0) / 100.0), 2) AS fiber,
  SUM(
    CASE
      WHEN im.effective_grams IS NOT NULL
           AND (
             p.calories_per_100g IS NULL
             OR p.carbohydrates_per_100g IS NULL
             OR p.fat_per_100g IS NULL
             OR p.protein_per_100g IS NULL
           )
        THEN 1
      ELSE 0
    END
  ) AS missing_nutrition_items,
  ROUND(
    CASE
      WHEN SUM(COALESCE(im.effective_grams, 0)) > 0
        THEN (
          100.0 * SUM(
            CASE
              WHEN p.calories_per_100g IS NOT NULL
                THEN COALESCE(im.effective_grams, 0)
              ELSE 0
            END
          )
        ) / SUM(COALESCE(im.effective_grams, 0))
      ELSE 0
    END,
    2
  ) AS coverage_percent
FROM recipes r
LEFT JOIN ingredient_mass im ON im.recipe_id = r.id
LEFT JOIN products p ON p.id = im.product_id
GROUP BY r.id;
