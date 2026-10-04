#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="${REPO_DIR}/.githooks"
GIT_DIR="${REPO_DIR}/.git"

if [ ! -d "${GIT_DIR}" ]; then
    echo "Ошибка: ${REPO_DIR} не является Git-репозиторием" >&2
    exit 1
fi

mkdir -p "${HOOKS_DIR}"
chmod +x "${HOOKS_DIR}/pre-commit"
git -C "${REPO_DIR}" config core.hooksPath .githooks

echo "✅ Pre-commit hook успешно установлен в ${REPO_DIR} (core.hooksPath = .githooks)"
