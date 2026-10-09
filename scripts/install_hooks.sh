#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="${REPO_DIR}/.githooks"

# rev-parse поддерживает и обычные репозитории, и worktree/submodule (там .git - файл)
if ! git -C "${REPO_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "Ошибка: ${REPO_DIR} не является Git-репозиторием" >&2
    exit 1
fi

if [ ! -f "${HOOKS_DIR}/pre-commit" ]; then
    echo "Ошибка: не найден файл ${HOOKS_DIR}/pre-commit" >&2
    exit 1
fi

# Тот же порядок поиска Python, что и в .githooks/pre-commit
PYTHON_BIN=""
for candidate in "${VIRTUAL_ENV:+${VIRTUAL_ENV}/bin/python}" "${REPO_DIR}/backend/.venv/bin/python" "${REPO_DIR}/.venv/bin/python" "/opt/chat-app/backend/.venv/bin/python" "/opt/assistant-core/.venv/bin/python"; do
    if [ -n "${candidate}" ] && [ -x "${candidate}" ]; then
        PYTHON_BIN="${candidate}"
        break
    fi
done
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Без assistant_shared hook упал бы при каждом коммите: лучше отказать в установке сразу
if ! "${PYTHON_BIN}" -c "import assistant_shared.security" >/dev/null 2>&1; then
    echo "Ошибка: ${PYTHON_BIN} не умеет импортировать assistant_shared.security; установите пакет assistant-shared" >&2
    exit 1
fi

chmod +x "${HOOKS_DIR}/pre-commit"

PREVIOUS_HOOKS_PATH="$(git -C "${REPO_DIR}" config --get core.hooksPath || true)"
if [ -n "${PREVIOUS_HOOKS_PATH}" ] && [ "${PREVIOUS_HOOKS_PATH}" != ".githooks" ]; then
    echo "⚠️  Внимание: core.hooksPath был '${PREVIOUS_HOOKS_PATH}', заменяется на '.githooks' (прежние хуки перестанут вызываться)" >&2
fi
git -C "${REPO_DIR}" config core.hooksPath .githooks

echo "✅ Pre-commit hook успешно установлен в ${REPO_DIR} (core.hooksPath = .githooks)"
