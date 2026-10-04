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
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    staged_only = "--all" not in sys.argv
    sys.exit(audit_repository(target, check_staged_only=staged_only))
