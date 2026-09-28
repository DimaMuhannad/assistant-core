import re
from typing import Sequence
from src.models.message import FilterResult, TelegramMessage


class TelegramMessageFilter:
    """Two-stage deterministic filter for Telegram messages.
    
    Filters out noise/chatter and detects high-priority academic notices,
    deadlines, schedule changes, and faculty announcements.
    """

    NOISE_PHRASES = {
        "ок", "ок.", "ок!", "хорошо", "спасибо", "спс", "принято", "+", "++",
        "буду", "понял", "понятно", "ясно", "договорились", "доброе утро",
        "здравствуйте", "привет", "добрый день", "добрый вечер", "ладно", "yes", "no"
    }

    CATEGORIES_CONFIG = [
        (
            "schedule_change",
            3,
            [
                r"\bперенос\w*",
                r"\bотмен\w*",
                r"\bзамен\w*",
                r"\bвместо\s+пары\b",
                r"\bдистант\w*",
                r"\bонлайн\b",
                r"\bаудитори\w*\s+перенес\w*",
                r"\bпары\s+не\s+будет\b",
                r"\bпару\s+перенес\w*",
            ],
        ),
        (
            "deadline",
            3,
            [
                r"\bдедлайн\w*",
                r"\bсдать\s+до\b",
                r"\bкрайний\s+срок\b",
                r"\bсрок\s+сдачи\b",
                r"\bдо\s+\d{1,2}[\.\/]\d{1,2}",
                r"\bсрочно\b",
                r"\bне\s+позднее\b",
                r"\bвнимание\b",
            ],
        ),
        (
            "exam_session",
            3,
            [
                r"\bэкзамен\w*",
                r"\bзач[её]т\w*",
                r"\bконсультаци\w*",
                r"\bсесси\w*",
                r"\bпересдач\w*",
                r"\bдопуск\w*",
                r"\bведомост\w*",
                r"\bкомисси\w*",
            ],
        ),
        (
            "faculty_notice",
            2,
            [
                r"\bкафедр\w*",
                r"\bдеканат\w*",
                r"\bраспоряжени\w*",
                r"\bприказ\w*",
                r"\bсобрани\w*",
                r"\bзаседани\w*",
                r"\bгуап\b",
                r"\bдирекци\w*",
                r"\bучебно-методическ\w*",
            ],
        ),
        (
            "academic_task",
            2,
            [
                r"\bлабораторн\w*",
                r"\bкурсов\w*",
                r"\bпрактическ\w*",
                r"\bзадани\w*",
                r"\bотч[её]т\w*",
                r"\bметодичк\w*",
                r"\bвариант\w*",
            ],
        ),
    ]

    def __init__(self) -> None:
        # Precompile category patterns
        self.compiled_rules = [
            (category, priority, [re.compile(p, re.IGNORECASE) for p in patterns])
            for category, priority, patterns in self.CATEGORIES_CONFIG
        ]

    def filter_message(self, message: TelegramMessage) -> FilterResult:
        raw_text = (message.text or "").strip()
        lower_text = raw_text.lower()

        # Step 1: Filter trivial noise
        if not raw_text and not message.has_media:
            return FilterResult(is_relevant=False, summary="Empty message")

        clean_punct = re.sub(r"[^\w\s]", "", lower_text).strip()
        if clean_punct in self.NOISE_PHRASES:
            return FilterResult(is_relevant=False, summary="Conversational noise")

        if len(raw_text) < 6 and not message.has_media:
            return FilterResult(is_relevant=False, summary="Too short")

        # Step 2: Categorization against compiled patterns
        matched_categories: list[tuple[str, int, list[str]]] = []

        for category, priority, patterns in self.compiled_rules:
            matched_words: list[str] = []
            for pattern in patterns:
                matches = pattern.findall(raw_text)
                if matches:
                    matched_words.extend([m.strip() if isinstance(m, str) else m[0] for m in matches])
            if matched_words:
                matched_categories.append((category, priority, list(set(matched_words))))

        if matched_categories:
            # Sort by highest priority
            matched_categories.sort(key=lambda x: x[1], reverse=True)
            top_category, top_priority, top_words = matched_categories[0]

            # Generate concise summary
            first_line = raw_text.split("\n")[0][:120].strip()
            summary = f"[{top_category.upper()}] {first_line}"

            all_matched_keywords = []
            for _, _, words in matched_categories:
                all_matched_keywords.extend(words)

            return FilterResult(
                is_relevant=True,
                priority=top_priority,
                category=top_category,
                matched_keywords=list(set(all_matched_keywords)),
                summary=summary,
            )

        # Step 3: Check for attachments or links in substantial messages
        has_url = bool(re.search(r"https?://\S+", raw_text))
        if message.has_media or has_url:
            if len(raw_text) >= 15:
                first_line = raw_text.split("\n")[0][:120].strip()
                summary = f"[DOCUMENT/LINK] {first_line or 'Вложение / ссылка'}"
                return FilterResult(
                    is_relevant=True,
                    priority=1,
                    category="attachment",
                    matched_keywords=["media" if message.has_media else "link"],
                    summary=summary,
                )

        return FilterResult(
            is_relevant=False,
            priority=1,
            category="general",
            summary="No trigger patterns matched",
        )
