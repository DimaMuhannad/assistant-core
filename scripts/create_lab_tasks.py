"""Batch-create unpublished laboratory tasks for Dmitry Popov's groups on pro.guap.ru."""

import logging
import time
from typing import Any

from src.connectors.guap_lms.client import GuapLmsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("create_lab_tasks")

GROUPS_CONFIG = [
    {
        "group": "1632",
        "subject_name": "Физика (1632)",
        "subject_id": 3444128,
        "group_id": 8008,
    },
    {
        "group": "М562",
        "subject_name": "Физика (М562)",
        "subject_id": 3428067,
        "group_id": 7525,
    },
    {
        "group": "8626",
        "subject_name": "Физика (8626)",
        "subject_id": 3435094,
        "group_id": 7872,
    },
    {
        "group": "М651Ксв",
        "subject_name": "Физика (М651Ксв)",
        "subject_id": 3441887,
        "group_id": 7929,
    },
    {
        "group": "М431К",
        "subject_name": "Физические основы нанотехнологий (М431К)",
        "subject_id": 3411934,
        "group_id": 7196,
    },
    {
        "group": "М553",
        "subject_name": "Физика (М553)",
        "subject_id": 3426739,
        "group_id": 7716,
    },
    {
        "group": "1538",
        "subject_name": "Физика (1538)",
        "subject_id": 3428181,
        "group_id": 7373,
    },
]

LAB_COUNT = 4


def create_all_labs() -> list[dict[str, Any]]:
    client = GuapLmsClient()
    client.ensure_authenticated()

    # Pre-fetch existing tasks to ensure idempotency
    existing_tasks = client.list_tasks(semester=28)
    existing_map: dict[str, dict[str, Any]] = {}
    for t in existing_tasks:
        key = f"{t['subject']}_{t['title']}"
        existing_map[key] = t

    results: list[dict[str, Any]] = []

    for item in GROUPS_CONFIG:
        group = item["group"]
        subject_id = item["subject_id"]
        group_id = item["group_id"]
        subject_name = item["subject_name"]

        logger.info("Processing group %s (%s)...", group, subject_name)

        for i in range(1, LAB_COUNT + 1):
            title = f"Попов: Лабораторная работа №{i}"
            # Check if already exists
            already_exists = False
            for t in existing_tasks:
                if t["title"] == title and group in t["subject"]:
                    logger.info("Task '%s' for group %s already exists with ID %s. Skipping creation.", title, group, t["id"])
                    results.append({
                        "group": group,
                        "subject": subject_name,
                        "title": title,
                        "ordernum": i,
                        "id": t["id"],
                        "url": f"https://pro.guap.ru/inside/professor/tasks/{t['id']}/show",
                        "is_public": t["is_public"],
                        "already_existed": True,
                    })
                    already_exists = True
                    break

            if already_exists:
                continue

            res = client.create_task(
                name=title,
                subject_id=subject_id,
                group_ids=[group_id],
                semester_id=28,
                task_type_id=2,  # Лабораторная работа
                description="Отчет по лабораторной работе (титульный лист, цель, измерения, расчет погрешностей, выводы).",
                markpoint=10,
                ordernum=i,
                harddeadline="2026-12-31",
                is_public=False,  # STRICT: Hidden from students
                report_required=True,
            )
            created_id = res.get("created_id")
            logger.info("Created '%s' for group %s -> ID: %s (Status: %s)", title, group, created_id, res["status"])
            results.append({
                "group": group,
                "subject": subject_name,
                "title": title,
                "ordernum": i,
                "id": created_id,
                "url": f"https://pro.guap.ru/inside/professor/tasks/{created_id}/show" if created_id else "",
                "is_public": res["is_public"],
                "already_existed": False,
            })
            time.sleep(0.4)

    return results


def publish_all_labs() -> list[dict[str, Any]]:
    """Publish all Dmitry Popov lab tasks for semester 28 on pro.guap.ru."""
    client = GuapLmsClient()
    client.ensure_authenticated()

    tasks = client.list_tasks(semester=28)
    popov_tasks = [t for t in tasks if "попов" in t["title"].lower()]
    logger.info("Found %d Popov tasks to verify/publish.", len(popov_tasks))

    results = []
    for t in popov_tasks:
        if not t["is_public"]:
            logger.info("Publishing task %s (%s)...", t["id"], t["title"])
            ok = client.set_task_visibility(t["id"], is_public=True)
            results.append({"id": t["id"], "title": t["title"], "success": ok, "is_public": True})
            time.sleep(0.3)
        else:
            results.append({"id": t["id"], "title": t["title"], "success": True, "is_public": True, "already_public": True})

    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--publish":
        print("Publishing all Dmitry Popov's lab tasks...")
        res = publish_all_labs()
        print(f"\n--- Published {len(res)} tasks ---")
        for r in res:
            print(f"ID: {r['id']} | {r['title']} | Success: {r['success']}")
    else:
        tasks = create_all_labs()
        print(f"\n--- Summary: Total {len(tasks)} tasks processed ---")
        for t in tasks:
            status_str = "HIDDEN (Не виден у студентов)" if not t["is_public"] else "PUBLIC (Виден)"
            print(f"Group: {t['group']:<10} | {t['title']} | ID: {t['id']} | {status_str} | {t['url']}")
