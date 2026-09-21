-- V4: condicoes de entrada da fase (JSON array de {attr, op, value}).
ALTER TABLE phases ADD COLUMN enter_conditions TEXT;
