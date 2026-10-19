# Фаза 4, План 02: Аддитивные методы ConfirmationStore в assistant-shared — Итоги (SUMMARY)

**Дата завершения:** 2026-10-11
**Статус:** Выполнен успешно (ЗЕЛЁНЫЙ)
**Коммит в `/opt/assistant-shared`:** `d672937` — `feat(04-02): ConfirmationStore.reopen_action and find_confirmations (additive, no migration)`

---

## 1. Что сделано

1. **`ConfirmationStore.reopen_action(confirmation_id: str)`:**
   - Атомарный перевод карточки со статусом `confirmed` обратно в `pending` с очисткой полей `confirmed_by = NULL`, `confirmed_at = NULL`.
   - Защита от повторного выполнения: срабатывает строго при `status = 'confirmed'`. Для любых других статусов (`pending`, `rejected`, `expired`) и неизвестных идентификаторов возвращает `None`.
   - Срок действия карточки (`expires_at`) не продлевается.

2. **`ConfirmationStore.find_confirmations(action_type, target_id=None, statuses=None)`:**
   - Поиск записей с фильтром по `action_type`, точному ключу `target_id` и списку статусов `statuses`.
   - Автоматический вызов `cleanup_expired()` перед выборкой для актуализации просроченных записей.
   - Все параметры подставляются строго через плейсхолдеры SQL, защита от SQL-инъекций подтверждена тестом.
   - Сортировка результатов `ORDER BY created_at DESC`.

3. **Тестовое покрытие:**
   - В `/opt/assistant-shared/tests/test_hitl_shared.py` добавлено 9 новых тестов:
     - 4 теста для `reopen_action` (перевод в pending, отказ для других статусов, атомарность, возможность ровно одного последующего `resume_action`);
     - 5 тестов для `find_confirmations` (фильтрация и порядок, множественные статусы, очистка просроченных, защита от SQL-инъекций, пустые выборки).

4. **Контроль регрессии потребителя (`chat-app`):**
   - Тесты HITL потребителя `backend/tests/test_hitl_shared.py` и `backend/tests/test_web_hitl_guardrails.py` в `/opt/chat-app` проходят без изменений (14 passed).

---

## 2. Экспортируемые артефакты

- `/opt/assistant-shared/assistant_shared/hitl/store.py`:
  - `async def reopen_action(self, confirmation_id: str) -> Optional[PendingConfirmation]`
  - `async def find_confirmations(self, action_type: str, target_id: Optional[str] = None, statuses: Optional[Sequence[ConfirmationStatus]] = None) -> List[PendingConfirmation]`
- `/opt/assistant-shared/tests/test_hitl_shared.py`: 9 новых тестов

---

## 3. Schema Gate

- **Миграции не тронуты:** в `/opt/assistant-shared/assistant_shared/db/migrations` нет новых или измененных файлов.
- **Push схемы не требуется.**
- Изменения носят строго аддитивный характер на уровне Python-интерфейса библиотеки.

---

## 4. Результаты проверок

- `/opt/assistant-shared/tests`: **211 passed in 46.25s**
- `/opt/chat-app` тесты HITL: **14 passed in 4.03s**
- Pre-commit Security Shield в `/opt/assistant-shared`: ЗЕЛЁНЫЙ
