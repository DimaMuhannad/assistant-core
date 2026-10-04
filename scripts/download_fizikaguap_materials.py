#!/usr/bin/env python3
"""Script to download core physics manuals, textbooks, problem collections, and templates."""

import argparse
import os
import sys
import logging
import urllib.parse
from pathlib import Path
import requests
import urllib3

urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_materials")

BASE_DIR = Path("/opt/assistant-core/data/methodist/raw")

RESOURCES = [
    # 1. Main Textbooks (Коваленко И.И.)
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2020/09/KovalenkoPhysics1.pdf",
        "filename": "Коваленко_Курс_физики_Ч1_Механика_2019.pdf",
        "title": "Коваленко И.И. Курс физики. Ч. 1. Механика. Колебания и волны (2019)",
    },
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2020/09/KovalenkoPhysics2.pdf",
        "filename": "Коваленко_Лавровская_Курс_физики_Ч2_Термодинамика_2019.pdf",
        "title": "Коваленко И.И., Лавровская Н.П. Курс физики. Ч. 2. Термодинамика и молекулярная физика (2019)",
    },
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2020/09/KovalenkoPhysics3.pdf",
        "filename": "Коваленко_Курс_физики_Ч3_Электричество_магнетизм_2020.pdf",
        "title": "Коваленко И.И. Курс физики. Ч. 3. Электричество и магнетизм (2020)",
    },
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2021/12/Коваленко-часть4.pdf",
        "filename": "Коваленко_Котликов_Курс_физики_Ч4_Оптика_2021.pdf",
        "title": "Коваленко И.И., Лавровская Н.П., Котликов Е.Н. Курс физики. Ч. 4. Оптика (2021)",
    },
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2023/09/Коваленко_Лавровская2023.pdf",
        "filename": "Коваленко_Лавровская_Курс_физики_Ч5_Квантовая_физика_2023.pdf",
        "title": "Коваленко И.И., Лавровская Н.П. Курс физики. Ч. 5. Квантовая физика (2023)",
    },
    {
        "category": "textbooks",
        "path": "/wp-content/uploads/2024/11/FIZIKA_v_tablitsakh_i_formulakh.pdf",
        "filename": "Трофимова_Физика_в_таблицах_и_формулах.pdf",
        "title": "Трофимова Т.И. Физика в таблицах и формулах",
    },

    # 2. Problem Books (Задачники)
    {
        "category": "problem_books",
        "path": "/wp-content/uploads/2026/09/Сборник_задач_по_Физике_1_семестр.pdf",
        "filename": "Сборник_задач_по_Физике_1_семестр_2026.pdf",
        "title": "Сборник задач по физике. 1 семестр (2026)",
    },
    {
        "category": "problem_books",
        "path": "/wp-content/uploads/2026/03/Андреев2019исправленнаяА.pdf",
        "filename": "Андреев_Сборник_задач_2_семестр_2019.pdf",
        "title": "Андреев В.М. и др. Сборник задач. 2 семестр: Электричество, магнетизм, оптика (2019)",
    },
    {
        "category": "problem_books",
        "path": "/wp-content/uploads/2023/09/АндреевКоваленко2023.pdf",
        "filename": "Андреев_Коваленко_Сборник_задач_3_семестр_2023.pdf",
        "title": "Андреев В.М., Коваленко И.И. Сборник задач. 3 семестр: Квантовая физика (2023)",
    },
    {
        "category": "problem_books",
        "path": "/wp-content/uploads/2021/09/СборникЗадач1семестр3семестра.pdf",
        "filename": "Сборник_задач_1_семестр_3семестровый_курс_2018.pdf",
        "title": "Сборник задач по физике: Механика, колебания и волны (2018)",
    },

    # 3. Lab Manuals (Методические пособия к лабораторным работам)
    {
        "category": "lab_manuals",
        "path": "/wp-content/uploads/2021/11/КвантоваяФизика2021.pdf",
        "filename": "Квантовая_физика_лабораторный_практикум_2021.pdf",
        "title": "Квантовая физика: Лабораторный практикум (2021)",
    },
    {
        "category": "lab_manuals",
        "path": "/wp-content/uploads/2021/05/Электричество_и_магнетизм_2021_РИЦ.pdf",
        "filename": "Электричество_и_магнетизм_лабораторный_практикум_2021.pdf",
        "title": "Электричество и магнетизм: Учебно-методическое пособие (2021)",
    },
    {
        "category": "lab_manuals",
        "path": "/wp-content/uploads/2021/05/Волновая-оптика_учеб-метод_пособие_2019_РИЦ.pdf",
        "filename": "Волновая_оптика_учебно_методическое_пособие_2019.pdf",
        "title": "Котликов Е.Н., Новикова Ю.А., Терещенко Г.В. Волновая оптика: уч.-метод. пособие (2019)",
    },
    {
        "category": "lab_manuals",
        "path": "/wp-content/uploads/2021/05/Физика_лазеров_2019_РИЦ.pdf",
        "filename": "Физика_лазеров_учебно_методическое_пособие_2019.pdf",
        "title": "Котликов Е.Н. Физика лазеров: уч.-метод. пособие (2019)",
    },
    {
        "category": "lab_manuals",
        "path": "/wp-content/uploads/2023/10/Кинематика-и-динамика-движения-маятников-лабораторный-практикум-Ю.-А.-Новикова-Г.-В.-Терещенко.pdf",
        "filename": "Маятники_кинематика_и_динамика_лабораторный_практикум_2023.pdf",
        "title": "Новикова Ю.А., Терещенко Г.В. Кинематика и динамика движения маятников (2023)",
    },

    # 4. Templates & Blank Protocols (Шаблоны титульных листов и бланки протоколов)
    {
        "category": "templates",
        "path": "/wp-content/uploads/2025/10/Титульный-лист-отчета-о-практической-работе-2025.docx",
        "filename": "Титульный_лист_отчета_о_практической_работе_2025.docx",
        "title": "Титульный лист отчета о практической работе (2025)",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2021/03/ТитульныйЛистПротоколЛР2Оптика.docx",
        "filename": "Титульный_лист_и_протокол_ЛР2_Оптика.docx",
        "title": "Шаблон титульного листа и протокола: Кольца Ньютона (ЛР №2 Оптика)",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2025/10/Лабораторная-работа-№5-Крутильный-маятник-Новая-установка.docx",
        "filename": "Протокол_ЛР5_Крутильный_маятник.docx",
        "title": "Бланк протокола: ЛР №5 Крутильный маятник",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2024/10/Протокол_Молекулярка11.docx",
        "filename": "Протокол_Молекулярка_11.docx",
        "title": "Бланк протокола: Молекулярная физика работа №11",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2020/05/Протокол-к-ЛР-3.docx",
        "filename": "Протокол_ЛР3_Магнитное_поле_Земли.docx",
        "title": "Бланк протокола: ЛР №3 Горизонтальная составляющая поля Земли",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2020/04/ПротоколЛабораторнаяРабота5.docx",
        "filename": "Протокол_ЛР5_Гистерезис_ферромагнетиков.docx",
        "title": "Бланк протокола: ЛР №5 Гистерезис ферромагнитных материалов",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2020/04/Шаблон_Протокола_ЛР_№10.docx",
        "filename": "Шаблон_протокола_ЛР10_Удельный_заряд_электрона.docx",
        "title": "Бланк протокола: ЛР №10 Удельный заряд электрона",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2026/02/5_Протокол-измеренийЭффектХолла2026.docx",
        "filename": "Протокол_ЛР5_Эффект_Холла_2026.docx",
        "title": "Бланк протокола: ЛР №5 Эффект Холла (2026)",
    },
    {
        "category": "templates",
        "path": "/wp-content/uploads/2026/04/Фотоэффект_ЛР10_КвантоваяФизика.docx",
        "filename": "Протокол_ЛР10_Фотоэффект_2026.docx",
        "title": "Бланк протокола: ЛР №10 Фотоэффект (Опыты Столетова)",
    },
]


def download_file(item: dict, base_url: str, target_base_dir: Path) -> bool:
    category = item["category"]
    path_suffix = item["path"]
    filename = item["filename"]
    target_dir = target_base_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    if target_path.exists() and target_path.stat().st_size > 1024:
        logger.info("File already exists: %s (%d bytes)", filename, target_path.stat().st_size)
        return True

    if not base_url:
        logger.warning("No base-url configured. Skipping remote download for %s", filename)
        return False

    url = f"{base_url.rstrip('/')}{path_suffix}"
    logger.info("Downloading %s -> %s", url, filename)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=30)
        if r.status_code == 200 and len(r.content) > 500:
            target_path.write_bytes(r.content)
            logger.info("Saved %s (%d bytes)", filename, len(r.content))
            return True
        else:
            logger.error("Failed to download %s: HTTP %s", url, r.status_code)
            return False
    except Exception as e:
        logger.error("Exception downloading %s: %s", url, e)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download physics department educational materials")
    parser.add_argument("--base-url", default=os.getenv("PHYSICS_MATERIALS_BASE_URL", ""), help="Materials portal base URL")
    parser.add_argument("--output-dir", default=str(BASE_DIR), help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    success_count = 0
    for item in RESOURCES:
        if download_file(item, base_url=args.base_url, target_base_dir=out_dir):
            success_count += 1

    logger.info("Processed %d of %d items.", success_count, len(RESOURCES))


if __name__ == "__main__":
    main()
