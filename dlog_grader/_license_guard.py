"""Compiled offline license guard.

This module is built as a native Windows extension. The Ed25519 public key is
embedded as raw bytes; the application never trusts a replaceable PEM file.
"""
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import math
import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import LICENSE_DIR, LICENSE_FILE, PROJECT_ROOT

TRIAL_DAYS = 7
TIME_ROLLBACK_TOLERANCE_SECONDS = 600
TRIAL_TYPE = "trial"
COMMERCIAL_TYPE = "commercial"
AUTO_TRIAL_ID = "AUTO-TRIAL-V1"
TRIAL_STATE_PROJECT = LICENSE_DIR / "license_state.bin"
LOCAL_APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "DJI-BatchGrader"
TRIAL_STATE_LOCAL = LOCAL_APP_DIR / "license_state.bin"
REGISTRY_KEY = r"Software\DJI-BatchGrader"
REGISTRY_VALUE = "LicenseState"

# Raw Ed25519 public key (32 bytes). Do not replace this with an external file.
_PUBLIC_KEY_RAW = bytes.fromhex(
    "ee639e134d377aec56d731a73707a1f78ba2a9215eaf11b8214977ab64872738"
)

# Add license_id values here only in a new release to revoke known leaked keys.
_REVOKED_LICENSE_IDS = frozenset()


class LicenseError(RuntimeError):
    pass


class LicenseStatus:
    def __init__(
        self,
        kind,
        can_run,
        message,
        days_left=None,
        expires_at="",
        customer="",
        edition="",
        is_new=False,
        machine_code="",
        license_id="",
    ):
        self.kind = kind
        self.can_run = bool(can_run)
        self.message = message
        self.days_left = days_left
        self.expires_at = expires_at
        self.customer = customer
        self.edition = edition
        self.is_new = bool(is_new)
        self.machine_code = machine_code
        self.license_id = license_id

    @property
    def is_trial(self):
        return self.kind == "trial"

    @property
    def is_commercial(self):
        return self.kind == "commercial"


def utcnow():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _machine_seed():
    parts = [platform.node() or "", os.environ.get("USERNAME") or os.environ.get("USER") or ""]
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                parts.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
        except Exception:
            pass
        try:
            volume = ctypes.create_unicode_buffer(256)
            serial = ctypes.c_uint()
            root = str(PROJECT_ROOT.anchor or "C:\\")
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), None, 0, ctypes.byref(serial), None, None, volume, 256
            )
            parts.append(str(serial.value))
        except Exception:
            pass
    else:
        parts.append(str(Path.home()))
    return "|".join(parts)


def machine_code():
    digest = hashlib.sha256(("DJI-DLogM-Grader|" + _machine_seed()).encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i:i + 4] for i in range(0, 24, 4))


def canonical_payload(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fallback_protect(data):
    return b"B64:" + base64.b64encode(data)


def _fallback_unprotect(data):
    if data.startswith(b"B64:"):
        return base64.b64decode(data[4:])
    raise ValueError("not fallback-protected")


def _dpapi_protect(data):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def protect_state(data):
    if os.name == "nt":
        try:
            return b"DPAPI:" + _dpapi_protect(data)
        except Exception:
            pass
    return _fallback_protect(data)


def unprotect_state(data):
    if data.startswith(b"DPAPI:"):
        return _dpapi_unprotect(data[6:])
    return _fallback_unprotect(data)


class LicenseManager:
    def __init__(
        self,
        license_file=None,
        state_paths=None,
        now_fn=utcnow,
        use_registry=True,
        _public_key_bytes=None,
    ):
        self.license_file = (license_file or LICENSE_FILE).resolve()
        self.state_paths = state_paths or (TRIAL_STATE_PROJECT, TRIAL_STATE_LOCAL)
        self.now_fn = now_fn
        self.use_registry = use_registry
        self.machine_code = machine_code()
        self._public_key_bytes = _public_key_bytes or _PUBLIC_KEY_RAW
        self._last_status = None
        LICENSE_DIR.mkdir(parents=True, exist_ok=True)
        LOCAL_APP_DIR.mkdir(parents=True, exist_ok=True)

    def _load_public_key(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        return Ed25519PublicKey.from_public_bytes(self._public_key_bytes)

    def _read_registry_state(self):
        if not self.use_registry or os.name != "nt":
            return None
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                encoded = winreg.QueryValueEx(key, REGISTRY_VALUE)[0]
            return self._decode_state(base64.b64decode(encoded))
        except Exception:
            return None

    def _write_registry_state(self, raw):
        if not self.use_registry or os.name != "nt":
            return
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, base64.b64encode(raw).decode("ascii"))
        except Exception:
            pass

    def _decode_state(self, raw):
        try:
            payload = json.loads(unprotect_state(raw).decode("utf-8"))
            if payload.get("machine_code") != self.machine_code:
                return None
            return payload
        except Exception:
            return None

    def _load_trial_state(self, license_id=""):
        candidates = []
        for path in self.state_paths:
            try:
                state = self._decode_state(Path(path).read_bytes())
                if state:
                    candidates.append(state)
            except Exception:
                pass
        registry_state = self._read_registry_state()
        if registry_state:
            candidates.append(registry_state)
        if license_id:
            candidates = [s for s in candidates if str(s.get("license_id") or "") == str(license_id)]
        if not candidates:
            return None
        candidates.sort(key=lambda s: str(s.get("last_seen_at", "")), reverse=True)
        state = candidates[0]
        self._save_trial_state(state)
        return state

    def _save_trial_state(self, state):
        raw = protect_state(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for path in self.state_paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_bytes(raw)
                tmp.replace(path)
            except Exception:
                pass
        self._write_registry_state(raw)

    def _reset_trial_state(self, payload):
        now = self.now_fn()
        state = {
            "version": 2,
            "machine_code": self.machine_code,
            "license_id": str(payload.get("license_id") or ""),
            "started_at": now.isoformat(timespec="seconds"),
            "last_seen_at": now.isoformat(timespec="seconds"),
        }
        self._save_trial_state(state)
        return state

    def _auto_trial_state(self):
        now = self.now_fn()
        state = self._load_trial_state(AUTO_TRIAL_ID)
        if state is None:
            state = {
                "version": 2,
                "machine_code": self.machine_code,
                "license_id": AUTO_TRIAL_ID,
                "started_at": now.isoformat(timespec="seconds"),
                "last_seen_at": now.isoformat(timespec="seconds"),
            }
            self._save_trial_state(state)
            return state, True
        started = parse_time(state.get("started_at"))
        last_seen = parse_time(state.get("last_seen_at"))
        if started is None or last_seen is None:
            raise LicenseError("试用状态损坏，请重新安装软件")
        if now.timestamp() < last_seen.timestamp() - TIME_ROLLBACK_TOLERANCE_SECONDS:
            raise LicenseError("检测到系统时间被回拨，7 天试用已锁定")
        if now > last_seen:
            state["last_seen_at"] = now.isoformat(timespec="seconds")
            self._save_trial_state(state)
        return state, False

    def _evaluate_auto_trial(self):
        now = self.now_fn()
        try:
            state, is_new = self._auto_trial_state()
        except LicenseError as exc:
            self._last_status = LicenseStatus(
                kind="blocked",
                can_run=False,
                message=str(exc),
                machine_code=self.machine_code,
            )
            return self._last_status
        started = parse_time(state.get("started_at"))
        if started is None:
            self._last_status = LicenseStatus(
                kind="blocked",
                can_run=False,
                message="试用状态损坏，请重新安装软件",
                machine_code=self.machine_code,
            )
            return self._last_status
        expires = started + timedelta(days=TRIAL_DAYS)
        remaining = (expires - now).total_seconds()
        if remaining <= 0:
            self._last_status = LicenseStatus(
                kind="expired",
                can_run=False,
                message="7 天免费试用已结束，请添加作者 QQ 购买买断授权",
                days_left=0,
                expires_at=expires.isoformat(timespec="seconds"),
                edition="trial",
                machine_code=self.machine_code,
                license_id=AUTO_TRIAL_ID,
            )
            return self._last_status
        days_left = max(1, int(math.ceil(remaining / 86400)))
        self._last_status = LicenseStatus(
            kind="trial",
            can_run=True,
            message="已开始 7 天免费试用" if is_new else "试用剩余 %d 天" % days_left,
            days_left=days_left,
            expires_at=expires.isoformat(timespec="seconds"),
            edition="trial",
            is_new=is_new,
            machine_code=self.machine_code,
            license_id=AUTO_TRIAL_ID,
        )
        return self._last_status

    def _check_trial_state(self, payload, now):
        license_id = str(payload.get("license_id") or "")
        state = self._load_trial_state(license_id)
        if state is None:
            state = self._reset_trial_state(payload)
        started = parse_time(state.get("started_at"))
        last_seen = parse_time(state.get("last_seen_at"))
        if started is None or last_seen is None:
            raise LicenseError("授权状态损坏，请重新导入试用授权")
        if now.timestamp() < last_seen.timestamp() - TIME_ROLLBACK_TOLERANCE_SECONDS:
            raise LicenseError("检测到系统时间被回拨，试用授权已锁定")
        if now > last_seen:
            state["last_seen_at"] = now.isoformat(timespec="seconds")
            self._save_trial_state(state)

    def verify_license_file(self, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            payload = data["payload"]
            signature = base64.b64decode(data["signature"])
        except Exception as exc:
            raise LicenseError("授权文件格式无效：%s" % exc) from exc
        try:
            self._load_public_key().verify(signature, canonical_payload(payload))
        except Exception as exc:
            raise LicenseError("授权文件签名无效") from exc
        if str(payload.get("machine_code") or "") != self.machine_code:
            raise LicenseError("授权文件不属于当前设备，请使用本机机器码重新签发")
        license_id = str(payload.get("license_id") or "")
        if license_id and license_id in _REVOKED_LICENSE_IDS:
            raise LicenseError("该授权已被停用，请联系作者重新签发")
        license_type = str(payload.get("type") or "")
        if license_type not in (TRIAL_TYPE, COMMERCIAL_TYPE):
            raise LicenseError("授权类型无效")
        expires_at = parse_time(payload.get("expires_at"))
        if license_type == TRIAL_TYPE and expires_at is None:
            raise LicenseError("试用授权缺少到期时间")
        now = self.now_fn()
        if expires_at and now >= expires_at:
            raise LicenseError("授权已过期：%s" % payload.get("expires_at"))
        if license_type == TRIAL_TYPE:
            self._check_trial_state(payload, now)
        return payload

    def activate_license_file(self, source):
        payload = self.verify_license_file(source)
        self.license_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.license_file.with_suffix(".tmp")
        tmp.write_bytes(Path(source).read_bytes())
        tmp.replace(self.license_file)
        if str(payload.get("type") or "") == TRIAL_TYPE:
            self._reset_trial_state(payload)
        self._last_status = self._status_from_payload(payload, is_new=True)
        return self._last_status

    def _status_from_payload(self, payload, is_new=False):
        license_type = str(payload.get("type") or "")
        expires = parse_time(payload.get("expires_at"))
        now = self.now_fn()
        days_left = None
        if expires:
            remaining = (expires - now).total_seconds()
            days_left = max(0, int(math.ceil(remaining / 86400)))
        if license_type == TRIAL_TYPE:
            message = "试用剩余 %d 天" % (days_left or 0)
            kind = "trial"
            can_run = bool(days_left and days_left > 0)
        else:
            kind = "commercial"
            can_run = True
            if expires:
                message = "已授权 · 商业版 · 剩余 %d 天" % (days_left or 0)
            else:
                message = "已授权 · 买断版"
        return LicenseStatus(
            kind=kind,
            can_run=can_run,
            message=message,
            days_left=days_left,
            expires_at=str(payload.get("expires_at") or ""),
            customer=str(payload.get("customer") or ""),
            edition=str(payload.get("edition") or ""),
            is_new=is_new,
            machine_code=self.machine_code,
            license_id=str(payload.get("license_id") or ""),
        )

    def evaluate(self):
        if not self.license_file.exists():
            return self._evaluate_auto_trial()
        try:
            payload = self.verify_license_file(self.license_file)
            self._last_status = self._status_from_payload(payload)
            return self._last_status
        except LicenseError as exc:
            text = str(exc)
            if "过期" in text:
                kind = "expired"
            elif "回拨" in text or "锁定" in text:
                kind = "blocked"
            else:
                kind = "invalid"
            self._last_status = LicenseStatus(
                kind=kind,
                can_run=False,
                message=text,
                machine_code=self.machine_code,
            )
            return self._last_status
        except Exception:
            self._last_status = LicenseStatus(
                kind="invalid",
                can_run=False,
                message="授权校验失败，请重新导入授权文件",
                machine_code=self.machine_code,
            )
            return self._last_status

    def status(self):
        return self._last_status or self.evaluate()

    def license_summary(self):
        status = self.status()
        if status.kind == "commercial":
            if status.expires_at:
                return "已授权 · %s · 剩余 %s 天" % (status.edition or "商业版", status.days_left)
            return "已授权 · %s" % (status.edition or "买断版")
        if status.kind == "trial":
            return "试用剩余 %s 天" % status.days_left
        return status.message
