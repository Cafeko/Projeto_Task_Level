# Task Level
Gerenciador de tarefas personalizavel (local, single-user, PySide6 + SQLite).

## Requisitos
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (gerenciador de pacotes)

## Uso
```powershell
uv sync --group dev   # instala dependencias (+ dev)
uv run task-level                 # abre a GUI (banco em ~/.task_level/task_level.db)
uv run task-level --seed          # abre com projeto demo
uv run task-level --db ./meu.db  # banco alternativo
python main.py                    # duplo-clique / de qualquer pasta (usa o .venv)
uv run pytest                     # testes
uv run ruff check src tests       # lint
```

## Dados e backup
- Banco padrao: `~/.task_level/task_level.db`
- Backups automaticos via menu **Arquivo > Fazer backup agora**
  (em `~/.task_level/backups/`)
- Exporte um projeto em JSON via **Arquivo > Exportar projeto (JSON)...**

## Conceitos
- **Projeto** tem varios **tipos de tarefa**; cada tipo define seus
  **atributos** (texto, numero, dinheiro, data, arquivo, selecao,
  booleano, referencia a task, referencia a atributo) e suas **fases**
  (ex: Novo > Em andamento > Concluido).
- Todas as tasks do mesmo tipo tem os mesmos atributos.
- Atributos obrigatorios bloqueiam a ida para a fase final.
- Referencias entre tasks nao podem formar ciclos.
- Referencias (`task` e `atributo`) valem entre tipos diferentes, desde que
  no mesmo projeto. Um atributo `reference_attribute` pode fixar o atributo
  alvo na edicao do tipo — ai na task basta escolher a task.
- Visao **Todos** do projeto tem 2 modos: **Por tipo e fase**
  (separadas por tipo, ordenadas pela ordem da fase) e **Recentes**
  (tudo misturado, criadas/modificadas no topo).
