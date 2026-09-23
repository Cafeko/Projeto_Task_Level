-- V6: numero sequencial da task por tipo (exibicao: #1, #2... por tipo).
-- Estavel: excluir nao renumera (nova task = MAX+1 do tipo).
ALTER TABLE tasks ADD COLUMN seq INTEGER;
UPDATE tasks SET seq = (
  SELECT COUNT(*) FROM tasks t2
  WHERE t2.task_type_id = tasks.task_type_id AND t2.id <= tasks.id
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_type_seq ON tasks (task_type_id, seq);
