import json
import re
from datetime import datetime, timezone, date, timedelta, time as dt_time
import httpx
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DAYS_MAP = {
    "Понедельник": 0,
    "Вторник": 1,
    "Среда": 2,
    "Четверг": 3,
    "Пятница": 4,
    "Суббота": 5,
    "Воскресенье": 6,
}

TIME_SLOTS = {
    "1 пара": (dt_time(9, 30), dt_time(11, 0)),
    "2 пара": (dt_time(11, 10), dt_time(12, 40)),
    "3 пара": (dt_time(13, 0), dt_time(14, 30)),
    "4 пара": (dt_time(15, 10), dt_time(16, 40)),
    "5 пара": (dt_time(17, 0), dt_time(18, 30)),
    "6 пара": (dt_time(18, 40), dt_time(20, 10)),
}


def parse_guap_schedule(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")

    # Determine current semester and week from header
    week_info = "Не определена"
    current_week_type = "UNKNOWN"
    for d in soup.find_all("div"):
        txt = d.get_text(" ", strip=True)
        if "учебного года" in txt and "неделя" in txt:
            week_info = txt
            if "▲" in txt or "верхняя" in txt.lower():
                current_week_type = "UPPER"  # Верхняя
            elif "▼" in txt or "нижняя" in txt.lower():
                current_week_type = "LOWER"  # Нижняя
            break

    # Parse days and lessons in one linear pass
    lessons = []
    current_day = None
    current_time_slot = None

    for elem in soup.find_all(["h4", "div"]):
        classes = elem.get("class", [])
        text = elem.get_text(" ", strip=True)

        if elem.name == "h4":
            day_name = text.strip()
            if day_name in DAYS_MAP:
                current_day = day_name
                current_time_slot = None
            continue

        if current_day and "mt-3" in classes and "text-danger" in classes:
            # Time slot e.g. "2 пара (11:10—12:40)"
            for slot_key in TIME_SLOTS:
                if slot_key in text:
                    current_time_slot = slot_key
                    break
            continue

        if current_day and current_time_slot and "d-flex" in classes and "gap-2" in classes:
            # Lesson entry
            # Check week marker
            week_marker = "BOTH"
            if "▲" in text:
                week_marker = "UPPER"
            elif "▼" in text:
                week_marker = "LOWER"

            # Lesson type
            l_type = "Занятие"
            if "Лекция" in text:
                l_type = "Лекция"
            elif "Лабораторное занятие" in text:
                l_type = "Лаб. работа"
            elif "Практическое занятие" in text:
                l_type = "Практика"

            # Room
            room_match = re.search(r"ауд\.\s*([^—]+)", text)
            room = room_match.group(1).strip() if room_match else "Не указана"

            # Subject
            subject = text
            for remove_prefix in ["▲", "▼", "Лекция", "Лабораторное занятие", "Практическое занятие"]:
                subject = subject.replace(remove_prefix, "")
            if room_match:
                subject = subject.split("ауд.")[0]
            subject = subject.strip(" .–—")

            # Groups
            groups = []
            grp_match = re.findall(r"\b(\d{4}[А-Яа-я]?)\b", text)
            if grp_match:
                groups = grp_match

            # Teacher
            teacher_match = re.search(r"преп:\s*([^.]+)", text)
            teacher = teacher_match.group(1).strip() if teacher_match else "Попов Д.А."

            lessons.append({
                "day": current_day,
                "slot": current_time_slot,
                "times": (TIME_SLOTS[current_time_slot][0].strftime('%H:%M'), TIME_SLOTS[current_time_slot][1].strftime('%H:%M')),
                "week_marker": week_marker,
                "type": l_type,
                "subject": subject,
                "room": room,
                "teacher": teacher,
                "groups": groups,
                "raw_text": text,
            })

    return week_info, current_week_type, lessons


def get_google_calendar_events():
    creds = Credentials.from_authorized_user_file("token.json")
    service = build("calendar", "v3", credentials=creds)

    # Fetch events for current week
    today = date.today()
    # Start of this week (Monday)
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=7)

    time_min = datetime.combine(start_week, dt_time(0, 0, 0), tzinfo=timezone.utc).isoformat()
    time_max = datetime.combine(end_week, dt_time(23, 59, 59), tzinfo=timezone.utc).isoformat()

    events_res = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return events_res.get("items", [])


def main():
    import asyncio
    from src.parser.schedule_parser import ScheduleParser

    print("1. Запрашиваю расписание с сайта ГУАП (https://guap.ru/rasp?pr=2903) через ScheduleParser...")
    parser = ScheduleParser(base_url="https://guap.ru/rasp", timeout_seconds=20.0, max_retries=4)

    async def fetch_html():
        return await parser.fetch_schedule_raw("2903", param_name="pr")

    res = asyncio.run(fetch_html())

    if not res.success or not res.raw_content:
        print(f"Ошибка получения расписания: {res.error_message}. Проверяю локальный кэш...")
        # Check if we saved a snapshot in DB
        import aiosqlite
        async def get_db_snapshot():
            async with aiosqlite.connect("./data/assistant.db") as conn:
                conn.row_factory = aiosqlite.Row
                c = await conn.execute("SELECT raw_payload FROM content_snapshots ORDER BY id DESC LIMIT 1;")
                r = await c.fetchone()
                return r["raw_payload"] if r else None
        cached = asyncio.run(get_db_snapshot())
        if not cached:
            print("Нет кэшированных данных.")
            return
        html_text = cached
    else:
        html_text = res.raw_content

    week_info, current_week_type, lessons = parse_guap_schedule(html_text)
    print(f"Информация о неделе на сайте: {week_info}")
    print(f"Текущий тип недели: {'▲ Верхняя (нечетная)' if current_week_type == 'UPPER' else '▼ Нижняя (четная)'}")
    print(f"Всего найдено занятий в сетке расписания: {len(lessons)}\n")

    print("2. Считываю события из Google Календаря...")
    cal_events = get_google_calendar_events()
    print(f"Всего событий в Google Календаре на текущую неделю: {len(cal_events)}\n")

    # Output detailed report
    output = {
        "week_info": week_info,
        "current_week_type": current_week_type,
        "guap_lessons": lessons,
        "calendar_events": [
            {
                "id": e.get("id"),
                "summary": e.get("summary"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date")),
                "location": e.get("location"),
                "description": e.get("description"),
            }
            for e in cal_events
        ]
    }

    with open("reconcile_report.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("=== РЕЗУЛЬТАТЫ СВЕРКИ ===")
    print("\n--- СОБЫТИЯ В GOOGLE КАЛЕНДАРЕ НА ЭТУ НЕДЕЛЮ ---")
    if not cal_events:
        print("  (Событий нет)")
    for e in cal_events:
        start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date"))
        print(f"  • [{start}] {e.get('summary')} (ауд: {e.get('location')})")

    print("\n--- РАСПИСАНИЕ НА САЙТЕ ГУАП (ПО ДНЯМ) ---")
    days_seen = set()
    for l in lessons:
        active_str = "Активна на этой неделе" if (l["week_marker"] == "BOTH" or l["week_marker"] == current_week_type) else "Не на этой неделе"
        marker_str = "▲" if l["week_marker"] == "UPPER" else ("▼" if l["week_marker"] == "LOWER" else "•")
        print(f"  [{l['day']}] {marker_str} {l['slot']} ({l['times'][0]}–{l['times'][1]}): [{l['type']}] {l['subject']} | ауд. {l['room']} ({active_str})")


if __name__ == "__main__":
    main()
