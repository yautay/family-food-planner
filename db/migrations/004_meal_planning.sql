CREATE TABLE IF NOT EXISTS meal_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CHECK (date(start_date) <= date(end_date))
);

CREATE INDEX IF NOT EXISTS idx_meal_plans_owner_user_id
  ON meal_plans(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_meal_plans_date_range
  ON meal_plans(start_date, end_date);

CREATE TABLE IF NOT EXISTS meal_plan_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  meal_plan_id INTEGER NOT NULL,
  planned_date TEXT NOT NULL,
  meal_slot TEXT NOT NULL,
  recipe_id INTEGER,
  custom_name TEXT,
  servings REAL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE SET NULL,
  CHECK (meal_slot IN ('breakfast', 'lunch', 'dinner', 'snack')),
  CHECK (recipe_id IS NOT NULL OR (custom_name IS NOT NULL AND length(trim(custom_name)) > 0)),
  UNIQUE (meal_plan_id, planned_date, meal_slot)
);

CREATE INDEX IF NOT EXISTS idx_meal_plan_entries_meal_plan_id
  ON meal_plan_entries(meal_plan_id);

CREATE INDEX IF NOT EXISTS idx_meal_plan_entries_recipe_id
  ON meal_plan_entries(recipe_id);

CREATE INDEX IF NOT EXISTS idx_meal_plan_entries_planned_date
  ON meal_plan_entries(planned_date);

CREATE TABLE IF NOT EXISTS shopping_lists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_user_id INTEGER NOT NULL,
  meal_plan_id INTEGER,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE SET NULL,
  CHECK (status IN ('open', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_shopping_lists_owner_user_id
  ON shopping_lists(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_shopping_lists_status
  ON shopping_lists(status);

CREATE TABLE IF NOT EXISTS shopping_list_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  shopping_list_id INTEGER NOT NULL,
  product_id INTEGER,
  custom_name TEXT,
  quantity REAL,
  unit_id INTEGER,
  is_checked INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (shopping_list_id) REFERENCES shopping_lists(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
  FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL,
  CHECK (is_checked IN (0, 1)),
  CHECK (product_id IS NOT NULL OR (custom_name IS NOT NULL AND length(trim(custom_name)) > 0))
);

CREATE INDEX IF NOT EXISTS idx_shopping_list_items_list_id
  ON shopping_list_items(shopping_list_id);

CREATE INDEX IF NOT EXISTS idx_shopping_list_items_product_id
  ON shopping_list_items(product_id);

CREATE INDEX IF NOT EXISTS idx_shopping_list_items_is_checked
  ON shopping_list_items(is_checked);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id
  ON audit_logs(actor_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action
  ON audit_logs(action);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
  ON audit_logs(created_at);
