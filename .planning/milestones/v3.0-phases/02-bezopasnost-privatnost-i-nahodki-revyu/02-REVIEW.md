---
phase: 02-bezopasnost-privatnost-i-nahodki-revyu
reviewed: 2026-10-10T00:00:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - /opt/assistant-core/scripts/auth_google.py
  - /opt/assistant-core/scripts/deploy.py
  - /opt/assistant-core/scripts/gate.py
  - /opt/assistant-core/scripts/security_shield.py
  - /opt/assistant-core/src/brain/dialog_safety.py
  - /opt/assistant-core/src/brain/intent_router.py
  - /opt/assistant-core/src/brain/secretary_dialog.py
  - /opt/assistant-core/src/connectors/gdrive/client.py
  - /opt/assistant-core/src/main.py
  - /opt/assistant-core/src/notifier/bot_handler.py
  - /opt/assistant-core/src/persona/models.py
  - /opt/assistant-core/src/persona/notices.py
  - /opt/assistant-core/src/storage/db.py
  - /opt/assistant-core/tests/live_db_guard.py
  - /opt/assistant-shared/assistant_shared/security/__init__.py
  - /opt/assistant-shared/assistant_shared/security/auditor.py
  - /opt/assistant-shared/assistant_shared/security/patterns.py
  - /opt/assistant-shared/assistant_shared/security/rules.py
  - /opt/assistant-shared/assistant_shared/security/scanner.py
  - /opt/assistant-shared/scripts/security_shield.py
  - /opt/chat-app/backend/app/api/v1/security.py
  - /opt/chat-app/scripts/agy_cross_ai.sh
  - /opt/chat-app/scripts/security_shield.py
findings:
  critical: 0
  warning: 6
  info: 5
  total: 11
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-10
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Reviewed the changed regions of all 23 files across assistant-core, assistant-shared and chat-app (diffs from the phase base commits, plus full reads of the security library, `live_db_guard.py`, the gdrive client, the new PRIV-01 code and the deploy/gate changes). No structural-findings block and no external-reviewer evidence were provided. The persona file, `.env` files and the live DB were not read; the persona workspace `path` values were checked only by count (all absolute).

Overall the phase delivers its stated goals and the main paths hold up:

- SAFE-01: the only code path that calls `clear_dialog_history` is the `dlg:confirm_clear` callback, reachable from the `/clear` HITL card. Text, voice, the fast router and the secretary engine all end in a warning. I found no bypass that wipes memory without the card.
- PRIV-01: the flag is set only after a successful send. The key prefix is validated. There are no duplicates in the single-loop worker. The notice also appears in `/help`.
- Workspace matching is real-path based, uses the strictest clearance and fails closed on unreadable data.
- The `deploy.py` state/backup hardening (O_NOFOLLOW, fstat on the descriptor, atomic replace) is sound.

No finding reaches BLOCKER level. The remaining defects are fail-open edges in the data-driven NDA rules (validation does not enforce the invariants the library assumes), two gate/adapter checks that are weaker than their documentation claims, and a validate-then-open race in the Drive client.

## Warnings

### WR-01: A restricted_nda workspace with blank-only keywords silently disables all NDA word protection

**File:** `/opt/assistant-core/src/persona/models.py:71-78` (with `/opt/assistant-shared/assistant_shared/security/rules.py:_clean_keywords`)
**Issue:** `WorkspaceConfig._nda_requires_rules` only checks that `forbidden_keywords` and `forbidden_remote_substrings` are non-empty lists. A list such as `[""]` or `["  "]` passes validation. `_clean_keywords` then drops blank items, so `collect_protected_keywords` returns `()`. The result is that no repository and no web audit searches for NDA words, and the audit is green. The validator comment says it exists so "empty data cannot silently switch off NDA blocking", but this input defeats it. The remote side is covered at runtime: `audit_repository` raises "правила remote не заданы" for blank substrings. The keyword side has no equivalent guard in `audit_repository` or `audit_path`.
**Fix:** Require at least one non-blank item in both lists, and strip the items:
```python
@model_validator(mode="after")
def _nda_requires_rules(self) -> "WorkspaceConfig":
    if self.clearance == "restricted_nda":
        kws = [k for k in self.forbidden_keywords if k.strip()]
        subs = [s for s in self.forbidden_remote_substrings if s.strip()]
        if not (kws and subs):
            raise ValueError(f"пространство restricted_nda {self.id} без правил NDA")
    return self
```
As a library-side guard, `audit_repository` and `audit_path` should add a violation when an `restricted_nda` rule has `forbidden_keywords == ()`. The web path gets its rules from DB rows, so the library cannot rely on the Pydantic validator.

### WR-02: An NDA workspace whose path cannot be matched is silently treated as public; the NDA remote check is skipped

**File:** `/opt/assistant-shared/assistant_shared/security/rules.py:118-130` (`_matches_by_path`), `/opt/assistant-shared/assistant_shared/security/auditor.py:241-244`
**Issue:** `WorkspaceConfig.path` only has `min_length=1`. A relative path, `~/...`, or a path with an environment variable is a valid persona. `_matches_by_path` returns False for these without any diagnostic. If the workspace also has no `remote`, or the repo's remote differs, `match_workspace` returns None. `audit_repository` then prints only a warning and applies the public profile. The `forbidden_remote_substrings` check (NDA repo pushing to a personal account) is skipped, which is a fail-open. The current persona is fine (all four paths are absolute), but nothing enforces it.
**Fix:** Validate that `path` is absolute (after `expanduser` is rejected, not applied) for at least `restricted_nda` workspaces. In `audit_repository`, add a CRITICAL violation when any `restricted_nda` workspace has an unusable `path`, and not only when the current repo matched.

### WR-03: A repository matched to an NDA workspace is never checked for the words of other NDA workspaces

**File:** `/opt/assistant-shared/assistant_shared/security/auditor.py:273` and `:165` (`scan_keywords = ... if nda_rule is None ...`)
**Issue:** `keywords = [] if is_nda else list(collect_protected_keywords(workspace_data))` drops all keyword checks for an NDA repo, including the words of a different NDA workspace B. Only A's own words are legitimate there. Cross-client leakage between two NDA workspaces is exactly what the air-gap model wants to catch. The same applies to `audit_path` for the web audit (SECF-02 says "NDA words of other workspaces"). The checks only get weaker than the data allows, against the "security checks only get stricter" invariant. This is currently harmless with a single NDA workspace.
**Fix:** Exclude only the matched workspace's own words:
```python
own = set(nda_rule_for(ws).forbidden_keywords) if is_nda else set()
keywords = [k for k in collect_protected_keywords(workspace_data) if k not in own]
```
Apply the same idea in `audit_path` by passing the workspace's own words to subtract, or by passing the "other workspaces" set from the chat-app caller.

### WR-04: The gate's integrity relaxation still accepts test writes into the live DB

**File:** `/opt/assistant-core/scripts/gate.py:585-611` (`compare_integrity`), `:520-533` (`RUNTIME_DELETES_FROM`)
**Issue:** The relaxation applies when the hash changed, the worker is active and the DB mtime lies in the window. It then requires only (a) an identical schema digest and (b) no row-count decrease in tables outside `RUNTIME_DELETES_FROM`. Therefore the following all pass as green: any INSERT into any table (growth is explicitly allowed), any UPDATE (counts are unchanged), and any DELETE from `tasks`, `reminders`, `documents`, `projects`, `workspaces` and others in the list. A test that writes tasks or reminders into the live DB is the failure mode this check exists for, and it is accepted whenever the worker happens to write during the 10-minute pytest window. The remeasure also compares the two quiet-window hashes only to each other, not to `before`. WR-03 of phase 1 is closed in name, but the check only detects schema change and shrinkage in tables the runtime never deletes from.
**Fix:** Tighten what is allowed, not only what is detected. For example, keep per-table row counts and `max(rowid)` for the tables the worker is known to write (`email_messages`, `router_audit_log`, `dialog_history`, and similar), and require that tables the worker does not write in a cycle stay byte-identical (per-table content hash taken in the same `mode=ro` transaction). At minimum, document in the docstring and in `docs/` that the relaxation accepts growth and updates, so the green row is not read as "tests did not touch the live DB".

### WR-05: Drive download validates a resolved path, then opens it with a plain `open(..., "wb")` as root

**File:** `/opt/assistant-core/src/connectors/gdrive/client.py:28-52` (`_safe_upload_path`), `:157-166` (`download_file`)
**Issue:** `_safe_upload_path` calls `resolve()` and checks `dest.parent == UPLOADS_DIR.resolve()`. The check and the later `open(dest, "wb")` happen in different threads and moments, and `open` follows symlinks and truncates. Two consequences:
1. If `gdrive_<name>` already exists as a symlink inside `UPLOADS_DIR` that points at another file inside `UPLOADS_DIR`, `resolve()` returns the other file. The parent check passes and the daemon (root) overwrites an unrelated upload.
2. If anyone who can write into `/opt/chat-app/uploads` (the chat-app upload endpoint writes there) swaps `dest` for a symlink between the check and the open, the root daemon follows it anywhere.
Also, `download_file` buffers the whole file in `BytesIO` with no size cap, on a 2 GB host, for any file matched by name patterns like `name contains '.db'`, which includes files shared by other Drive users.
**Fix:** Write with `os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)` (or write to a private temp dir and `os.replace`), compare `fstat` of the descriptor with the expected directory, and refuse when `size` from Drive metadata exceeds a limit. Prefer a private `UPLOADS_DIR`-independent directory owned by the daemon.

### WR-06: The cross-AI adapter's PROTECTED list does not cover everything the gate executes

**File:** `/opt/chat-app/scripts/agy_cross_ai.sh:91-95`
**Issue:** The header claims the target's gate "can be trusted" because the gate file and its executed environment are protected. The environment list is incomplete. With `pytest.ini` having `testpaths = tests` and `pythonpath = .`, pytest also loads a root `conftest.py` and any `tests/**/conftest.py`, and imports `sitecustomize.py`/`usercustomize.py` placed on the path. None of these are in `PROTECTED`, and a patch that adds them is accepted. Any of them can alter the result of the gate (a `pytest_sessionfinish` that rewrites the exit status or the junit file, or a monkeypatch of the guard). The same applies to a new `tests/*.py` that is run by the gate's own pytest step; that part is inherent, but the conftest/sitecustomize hooks run before tests and can weaken the guard itself.
**Fix:** Protect `conftest.py` (root), `sitecustomize.py`, `usercustomize.py`, `tox.ini`, `setup.cfg` and `.coveragerc`, and treat any basename `conftest.py` at any depth as protected:
```python
def is_protected(path):
    if posixpath.basename(path) in ("conftest.py", "sitecustomize.py", "usercustomize.py"):
        return True
    ...
```

## Info

### IN-01: `_has_connected_mailbox` identifies mailboxes by exclusion of known keys

**File:** `/opt/assistant-core/src/main.py:200-227`
**Issue:** Any new dict-valued key added to `sync_all_accounts` (for example another stats block) that has no `status` and no `error` counts as a connected mailbox. That would show the PRIV-01 notice before any mailbox is connected, and it would set the "shown" flag permanently. All real account results carry an `"account"` key (`ingest_imap_account` and `ingest_gmail_account` set it even for the skipped case).
**Fix:** Select accounts positively: `if "account" not in value: continue`, and drop `_NON_ACCOUNT_RESULT_KEYS`.

### IN-02: Notice flag can repeat if `mark_notice_shown` fails after a successful send

**File:** `/opt/assistant-core/src/main.py:236-240`
**Issue:** The send is followed by `mark_notice_shown`. If the DB write raises (locked DB), the outer handler logs a warning and the notice is sent again each 15-minute cycle until the write succeeds. This is the safer direction (never lost), but there is no bound and no backoff.
**Fix:** Acceptable as is; optionally log at `error` when `mark_notice_shown` fails after delivery, so the repeat is visible.

### IN-03: `auth_google.py` imports `src.persona.notices` outside the fallback `try`

**File:** `/opt/assistant-core/scripts/auth_google.py:23-24`
**Issue:** The docstring says the fallback text is used when the persona cannot be loaded. A failure to import `src.persona.notices`/`src.persona` (package changes, missing dependency in the interpreter used to run the script) aborts the OAuth helper before the flow, so an unrelated warning blocks authorization.
**Fix:** Move the `notices` import inside the `try` and fall back to a literal Russian string if the import fails.

### IN-04: The adapter-fallback gate still exits 0 for a repository that was not checked

**File:** `/opt/chat-app/scripts/agy_cross_ai.sh:362-370`
**Issue:** When the target has no `scripts/gate.py`, the adapter runs the chat-app gate, keeps the patch and exits 0. The WR-06 closure only adds a message and a SUMMARY line. The caller (a script or a person skimming) sees success while the target was not checked at all.
**Fix:** Either exit with a distinct non-zero code for `adapter-fallback` (for example 18) unless an explicit `AGY_ALLOW_FALLBACK_GATE=1` is set, or keep exit 0 and make the warning the first line of the SUMMARY.

### IN-05: The shared and chat-app shields execute whatever `ASSISTANT_CORE_DIR` points to

**File:** `/opt/assistant-shared/scripts/security_shield.py:36-52`, `/opt/chat-app/scripts/security_shield.py:34-50`
**Issue:** The delegator runs `<ASSISTANT_CORE_DIR>/.venv/bin/python <ASSISTANT_CORE_DIR>/scripts/security_shield.py` and returns its exit code. A stub directory in the environment makes the pre-commit check always return 0, so the "security checks can only get stricter" property rests on environment trust. The docstring states the trust is accepted (same as `PERSONA_CONFIG_PATH`), so this is informational. The same environment-trust applies to `PERSONA_CONFIG_PATH` pointing at a persona without NDA workspaces: `audit_repository` treats an empty workspace list as "no workspaces" and prints only a warning.
**Fix:** Optional hardening: ignore `ASSISTANT_CORE_DIR` inside git hooks (`GIT_DIR` is set), or require the resolved directory to contain a marker file whose hash the delegator knows.

---

_Reviewed: 2026-10-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
