-- V2: opcoes do atributo tipo 'select' (JSON array, ex: ["Baixa","Media","Alta"]).
ALTER TABLE attribute_definitions ADD COLUMN options TEXT;
