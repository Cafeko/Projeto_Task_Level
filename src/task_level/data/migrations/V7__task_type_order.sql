-- V7: ordem customizavel dos tipos de tarefa dentro do projeto.
-- Novos tipos entram no fim (MAX+1); existentes preservam a ordem de criacao.
ALTER TABLE task_types ADD COLUMN "order" INTEGER NOT NULL DEFAULT 0;
UPDATE task_types SET "order" = id;
CREATE INDEX IF NOT EXISTS idx_task_types_project_order ON task_types (project_id, "order");
