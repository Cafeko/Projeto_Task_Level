-- V1: schema inicial do MVP (Parte 3).
-- PKs INTEGER AUTOINCREMENT, datas TEXT ISO8601 UTC, FKs com PRAGMA foreign_keys=ON.

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_types (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '#888888',
  icon TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_types_project ON task_types (project_id);

CREATE TABLE IF NOT EXISTS attribute_definitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_type_id INTEGER NOT NULL REFERENCES task_types (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  label TEXT NOT NULL,
  type TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 0,
  default_value TEXT NOT NULL DEFAULT '',
  reference_config TEXT,
  "order" INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (task_type_id, name)
);
CREATE INDEX IF NOT EXISTS idx_attr_defs_type ON attribute_definitions (task_type_id);

CREATE TABLE IF NOT EXISTS phases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_type_id INTEGER NOT NULL REFERENCES task_types (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '#888888',
  "order" INTEGER NOT NULL DEFAULT 0,
  is_initial INTEGER NOT NULL DEFAULT 0,
  is_final INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phases_type ON phases (task_type_id);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  task_type_id INTEGER NOT NULL REFERENCES task_types (id) ON DELETE CASCADE,
  phase_id INTEGER REFERENCES phases (id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks (task_type_id);
CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks (phase_id);

CREATE TABLE IF NOT EXISTS task_attributes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
  attribute_definition_id INTEGER NOT NULL REFERENCES attribute_definitions (id) ON DELETE CASCADE,
  value_text TEXT,
  value_number REAL,
  value_boolean INTEGER,
  value_reference_task_id INTEGER REFERENCES tasks (id) ON DELETE SET NULL,
  value_reference_attribute_id INTEGER REFERENCES task_attributes (id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (task_id, attribute_definition_id)
);
CREATE INDEX IF NOT EXISTS idx_task_attrs_task ON task_attributes (task_id);
CREATE INDEX IF NOT EXISTS idx_task_attrs_def ON task_attributes (attribute_definition_id);
