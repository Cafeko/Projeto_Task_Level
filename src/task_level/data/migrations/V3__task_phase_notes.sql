-- V3: observacao da task por fase (uma nota livre por (task, fase)).
CREATE TABLE IF NOT EXISTS task_phase_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
  phase_id INTEGER NOT NULL REFERENCES phases (id) ON DELETE CASCADE,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (task_id, phase_id)
);
CREATE INDEX IF NOT EXISTS idx_phase_notes_task ON task_phase_notes (task_id);
