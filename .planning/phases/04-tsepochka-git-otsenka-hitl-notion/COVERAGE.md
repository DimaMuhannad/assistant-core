# API Coverage — Notion REST API (версия 2022-06-28)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

Фаза 4 использует Notion как приёмник журнала активности проектов: запись «Сводка YYYY-MM-DD» в базе активности, связанная со страницей проекта, и проверка «запись уже есть» перед созданием. Перечень охватывает поверхность публичного REST API Notion; решения приняты для цепочки «git → оценка → HITL → Notion» (D-06..D-10). Прочие интеграции с Notion (Second Brain: задачи, ожидания, журнал дня) существуют с v2.0 и в этой фазе не меняются.

| capability | decision | reason |
|---|---|---|
| pages.create (POST /pages) в базу активности | INTEGRATE | |
| databases.query (POST /databases/{id}/query) | INTEGRATE | |
| blocks.append (содержимое страницы) | INTEGRATE | |
| pages.retrieve (GET /pages/{id}) | OPT-OUT | не нужно: формат ID проверяется локально положительным регэкспом (D-06) |
| pages.update (PATCH /pages/{id}) | OPT-OUT | цепочка только добавляет записи; правка созданной записи вне фазы |
| pages.archive (удаление страницы) | OPT-OUT | разрушающее действие вне фазы; откат записи делает владелец в самом Notion |
| databases.retrieve (GET /databases/{id}) | OPT-OUT | сверка структуры базы по живому Notion после выдачи владельцем ID; до того проверяется только формат ID |
| databases.create / databases.update | OPT-OUT | базу активности создаёт владелец (D-07), автосоздание схемы вне фазы |
| blocks.retrieve / blocks.update / blocks.delete | OPT-OUT | содержимое созданных страниц цепочка не читает и не правит |
| search (POST /search) | OPT-OUT | поиск страниц проектов по имени отложен (мастер подключения Notion, Phase 8/9); связь берётся из персоны |
| users.me / users.list / users.retrieve | OPT-OUT | не нужно цепочке; проверка живости коннектора относится к Phase 9 |
| comments.create / comments.list | OPT-OUT | цепочка не комментирует страницы |
| file uploads | OPT-OUT | вложения в записи активности не нужны |
| webhooks и подписки на события | OPT-OUT | запись только по решению владельца в Telegram, входящие события Notion не нужны |
| data sources API (версия 2025-09-03) | OPT-OUT | миграция версии API вне фазы; версия 2022-06-28 работает, пока у базы один data source (docs/GIT_NOTION_SETUP.md) |

Пояснения к INTEGRATE:

- pages.create: основной путь записи после подтверждения владельцем (`log_project_activity`, свойства Name, Project, Date, Commits, Status; в `children` абзац сводки).
- databases.query: фильтр `and` из relation.contains по странице проекта и date.equals по дате периода; новый метод `find_project_activity` защищает от дубля при потерянном ответе и повторном нажатии (D-08).
- blocks.append: абзац сводки передаётся в `children` при создании страницы, отдельный вызов не нужен.
