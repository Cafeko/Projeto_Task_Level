# Planejamento - Task Level (Gerenciador de Tarefas Personalizável)

## Visão Geral
Aplicação desktop local (single-user) para gerenciamento de tarefas altamente personalizável, com projetos, tipos de tarefa dinâmicos, atributos flexíveis, fases e referências entre tarefas.

## Stack Tecnológica
- **Backend**: Python 3.11+ + SQLite (arquivo único, zero config)
- **Frontend**: **PyQt6** (GUI desktop nativa, widgets ricos)
- **Persistência**: SQLite com schema relacional normalizado
- **Validação**: **Dataclasses + validação manual** (zero dependência, controle total)
- **Migrações**: **SQL manual versionado** (scripts `V{N}__descricao.sql` em `src/data/migrations/`)

---

## Modelo de Dados (MVP)

### 1. Projects
```sql
projects (id, name, description, created_at, updated_at)
```

### 2. Task Types (por projeto)
```sql
task_types (id, project_id, name, description, color, icon, created_at)
```

### 3. Attributes Definition (metadados dos atributos por tipo)
```sql
attribute_definitions (
  id, task_type_id, name, label, 
  type: 'text' | 'number' | 'boolean' | 'reference_task' | 'reference_attribute',
  required: boolean, default_value, 
  reference_config: JSON, -- para tipos de referência: {target_type_id?, attribute_name?}
  order, created_at
)
```

### 4. Phases (por tipo de tarefa)
```sql
phases (id, task_type_id, name, description, color, order, is_initial, is_final, created_at)
```

### 5. Tasks (instâncias)
```sql
tasks (
  id, project_id, task_type_id, phase_id, 
  title, description, 
  created_at, updated_at, completed_at
)
```

### 6. Task Attributes (valores dinâmicos)
```sql
task_attributes (
  id, task_id, attribute_definition_id, 
  value_text, value_number, value_boolean, 
  value_reference_task_id, value_reference_attribute_id,
  created_at, updated_at
)
```

---

## Regras de Negócio

### Referências
- **reference_task**: Aponta para outra task (task_id). Útil para dependências, bloqueios, relacionamentos.
- **reference_attribute**: Aponta para atributo específico de outra task (task_id + attribute_definition_id). Útil para valores computados, espelhamento.

### Fases
- Cada task_type tem suas fases ordenadas
- Task inicia na fase `is_initial`
- Transição manual entre fases (condições futuramente)

### Validação
- Atributos `required` devem ter valor ao mover para fase final
- Referências devem apontar para tasks existentes
- Tipo do valor deve coincidir com `attribute_definition.type`

---

## Arquitetura da Aplicação

```
task_level/
├── src/
│   ├── domain/           # Entidades, value objects, regras de negócio
│   │   ├── models.py     # Dataclasses/Pydantic models
│   │   ├── enums.py      # AttributeType, PhaseStatus, etc.
│   │   └── exceptions.py
│   ├── data/             # Camada de persistência
│   │   ├── database.py   # Conexão SQLite, migrations
│   │   ├── repositories/ # ProjectRepo, TaskRepo, TaskTypeRepo, etc.
│   │   └── migrations/   # SQL de schema versionado
│   ├── services/         # Casos de uso / application services
│   │   ├── project_service.py
│   │   ├── task_type_service.py
│   │   ├── task_service.py
│   │   └── attribute_service.py
│   ├── presentation/     # GUI (PyQt6)
│   │   ├── main_window.py
│   │   ├── widgets/      # Componentes reutilizáveis (DynamicForm, PhaseBadge, ReferencePicker)
│   │   ├── dialogs/      # Modais para criar/editar (ProjectDialog, TaskTypeDialog, TaskDialog)
│   │   └── views/        # Páginas/telas principais (ProjectListView, ProjectView, TaskTypeManagerView)
│   └── main.py           # Entry point
├── tests/
├── pyproject.toml
└── README.md
```

---

## Telas Principais (MVP)

1. **Dashboard/Lista de Projetos** - Criar, abrir, excluir projetos
2. **Visão do Projeto** - Kanban por fase OU Todos (Recentes misturado
   por criado/modificado, ou separado por tipo e ordenado pela fase)
3. **Gerenciar Tipos de Tarefa** - CRUD de task_types + attribute_definitions + phases
4. **Criar/Editar Task** - Formulário dinâmico baseado nos attribute_definitions
5. **Detalhes da Task** - Ver todos atributos, mudar fase, ver referências
6. **Configurações** - Backup/export, preferências

---

## Fluxos Principais

### Criar Projeto + Tipo + Atributos + Fases
1. Usuário cria projeto
2. Define task_types (ex: "Bug", "Feature", "Task")
3. Para cada tipo: define atributos (texto, número, bool, ref-task, ref-attr)
4. Para cada tipo: define fases (ex: "Backlog" → "Em Progresso" → "Review" → "Pronto")

### Criar Task
1. Seleciona tipo → formulário renderiza campos baseados nas attribute_definitions
2. Preenche valores (inclui dropdowns para referências)
3. Salva → task criada na fase inicial

### Referências
- **ref-task**: Combo com busca de tasks do mesmo projeto (ou filtrado por tipo)
- **ref-attr**: Seleciona task + atributo compatível (mesmo tipo ou tipo permitido)

---

## Próximos Passos (Pós-MVP)
- Condições de transição entre fases (expressões booleanas sobre atributos)
  → terreno pronto: `TaskService.neighbors` (UI), `TaskService.check_move`
  + `_check_conditions` (validacao), botoes Voltar/Avancar no Kanban e no
  dialogo da task; regra atual = uma fase por vez.
- Automações (quando X → faça Y)
- Views salvas / filtros avançados
- Import/Export (JSON, CSV)
- Plugins / extensibilidade

---

## Decisões Confirmadas ✅
- [x] GUI framework: **PySide6** (LGPL, API idêntica ao PyQt6)
- [x] Validação: **Dataclasses + validação manual**
- [x] Migrações: **SQL manual versionado** (`src/data/migrations/V{N}__desc.sql`)
- [x] Package structure: **`src/task_level/`** (package Python adequado)
- [x] Dependências: **`pyproject.toml` + `uv`** (rápido, lockfile, moderno)
- [x] Repositórios: **Um por entidade + `UnitOfWork` simples** (transação única)
- [x] Datas: **`TEXT` ISO8601** (`YYYY-MM-DDTHH:MM:SSZ` UTC)
- [x] PKs: **`INTEGER PRIMARY KEY AUTOINCREMENT`** (nativo, performático)
- [x] FKs: **`PRAGMA foreign_keys=ON`** + `ON DELETE SET NULL` (padrão), `CASCADE` onde semântico
- [x] Referências circulares: **Bloquear no service** (DFS detecta ciclos ao salvar ref-task/ref-attr)
- [x] Dev workflow: **`uv run` + reload manual** (simples, sem ferramenta extra)

---

## Resumo Final das Decisões Técnicas

| Item | Decisão | Justificativa |
|------|---------|---------------|
| GUI | PySide6 | LGPL, oficial Qt, mesmo código PyQt6 |
| Validação | Dataclasses + manual | Zero dep, controle total, simples |
| Migrações | SQL versionado manual | Zero dep, controle total, SQLite local |
| Package | `src/task_level/` | Import limpo, pytest encontra, empacotável |
| Deps | `pyproject.toml` + `uv` | Velocidade, lockfile, padrão moderno |
| Repos | Repo/entidade + UnitOfWork | Transação atômica, testável, desacoplado |
| Datas | TEXT ISO8601 UTC | Legível, ordenável, timezone-safe |
| PKs | INTEGER AUTOINCREMENT | Nativo SQLite, 8 bytes, rápido |
| FKs | ON + SET NULL padrão | Integridade, evita orphans acidentais |
| Ciclos | Validação no service | Regra de negócio, não só DB |
| Dev | `uv run` + manual | Simples, zero config extra |