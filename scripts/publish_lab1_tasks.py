"""Script to publish only Lab Work #1 (Попов: Лабораторная работа №1) for all groups in semester 28."""

import logging
import time
from typing import Any

from src.connectors.guap_lms.client import GuapLmsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("publish_lab1")


def publish_lab1_for_all_groups() -> dict[str, Any]:
    client = GuapLmsClient()
    client.ensure_authenticated()

    all_tasks = client.list_tasks(semester=28)
    popov_tasks = [t for t in all_tasks if "попов" in t["title"].lower()]

    lab1_tasks = [t for t in popov_tasks if "№1" in t["title"]]
    other_labs = [t for t in popov_tasks if "№1" not in t["title"]]

    logger.info("Found %d total Popov tasks. Lab 1 tasks: %d. Other lab tasks: %d.",
                len(popov_tasks), len(lab1_tasks), len(other_labs))

    published_results = []
    for t in lab1_tasks:
        task_id = t["id"]
        title = t["title"]
        subject = t["subject"].replace("\n", " ").strip()

        if t["is_public"]:
            logger.info("Task %s (%s, %s) is ALREADY public.", task_id, title, subject)
            published_results.append({
                "id": task_id,
                "title": title,
                "subject": subject,
                "status": "already_public",
                "success": True,
            })
            continue

        logger.info("Publishing task %s (%s, %s)...", task_id, title, subject)
        ok = client.set_task_visibility(task_id, is_public=True)
        logger.info("Publish task %s -> Success: %s", task_id, ok)
        published_results.append({
            "id": task_id,
            "title": title,
            "subject": subject,
            "status": "published" if ok else "failed",
            "success": ok,
        })
        time.sleep(0.5)

    # Verification: re-fetch all tasks
    verified_tasks = client.list_tasks(semester=28)
    verified_popov = [t for t in verified_tasks if "попов" in t["title"].lower()]
    verified_lab1 = [t for t in verified_popov if "№1" in t["title"]]
    verified_other = [t for t in verified_popov if "№1" not in t["title"]]

    return {
        "published_results": published_results,
        "lab1_count": len(verified_lab1),
        "lab1_public_count": sum(1 for t in verified_lab1 if t["is_public"]),
        "other_labs_count": len(verified_other),
        "other_labs_hidden_count": sum(1 for t in verified_other if not t["is_public"]),
        "all_lab1": verified_lab1,
        "all_other": verified_other,
    }


if __name__ == "__main__":
    res = publish_lab1_for_all_groups()
    print("\n================= PUBLISH REPORT =================")
    print(f"Total Lab 1 tasks: {res['lab1_count']} | Successfully Public: {res['lab1_public_count']}")
    print(f"Total Other Lab tasks: {res['other_labs_count']} | Strictly Hidden: {res['other_labs_hidden_count']}")
    print("\n--- PUBLISHED LAB 1 TASKS (PUBLIC) ---")
    for t in res["all_lab1"]:
        vis = "PUBLIC (Виден)" if t["is_public"] else "HIDDEN (Скрыт)"
        print(f"ID: {t['id']} | {vis:<15} | {t['title']} | {t['subject'][:35]}")

    print("\n--- REMAINING LAB TASKS (HIDDEN) ---")
    for t in res["all_other"][:8]:
        vis = "PUBLIC (Виден)" if t["is_public"] else "HIDDEN (Скрыт)"
        print(f"ID: {t['id']} | {vis:<15} | {t['title']} | {t['subject'][:35]}")
    if len(res["all_other"]) > 8:
        print(f"... and {len(res['all_other']) - 8} more hidden tasks.")
