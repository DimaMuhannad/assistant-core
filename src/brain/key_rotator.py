"""Dynamic Gemini API Key Rotator & Pool Manager.

Provides:
- In-flight failover on 429 RESOURCE_EXHAUSTED or 503 UNAVAILABLE
- Health tracking and automatic cooldowns per key
- Round-robin or active-fallback key resolution
- Atomic persistence of the active healthy key into .env
- Singleton instance for cross-module reuse
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Coroutine
from google import genai

from src import config

logger = logging.getLogger(__name__)


class GeminiKeyRotator:
    """Manages a pool of Gemini API keys with health status and hot failover."""

    def __init__(
        self,
        keys: list[str] | None = None,
        env_path: Path | None = None,
    ) -> None:
        raw_keys = keys or config.GEMINI_API_KEYS
        # Remove duplicates while preserving order
        self.keys: list[str] = []
        for k in raw_keys:
            clean = k.strip()
            if clean and clean not in self.keys:
                self.keys.append(clean)

        if not self.keys and config.GEMINI_API_KEY:
            self.keys = [config.GEMINI_API_KEY.strip()]

        self.env_path = env_path or (config.BASE_DIR / ".env")
        self.cooldowns: dict[str, float] = {}
        self._clients: dict[str, genai.Client] = {}
        self.active_index: int = 0
        self._lock = asyncio.Lock()

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def get_active_key(self) -> str:
        """Returns the currently active key or the first non-cooled-down key."""
        if not self.keys:
            return ""

        now = time.time()
        # Check current key first
        cur_key = self.keys[self.active_index]
        if self.cooldowns.get(cur_key, 0) <= now:
            return cur_key

        # Current key is on cooldown: find next healthy key
        for idx, k in enumerate(self.keys):
            if self.cooldowns.get(k, 0) <= now:
                self.active_index = idx
                logger.info("Switched active Gemini API key to slot #%d (%s...%s)", idx + 1, k[:10], k[-6:])
                return k

        # If all keys are on cooldown, return the one that will cool down earliest
        earliest_key = min(self.keys, key=lambda k: self.cooldowns.get(k, 0))
        self.active_index = self.keys.index(earliest_key)
        return earliest_key

    def get_client(self, api_key: str | None = None) -> genai.Client:
        """Returns a cached or new genai.Client for the given or active key."""
        target_key = api_key or self.get_active_key()
        if not target_key:
            raise ValueError("No Gemini API key available in pool.")

        if target_key not in self._clients:
            self._clients[target_key] = genai.Client(api_key=target_key)
        return self._clients[target_key]

    def mark_exhausted(self, key: str, retry_delay: float = 60.0) -> str:
        """Mark key as exhausted with a cooldown and switch to next available key."""
        cooldown_until = time.time() + retry_delay
        self.cooldowns[key] = cooldown_until
        key_abbr = f"{key[:10]}...{key[-6:]}" if len(key) >= 16 else key
        logger.warning(
            "Gemini API key %s marked exhausted (cooldown %.1fs). Remaining in pool: %d",
            key_abbr,
            retry_delay,
            len(self.keys),
        )

        # Select next key
        now = time.time()
        for idx, k in enumerate(self.keys):
            if k != key and self.cooldowns.get(k, 0) <= now:
                self.active_index = idx
                new_key = k
                new_abbr = f"{new_key[:10]}...{new_key[-6:]}"
                logger.info("Rotated to healthy Gemini API key slot #%d (%s)", idx + 1, new_abbr)
                self.sync_active_key_to_env(new_key)
                return new_key

        # If no key is completely cool, pick the one expiring soonest
        candidates = [k for k in self.keys if k != key]
        if candidates:
            next_key = min(candidates, key=lambda k: self.cooldowns.get(k, 0))
            self.active_index = self.keys.index(next_key)
            self.sync_active_key_to_env(next_key)
            return next_key

        return key

    def sync_active_key_to_env(self, active_key: str) -> bool:
        """Atomically update GEMINI_API_KEY in .env file to persist active key."""
        if not self.env_path or not self.env_path.exists():
            return False

        try:
            content = self.env_path.read_text(encoding="utf-8")
            pattern = r"^GEMINI_API_KEY=.*$"
            if re.search(pattern, content, flags=re.MULTILINE):
                new_content = re.sub(pattern, f"GEMINI_API_KEY={active_key}", content, flags=re.MULTILINE)
            else:
                new_content = content.rstrip() + f"\nGEMINI_API_KEY={active_key}\n"

            # Write atomically via temp file
            tmp_path = self.env_path.with_suffix(".tmp")
            tmp_path.write_text(new_content, encoding="utf-8")
            tmp_path.replace(self.env_path)

            # Update in-process config
            config.GEMINI_API_KEY = active_key
            logger.info("Persisted active Gemini API key to %s", self.env_path.name)
            return True
        except Exception as e:
            logger.warning("Could not persist active Gemini API key to .env: %s", e)
            return False

    async def execute_with_failover(
        self,
        call_factory: Callable[[genai.Client], Coroutine[Any, Any, Any]],
        max_attempts: int | None = None,
    ) -> Any:
        """Execute an async Gemini operation with automatic key failover on 429 / 503."""
        attempts = max_attempts or max(len(self.keys), 2)
        last_error: Exception | None = None

        for attempt in range(attempts):
            active_key = self.get_active_key()
            client = self.get_client(active_key)
            try:
                return await call_factory(client)
            except Exception as e:
                err_str = str(e)
                last_error = e

                # Detect quota or overload errors
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                is_overload = "503" in err_str or "UNAVAILABLE" in err_str

                if is_rate_limit or is_overload:
                    # Extract suggested retry delay if present
                    m = re.search(r"retry in ([0-9.]+)s", err_str)
                    delay = float(m.group(1)) if m else (60.0 if is_rate_limit else 15.0)

                    self.mark_exhausted(active_key, retry_delay=delay)
                    logger.warning(
                        "Attempt %d/%d failed with %s. Rotated key and retrying immediately...",
                        attempt + 1,
                        attempts,
                        "429 Quota" if is_rate_limit else "503 Overload",
                    )
                    # Instant zero-wait failover to next key in pool
                    continue
                else:
                    # Non-quota error (e.g. 400 Bad Request, schema mismatch, cancellation)
                    raise e

        if last_error:
            raise last_error
        raise RuntimeError("All Gemini API keys in pool failed.")


# Global singleton instance
key_rotator = GeminiKeyRotator()
