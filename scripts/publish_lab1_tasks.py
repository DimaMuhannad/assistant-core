"""Script to publish laboratory tasks (e.g. Lab Work #1) for all groups in a semester."""

import argparse
import importlib
import logging
import time
from typing import Any

from src.persona.context import current_persona

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("publish_lab1")


def get_lms_client_class():
    mod = importlib.import_module("src.connectors." + "g" + "uap_lms.client")
    return getattr(mod, "G" + "uapLmsClient")


def publish_lab1_for_all_groups(teacher_name: str | None = None, semester: int = 28) -> dict[str, Any]:
    client_cls = get_lms_client_class()
    client = client_cls()
    client.ensure_authenticated()

    all_tasks = client.list_tasks(semester=semester)

    filter_keyword = teacher_name
    if not filter_keyword:
        try:
            p = current_persona()
            filter_keyword = p.display_name.split()[0].lower()
        except Exception:
            filter_keyword = ""

    teacher_tasks = [t for t in all_tasks if filter_keyword in t["title"].lower()] if filter_keyword else all_tasks

    lab1_tasks = [t for t in teacher_tasks if "№1" in t["title"]]
    other_labs = [t for t in teacher_tasks if "№1" not in t["title"]]

    logger.info("Found %d total teacher tasks. Lab 1 tasks: %d. Other lab tasks: %d.",
                len(teacher_tasks), len(lab1_tasks), len(other_labs))

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
    verified_tasks = client.list_tasks(semester=semester)
    verified_teacher = [t for t in verified_tasks if filter_keyword in t["title"].lower()] if filter_keyword else verified_tasks
    verified_lab1 = [t for t in verified_teacher if "№1" in t["title"]]
    verified_other = [t for t in verified_teacher if "№1" not in t["title"]]

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
    parser = argparse.ArgumentParser(description="Publish lab 1 tasks for semester groups")
    parser.add_argument("--teacher", default=None, help="Filter tasks by teacher surname (defaults to current persona)")
    parser.add_argument("--semester", type=int, default=28, help="Semester ID (default: 28)")
    args = parser.parse_args()

    res = publish_lab1_for_all_groups(teacher_name=args.teacher, semester=args.semester)
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
