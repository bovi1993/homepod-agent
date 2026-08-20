"""Xiaomi cloud helpers — list devices + extract local tokens.

Dreamehome app accounts are Xiaomi-cloud based for most Dreame vacuums sold
in EU/US; country server is usually ``de`` for NL/EU.

Login handles Xiaomi's email 2FA (identity/authStart) interactively when
needed. Never stores the password — only device tokens land in devices.yaml.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

import requests

from shared.log import get_logger

from .config import (
    infer_kind,
    load_devices_file,
    save_devices_file,
    stable_id_from_cloud,
    upsert_device,
)
from .models import DeviceConfig, DevicesFile

log = get_logger("devices.cloud")

COUNTRY_CHOICES = ("cn", "de", "us", "ru", "tw", "sg", "in", "i2")

_UA_TMPL = (
    "Android-7.1.1-1.0.0-ONEPLUS A3010-136-{client} "
    "APP/xiaomi.smarthome APPV/62830"
)


def _jload(text: str) -> dict[str, Any]:
    return json.loads(text.replace("&&&START&&&", ""))


def _client_id() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


class XiaomiCloudSession:
    """Password + optional email-2FA login for sid=xiaomiio."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self.client_id = _client_id()
        self.useragent = _UA_TMPL.format(client=self.client_id)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.useragent})
        self.session.cookies.set("sdkVersion", "3.8.6", domain="mi.com")
        self.session.cookies.set("sdkVersion", "3.8.6", domain="xiaomi.com")
        self.session.cookies.set("deviceId", self.client_id, domain="mi.com")
        self.session.cookies.set("deviceId", self.client_id, domain="xiaomi.com")
        self.user_id: str | None = None
        self.service_token: str | None = None
        self.ssecurity: str | None = None
        self.verification_url: str | None = None
        self.verification_dest: str | None = None

    def login(self, code_provider: Callable[[str], str] | None = None) -> bool:
        """Login; if 2FA required, call code_provider(masked_dest) for the email code."""
        if not self._login_step1_2():
            return False
        if self.service_token and self.ssecurity and self.user_id:
            return True
        if not self.verification_url:
            return False
        if code_provider is None:
            raise RuntimeError(
                "Xiaomi requires email 2FA. Re-run with an interactive terminal "
                f"(code sent to {self.verification_dest or 'your email'})."
            )
        code = (code_provider(self.verification_dest or "email") or "").strip()
        if not code:
            raise RuntimeError("Empty 2FA code")
        return self._verify_email_code(code)

    def _login_step1_2(self) -> bool:
        r = self.session.get(
            "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true",
            timeout=20,
        )
        d = _jload(r.text)
        data = {
            "sid": "xiaomiio",
            "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
            "callback": d.get("callback") or "https://sts.api.io.mi.com/sts",
            "qs": d.get("qs") or "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": self.username,
            "_json": "true",
        }
        if d.get("_sign"):
            data["_sign"] = d["_sign"]
        r2 = self.session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        d2 = _jload(r2.text)
        code = d2.get("code")
        if code == 87001:
            raise RuntimeError(
                "Xiaomi wants a captcha (rate-limit / bot check). Wait a bit and retry, "
                "or complete one login in a browser first."
            )
        if d2.get("ssecurity") and d2.get("location"):
            return self._finish_sts(
                d2["location"], d2["ssecurity"], d2.get("userId"), d2.get("nonce")
            )
        nurl = d2.get("notificationUrl")
        if not nurl:
            desc = d2.get("desc") or d2.get("description") or d2
            raise RuntimeError(f"Xiaomi login failed: {desc}")
        if not str(nurl).startswith("http"):
            nurl = "https://account.xiaomi.com" + nurl
        if not self._send_2fa(str(nurl)):
            raise RuntimeError(
                "Could not send Xiaomi 2FA email "
                f"(dest={self.verification_dest}). "
                "If you see 'try again tomorrow', Xiaomi rate-limited this account."
            )
        return True  # pending 2FA

    def _send_2fa(self, verification_url: str) -> bool:
        self.verification_url = verification_url
        ctx = parse_qs(urlparse(verification_url).query).get("context", [""])[0]
        self.session.get(verification_url, timeout=15)
        r = self.session.get(
            "https://account.xiaomi.com/identity/list",
            params={"sid": "xiaomiio", "context": ctx, "_locale": "en_US"},
            timeout=15,
        )
        if r.status_code != 200:
            return False
        data = _jload(r.text) if "&&&START&&&" in r.text or r.text[:1] == "{" else {}
        options = data.get("options") or []
        flag = 8 if 8 in options else (4 if 4 in options else int(data.get("flag") or 8))
        key = "Phone" if flag == 4 else "Email"
        vr = self.session.get(
            f"https://account.xiaomi.com/identity/auth/verify{key}",
            params={
                "_flag": flag,
                "_json": "true",
                "sid": "xiaomiio",
                "context": ctx,
                "mask": "0",
                "_locale": "en_US",
            },
            timeout=15,
        )
        vd = _jload(vr.text)
        if vd.get("code") not in (0, None) and vd.get("code") != 0:
            # still try send — some responses are soft
            pass
        self.verification_dest = (
            vd.get("maskedEmail") or vd.get("maskedPhone") or "*****"
        )
        sr = self.session.post(
            f"https://account.xiaomi.com/identity/auth/send{key}Ticket",
            params={
                "_dc": str(int(time.time() * 1000)),
                "sid": "xiaomiio",
                "context": ctx,
                "mask": "0",
                "_locale": "en_US",
            },
            data={
                "retry": 0,
                "icode": "",
                "_json": "true",
                "ick": self.session.cookies.get("ick", ""),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        sd = _jload(sr.text)
        if sd.get("code") != 0:
            tips = sd.get("tips") or sd.get("desc") or sd.get("description") or sd
            raise RuntimeError(f"2FA send failed: {tips}")
        log.info("devices.cloud_2fa_sent", dest=self.verification_dest, flag=flag)
        return True

    def _verify_email_code(self, code: str) -> bool:
        assert self.verification_url
        ctx = parse_qs(urlparse(self.verification_url).query).get("context", [""])[0]
        headers = {
            "User-Agent": self.useragent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = self.session.get(
            "https://account.xiaomi.com/identity/list",
            params={"sid": "xiaomiio", "context": ctx, "_locale": "en_US"},
            headers=headers,
            timeout=15,
        )
        data = _jload(r.text) if r.text else {}
        options = data.get("options") or []
        flag = 8 if 8 in options else (4 if 4 in options else 8)
        key = "Phone" if flag == 4 else "Email"
        vr = self.session.post(
            f"https://account.xiaomi.com/identity/auth/verify{key}",
            headers=headers,
            params={
                "_flag": flag,
                "_json": "true",
                "sid": "xiaomiio",
                "context": ctx,
                "mask": "0",
                "_locale": "en_US",
            },
            data={
                "_flag": flag,
                "ticket": code,
                "trust": "true",
                "_json": "true",
                "ick": self.session.cookies.get("ick", ""),
            },
            timeout=20,
        )
        vd = _jload(vr.text)
        if vd.get("code") != 0:
            raise RuntimeError(
                f"2FA code rejected: {vd.get('desc') or vd.get('description') or vd}"
            )
        loc = vd.get("location")
        if loc:
            self.session.get(loc, headers=headers, allow_redirects=True, timeout=20)
        # Re-run login; identity should now be trusted
        r1 = self.session.get(
            "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true",
            timeout=20,
        )
        d = _jload(r1.text)
        if d.get("ssecurity") and d.get("location"):
            return self._finish_sts(
                d["location"], d["ssecurity"], d.get("userId"), d.get("nonce")
            )
        data = {
            "sid": "xiaomiio",
            "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
            "callback": d.get("callback") or "https://sts.api.io.mi.com/sts",
            "qs": d.get("qs") or "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": self.username,
            "_json": "true",
        }
        if d.get("_sign"):
            data["_sign"] = d["_sign"]
        r2 = self.session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        d2 = _jload(r2.text)
        if d2.get("notificationUrl"):
            raise RuntimeError("2FA still required after code — try a fresh code")
        if not (d2.get("ssecurity") and d2.get("location")):
            raise RuntimeError(f"Post-2FA login failed: {d2.get('desc') or d2}")
        return self._finish_sts(
            d2["location"], d2["ssecurity"], d2.get("userId"), d2.get("nonce")
        )

    def _finish_sts(
        self,
        location: str,
        ssecurity: str,
        user_id: Any,
        nonce: Any,
    ) -> bool:
        if nonce and "clientSign" not in location:
            sign = base64.b64encode(
                hashlib.sha1(f"nonce={nonce}&{ssecurity}".encode()).digest()
            ).decode()
            location = location + ("&" if "?" in location else "?") + "clientSign=" + quote(
                sign
            )
        self.session.get(location, allow_redirects=True, timeout=20)
        st = next(
            (c.value for c in self.session.cookies if c.name == "serviceToken"),
            None,
        )
        uid = str(user_id) if user_id else next(
            (c.value for c in self.session.cookies if c.name == "userId"),
            None,
        )
        if not st or not uid:
            return False
        self.service_token = st
        self.ssecurity = ssecurity
        self.user_id = str(uid)
        self.verification_url = None
        log.info("devices.cloud_login_ok", user_id=self.user_id)
        return True

    def get_devices(self, country: str = "de") -> list[dict[str, Any]]:
        """List devices via micloud using our established session."""
        from micloud import MiCloud

        mc = MiCloud(self.username, self.password)
        mc.user_id = self.user_id
        mc.service_token = self.service_token
        mc.ssecurity = self.ssecurity
        mc.session = self.session
        mc.default_server = country
        raw = mc.get_devices(country=country) or []
        if isinstance(raw, dict):
            raw = (
                raw.get("result", {}).get("list")
                or raw.get("list")
                or []
            )
        out: list[dict[str, Any]] = [d for d in raw if isinstance(d, dict)]
        return out


def cloud_login_and_list(
    username: str,
    password: str,
    country: str = "de",
    code_provider: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """Login to Xiaomi cloud and return raw device dicts (incl. localip + token)."""
    if country not in COUNTRY_CHOICES:
        raise ValueError(f"country must be one of {COUNTRY_CHOICES}, got {country!r}")

    def _default_provider(dest: str) -> str:
        print(f"\nXiaomi sent a verification code to {dest}.")
        print("Check Gmail for 'Xiaomi Account verificatie' and paste the 6-digit code.")
        return input("2FA code: ").strip()

    sess = XiaomiCloudSession(username, password)
    ok = sess.login(code_provider=code_provider or _default_provider)
    if not ok or not sess.service_token:
        raise RuntimeError(
            "Xiaomi cloud login failed. Check email/password and country "
            f"(tried server={country}). Dreamehome uses the same Xiaomi account."
        )

    # Prefer requested country; fall back across regions if empty
    devices = sess.get_devices(country=country)
    if not devices:
        for c in COUNTRY_CHOICES:
            if c == country:
                continue
            try:
                devices = sess.get_devices(country=c)
            except Exception as e:  # noqa: BLE001
                log.warning("devices.cloud_country_fail", country=c, err=str(e))
                continue
            if devices:
                log.info("devices.cloud_found_on", country=c, count=len(devices))
                break
    log.info("devices.cloud_listed", count=len(devices), country=country)
    return list(devices)


def _pick(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def cloud_device_to_config(raw: dict[str, Any]) -> DeviceConfig | None:
    """Map a Xiaomi cloud device row into our DeviceConfig."""
    did = _pick(raw, "did", "deviceID", "device_id")
    if did is None:
        return None
    model = _pick(raw, "model", "model_name")
    name = _pick(raw, "name", "extra.name", default=str(model or did))
    if isinstance(raw.get("extra"), dict):
        name = raw["extra"].get("name") or name
    ip = _pick(raw, "localip", "local_ip", "ip")
    token = _pick(raw, "token")
    mac = _pick(raw, "mac")
    kind = infer_kind(str(model) if model else None, str(name))
    if kind.value == "unknown" and not token:
        return None
    return DeviceConfig(
        id=stable_id_from_cloud(did, str(model) if model else None),
        name=str(name),
        kind=kind,
        model=str(model) if model else None,
        ip=str(ip) if ip else None,
        token=str(token) if token else None,
        did=str(did),
        mac=str(mac) if mac else None,
        extra={
            "uid": _pick(raw, "uid"),
            "isOnline": _pick(raw, "isOnline", "is_online"),
            "ssid": _pick(raw, "ssid"),
            "country": raw.get("_country"),
        },
    )


def sync_from_cloud(
    username: str,
    password: str,
    country: str = "de",
    kinds_only: set[str] | None = None,
    code_provider: Callable[[str], str] | None = None,
) -> DevicesFile:
    """Pull cloud device list and merge into devices.yaml (never stores password)."""
    raw_list = cloud_login_and_list(
        username, password, country=country, code_provider=code_provider
    )
    cfg = load_devices_file()
    kinds_only = kinds_only or {"air_purifier", "vacuum"}

    imported = 0
    skipped = 0
    for raw in raw_list:
        dev = cloud_device_to_config(raw)
        if not dev:
            skipped += 1
            continue
        if dev.kind.value not in kinds_only and "all" not in kinds_only:
            skipped += 1
            continue
        cfg = upsert_device(cfg, dev)
        imported += 1

    cfg.cloud = {
        **(cfg.cloud or {}),
        "country": country,
        "username": username,
        "last_sync": time.time(),
        "last_import_count": imported,
    }
    save_devices_file(cfg)
    log.info("devices.cloud_synced", imported=imported, skipped=skipped)
    return cfg
