---
phase: 05-retro-verifikatsiya-v2-0
type: evidence
requirement: DAT-03
collected: 2026-10-18T22:09:30Z
---

# Протокол прогонов DAT-03

Тест: `/opt/chat-app/backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes`. Тест и код не менялись, skip, xfail и deselected не применялись, повторов сбойных прогонов нет (D-08, D-10).

## Среда

| Параметр | Значение |
|---|---|
| nproc | 1 |
| MemAvailable до прогонов | 873 МБ (перед пробой 858 МБ, перед порогом 450 МБ) |
| Python (venv chat-app) | Python 3.12.3 |
| pytest (venv chat-app) | pytest 9.1.1 |
| HEAD chat-app | `011f9c235c40aca48be33efe0c1b120b1d96e1b5` |
| Последний коммит файла теста | `fd08aa57b2a2e21846cc06ace70232ac479aded7` |
| assistant-worker до прогонов | ActiveState=active, NRestarts=0, ActiveEnterTimestamp=Sun 2026-10-18 17:14:12 UTC |
| chat-app `git status --porcelain --ignored` до прогонов | 20 строк; неотслеживаемый `.watchdog_disabled` существовал до начала работ (снимок в каталоге проб) |

Каталог проб вне репозиториев: `/var/tmp/gsd-phase05-probes/dat03/` (права 0700): `run_one.sh` (один прогон), `rows.md` (строки таблицы), `logs/` (лог каждого прогона), `tmp/` (basetemp, удаляется после каждого прогона), `load/` (логи полных прогонов набора под нагрузкой). В коммит не входит.

## Команда одного прогона

```bash
cd /opt/chat-app && PYTHONDONTWRITEBYTECODE=1 timeout 300 backend/.venv/bin/pytest -p no:cacheprovider -q --basetemp=/var/tmp/gsd-phase05-probes/dat03/tmp/<режим>-<номер> backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes
```

Правило успеха: код возврата 0 и строка `1 passed` в логе. Иначе FAIL; код 124 означает таймаут 300 с. Первая строка ошибки берётся из лога по шаблону `Error|locked|FAILED|timeout|assert`, символ `|` заменён на `/`, длина обрезана до 200 символов. Полный текст сбоя приводится в разделе «Тексты ошибок».

## Таблица прогонов

Строка `probe-00` — проба харнесса, в 30 прогонов не входит.

| Прогон | Режим | rc | сек | Итог | Первая строка ошибки |
|---|---|---|---|---|---|
| probe-00 | probe | 0 | 2.3 | OK | - |
| free-01 | free | 0 | 1.8 | OK | - |
| free-02 | free | 0 | 1.8 | OK | - |
| free-03 | free | 0 | 2.6 | OK | - |
| free-04 | free | 0 | 1.7 | OK | - |
| free-05 | free | 0 | 2.0 | OK | - |
| free-06 | free | 0 | 1.5 | OK | - |
| free-07 | free | 0 | 1.6 | OK | - |
| free-08 | free | 0 | 1.6 | OK | - |
| free-09 | free | 0 | 2.5 | OK | - |
| free-10 | free | 0 | 2.4 | OK | - |
| free-11 | free | 0 | 2.5 | OK | - |
| free-12 | free | 0 | 1.8 | OK | - |
| free-13 | free | 0 | 2.0 | OK | - |
| free-14 | free | 0 | 1.7 | OK | - |
| free-15 | free | 0 | 1.6 | OK | - |
| free-16 | free | 0 | 1.7 | OK | - |
| free-17 | free | 0 | 2.1 | OK | - |
| free-18 | free | 0 | 1.4 | OK | - |
| free-19 | free | 0 | 1.4 | OK | - |
| free-20 | free | 0 | 1.6 | OK | - |
| free-21 | free | 0 | 18.5 | OK | - |
| free-22 | free | 0 | 3.3 | OK | - |
| free-23 | free | 0 | 3.4 | OK | - |
| free-24 | free | 0 | 4.2 | OK | - |
| free-25 | free | 0 | 6.3 | OK | - |
| free-26 | free | 0 | 15.5 | OK | - |
| free-27 | free | 1 | 1.6 | FAIL | sqlite3.OperationalError: database is locked |
| free-28 | free | 0 | 1.6 | OK | - |
| free-29 | free | 0 | 1.4 | OK | - |
| free-30 | free | 0 | 1.7 | OK | - |
| load-01 | load | 0 | 2.9 | OK | - |
| load-02 | load | 0 | 2.3 | OK | - |
| load-03 | load | 0 | 2.1 | OK | - |
| load-04 | load | 0 | 34.1 | OK | - |
| load-05 | load | 0 | 2.2 | OK | - |
| load-06 | load | 0 | 1.6 | OK | - |
| load-07 | load | 0 | 1.9 | OK | - |
| load-08 | load | 0 | 1.6 | OK | - |
| load-09 | load | 0 | 1.9 | OK | - |
| load-10 | load | 0 | 1.8 | OK | - |
| load-11 | load | 0 | 1.7 | OK | - |
| load-12 | load | 0 | 1.9 | OK | - |
| load-13 | load | 0 | 1.8 | OK | - |
| load-14 | load | 0 | 1.9 | OK | - |
| load-15 | load | 0 | 1.9 | OK | - |
| load-16 | load | 0 | 1.8 | OK | - |
| load-17 | load | 0 | 2.1 | OK | - |
| load-18 | load | 0 | 1.8 | OK | - |
| load-19 | load | 0 | 2.1 | OK | - |
| load-20 | load | 0 | 1.8 | OK | - |
| load-21 | load | 0 | 2.0 | OK | - |
| load-22 | load | 0 | 1.3 | OK | - |
| load-23 | load | 0 | 1.3 | OK | - |
| load-24 | load | 0 | 1.7 | OK | - |
| load-25 | load | 0 | 1.7 | OK | - |
| load-26 | load | 0 | 1.6 | OK | - |
| load-27 | load | 0 | 1.3 | OK | - |
| load-28 | load | 0 | 2.0 | OK | - |
| load-29 | load | 0 | 1.8 | OK | - |
| load-30 | load | 0 | 1.2 | OK | - |

## Итоги

### Свободная система (режим free)

- Прогонов 30 (free-01..free-30), сбоев **1 из 30** (free-27: rc 1, `sqlite3.OperationalError: database is locked`), успешных 29.
- Секунды на прогон: минимум 1.4, медиана 1.8, максимум 18.5, среднее 3.16. Замедленные прогоны free-21 (18.5 с) и free-26 (15.5 с) записаны как наблюдение, причина не исследовалась.
- Прогоны шли строго по одному (`run_free.sh`, синхронно, без фоновых процессов); параллельных pytest и gate не было.
- Сверка `git -C /opt/chat-app status --porcelain --ignored` после серии совпала со снимком до прогонов (md5 `c75b75918019ac0adda115962b3eab8b`).

### Под нагрузкой (режим load)

- Прогонов 30 (load-01..load-30), сбоев **0 из 30**, успешных 30. Прерываний по памяти не было: минимум MemAvailable за всё окно нагрузки 801 МБ, порог 250 МБ не достигнут, флаг MEMLOW не ставился.
- Секунды на прогон: минимум 1.2, медиана 1.8, максимум 34.1 (load-04, наблюдение без анализа), среднее 2.90.
- Полные прогоны набора chat-app (`backend/tests`, `nice -n 10`, timeout 1800 с): завершено K = 1 (`load/full-1.log`), из них J = 0 с падением целевого теста. Полный прогон: 279 passed, 3 warnings, 168 с, rc 0. Других падений в нём нет. Этот один полный прогон шёл поверх всего окна из 30 целевых прогонов, поэтому нагрузка была на протяжении всей серии, но число полных прогонов мало.
- Целевые прогоны запускались без `nice` (как и в плане, `nice -n 10` относится к циклу полных прогонов). Прогоны шли строго по одному: цикл полных прогонов и целевые прогоны не пересекались с другими pytest и gate.
- Состояние `assistant-worker` до и после совпало: ActiveState=active, NRestarts=0, ActiveEnterTimestamp=Sun 2026-10-18 17:14:12 UTC (`worker-before.txt` и `worker-after.txt`, без изменений).
- Сверка `git -C /opt/chat-app status --porcelain --ignored` после серии совпала со снимком до прогонов (md5 `c75b75918019ac0adda115962b3eab8b`). Остатков процессов pytest нет, каталог basetemp `dat03/tmp` пуст.
- Боевая БД `/opt/assistant-core/data/assistant.db` не открывалась и не хешировалась; тест работал на `tmp_path` в каталоге проб.

### Итого по режимам

- Свободная система: 1 из 30 сбоев (free-27, `database is locked` при `PRAGMA journal_mode = WAL` в фабрике соединений).
- Под нагрузкой: 0 из 30 сбоев; полных прогонов K = 1, в них J = 0.
- Всего целевых прогонов 60 (30 + 30) плюс проба probe-00, которая в 60 не входит.

## Тексты ошибок

### free-27 (режим free, rc 1, 1.6 с)

Выдержка из `logs/free-27.log` (полный лог 64 строки, без значений из окружения):

```text
multiprocessing.pool.RemoteTraceback:
"""
Traceback (most recent call last):
  File "/usr/lib/python3.12/multiprocessing/pool.py", line 125, in worker
    result = (True, func(*args, **kwds))
                    ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/multiprocessing/pool.py", line 48, in mapstar
    return list(map(*args))
           ^^^^^^^^^^^^^^^^
  File "/opt/chat-app/backend/tests/test_concurrent_write.py", line 20, in _worker_write_batch
    with get_sync_connection(db_path) as conn:
  File "/usr/lib/python3.12/contextlib.py", line 137, in __enter__
    return next(self.gen)
           ^^^^^^^^^^^^^^
  File "/opt/assistant-shared/assistant_shared/db/connection.py", line 64, in get_sync_connection
    conn.execute("PRAGMA journal_mode = WAL;")
sqlite3.OperationalError: database is locked
"""

The above exception was the direct cause of the following exception:

...
backend/tests/test_concurrent_write.py:69: 
...
pool.py:774: OperationalError
=========================== short test summary info ============================
FAILED backend/tests/test_concurrent_write.py::test_concurrent_write_two_processes
1 failed in 0.66s
```

Строка `E   sqlite3.OperationalError: database is locked` в хвосте pytest-трассы совпадает с исключением выше; промежуточные кадры pytest опущены как повтор.

### load (режим load, полные прогоны набора)

Сбоев целевого теста под нагрузкой нет (0 из 30). Полные прогоны набора: K = 1, J = 0, сбоев других тестов нет (279 passed).

## Вердикт DAT-03

**Вердикт DAT-03:** gap

Частоты: free 1/30, load 0/30, в полных прогонах под нагрузкой J из K: 0 из 1.

Основание: критерий D-08 требует 0 сбоев из 30 в каждом режиме и J = 0. В режиме free зафиксирован 1 сбой (free-27, полный текст выше), поэтому стабильность не подтверждена, несмотря на 0 сбоев под нагрузкой.

Связь с фабрикой соединений: тест использует `get_sync_connection` из `/opt/assistant-shared/assistant_shared/db/connection.py` (timeout=30.0 с, `PRAGMA busy_timeout = 30000`, `PRAGMA journal_mode = WAL` на каждом соединении). Сбой free-27 возник на строке 64 этого файла (`PRAGMA journal_mode = WAL`) при открытии соединения, хотя `busy_timeout` задан; причина не исследовалась (D-10).

Класс по D-09: целостность данных; предложение: требование DAT-05, оформляется планом 05-08; текст ошибки выше (раздел «Тексты ошибок», free-27).
