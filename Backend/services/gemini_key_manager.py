import os
import time
import threading
from collections import deque
from typing import Deque, List, Tuple, Optional, Dict

from utils.logging import log_info, log_warning, log_error


class _KeyState:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.lock = threading.Lock()
        # Rolling windows for the last minute (RPM/TPM) and last second (RPS)
        self.rpm_timestamps: Deque[float] = deque()
        self.tpm_entries: Deque[Tuple[float, int]] = deque()  # (timestamp, tokens)
        self.rps_timestamps: Deque[float] = deque()
        # Daily counters
        self.daily_date: Optional[str] = None
        self.daily_count: int = 0
        # Cooldown
        self.cooldown_until: float = 0.0
        # Errors and latency could be tracked for adaptive strategy (not required in v1)
        # Error counters for observability
        self.err_429: int = 0
        self.err_auth: int = 0  # 401/403
        self.err_5xx: int = 0
        # Generic error status counters (e.g., INVALID_ARGUMENT, FAILED_PRECONDITION, UNAVAILABLE...)
        self.err_counts: Dict[str, int] = {}


class GeminiKeyManager:
    """
    A per-key rate-aware selector and limiter for Google Gemini API keys.

    - Parses keys from env: GEMINI_API_KEYS (comma/semicolon separated),
      GEMINI_API_KEY_1..N, and fallback single GEMINI_API_KEY.
    - Enforces RPM, RPS, TPM (with safety factor), and RPD per key using rolling windows.
    - Provides acquire(blocking) to select a key that can accept the request now or waits for the
      soonest available key. report_result() updates cooldowns on 429/4xx.
    """

    def __init__(self):
        # Budgets (embedding-focused for Phase 1)
        self.rpm = int(os.getenv("GEMINI_EMBED_RPM", "100"))
        self.rps = int(os.getenv("GEMINI_EMBED_RPS", "2"))
        self.tpm = int(os.getenv("GEMINI_EMBED_TPM", "30000"))
        self.tpm_safety = float(os.getenv("GEMINI_TPM_SAFETY", "0.9"))
        self.rpd = int(os.getenv("GEMINI_EMBED_RPD", "1000"))
        self.cooldown_sec_default = float(os.getenv("GEMINI_KEY_COOLDOWN_SEC", "15"))

        # Parse keys
        self._keys: List[_KeyState] = []
        self._mgr_lock = threading.Lock()
        self._parse_keys_from_env()

    def _parse_keys_from_env(self) -> None:
        keys: List[str] = []
        # GEMINI_API_KEYS=key1,key2;key3
        multi = os.getenv("GEMINI_API_KEYS", "")
        if multi:
            for part in multi.replace(";", ",").split(","):
                k = part.strip()
                if k:
                    keys.append(k)
        # GEMINI_API_KEY_1..N
        for i in range(1, 101):  # support up to 100 keys
            k = os.getenv(f"GEMINI_API_KEY_{i}")
            if k and k.strip():
                keys.append(k.strip())
        # Fallback single
        single = os.getenv("GEMINI_API_KEY")
        if single and single.strip():
            keys.append(single.strip())

        # De-duplicate while preserving order
        seen = set()
        deduped: List[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                deduped.append(k)

        with self._mgr_lock:
            self._keys = [_KeyState(k) for k in deduped]
            log_info(
                f"GeminiKeyManager initialized with {len(self._keys)} key(s)",
                "gemini_key_manager",
                {"key_count": len(self._keys)},
            )

    def has_keys(self) -> bool:
        with self._mgr_lock:
            return len(self._keys) > 0

    def _now(self) -> float:
        return time.time()

    def _prune_windows(self, st: _KeyState, now: float) -> None:
        one_min_ago = now - 60.0
        one_sec_ago = now - 1.0
        while st.rpm_timestamps and st.rpm_timestamps[0] <= one_min_ago:
            st.rpm_timestamps.popleft()
        while st.tpm_entries and st.tpm_entries[0][0] <= one_min_ago:
            st.tpm_entries.popleft()
        while st.rps_timestamps and st.rps_timestamps[0] <= one_sec_ago:
            st.rps_timestamps.popleft()

    def _reset_daily_if_needed(self, st: _KeyState, now: float) -> None:
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if st.daily_date != today:
            st.daily_date = today
            st.daily_count = 0
            st.rpm_timestamps.clear()
            st.tpm_entries.clear()
            st.rps_timestamps.clear()

    def _effective_tpm(self) -> int:
        return int(self.tpm * self.tpm_safety)

    def _check_capacity_and_reserve(
        self, st: _KeyState, tokens: int, now: float
    ) -> Tuple[bool, float]:
        """
        Returns (ok, wait_seconds). If ok==True, the reservation has been recorded.
        If ok==False, wait_seconds is the predicted time until the key can accept the request.
        """
        with st.lock:
            if now < st.cooldown_until:
                return False, max(0.0, st.cooldown_until - now)

            self._reset_daily_if_needed(st, now)
            if self.rpd > 0 and st.daily_count >= self.rpd:
                # No capacity for remainder of day; backoff 1 hour to avoid tight loops
                return False, 3600.0

            self._prune_windows(st, now)

            reqs_last_min = len(st.rpm_timestamps)
            reqs_last_sec = len(st.rps_timestamps)
            tokens_last_min = sum(t for (_, t) in st.tpm_entries)

            rpm_ok = reqs_last_min < self.rpm
            rps_ok = reqs_last_sec < self.rps
            tpm_limit_eff = self._effective_tpm()
            tpm_ok = (tokens_last_min + tokens) <= tpm_limit_eff

            if rpm_ok and rps_ok and tpm_ok:
                # Reserve budgets
                st.rpm_timestamps.append(now)
                st.rps_timestamps.append(now)
                st.tpm_entries.append((now, tokens))
                st.daily_count += 1
                return True, 0.0

            waits: List[float] = []
            if not rpm_ok and st.rpm_timestamps:
                waits.append(st.rpm_timestamps[0] + 60.0 - now)
            if not rps_ok and st.rps_timestamps:
                waits.append(st.rps_timestamps[0] + 1.0 - now)
            if not tpm_ok and st.tpm_entries:
                need = tokens_last_min + tokens - tpm_limit_eff
                acc = 0
                for ts, t in st.tpm_entries:
                    acc += t
                    if acc >= need:
                        waits.append(ts + 60.0 - now)
                        break
            wait_s = max(0.0, min(max(waits) if waits else 0.5, 60.0))
            return False, wait_s

    def acquire(
        self, tokens: int, request_type: str = "embed", max_wait_seconds: float = 60.0
    ) -> str:
        """
        Block until a key is available and return its string value.
        Chooses the key with the smallest predicted wait time.
        """
        start = self._now()
        while True:
            with self._mgr_lock:
                keys_snapshot = list(self._keys)
                if not keys_snapshot:
                    raise RuntimeError("No Gemini API keys configured")

            now = self._now()
            best_key: Optional[_KeyState] = None
            best_wait: float = 1e9

            # First pass: try to reserve immediately
            for st in keys_snapshot:
                ok, wait_s = self._check_capacity_and_reserve(st, tokens, now)
                if ok:
                    log_info(
                        "GeminiKeyManager selected key immediately",
                        "gemini_key_manager",
                        {"key_prefix": st.api_key[:100], "tokens": tokens},
                    )
                    return st.api_key
                else:
                    if wait_s < best_wait:
                        best_wait = wait_s
                        best_key = st

            # None available right now, sleep until earliest predicted availability
            if best_key is None:
                # No keys at all
                raise RuntimeError("No Gemini API keys available")

            slept = min(max(0.05, best_wait), 2.0)
            if (self._now() - start) + slept > max_wait_seconds:
                # Final attempt: try to reserve again; if still not possible, raise
                now2 = self._now()
                for st in keys_snapshot:
                    ok, _ = self._check_capacity_and_reserve(st, tokens, now2)
                    if ok:
                        return st.api_key
                raise RuntimeError("Timeout waiting for an available Gemini API key")

            time.sleep(slept)

    def report_result(
        self,
        api_key: str,
        status_code: int,
        retry_after: Optional[float] = None,
        status: Optional[str] = None,
    ) -> None:
        """
        Inform the manager of the outcome so it can cooldown misbehaving keys.
        - 429: apply Retry-After if provided, else default cooldown
        - 401/403: long cooldown (5 minutes) to effectively disable the key
        - 5xx: short cooldown
        """
        st = None
        with self._mgr_lock:
            for ks in self._keys:
                if ks.api_key == api_key:
                    st = ks
                    break
        if st is None:
            return

        now = self._now()
        with st.lock:
            # Record structured error status counts for observability
            if status_code >= 400 and status:
                st.err_counts[status] = st.err_counts.get(status, 0) + 1
            if status_code == 429:
                delta = (
                    float(retry_after)
                    if retry_after and retry_after > 0
                    else self.cooldown_sec_default
                )
                st.cooldown_until = max(st.cooldown_until, now + delta)
                st.err_429 += 1
                log_warning(
                    "Applied cooldown due to 429",
                    "gemini_key_manager",
                    {"key_prefix": st.api_key[:100], "cooldown_sec": delta},
                )
            elif status_code in (401, 403):
                # Effectively disable for 5 minutes
                st.cooldown_until = max(st.cooldown_until, now + 300.0)
                st.err_auth += 1
                log_error(
                    "Applied long cooldown due to auth/permission error",
                    "gemini_key_manager",
                    {"key_prefix": st.api_key[:100], "status": status_code},
                )
            elif 500 <= status_code <= 599:
                st.cooldown_until = max(st.cooldown_until, now + 5.0)
                st.err_5xx += 1
                log_warning(
                    "Applied short cooldown due to server error",
                    "gemini_key_manager",
                    {"key_prefix": st.api_key[:100], "status": status_code},
                )
            else:
                # Success or other statuses: no cooldown
                pass

    def get_status(self) -> dict:
        """
        Return aggregated usage and per-key status for observability.
        Does not mutate internal counters beyond daily reset and window pruning.
        """
        with self._mgr_lock:
            keys_snapshot = list(self._keys)

        now = self._now()
        keys_out = []

        for st in keys_snapshot:
            with st.lock:
                # Keep window stats fresh for accurate reporting
                self._reset_daily_if_needed(st, now)
                self._prune_windows(st, now)

                rpm_last_min = len(st.rpm_timestamps)
                rps_last_sec = len(st.rps_timestamps)
                tpm_last_min = sum(t for (_, t) in st.tpm_entries)
                cooldown_remaining = max(0.0, st.cooldown_until - now)

                # Build combined error counts including legacy aggregates and structured statuses
                combined_errs: Dict[str, int] = dict(st.err_counts)
                # Keep legacy aggregates for UI backward compatibility
                combined_errs["429"] = st.err_429
                combined_errs["auth_401_403"] = st.err_auth
                combined_errs["5xx"] = st.err_5xx

                keys_out.append(
                    {
                        "key_prefix": st.api_key[:100],
                        "cooldown_until": st.cooldown_until
                        if cooldown_remaining > 0
                        else 0.0,
                        "cooldown_remaining_s": round(cooldown_remaining, 3),
                        "rpm_last_min": rpm_last_min,
                        "rps_last_sec": rps_last_sec,
                        "tpm_last_min": tpm_last_min,
                        "daily_date": st.daily_date,
                        "daily_count": st.daily_count,
                        "error_counts": combined_errs,
                    }
                )

        status = {
            "timestamp": now,
            "summary": {
                "key_count": len(keys_snapshot),
                "has_keys": len(keys_snapshot) > 0,
                "rpm_limit": self.rpm,
                "rps_limit": self.rps,
                "tpm_limit_raw": self.tpm,
                "tpm_limit_effective": self._effective_tpm(),
                "rpd_limit": self.rpd,
                "cooldown_default_s": self.cooldown_sec_default,
            },
            "keys": keys_out,
        }
        return status


# Create a process-wide singleton for convenient imports
gemini_key_manager = GeminiKeyManager()
