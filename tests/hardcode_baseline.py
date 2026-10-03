"""Остаточный хардкод профиля владельца вне данных персоны: baseline сканера (PER-08, D-16).

Словарь {путь: {класс токена: число строк}} создан один раз программой (render_baseline из
test_hardcode_scanner.py) и просмотрен вручную в конце Фазы 3. Он может только сокращаться:
тесты test_no_new_hardcode_outside_baseline (новая находка или новый файл) и
test_baseline_has_no_stale_entries (запись больше фактического счёта) краснеют иначе.
Фаза 6 доводит словарь до пустого (FIN-01). Причины остатка по группам - в docs/BASELINE.md,
раздел «Итог после Фазы 3».

Счёт - число строк файла, где есть хотя бы один токен класса. Токены вычисляются из данных
персоны по умолчанию (persona_tokens.owner_tokens), в этот файл не копируются.
"""

HARDCODE_BASELINE: dict[str, dict[str, int]] = {
    "reconcile_report.json": {"name": 22, "organization": 1},
    "scripts/create_lab_tasks.py": {"domain": 4, "name": 2, "organization": 7},
    "scripts/download_fizikaguap_materials.py": {"domain": 25, "organization": 29},
    "scripts/generate_brief.py": {"organization": 1},
    "scripts/notion_dev.py": {"domain": 2, "organization": 8},
    "scripts/populate_notion_retrospective.py": {"domain": 2, "organization": 8},
    "scripts/provision_dev_roadmap.py": {"account": 5, "domain": 5, "organization": 29},
    "scripts/provision_notion.py": {"organization": 9},
    "scripts/publish_lab1_tasks.py": {"name": 3, "organization": 2},
    "scripts/reconcile_schedule.py": {"domain": 2, "name": 1, "organization": 6},
    "scripts/run_stt_stress_test.py": {"organization": 2},
    "scripts/security_shield.py": {"account": 2, "organization": 6},
    "scripts/test_secretary_simulation.py": {"account": 1, "domain": 4, "organization": 14},
    "src/brain/debrief_parser.py": {"organization": 8},
    "src/brain/intent_router.py": {"organization": 1},
    "src/brain/methodist.py": {"organization": 6},
    "src/brain/reply_generator.py": {"name": 2, "organization": 3},
    "src/brain/secretary_dialog.py": {"domain": 4, "name": 3, "organization": 26},
    "src/brain/summarizer.py": {"organization": 10},
    "src/collector/email_collector.py": {"domain": 2, "organization": 33},
    "src/composition.py": {"organization": 2},
    "src/config.py": {"domain": 3, "organization": 9},
    "src/connectors/aadhk/parser.py": {"organization": 7},
    "src/connectors/guap_lms/__init__.py": {"domain": 1, "organization": 3},
    "src/connectors/guap_lms/client.py": {"domain": 13, "organization": 17},
    "src/connectors/guap_lms/provider.py": {"organization": 1},
    "src/detector/tg_filter.py": {"organization": 1},
    "src/main.py": {"domain": 2, "name": 1, "organization": 12},
    "src/models/schedule.py": {"organization": 2},
    "src/models/second_brain.py": {"organization": 2},
    "src/notifier/bot_handler.py": {"domain": 20, "name": 7, "organization": 40},
    "src/notifier/live_ticker.py": {"domain": 1, "organization": 18},
    "src/notifier/telegram.py": {"organization": 3},
    "src/sender/email_sender.py": {"domain": 1, "name": 2, "organization": 8},
    "src/storage/db.py": {"domain": 3, "name": 2, "organization": 34},
}
