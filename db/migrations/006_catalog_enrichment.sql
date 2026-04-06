ALTER TABLE units ADD COLUMN symbol TEXT;
ALTER TABLE units ADD COLUMN unit_type TEXT NOT NULL DEFAULT 'custom';
ALTER TABLE units ADD COLUMN to_grams_factor REAL;
ALTER TABLE units ADD COLUMN to_ml_factor REAL;

ALTER TABLE products ADD COLUMN comment TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN quantity_per_package REAL;
ALTER TABLE products ADD COLUMN calories_per_100g REAL;
ALTER TABLE products ADD COLUMN carbohydrates_per_100g REAL;
ALTER TABLE products ADD COLUMN sugars_per_100g REAL;
ALTER TABLE products ADD COLUMN fat_per_100g REAL;
ALTER TABLE products ADD COLUMN protein_per_100g REAL;
ALTER TABLE products ADD COLUMN fiber_per_100g REAL;
ALTER TABLE products ADD COLUMN nutrition_source TEXT;
ALTER TABLE products ADD COLUMN nutrition_updated_at TEXT;

ALTER TABLE recipe_ingredients ADD COLUMN package_id INTEGER;

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_unique
  ON tags (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS product_tags (
  product_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id, tag_id),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_product_tags_tag_id
  ON product_tags(tag_id);

CREATE TABLE IF NOT EXISTS packages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  unit_id INTEGER NOT NULL,
  quantity REAL,
  grams REAL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_packages_unit_id
  ON packages(unit_id);

CREATE TABLE IF NOT EXISTS product_packages (
  product_id INTEGER NOT NULL,
  package_id INTEGER NOT NULL,
  grams REAL,
  is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id, package_id),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
  CHECK (is_default IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_product_packages_package_id
  ON product_packages(package_id);

INSERT OR IGNORE INTO units(name, symbol, unit_type, to_grams_factor, to_ml_factor)
VALUES
  ('mg', 'mg', 'mass', 0.001, NULL),
  ('g', 'g', 'mass', 1.0, NULL),
  ('dag', 'dag', 'mass', 10.0, NULL),
  ('kg', 'kg', 'mass', 1000.0, NULL),
  ('ml', 'ml', 'volume', NULL, 1.0),
  ('l', 'l', 'volume', NULL, 1000.0),
  ('szt', 'szt', 'count', NULL, NULL);

UPDATE units
SET
  symbol = COALESCE(symbol, 'mg'),
  unit_type = 'mass',
  to_grams_factor = COALESCE(to_grams_factor, 0.001)
WHERE lower(name) IN ('mg', 'miligram', 'miligramy');

UPDATE units
SET
  symbol = COALESCE(symbol, 'g'),
  unit_type = 'mass',
  to_grams_factor = COALESCE(to_grams_factor, 1.0)
WHERE lower(name) IN ('g', 'gram', 'gramy');

UPDATE units
SET
  symbol = COALESCE(symbol, 'dag'),
  unit_type = 'mass',
  to_grams_factor = COALESCE(to_grams_factor, 10.0)
WHERE lower(name) = 'dag';

UPDATE units
SET
  symbol = COALESCE(symbol, 'kg'),
  unit_type = 'mass',
  to_grams_factor = COALESCE(to_grams_factor, 1000.0)
WHERE lower(name) IN ('kg', 'kilogram', 'kilogramy');

UPDATE units
SET
  symbol = COALESCE(symbol, 'ml'),
  unit_type = 'volume',
  to_ml_factor = COALESCE(to_ml_factor, 1.0)
WHERE lower(name) IN ('ml', 'mililitr', 'mililitry');

UPDATE units
SET
  symbol = COALESCE(symbol, 'l'),
  unit_type = 'volume',
  to_ml_factor = COALESCE(to_ml_factor, 1000.0)
WHERE lower(name) IN ('l', 'litr', 'litr', 'litry');

UPDATE units
SET
  symbol = COALESCE(symbol, 'szt'),
  unit_type = 'count'
WHERE lower(name) IN ('szt', 'sztuka', 'porcja', 'kromka');

INSERT OR IGNORE INTO packages(name, normalized_name, unit_id, quantity, grams, note)
SELECT
  'Lyzeczka od herbaty',
  'lyzeczka od herbaty',
  u.id,
  5,
  5,
  'Domyslna miara kuchenna'
FROM units u
WHERE lower(u.name) = 'g';

INSERT OR IGNORE INTO packages(name, normalized_name, unit_id, quantity, grams, note)
SELECT
  'Lyzka stolowa',
  'lyzka stolowa',
  u.id,
  15,
  15,
  'Domyslna miara kuchenna'
FROM units u
WHERE lower(u.name) = 'g';

INSERT OR IGNORE INTO packages(name, normalized_name, unit_id, quantity, grams, note)
SELECT
  'Sloik 250',
  'sloik 250',
  u.id,
  250,
  250,
  'Typowe opakowanie 250 g'
FROM units u
WHERE lower(u.name) = 'g';

INSERT OR IGNORE INTO packages(name, normalized_name, unit_id, quantity, grams, note)
SELECT
  'Puszka 500',
  'puszka 500',
  u.id,
  500,
  500,
  'Typowe opakowanie 500 g'
FROM units u
WHERE lower(u.name) = 'g';

INSERT OR IGNORE INTO packages(name, normalized_name, unit_id, quantity, grams, note)
SELECT
  'Sloik 1000',
  'sloik 1000',
  u.id,
  1000,
  1000,
  'Typowe opakowanie 1000 g'
FROM units u
WHERE lower(u.name) = 'g';

CREATE VIEW IF NOT EXISTS recipe_nutrition_summary AS
WITH ingredient_mass AS (
  SELECT
    ri.id AS recipe_ingredient_id,
    ri.recipe_id,
    ri.product_id,
    CASE
      WHEN ri.grams IS NOT NULL THEN ri.grams
      WHEN ri.quantity IS NOT NULL AND ri.package_id IS NOT NULL AND pkg.grams IS NOT NULL
        THEN ri.quantity * pkg.grams
      WHEN ri.quantity IS NOT NULL AND u.to_grams_factor IS NOT NULL
        THEN ri.quantity * u.to_grams_factor
      ELSE NULL
    END AS effective_grams
  FROM recipe_ingredients ri
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
