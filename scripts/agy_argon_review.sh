#!/usr/bin/env bash
# Второй независимый ревьюер: Argon (agy, аккаунт acc2) на чистом клоне репозитория.
# Использование: scripts/agy_argon_review.sh <BASE_COMMIT> [--dry-run] [--account acc2] [--model gemini-4-argon-high]
#   [--worktree]      копия рабочего дерева (с незакоммиченным), секреты и БД исключены всегда
#   [--skip-shield]   не отказывать при находках security_shield (остаётся предупреждение)
#   [--timeout 60m] [--max-findings 30]
# Результат: .planning/REVIEW-ARGON-<дата>.md (в рабочем дереве, без коммита).
# Только для не-NDA репозиториев: содержимое NDA во внешнюю LLM не уходит (ядро проекта).
set -euo pipefail

BASE="${1:-}"; shift || true
ACC="acc2"; MODEL="gemini-4-argon-high"; DRY=0; WT=0; SKIP_SHIELD=0; TMO="60m"; MAXF=30
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --account) ACC="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --worktree) WT=1; shift ;;
    --skip-shield) SKIP_SHIELD=1; shift ;;
    --timeout) TMO="$2"; shift 2 ;;
    --max-findings) MAXF="$2"; shift 2 ;;
    *) echo "Неизвестный аргумент: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$BASE" ]] || { echo "Нужен BASE_COMMIT: scripts/agy_argon_review.sh <commit>" >&2; exit 2; }

REPO="$(git rev-parse --show-toplevel)"
git -C "$REPO" rev-parse --verify "$BASE^{commit}" >/dev/null

# Air-Gap: репозиторий с NDA-признаками во внешнюю модель не отправляется (fail-closed).
ORIGIN="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
if printf '%s %s' "$REPO" "$ORIGIN" | grep -qiE 'nda|tydex|corporate|restricted'; then
  echo "ОТКАЗ (Air-Gap): репозиторий похож на NDA/корпоративный, отправка запрещена" >&2; exit 3
fi
if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]]; then
  echo "Предупреждение: в рабочем дереве есть незакоммиченные правки, ревью увидит только HEAD" >&2
fi

WORK="$(mktemp -d /var/tmp/argon-review.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
git clone -q "$REPO" "$WORK/clone"
git -C "$WORK/clone" remote remove origin
if [[ "$WT" == 1 ]]; then
  # Незакоммиченные правки поверх клона; секреты, БД и сессии исключены всегда.
  rsync -a --exclude='.git/' --exclude='.env' --exclude='.env.*' --exclude='*.db' --exclude='*.db-*' \
    --exclude='*.session' --exclude='credentials.json' --exclude='token.json' --exclude='data/' \
    --exclude='.venv/' --exclude='__pycache__/' "$REPO"/ "$WORK/clone"/
  cp "$REPO/.env.example" "$WORK/clone/.env.example" 2>/dev/null || true
fi

# Секреты: гейт безопасности на клоне; при находках отказ (код 4).
if [[ -f "$WORK/clone/scripts/security_shield.py" ]]; then
  if ! (cd "$WORK/clone" && "$REPO/.venv/bin/python3" scripts/security_shield.py >/dev/null 2>&1); then
    if [[ "$SKIP_SHIELD" == 1 ]]; then
      echo "ПРЕДУПРЕЖДЕНИЕ: security_shield нашёл проблемы, продолжаю по --skip-shield" >&2
    else
      echo "ОТКАЗ: security_shield нашёл проблемы в клоне, отправка отменена (обойти: --skip-shield)" >&2; exit 4
    fi
  fi
fi

TASK="$WORK/task.txt"
cat > "$TASK" <<EOF
Задача: независимое состязательное ревью кода. Только чтение: ничего не изменяй, не создавай и не удаляй, не запускай сервисы, не читай .env и *.db. Рабочая директория — копия репозитория, правила в CLAUDE.md.
Смотри изменения: git diff $BASE..HEAD (src, config, scripts). Для проверки читай tests/.
Ищи реальные баги: обходы инвариантов безопасности (NDA Air-Gap fail-closed, HITL-подтверждение до необратимых действий), гонки, пропущенные ветки ошибок, часовые пояса, утечки в логи, нарушения async, расхождения кода и тестов. Не пиши про стиль.
Перед тем как заявить дефект, проверь по коду, что он реален и не закрыт в другом месте (в том числе в общей библиотеке); если не проверил, ставь уверенность «низкая».
Формат (по-русски, максимум $MAXF пунктов, серьёзные первыми):
N. [critical|high|medium|low] файл:строка — суть одним предложением. Сценарий: вход -> неверный результат. Уверенность: высокая|средняя|низкая.
В конце одной строкой: сколько файлов прочитал и что не проверил.
EOF

if [[ "$DRY" == 1 ]]; then
  echo "DRY-RUN: клон $WORK/clone подготовлен, задача:"; cat "$TASK"; trap - EXIT; exit 0
fi

OUT="$REPO/.planning/REVIEW-ARGON-$(date +%Y%m%d-%H%M).md"
agy-subagent "$ACC" -C "$WORK/clone" -m "$MODEL" -t "$TMO" "$(cat "$TASK")" > "$OUT"
echo "Готово: $OUT ($(wc -c < "$OUT") байт). Пункты проверь по коду до принятия."
