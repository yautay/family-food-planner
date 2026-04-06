ALTER TABLE products ADD COLUMN default_package_type_id INTEGER REFERENCES package_types(id) ON DELETE SET NULL;
ALTER TABLE products ADD COLUMN unit_to_ml REAL;

CREATE INDEX IF NOT EXISTS idx_products_default_package_type_id
  ON products(default_package_type_id);

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
      END,
      CASE
        WHEN ri.quantity IS NOT NULL
             AND u.to_ml_factor IS NOT NULL
             AND p.unit_to_ml IS NOT NULL
             AND p.unit_to_ml > 0
             AND du.to_grams_factor IS NOT NULL
          THEN ri.quantity * u.to_ml_factor * du.to_grams_factor / p.unit_to_ml
        ELSE NULL
      END
    ) AS effective_grams
  FROM recipe_ingredients ri
  LEFT JOIN ingredient_package_conversions ipc ON ipc.id = ri.ingredient_package_conversion_id
  LEFT JOIN packages pkg ON pkg.id = ri.package_id
  LEFT JOIN units u ON u.id = ri.unit_id
  LEFT JOIN products p ON p.id = ri.product_id
  LEFT JOIN units du ON du.id = p.default_unit_id
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
