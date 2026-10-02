"""Вторая синтетическая персона: каркас Фазы 1 (FND-03).

Назначение: данные вымышленного пользователя, который отличается от «зашитого сегодня»
владельца во всех идентифицирующих полях. Фаза 3 прогонит через эти данные реальные
кодовые пути (промпты, рабочие пространства, дефолты, scope) и докажет, что платформа
не привязана к одному человеку. Сейчас каркас проверяет только сами данные.

Это обычный dict. Это не Pydantic-модель и не YAML: схема config/persona.yaml
принадлежит PER-01 и здесь не предвосхищается.

Правило копий: у модуля две байт-в-байт одинаковые копии - backend/tests/ в chat-app и
tests/ в assistant-core. Дрейф ловит шаг гейта «синтетическая персона (дрейф SHA-256)»
(scripts/gate.py, D-16). Копии существуют до общей библиотеки Фазы 4; править нужно обе
одновременно.

Все значения вымышленные: домены оканчиваются на .example, пути начинаются с /synthetic/,
идентификатор Telegram лежит в зарезервированном диапазоне 100000000..100000999.

Ожидают Фазы 3
--------------
Эти восемь проверок включаются в Фазе 3. Сейчас они только перечислены текстом, без
маркеров пропуска и ожидаемого падения (D-15):

1) PER-01 - персона загружается из config/persona.yaml с Pydantic-валидацией; персона по умолчанию грузится без PERSONA_CONFIG_PATH;
2) PER-02 - персона записывается в таблицы personas, workspaces, connector_bindings; несколько привязок на одну роль;
3) PER-03/PER-04 - /api/v1/security/overview и аудит строятся из рабочих пространств персоны (три уровня clearance); NDA-проверки воспроизводятся из данных без ослабления;
4) PER-05 - дефолт области и white-label-поля веб-интерфейса приходят из /api/v1/persona/current;
5) PER-06 - параметры коннекторов (проект учёта, норма часов, адреса, предметы, слоты) читаются из персоны;
6) PER-07/BCK-02 - промпты секретаря, маршрутизатора и методиста рендерятся из шаблонов с этой персоной и отличаются от промптов персоны по умолчанию; тесты хардкода переписаны на загруженную персону;
7) PER-08 - сканер хардкода не находит токены владельца вне allowlist; denylist теста каркаса заменяется данными персоны по умолчанию;
8) PER-09 - test_persona_config.py: те же кодовые пути дают для синтетической персоны иные промпты, список рабочих пространств, дефолты и scope-решения.
"""

SYNTHETIC_PERSONA: dict = {
    "id": "synthetic-test-persona",
    "display_name": "Тестовый Тест Тестович",
    "short_name": "Тестовый Т.Т.",
    "title": "старший синтетический преподаватель",
    "organizations": {
        "university": "Тестовый университет Альфа",
        "company": "Тестовая компания Бета",
    },
    "telegram": {
        "authorized_user_id": 100000001,
        "bot_username": "synthetic_test_bot",
    },
    "workspaces": [
        {
            "id": "synthetic-public",
            "label": "Синтетический открытый проект",
            "path": "/synthetic/public",
            "clearance": "public",
            "account": "synthetic-account",
            "remote": "https://git.synthetic.example/synthetic/public.git",
            "forbidden_remote_substrings": [],
            "forbidden_keywords": [],
        },
        {
            "id": "synthetic-internal",
            "label": "Синтетическая кафедра",
            "path": "/synthetic/internal",
            "clearance": "internal",
            "account": "synthetic-account",
            "remote": "https://git.synthetic.example/synthetic/internal.git",
            "forbidden_remote_substrings": [],
            "forbidden_keywords": [],
        },
        {
            "id": "synthetic-nda",
            "label": "Синтетическая закрытая работа",
            "path": "/synthetic/nda",
            "clearance": "restricted_nda",
            "account": "synthetic-corp-account",
            "remote": "https://git.synthetic.example/synthetic-corp/nda.git",
            "forbidden_remote_substrings": ["git.synthetic.example/forbidden"],
            "forbidden_keywords": ["synthetic_marker_alpha", "synthetic_marker_beta"],
        },
    ],
    "timesheet": {
        "default_project": "Синтетический проект учёта",
        "daily_norm_hours": 6.0,
    },
    "schedule_source": {"base_url": "https://schedule.synthetic.example/"},
    "lms": {"base_url": "https://lms.synthetic.example/"},
    "default_area": "Синтетическая область",
    "subjects": {"синтетическая механика": "СинтМех"},
    "lesson_slots": {1: ("08:15", "09:45")},
}
