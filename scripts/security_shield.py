#!/usr/bin/env python3
"""Security Shield CLI Wrapper (SEC-02)."""

import sys
from pathlib import Path

try:
    from assistant_shared.security import audit_repository, CORPORATE_NDA_KEYWORDS
except ImportError:
    shared_path = Path("/opt/assistant-shared")
    if shared_path.is_dir() and str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from assistant_shared.security import audit_repository, CORPORATE_NDA_KEYWORDS

__all__ = ["audit_repository", "CORPORATE_NDA_KEYWORDS"]

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Security Shield: scan staged (default) or all tracked files.")
    parser.add_argument("path", nargs="?", default=".", help="repository path (default: current directory)")
    parser.add_argument("--all", action="store_true", help="scan all tracked files instead of staged ones")
    args = parser.parse_args()  # unknown flags exit with code 2 (fail-closed), never treated as a path
    sys.exit(audit_repository(Path(args.path).resolve(), check_staged_only=not args.all))
