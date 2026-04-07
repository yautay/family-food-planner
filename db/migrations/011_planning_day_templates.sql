ALTER TABLE meal_plans
ADD COLUMN portions_count INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS meal_plan_meal_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  meal_plan_id INTEGER NOT NULL,
  slot_name TEXT NOT NULL,
  slot_time TEXT,
  sort_order INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
  CHECK (length(trim(slot_name)) > 0),
  CHECK (slot_time IS NULL OR slot_time GLOB '[0-2][0-9]:[0-5][0-9]')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_plan_meal_slots_plan_order
  ON meal_plan_meal_slots(meal_plan_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_meal_plan_meal_slots_plan_id
  ON meal_plan_meal_slots(meal_plan_id);

CREATE TABLE IF NOT EXISTS day_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_day_plans_owner_user_id
  ON day_plans(owner_user_id);

CREATE TABLE IF NOT EXISTS day_plan_meals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_plan_id INTEGER NOT NULL,
  recipe_id INTEGER NOT NULL,
  servings REAL,
  note TEXT NOT NULL DEFAULT '',
  meal_order INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (day_plan_id) REFERENCES day_plans(id) ON DELETE CASCADE,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE RESTRICT,
  CHECK (servings IS NULL OR servings > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_day_plan_meals_order
  ON day_plan_meals(day_plan_id, meal_order);

CREATE INDEX IF NOT EXISTS idx_day_plan_meals_day_plan_id
  ON day_plan_meals(day_plan_id);

CREATE TABLE IF NOT EXISTS meal_plan_day_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  meal_plan_id INTEGER NOT NULL,
  planned_date TEXT NOT NULL,
  day_plan_id INTEGER,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
  FOREIGN KEY (day_plan_id) REFERENCES day_plans(id) ON DELETE SET NULL,
  UNIQUE (meal_plan_id, planned_date)
);

CREATE INDEX IF NOT EXISTS idx_meal_plan_day_slots_plan_id
  ON meal_plan_day_slots(meal_plan_id);

CREATE INDEX IF NOT EXISTS idx_meal_plan_day_slots_day_plan_id
  ON meal_plan_day_slots(day_plan_id);

CREATE TABLE IF NOT EXISTS meal_plan_day_slot_meals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_slot_id INTEGER NOT NULL,
  recipe_id INTEGER NOT NULL,
  servings REAL,
  note TEXT NOT NULL DEFAULT '',
  meal_order INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (day_slot_id) REFERENCES meal_plan_day_slots(id) ON DELETE CASCADE,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE RESTRICT,
  CHECK (servings IS NULL OR servings > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_plan_day_slot_meals_order
  ON meal_plan_day_slot_meals(day_slot_id, meal_order);

CREATE INDEX IF NOT EXISTS idx_meal_plan_day_slot_meals_slot_id
  ON meal_plan_day_slot_meals(day_slot_id);
