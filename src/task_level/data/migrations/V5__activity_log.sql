-- V5: log de mudancas das tasks (p/ Historico + desfazer/refazer).
CREATE TABLE IF NOT EXISTS activity_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  task_id INTEGER REFERENCES tasks (id) ON DELETE SET NULL,
  task_title TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  undo_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_project ON activity_log (project_id);
CREATE INDEX IF NOT EXISTS idx_activity_task ON activity_log (task_id);
