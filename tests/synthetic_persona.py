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

Конвертер (Фаза 3, D-06, PER-09): synthetic_to_config(SYNTHETIC_PERSONA) превращает этот словарь в
структуру config/persona.yaml (корень persona), чтобы вторая персона загружалась теми же
load_persona / seed-CLI / DatabaseService, что и персона по умолчанию. Словарь и каркас Фазы 1
не меняются: к схеме приспосабливается только конвертер. Модуль остаётся без импортов, чтобы
одинаково работать в обоих репозиториях; запись в YAML или JSON делает вызывающий тест.

Включено в Фазе 3
-----------------
Восемь проверок, которые в Фазе 1 были только перечислены текстом (D-15), включены в Фазе 3:

1) PER-01 - персона загружается из config/persona.yaml с Pydantic-валидацией; персона по умолчанию грузится без PERSONA_CONFIG_PATH (test_persona_loader.py);
2) PER-02 - персона записывается в таблицы personas, workspaces, connector_bindings; несколько привязок на одну роль (test_persona_storage.py);
3) PER-03/PER-04 - /api/v1/security/overview и аудит строятся из рабочих пространств персоны (три уровня clearance); NDA-проверки воспроизводятся из данных без ослабления (test_nda_equivalence.py, test_security_api.py, test_nda_script_parity.py);
4) PER-05 - дефолт области и white-label-поля веб-интерфейса приходят из /api/v1/persona/current (test_persona_api.py, test_index_whitelabel.py);
5) PER-06 - параметры коннекторов (проект учёта, норма часов, адреса, предметы, слоты) читаются из персоны (test_connector_params.py);
6) PER-07/BCK-02 - промпты секретаря, маршрутизатора и методиста рендерятся из шаблонов с этой персоной и отличаются от промптов персоны по умолчанию; тесты хардкода переписаны на загруженную персону (test_prompt_snapshot.py, test_persona_prompts.py);
7) PER-08 - сканер хардкода не находит новых токенов владельца вне allowlist, остаточный долг зафиксирован baseline; denylist теста каркаса заменён данными персоны по умолчанию (test_hardcode_scanner.py, test_synthetic_persona.py);
8) PER-09 - те же кодовые пути дают для синтетической персоны иные промпты, список рабочих пространств, дефолты и scope-решения (test_persona_config.py).
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

SYNTHETIC_TELEGRAM_ENV = "SYNTHETIC_TELEGRAM_USER_ID"

_CLEARANCE_VIEW = {
    "public": ("blue", "Открытый"),
    "internal": ("yellow", "Внутренний"),
    "restricted_nda": ("red", "Закрытый NDA"),
}

_FULL_NAME_FORMS = (
    "nominative",
    "genitive",
    "dative_first_patronymic",
    "genitive_first_patronymic",
    "instrumental_first_patronymic",
    "signature",
)
_SHORT_NAME_FORMS = ("short", "short_genitive", "initials_genitive")


def synthetic_to_config(d: dict, prompts: dict[str, str] | None = None) -> dict:
    """dict каркаса Фазы 1 -> структура persona.yaml; lesson_slots: {1: (s, e)} -> [{number, start, end}]."""
    university = d["organizations"]["university"]
    company = d["organizations"]["company"]
    area = d["default_area"]

    workspaces = []
    for ws in d["workspaces"]:
        color, clearance_label = _CLEARANCE_VIEW[ws["clearance"]]
        item = {
            "id": ws["id"],
            "label": ws["label"],
            "path": ws["path"],
            "clearance": ws["clearance"],
            "account": ws["account"],
            "clearance_label": clearance_label,
            "color": color,
            "remote": ws["remote"],
            "forbidden_remote_substrings": list(ws["forbidden_remote_substrings"]),
            "forbidden_keywords": list(ws["forbidden_keywords"]),
        }
        if ws["clearance"] == "restricted_nda":
            item["remote_violation_message"] = (
                f"CRITICAL: remote пространства «{ws['label']}» указывает на запрещённый аккаунт!"
            )
        workspaces.append(item)

    name_forms = {key: d["display_name"] for key in _FULL_NAME_FORMS}
    name_forms.update({key: d["short_name"] for key in _SHORT_NAME_FORMS})

    return {
        "persona": {
            "id": d["id"],
            "display_name": d["display_name"],
            "short_name": d["short_name"],
            "title": d["title"],
            "name_forms": name_forms,
            "organizations": {
                "university": {"name": university, "aliases": []},
                "company": {"name": company, "aliases": []},
            },
            "telegram": {
                "authorized_user_ids": ["${" + SYNTHETIC_TELEGRAM_ENV + "}"],
                "bot_username": d["telegram"]["bot_username"],
            },
            "default_area": area,
            "task_areas": [
                {"value": area, "label": area, "filter_label": area, "show_in_filter": True}
            ],
            "ui": {
                "texts": {
                    "header_subtitle": f"{d['short_name']} • {university} / {company}",
                    "schedule_title": f"Расписание: {university}",
                    "security_intro": f"Политики безопасности между открытыми проектами и закрытым контуром: {company}.",
                    "clearance_tile_caption": f"{company} (строгая изоляция)",
                    "remote_tile_caption": "аккаунты и remote пространств",
                    "airgap_tile_caption": f"Запрет агентам читать закрытые материалы: {company}",
                    "reminder_context_placeholder": f"Например: {university}: семестр",
                }
            },
            "workspaces": workspaces,
            "connectors": {
                "schedule_source": [
                    {
                        "id": "main",
                        "provider": "schedule_site",
                        "scopes": ["schedule.read"],
                        "config": {
                            "base_url": d["schedule_source"]["base_url"],
                            "subjects": dict(d["subjects"]),
                            "lesson_slots": [
                                {"number": number, "start": start, "end": end}
                                for number, (start, end) in d["lesson_slots"].items()
                            ],
                        },
                    }
                ],
                "calendar_sync": [],
                "timesheet": [
                    {
                        "id": "main",
                        "provider": "aadhk_timesheet",
                        "scopes": [],
                        "config": {
                            "default_project": d["timesheet"]["default_project"],
                            "daily_norm_hours": d["timesheet"]["daily_norm_hours"],
                        },
                    }
                ],
                "lms": [
                    {
                        "id": "main",
                        "provider": "lms_portal",
                        "scopes": [],
                        "config": {"base_url": d["lms"]["base_url"]},
                    }
                ],
                "git_source": [],
                "notion": [],
            },
            "methodist": {
                "raw_dir": "/synthetic/methodist/raw",
                "kb_dir": "/synthetic/methodist/knowledge_base",
                "file_catalog": [],
                "scope_rules": {
                    "out_of_scope_keywords": [company.lower()],
                    "academic_keywords": list(d["subjects"]),
                    "out_of_scope_reason": f"Вопрос вне методической работы: {university}",
                },
            },
            "prompts": dict(prompts) if prompts else {},
        }
    }
