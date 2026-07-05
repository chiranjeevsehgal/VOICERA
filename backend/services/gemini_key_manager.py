import os
import time
import threading
from collections import deque
from typing import Deque, List, Tuple, Optional, Dict
import json
import hashlib
from utils.logging import log_info, log_warning, log_error
from services.redis_client import get_sync_client

class _KeyState:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.lock = threading.Lock()
        self.rpm_timestamps: Deque[float] = deque()
        self.tpm_entries: Deque[Tuple[float, int]] = deque()
        self.rps_timestamps: Deque[float] = deque()
        self.daily_date: Optional[str] = None
        self.daily_count: int = 0
        self.cooldown_until: float = 0.0
        self.err_429: int = 0
        self.err_auth: int = 0
        self.err_5xx: int = 0
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
        self.rpm = int(os.getenv('GEMINI_EMBED_RPM', '100'))
        self.rps = int(os.getenv('GEMINI_EMBED_RPS', '2'))
        self.tpm = int(os.getenv('GEMINI_EMBED_TPM', '30000'))
        self.tpm_safety = float(os.getenv('GEMINI_TPM_SAFETY', '0.9'))
        self.rpd = int(os.getenv('GEMINI_EMBED_RPD', '1000'))
        self.cooldown_sec_default = float(os.getenv('GEMINI_KEY_COOLDOWN_SEC', '15'))
        self._keys: List[_KeyState] = []
        self._mgr_lock = threading.Lock()
        self._parse_keys_from_env()
        try:
            self._redis = get_sync_client()
            if self._redis:
                log_info('GeminiKeyManager Redis backend available (sync, pooled)', 'gemini_key_manager')
                try:
                    self._restore_from_redis()
                except Exception:
                    pass
        except Exception as e:
            self._redis = None
            log_warning(f'GeminiKeyManager Redis init failed: {e}', 'gemini_key_manager')

    def _parse_keys_from_env(self) -> None:
        keys: List[str] = []
        multi = os.getenv('GEMINI_API_KEYS', '')
        if multi:
            for part in multi.replace(';', ',').split(','):
                k = part.strip()
                if k:
                    keys.append(k)
        for i in range(1, 101):
            k = os.getenv(f'GEMINI_API_KEY_{i}')
            if k and k.strip():
                keys.append(k.strip())
        single = os.getenv('GEMINI_API_KEY')
        if single and single.strip():
            keys.append(single.strip())
        seen = set()
        deduped: List[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                deduped.append(k)
        with self._mgr_lock:
            self._keys = [_KeyState(k) for k in deduped]
            log_info(f'GeminiKeyManager initialized with {len(self._keys)} key(s)', 'gemini_key_manager', {'key_count': len(self._keys)})

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
        today = time.strftime('%Y-%m-%d', time.localtime(now))
        if st.daily_date != today:
            st.daily_date = today
            st.daily_count = 0
            st.rpm_timestamps.clear()
            st.tpm_entries.clear()
            st.rps_timestamps.clear()

    def _effective_tpm(self) -> int:
        return int(self.tpm * self.tpm_safety)

    def _redis_enabled(self) -> bool:
        return self._redis is not None

    def _key_hash(self, api_key: str) -> str:
        return hashlib.sha1(api_key.encode('utf-8')).hexdigest()[:12]

    def _rkey(self, api_key: str) -> str:
        return f'gkm:key:{self._key_hash(api_key)}'

    def _restore_from_redis(self) -> None:
        """
        Restore per-key persisted state from Redis if available:
        - daily_date (YYYY-MM-DD)
        - daily_count (int)
        - cooldown_until (float epoch seconds)
        - error counters (err_429, err_auth, err_5xx)
        Data is best-effort and only used to initialize in-memory state.
        """
        if not self._redis_enabled():
            return
        now = self._now()
        today = time.strftime('%Y-%m-%d', time.localtime(now))
        with self._mgr_lock:
            keys_snapshot = list(self._keys)
        for st in keys_snapshot:
            try:
                rkey = self._rkey(st.api_key)
                data = self._redis.hgetall(rkey) or {}
                if not data:
                    continue
                stored_date = data.get('daily_date')
                stored_count = data.get('daily_count')
                stored_cooldown = data.get('cooldown_until')
                err_429 = data.get('err_429')
                err_auth = data.get('err_auth')
                err_5xx = data.get('err_5xx')
                with st.lock:
                    st.daily_date = today
                    if stored_date == today and stored_count is not None:
                        try:
                            st.daily_count = int(stored_count)
                        except Exception:
                            st.daily_count = st.daily_count
                    if stored_cooldown is not None:
                        try:
                            sc = float(stored_cooldown)
                            if sc > now:
                                st.cooldown_until = max(st.cooldown_until, sc)
                        except Exception:
                            pass
                    try:
                        if err_429 is not None:
                            st.err_429 = int(err_429)
                        if err_auth is not None:
                            st.err_auth = int(err_auth)
                        if err_5xx is not None:
                            st.err_5xx = int(err_5xx)
                    except Exception:
                        pass
            except Exception:
                pass

    def _check_capacity_and_reserve(self, st: _KeyState, tokens: int, now: float) -> Tuple[bool, float]:
        """
        Returns (ok, wait_seconds). If ok==True, the reservation has been recorded.
        If ok==False, wait_seconds is the predicted time until the key can accept the request.
        """
        with st.lock:
            if now < st.cooldown_until:
                return (False, max(0.0, st.cooldown_until - now))
            self._reset_daily_if_needed(st, now)
            if self.rpd > 0 and st.daily_count >= self.rpd:
                return (False, 3600.0)
            self._prune_windows(st, now)
            reqs_last_min = len(st.rpm_timestamps)
            reqs_last_sec = len(st.rps_timestamps)
            tokens_last_min = sum((t for _, t in st.tpm_entries))
            rpm_ok = reqs_last_min < self.rpm
            rps_ok = reqs_last_sec < self.rps
            tpm_limit_eff = self._effective_tpm()
            tpm_ok = tokens_last_min + tokens <= tpm_limit_eff
            if rpm_ok and rps_ok and tpm_ok:
                st.rpm_timestamps.append(now)
                st.rps_timestamps.append(now)
                st.tpm_entries.append((now, tokens))
                st.daily_count += 1
                if self._redis_enabled():
                    try:
                        self._redis.hset(self._rkey(st.api_key), mapping={'last_reservation': now, 'daily_count': st.daily_count, 'daily_date': st.daily_date})
                        self._redis.expire(self._rkey(st.api_key), 86400)
                    except Exception:
                        pass
                return (True, 0.0)
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
            return (False, wait_s)

    def acquire(self, tokens: int, request_type: str='embed', max_wait_seconds: float=60.0) -> str:
        """
        Block until a key is available and return its string value.
        Chooses the key with the smallest predicted wait time.
        """
        start = self._now()
        while True:
            with self._mgr_lock:
                keys_snapshot = list(self._keys)
                if not keys_snapshot:
                    raise RuntimeError('No Gemini API keys configured')
            now = self._now()
            best_key: Optional[_KeyState] = None
            best_wait: float = 1000000000.0
            for st in keys_snapshot:
                ok, wait_s = self._check_capacity_and_reserve(st, tokens, now)
                if ok:
                    log_info('GeminiKeyManager selected key immediately', 'gemini_key_manager', {'key_prefix': st.api_key[:100], 'tokens': tokens})
                    return st.api_key
                elif wait_s < best_wait:
                    best_wait = wait_s
                    best_key = st
            if best_key is None:
                raise RuntimeError('No Gemini API keys available')
            slept = min(max(0.05, best_wait), 2.0)
            if self._now() - start + slept > max_wait_seconds:
                now2 = self._now()
                for st in keys_snapshot:
                    ok, _ = self._check_capacity_and_reserve(st, tokens, now2)
                    if ok:
                        return st.api_key
                raise RuntimeError('Timeout waiting for an available Gemini API key')
            time.sleep(slept)

    def report_result(self, api_key: str, status_code: int, retry_after: Optional[float]=None, status: Optional[str]=None) -> None:
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
            if status_code >= 400 and status:
                st.err_counts[status] = st.err_counts.get(status, 0) + 1
            if status_code == 429:
                delta = float(retry_after) if retry_after and retry_after > 0 else self.cooldown_sec_default
                st.cooldown_until = max(st.cooldown_until, now + delta)
                st.err_429 += 1
                log_warning('Applied cooldown due to 429', 'gemini_key_manager', {'key_prefix': st.api_key[:100], 'cooldown_sec': delta})
            elif status_code in (401, 403):
                st.cooldown_until = max(st.cooldown_until, now + 300.0)
                st.err_auth += 1
                log_error('Applied long cooldown due to auth/permission error', 'gemini_key_manager', {'key_prefix': st.api_key[:100], 'status': status_code})
            elif 500 <= status_code <= 599:
                st.cooldown_until = max(st.cooldown_until, now + 5.0)
                st.err_5xx += 1
                log_warning('Applied short cooldown due to server error', 'gemini_key_manager', {'key_prefix': st.api_key[:100], 'status': status_code})
            else:
                pass
        if self._redis_enabled():
            try:
                rkey = self._rkey(api_key)
                payload = {'cooldown_until': st.cooldown_until, 'err_429': st.err_429, 'err_auth': st.err_auth, 'err_5xx': st.err_5xx, 'daily_date': st.daily_date, 'daily_count': st.daily_count, 'updated_at': int(now)}
                self._redis.hset(rkey, mapping=payload)
                self._redis.expire(rkey, 86400)
                try:
                    self._redis.publish('gkm:events', json.dumps({'type': 'report_result', 'key': rkey, 'status_code': status_code, 'retry_after': retry_after, 'ts': int(now)}))
                except Exception:
                    pass
            except Exception:
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
                self._reset_daily_if_needed(st, now)
                self._prune_windows(st, now)
                rpm_last_min = len(st.rpm_timestamps)
                rps_last_sec = len(st.rps_timestamps)
                tpm_last_min = sum((t for _, t in st.tpm_entries))
                cooldown_remaining = max(0.0, st.cooldown_until - now)
                combined_errs: Dict[str, int] = dict(st.err_counts)
                combined_errs['429'] = st.err_429
                combined_errs['auth_401_403'] = st.err_auth
                combined_errs['5xx'] = st.err_5xx
                keys_out.append({'key_prefix': st.api_key[:100], 'cooldown_until': st.cooldown_until if cooldown_remaining > 0 else 0.0, 'cooldown_remaining_s': round(cooldown_remaining, 3), 'rpm_last_min': rpm_last_min, 'rps_last_sec': rps_last_sec, 'tpm_last_min': tpm_last_min, 'daily_date': st.daily_date, 'daily_count': st.daily_count, 'error_counts': combined_errs})
        status = {'timestamp': now, 'summary': {'key_count': len(keys_snapshot), 'has_keys': len(keys_snapshot) > 0, 'rpm_limit': self.rpm, 'rps_limit': self.rps, 'tpm_limit_raw': self.tpm, 'tpm_limit_effective': self._effective_tpm(), 'rpd_limit': self.rpd, 'cooldown_default_s': self.cooldown_sec_default}, 'keys': keys_out}
        if self._redis_enabled():
            try:
                self._redis.set('gkm:status', json.dumps(status), ex=30)
            except Exception:
                pass
        return status
gemini_key_manager = GeminiKeyManager()