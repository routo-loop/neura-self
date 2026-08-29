# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.


"""
Author: Routo
NeuraSelf-UwU - https://github.com/routo-loop/neura-self
"""



import asyncio
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

try:
    import aiohttp
except ImportError:
    aiohttp = None

import core.state as state

PROXIES_FILE = os.path.join(state.CONFIG_DIR, "proxies.json")
ACCOUNTS_FILE = os.path.join(state.CONFIG_DIR, "accounts.json")

DEFAULT_PROXY_TYPE = "socks5"
SUPPORTED_TYPES = ("http", "https", "socks5", "socks4")


def _ensure_config_dir():
    if not os.path.exists(state.CONFIG_DIR):
        os.makedirs(state.CONFIG_DIR)


def _new_proxy_id():
    return f"px_{secrets.token_hex(4)}"


def load_proxies():
    _ensure_config_dir()
    if not os.path.exists(PROXIES_FILE):
        save_proxies([])
        return []
    try:
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("proxies", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_proxies(proxies):
    _ensure_config_dir()
    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
        json.dump({"proxies": proxies}, f, indent=4)


def load_accounts():
    accounts = []

    # Đọc accounts.json nếu có
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f).get("accounts", [])
        except (json.JSONDecodeError, OSError):
            accounts = []

    # Nếu file có account thì dùng như cũ
    if accounts:
        return accounts

    # ============================
    # Không có account -> đọc ENV
    # ============================

    env_accounts = []
    index = 1

    while True:
        token = os.getenv(f"ACCOUNT{index}_TOKEN")

        # Không còn token thì dừng
        if not token:
            break

        account = {
            "name": os.getenv(f"ACCOUNT{index}_NAME", f"Account {index}"),
            "token": token,
            "channels": [],
            "enabled": True,
            "proxy_id": None,
            "token_masked": ""
        }

        channels = os.getenv(f"ACCOUNT{index}_CHANNELS", "")

        if channels:
            account["channels"] = [
                c.strip()
                for c in channels.split(",")
                if c.strip()
            ]

        proxy = os.getenv(f"ACCOUNT{index}_PROXY")

        if proxy:
            account["proxy_id"] = proxy

        env_accounts.append(account)
        index += 1

    return env_accounts


def save_accounts(accounts):
    _ensure_config_dir()
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"accounts": accounts}, f, indent=4)


def _normalize_type(proxy_type):
    proxy_type = (proxy_type or DEFAULT_PROXY_TYPE).lower().strip()
    if proxy_type not in SUPPORTED_TYPES:
        return DEFAULT_PROXY_TYPE
    return proxy_type


def _proxy_fingerprint(host, port, username="", password="", proxy_type=DEFAULT_PROXY_TYPE):
    return f"{_normalize_type(proxy_type)}://{username}:{password}@{host}:{port}"


def parse_proxy_line(line):
    """
    parse a single proxy line.
    support: host:port, user:pass@host:port, socks5://..., http://...
    returns (proxy_dict, error_message).
    """
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None, "empty"

    proxy_type = DEFAULT_PROXY_TYPE
    username = ""
    password = ""
    host = ""
    port = None

    if "://" in line:
        parsed = urlparse(line)
        proxy_type = _normalize_type(parsed.scheme)
        host = parsed.hostname or ""
        port = parsed.port
        username = parsed.username or ""
        password = parsed.password or ""
        if not host or not port:
            return None, f"invalid URL: {line}"
    else:
        auth_part = None
        host_part = line
        if "@" in line:
            auth_part, host_part = line.rsplit("@", 1)

        if auth_part and ":" in auth_part:
            username, password = auth_part.split(":", 1)

        if ":" not in host_part:
            return None, f"missing port: {line}"

        host, port_str = host_part.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            return None, f"invalid port: {line}"

    if not host or not port:
        return None, f"invalid format: {line}"

    label = f"{host}:{port}"
    return {
        "id": _new_proxy_id(),
        "label": label,
        "type": _normalize_type(proxy_type),
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "enabled": True,
        "status": "unknown",
        "last_check": None,
        "assigned_to": None,
    }, None


def build_proxy_url(proxy_dict):
    if not proxy_dict:
        return None
    proxy_type = _normalize_type(proxy_dict.get("type"))
    host = proxy_dict.get("host", "")
    port = proxy_dict.get("port")
    if not host or not port:
        return None
    return f"{proxy_type}://{host}:{port}"


def get_proxy_auth(proxy_dict):
    if not proxy_dict:
        return None
    username = proxy_dict.get("username") or ""
    password = proxy_dict.get("password") or ""
    if username:
        return aiohttp.BasicAuth(username, password)
    return None


def get_proxy_by_id(proxy_id):
    if not proxy_id:
        return None
    for proxy in load_proxies():
        if proxy.get("id") == proxy_id and proxy.get("enabled", True):
            return proxy
    return None


def resolve_account_proxy(account):
    proxy_id = account.get("proxy_id") if account else None
    if not proxy_id:
        return None, None, "direct"

    proxy = get_proxy_by_id(proxy_id)
    if not proxy:
        return None, None, "direct"

    label = proxy.get("label") or f"{proxy.get('host')}:{proxy.get('port')}"
    return build_proxy_url(proxy), get_proxy_auth(proxy), label


def bulk_import(text):
    existing = load_proxies()
    fingerprints = {
        _proxy_fingerprint(p.get("host"), p.get("port"), p.get("username", ""), p.get("password", ""), p.get("type"))
        for p in existing
    }

    added = []
    errors = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        proxy, err = parse_proxy_line(raw_line)
        if err == "empty":
            continue
        if err:
            errors.append({"line": i, "text": raw_line.strip(), "error": err})
            continue

        fp = _proxy_fingerprint(
            proxy["host"], proxy["port"], proxy.get("username", ""), proxy.get("password", ""), proxy.get("type")
        )
        if fp in fingerprints:
            errors.append({"line": i, "text": raw_line.strip(), "error": "duplicate"})
            continue

        fingerprints.add(fp)
        existing.append(proxy)
        added.append(proxy)

    if added:
        save_proxies(existing)
    return {"added": added, "errors": errors, "total": len(existing)}


async def _request_through_proxy(proxy_dict, timeout=5):
    url = build_proxy_url(proxy_dict)
    auth = get_proxy_auth(proxy_dict)
    proxy_type = _normalize_type(proxy_dict.get("type"))

    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    try:
        if proxy_type in ("socks4", "socks5"):
            from aiohttp_socks import ProxyConnector

            connector = ProxyConnector.from_url(url, rdns=True)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout_cfg) as session:
                async with session.get("https://discord.com/api/v9/gateway") as resp:
                    return resp.status < 500
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get("https://discord.com/api/v9/gateway", proxy=url, proxy_auth=auth) as resp:
                return resp.status < 500
    except Exception:
        return False


async def test_proxy(proxy_dict):
    ok = await _request_through_proxy(proxy_dict)
    proxy_dict["status"] = "ok" if ok else "fail"
    proxy_dict["last_check"] = datetime.now(timezone.utc).isoformat()
    return ok


async def test_all_proxies():
    proxies = load_proxies()
    results = []
    for proxy in proxies:
        if not proxy.get("enabled", True):
            continue
        ok = await test_proxy(proxy)
        results.append({"id": proxy.get("id"), "ok": ok})
    save_proxies(proxies)
    return results


def _sync_assigned_to(proxies, accounts):
    account_names = {a.get("name"): a for a in accounts}
    proxy_ids = {p.get("id") for p in proxies}
    for proxy in proxies:
        assigned = proxy.get("assigned_to")
        if assigned and assigned not in account_names:
            proxy["assigned_to"] = None
    for acc in accounts:
        pid = acc.get("proxy_id")
        if pid and pid in proxy_ids:
            for proxy in proxies:
                if proxy.get("id") == pid:
                    proxy["assigned_to"] = acc.get("name")
    save_proxies(proxies)


def auto_assign():
    proxies = load_proxies()
    accounts = load_accounts()

    free_proxies = [
        p for p in proxies
        if p.get("enabled", True)
        and not p.get("assigned_to")
        and p.get("status") == "ok"
    ]
    unassigned_accounts = [a for a in accounts if not a.get("proxy_id")]

    assigned = []
    for acc, proxy in zip(unassigned_accounts, free_proxies):
        acc["proxy_id"] = proxy["id"]
        proxy["assigned_to"] = acc.get("name")
        assigned.append({"account": acc.get("name"), "proxy_id": proxy["id"]})

    if assigned:
        save_accounts(accounts)
        save_proxies(proxies)
    return assigned


def remove_proxy(proxy_id):
    proxies = load_proxies()
    proxies = [p for p in proxies if p.get("id") != proxy_id]
    save_proxies(proxies)

    accounts = load_accounts()
    changed = False
    for acc in accounts:
        if acc.get("proxy_id") == proxy_id:
            acc["proxy_id"] = None
            changed = True
    if changed:
        save_accounts(accounts)
    return True


def remove_all_proxies():
    save_proxies([])
    accounts = load_accounts()
    changed = False
    for acc in accounts:
        if acc.get("proxy_id"):
            acc["proxy_id"] = None
            changed = True
    if changed:
        save_accounts(accounts)
    return True


def remove_failed_proxies():
    proxies = load_proxies()
    failed_ids = {p["id"] for p in proxies if p.get("status") == "fail"}
    proxies = [p for p in proxies if p.get("id") not in failed_ids]
    save_proxies(proxies)

    if failed_ids:
        accounts = load_accounts()
        changed = False
        for acc in accounts:
            if acc.get("proxy_id") in failed_ids:
                acc["proxy_id"] = None
                changed = True
        if changed:
            save_accounts(accounts)
    return len(failed_ids)



def unassign_proxy_from_accounts(proxy_id):
    accounts = load_accounts()
    changed = False
    for acc in accounts:
        if acc.get("proxy_id") == proxy_id:
            acc["proxy_id"] = None
            changed = True
    if changed:
        save_accounts(accounts)


def sync_proxy_assignments():
    proxies = load_proxies()
    accounts = load_accounts()
    _sync_assigned_to(proxies, accounts)


def mask_token(token):
    if not token or len(token) < 12:
        return token
    return f"{token[:6]}...{token[-4:]}"
