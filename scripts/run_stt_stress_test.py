"""Stress test harness for STT (VoiceProcessor) on 15-minute Russian audio with Ground Truth comparison."""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
import resource

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.brain.voice import VoiceProcessor
from src.brain.debrief_parser import DebriefParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stt_stress_test")


def normalize_text(text: str) -> str:
    """Normalize text for lexical metrics: lowercase, strip punctuation and extra spaces."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


import difflib


def compute_edit_distance_words(seq1: list, seq2: list) -> int:
    """Compute Levenshtein distance using O(M) memory 2-row buffer."""
    n, m = len(seq1), len(seq2)
    prev = list(range(m + 1))
    for i, x in enumerate(seq1, 1):
        curr = [i] * (m + 1)
        for j, y in enumerate(seq2, 1):
            if x == y:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr
    return prev[m]


def calculate_wer(reference: str, hypothesis: str) -> dict:
    """Compute Word Error Rate (WER)."""
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()

    dist = compute_edit_distance_words(ref_words, hyp_words)
    wer = dist / max(1, len(ref_words))
    accuracy = max(0.0, 1.0 - wer)

    return {
        "wer": round(wer, 4),
        "accuracy_pct": round(accuracy * 100, 2),
        "ref_word_count": len(ref_words),
        "hyp_word_count": len(hyp_words),
        "edit_distance": dist,
    }


def calculate_cer(reference: str, hypothesis: str) -> dict:
    """Compute Character Error Rate (CER) and character similarity ratio."""
    ref_clean = normalize_text(reference).replace(" ", "")
    hyp_clean = normalize_text(hypothesis).replace(" ", "")

    matcher = difflib.SequenceMatcher(None, ref_clean, hyp_clean)
    sim_ratio = matcher.ratio()
    cer = round(max(0.0, 1.0 - sim_ratio), 4)

    return {
        "cer": cer,
        "accuracy_pct": round(sim_ratio * 100, 2),
        "ref_char_count": len(ref_clean),
        "hyp_char_count": len(hyp_clean),
    }


async def run_stress_test():
    bench_dir = Path("/opt/assistant-core/data/benchmarks")
    audio_path = bench_dir / "night3_15min.mp3"
    txt_path = bench_dir / "night3_ground_truth.txt"

    if not audio_path.exists() or not txt_path.exists():
        raise FileNotFoundError(f"Benchmark files missing in {bench_dir}")

    audio_bytes = audio_path.read_bytes()
    ground_truth_text = txt_path.read_text(encoding="utf-8")
    audio_duration_sec = 873.7  # 14 minutes 33.7 seconds

    logger.info("=== STARTING STT STRESS TEST ===")
    logger.info("Audio size: %d bytes (%.2f MB), duration: %.1f sec (~14.5 min)", len(audio_bytes), len(audio_bytes) / 1024 / 1024, audio_duration_sec)
    logger.info("Ground truth word count: %d words, char count: %d", len(ground_truth_text.split()), len(ground_truth_text))

    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    vp = VoiceProcessor()
    t_start = time.perf_counter()

    logger.info("Triggering VoiceProcessor.process_voice...")
    stt_res = await vp.process_voice(
        voice_bytes=audio_bytes,
        mime_type="audio/mp3",
        duration_seconds=int(audio_duration_sec),
    )
    t_elapsed = time.perf_counter() - t_start
    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    if not stt_res.success:
        logger.error("STT failed: %s", stt_res.error)
        return False

    transcription = stt_res.transcription
    logger.info("STT finished in %.2f sec (RTF: %.2fx faster than realtime)", t_elapsed, audio_duration_sec / t_elapsed)
    logger.info("Engine used: %s, Transcription length: %d words", stt_res.engine, len(transcription.split()))

    # Calculate metrics
    wer_res = calculate_wer(ground_truth_text, transcription)
    cer_res = calculate_cer(ground_truth_text, transcription)

    logger.info("WER: %.2f%% (Accuracy: %.2f%%)", wer_res["wer"] * 100, wer_res["accuracy_pct"])
    logger.info("CER: %.2f%% (Accuracy: %.2f%%)", cer_res["cer"] * 100, cer_res["accuracy_pct"])

    # Key entities recall (Names, places from Dostoevsky Night 3)
    key_entities = ["настенька", "петербург", "письмо", "старость", "сегодня", "слезы", "счастье"]
    found_entities = [e for e in key_entities if e in transcription.lower()]
    entity_recall_pct = round(len(found_entities) / len(key_entities) * 100, 1)

    logger.info("Key Entities Recall: %d/%d (%.1f%%): %s", len(found_entities), len(key_entities), entity_recall_pct, found_entities)

    # 2. Test DebriefParser semantic deconstruction on reflection
    logger.info("Testing semantic deconstruction with DebriefParser...")
    debrief_parser = DebriefParser()
    debrief_sample = (
        "Сегодня был продуктивный день. С утра провел две пары по волновой оптике у группы 2341, "
        "студенты хорошо сдали предварительные протоколы по интерферометру Майкельсона. "
        "Потом заехал в Тидекс, закончили юстировку террагерцового спектрометра, переработка составила 1.5 часа. "
        "Завтра нужно срочно подписать служебную записку в отделе кадров ГУАП и созвониться с Новиковой по эффективному контракту. "
        "Дипломник Алексей обещал прислать доработанный расчетный раздел к вечеру четверга. "
        "В целом усталость средняя, настроение рабочее, приборная часть радует стабильностью."
    )
    debrief_result = await debrief_parser.parse_debrief(debrief_sample)

    report_data = {
        "audio_benchmark": {
            "source": "LibriVox White Nights Night 3 (Dostoevsky)",
            "file_size_bytes": len(audio_bytes),
            "file_size_mb": round(len(audio_bytes) / 1024 / 1024, 2),
            "duration_seconds": audio_duration_sec,
            "engine": stt_res.engine,
            "elapsed_seconds": round(t_elapsed, 2),
            "realtime_factor": round(audio_duration_sec / t_elapsed, 2),
            "mem_before_mb": round(mem_before, 2),
            "mem_after_mb": round(mem_after, 2),
            "ram_delta_mb": round(mem_after - mem_before, 2),
            "wer": wer_res,
            "cer": cer_res,
            "key_entities": {
                "tested": key_entities,
                "found": found_entities,
                "recall_pct": entity_recall_pct,
            },
            "transcription_snippet": transcription[:300] + "...",
        },
        "semantic_reflection_benchmark": {
            "completed_tasks_count": len(debrief_result.completed_tasks),
            "completed_tasks": [t.model_dump() for t in debrief_result.completed_tasks],
            "new_tasks_count": len(debrief_result.new_tasks),
            "new_tasks": [t.model_dump() for t in debrief_result.new_tasks],
            "waiting_for_count": len(debrief_result.waiting_for_items),
            "waiting_for": [w.model_dump() for w in debrief_result.waiting_for_items],
            "journal_done_summary": debrief_result.journal_entry.done_summary,
            "journal_insights": debrief_result.journal_entry.key_insights,
        },
    }

    report_path = bench_dir / "stress_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    logger.info("Saved full benchmark report to %s", report_path)
    return report_data


if __name__ == "__main__":
    res = asyncio.run(run_stress_test())
    print("\n=== BENCHMARK COMPLETED SUCCESSFULLY ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
