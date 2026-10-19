# Независимый аудит допуска Air-Gap (Волна 2: 04-REVIEW-AIRGAP.md)

Дата: 2026-10-11
Аудитор: субагент `reader` (Air-Gap Security Auditor)
Статус: **ОДОБРЕНО (Утечек не обнаружено)**

---

## 1. Проверенные рубежи обороны

1. **Входной шлюз `git_chain_workspaces` (`src/security/airgap.py`)**:
   - Первый проход: строгая фильтрация через `is_git_chain_eligible` (допущены исключительно `public` и `internal`).
   - Второй проход: проверка пересечений (`_workspace_overlaps`) по `path`, `remote` и `ssh_alias` с исключёнными пространствами (`restricted_nda` и неизвестные). При обнаружении любого пересечения пространство отбраковывается по принципу fail-closed.
   - При `persona is None` либо любых ошибках валидации возвращается `unresolved=True`, `eligible=()`.

2. **Защитные guard-блоки в `SshGitProvider` (`src/connectors/git/provider.py`)**:
   - Методы `fetch_remote` и `get_commits_since` начинают работу с обязательной проверки `is_git_chain_eligible(workspace)`. При нарушении выбрасывается `AirGapViolationError` до создания любых процессов `git` в ОС.
   - Метод `list_repositories` возвращает репозитории строго из `split.eligible`.

3. **Изоляция LLM-контекста в `GitProgressEvaluator` (`src/brain/git_evaluator.py`)**:
   - Метод `evaluate` итерируется строго по `split.eligible`.
   - Санитизация `sanitize_git_commits_for_llm` маскирует сообщения маркером `NDA_GIT_MASK_MARKER` (защита в глубину).
   - Генерация сводки (`_generate_summary` -> вызов модели `generate_content` / `key_rotator`) физически недостижима для исключённых пространств.

4. **Контур формирования карточек HITL и публикации в Notion (`src/brain/git_evaluator.py`)**:
   - `propose_card` требует валидный `entry.report` и `notion_ready=True`, которые генерируются только внутри `evaluate` для допущенных пространств.
   - Исключённые пространства помечаются `nda_excluded=True` (вывод в Telegram строки `🔒 NDA: исключено из оценки`) без создания карточек подтверждения.

---

## 2. Анализ крайних случаев

- **Неизвестный или отсутствующий clearance**: `clearance=None`, пустые строки, регистровые варианты (`PUBLIC`, `Restricted_NDA`) и любые нестандартные статусы (`secret`, `confidential`, `partner`) дают `False` в `is_git_chain_eligible` (fail-closed).
- **Пустые поля и невалидные структуры**:
  - Отсутствие пути, отсутствие каталога или каталога `.git` приводит к статусам `NO_DIR`/`NOT_GIT`, `report=None` и `notion_ready=False` без обращения к git и LLM.
  - Отсутствие `remote` и `ssh_alias` выставляет статус `NO_REMOTE` и прерывает обработку.
- **Пересечения каталогов**: `_paths_overlap` нормализует пути (`os.path.normpath`, `casefold`) и проверяет префиксы компонентов (`PurePath.parts`), надёжно выявляя идентичные каталоги и вложенные поддиректории.
- **Пересечения алиасов и remote**: `_norm_alias` и `_norm_remote` отсекают суффиксы `.git`, слэши и регистр, блокируя алиасинг идентичных репозиториев.

---

## 3. Итоговый вердикт

Утечек данных и путей обхода шлюза Air-Gap для пространств со статусом `RESTRICTED_NDA` либо неизвестным/отсутствующим `clearance` **не обнаружено**. Доступ к методам git, вызовам внешних LLM и созданию карточек Notion надёжно заблокирован на нескольких независимых рубежах обороны.
