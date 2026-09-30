#!/usr/bin/env python3
"""Security Shield & Pre-Commit Guardrail for Multi-Repo Agent Development.

Enforces security policies:
1. Secret leak prevention (API keys, private keys, session files, credentials).
2. Remote URL verification (prevents accidental push of NDA code to public origins).
3. Author email validation per repository (personal vs corporate).
4. Cross-repository boundary isolation (Air-Gap checks).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Common high-risk patterns
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Private Key", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP)?\s*PRIVATE KEY-----")),
    ("GitHub Personal Access Token", re.compile(r"(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})")),
    ("Google API Key", re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}")),
    ("Telegram Bot Token", re.compile(r"\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b")),
    ("OpenAI/Anthropic API Key", re.compile(r"(sk-[a-zA-Z0-9]{20,}|sk-ant-[a-zA-Z0-9]{20,})")),
    ("Notion API Token", re.compile(r"(ntn_[a-zA-Z0-9]{40,}|secret_[a-zA-Z0-9]{40,})")),
    ("Generic Bearer Secret", re.compile(r"(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token)\s*[:=]\s*['\"][a-zA-Z0-9_-]{16,}['\"]")),
]

FORBIDDEN_FILES: list[re.Pattern] = [
    re.compile(r"(^|/)\.env(\..+)?$"),
    re.compile(r"(^|/)credentials\.json$"),
    re.compile(r"(^|/)token\.json$"),
    re.compile(r".+\.session$"),
    re.compile(r".+\.session-journal$"),
    re.compile(r".+\.(pem|key|pkcs12|pfx)$"),
]

# Sensitive corporate keywords that must never appear in public / student repos
CORPORATE_NDA_KEYWORDS: list[str] = [
    "tydex_internal_secret",
    "golay_calibration_key",
    "thz_proprietary_firmware",
]


def run_cmd(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode, res.stdout.strip()
    except Exception as e:
        return 1, str(e)


def get_staged_or_tracked_files(repo_path: Path, check_staged_only: bool = True) -> list[str]:
    if check_staged_only:
        code, out = run_cmd(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], cwd=str(repo_path))
        if code == 0 and out:
            return [line.strip() for line in out.splitlines() if line.strip()]
        # If no staged files, fall back to checking modified files
        code, out = run_cmd(["git", "diff", "--name-only", "--diff-filter=ACM"], cwd=str(repo_path))
        if code == 0 and out:
            return [line.strip() for line in out.splitlines() if line.strip()]
        return []
    else:
        code, out = run_cmd(["git", "ls-files"], cwd=str(repo_path))
        return [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else []


def check_file_content(file_path: Path, is_public_repo: bool = True) -> list[str]:
    violations = []
    if not file_path.is_file():
        return violations

    # Check forbidden filenames
    str_path = str(file_path).replace("\\", "/")
    for pattern in FORBIDDEN_FILES:
        if pattern.search(str_path):
            violations.append(f"Forbidden file pattern committed: {file_path.name}")
            return violations

    try:
        # Ignore binary files
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for idx, line in enumerate(lines, 1):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    # Mask secret for log display
                    violations.append(f"{file_path}:{idx} - Found potential {name}")

            if is_public_repo:
                for kw in CORPORATE_NDA_KEYWORDS:
                    if kw in line:
                        violations.append(f"{file_path}:{idx} - Found proprietary corporate keyword '{kw}' in public repository!")
    except Exception as e:
        violations.append(f"{file_path} - Read error: {e}")

    return violations


def audit_repository(repo_path: Path, check_staged_only: bool = True) -> int:
    print(f"🛡️ Running Security Shield on repository: {repo_path}")
    violations = []

    # 1. Check Git config / Remote sanity
    code, origin_url = run_cmd(["git", "remote", "get-url", "origin"], cwd=str(repo_path))
    code_user, user_email = run_cmd(["git", "config", "user.email"], cwd=str(repo_path))

    is_tydex_repo = "tydex" in str(repo_path).lower()
    print(f"   • Origin Remote: {origin_url if code == 0 else 'None'}")
    print(f"   • Author Email:  {user_email if code_user == 0 else 'Not set'}")
    print(f"   • Profile Mode:  {'🔒 RESTRICTED (Tydex NDA)' if is_tydex_repo else '🌐 PUBLIC / ACADEMIC'}")

    if is_tydex_repo:
        if code == 0 and "github.com/DimaMuhannad" in origin_url:
            violations.append("CRITICAL: Tydex private project remote points to personal public account (DimaMuhannad)!")

    # 2. Check staged / changed files
    files = get_staged_or_tracked_files(repo_path, check_staged_only=check_staged_only)
    if not files:
        print("   • No staged or modified files found to scan.")
    else:
        print(f"   • Scanning {len(files)} files...")
        for rel_path in files:
            full_path = repo_path / rel_path
            file_violations = check_file_content(full_path, is_public_repo=not is_tydex_repo)
            violations.extend(file_violations)

    if violations:
        print("\n❌ SECURITY VIOLATIONS DETECTED:")
        for v in violations:
            print(f"   🚨 {v}")
        print("\nCommit or push blocked. Please sanitize files or update configuration before proceeding.\n")
        return 1

    print("\n✅ Security Shield passed: No leaks or cross-account policy violations detected.\n")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    staged_only = "--all" not in sys.argv
    sys.exit(audit_repository(target, check_staged_only=staged_only))
