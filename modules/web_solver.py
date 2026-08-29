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

WebSolver - handles hCaptcha solving and the manual-solve queue.

Supports both:
  - Single-service mode (legacy `service` key), and
  - Tiered mode (set "tiered": true): automatically activates
    Nopecha -> YesCaptcha -> Captchaly -> AntiCaptcha based on which
    API keys are present. Nopecha always tried first. Each tier tries
    3 times before falling through. Balance gating enabled.
"""


import asyncio
import aiohttp
import time
import json
import re
import webbrowser
import sys
import os
import subprocess
from urllib.parse import quote

from modules.services.yescaptcha import YesCaptchaService
from modules.services.nopecha import NopeCaptchaService
from modules.services.anticaptcha import AntiCaptchaService
from modules.services.captchaly import CaptchalyService
from modules.tiered_solver import TieredCaptchaSolver

class WebSolver:
    _manual_lock = asyncio.Lock()
    _solve_queue = asyncio.Queue()
    _processor_task = None
    _verification_futures = {}

    def __init__(self, bot):
        self.bot = bot
        self.site_key = "a6a1d5ce-612d-472d-8e37-7601408fbc09"
        self.auth_url = "https://discord.com/api/v9/oauth2/authorize?client_id=408785106942164992&response_type=code&redirect_uri=https://owobot.com/api/auth/discord/redirect&scope=identify guilds"
        self.tiered = False
        self.tiered_solver = None
        self._reload_service()

    def _reload_service(self):
        cfg = self.bot.config.get('security', {}).get('captcha_solver', {})
        self.api_key = cfg.get('api_key', '')
        self.active_service_name = cfg.get('service', 'yescaptcha').lower()
        self.enabled = cfg.get('enabled', True)
        self.browser_cfg = cfg.get('browser_config', {})
        self.tiered = bool(cfg.get('tiered', False))

        if self.tiered:
            self.tiered_solver = self.tiered_solver or TieredCaptchaSolver(self.bot)
            self.tiered_solver.reload()
            return

        if self.active_service_name == 'nopecha':
            self.active_key = cfg.get('nopecha_api_key', self.api_key)
            self.service = NopeCaptchaService(self.bot, self.active_key, self.site_key)
        elif self.active_service_name == 'anticaptcha':
            self.active_key = cfg.get('anticaptcha_api_key', self.api_key)
            self.service = AntiCaptchaService(self.bot, self.active_key, self.site_key)
        elif self.active_service_name == 'captchaly':
            self.active_key = cfg.get('captchaly_api_key', self.api_key)
            self.service = CaptchalyService(self.bot, self.active_key, self.site_key)
        else:
            self.active_key = cfg.get('yescaptcha_api_key', self.api_key)
            self.service = YesCaptchaService(self.bot, self.active_key, self.site_key)

    async def get_balance(self):
        self._reload_service()
        if self.tiered:
            return await self.tiered_solver.get_balance()
        return await self.service.get_balance()

    async def solve_hcaptcha(self, retries=3):
        self._reload_service()
        if self.tiered:
            return await self.tiered_solver.solve_hcaptcha(retries)
        return await self.service.solve_hcaptcha(retries)

    async def auto_verify(self, tries=3):
        self._reload_service()

        if self.tiered:
            if not self.tiered_solver.active_tiers:
                self.bot.log("ERROR", "No captcha API keys found in settings. Tier system inactive.")
                return False
        else:
            if not self.active_key and self.active_service_name != 'nopecha':
                self.bot.log("ERROR", f"{self.active_service_name.capitalize()} API key missing in settings.")
                return False

            balance = await self.get_balance()
            if self.active_service_name == 'yescaptcha' and balance < 30:
                self.bot.log("ERROR", f"YesCaptcha balance too low: {balance}")
                return False
            elif self.active_service_name == 'nopecha' and balance < 1:
                self.bot.log("ERROR", f"NopeCHA balance too low: {balance}")
                return False
            elif self.active_service_name == 'anticaptcha' and balance < 0.5:
                self.bot.log("ERROR", f"AntiCaptcha balance too low: {balance}")
                return False
            elif self.active_service_name == 'captchaly' and balance < 0.005:
                self.bot.log("ERROR", f"Captchaly balance too low: {balance}")
                return False

        headers = {
            "Authorization": self.bot.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                auth_payload = {
                    "authorize": True,
                    "permissions": "0",
                    "integration_type": 0,
                    "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000}
                }
                async with session.post(self.auth_url, json=auth_payload) as resp:
                    if resp.status != 200:
                        return False
                    auth_data = await resp.json()
                    redirect_url = auth_data.get("location")

                if redirect_url:
                    async with session.get(redirect_url) as r:
                        pass

                async with session.get("https://owobot.com/captcha") as captcha_resp:
                    if captcha_resp.status != 200:
                        self.bot.log("ERROR", "Failed to visit captcha page.")
                        return False

                async with session.get("https://owobot.com/api/auth") as auth_check:
                    if auth_check.status != 200:
                        self.bot.log("ERROR", "Auth session check failed.")
                        return False

                solution = await self.solve_hcaptcha(tries)
                if not solution:
                    return False

                verify_headers = {
                    "Referer": "https://owobot.com/captcha",
                    "Origin": "https://owobot.com",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    "https://owobot.com/api/captcha/verify",
                    json={"token": solution},
                    headers=verify_headers
                ) as verify_resp:
                    if verify_resp.status == 200:
                        self.bot.log("SUCCESS", "Captcha verified successfully.")
                        self.mark_verification_done(str(self.bot.user.id))
                        return True
                    else:
                        error_text = await verify_resp.text()
                        self.bot.log("ERROR", f"Verification failed (Status {verify_resp.status}): {error_text}")
                        return False

            except Exception as e:
                self.bot.log("ERROR", f"Auto-verification failed: {e}")
                return False

    @classmethod
    def enqueue_manual_solve(cls, bot_id, captcha_url=None):
        cls._solve_queue.put_nowait((bot_id, captcha_url or "https://owobot.com/captcha"))
        if cls._processor_task is None or cls._processor_task.done():
            cls._processor_task = asyncio.create_task(cls._manual_processor())

    @classmethod
    async def _manual_processor(cls):
        while True:
            try:
                bot_id, captcha_url = await cls._solve_queue.get()

                async with cls._manual_lock:
                    future = asyncio.get_event_loop().create_future()
                    cls._verification_futures[bot_id] = future

                    bot = cls._get_bot_by_user_id(bot_id)
                    if not bot:
                        cls._verification_futures.pop(bot_id, None)
                        cls._solve_queue.task_done()
                        continue

                    username = getattr(bot, 'username', bot_id)
                    bot.log("SECURITY", f"[QUEUE] Manual solve started for {username} - {captcha_url}")

                    try:
                        from dashboard.app import register_captcha_challenge
                        register_captcha_challenge(bot_id, {"account_name": username, "captcha_url": captcha_url})
                    except Exception as e:
                        bot.log("ERROR", f"[QUEUE] Failed to register captcha for dashboard: {e}")

                    async def alert_loop():
                        start = time.time()
                        last_alert = 0
                        while not future.done():
                            elapsed = int(time.time() - start)
                            if elapsed > 0 and elapsed % 60 == 0 and elapsed != last_alert:
                                mins = elapsed // 60
                                secs = elapsed % 60
                                if mins == 0:
                                    bot.log("SECURITY", f"[QUEUE] {username}: {secs}s elapsed – captcha still pending")
                                elif mins < 10:
                                    bot.log("SECURITY", f"[QUEUE] {username}: {mins}m {secs}s elapsed – captcha still pending")
                                else:
                                    bot.log("SECURITY", f"[QUEUE] {username}: {mins}m {secs}s elapsed – OVER 10 MINUTES! Solve now to avoid strike!")
                                last_alert = elapsed
                            await asyncio.sleep(1)

                    alert_task = asyncio.create_task(alert_loop())

                    sec_cfg = bot.config.get("security", {})
                    if not getattr(bot, 'is_mobile', False):
                        auto_open = sec_cfg.get("open_captcha_url_on_pc", False)
                    else:
                        auto_open = sec_cfg.get("open_captcha_url_on_mobile", False)

                    if auto_open:
                        bot.log("SYS", f"[QUEUE] Opening captcha for {username}...")
                        success = await cls.open_in_browser(captcha_url, bot=bot)
                        if not success:
                            bot.log("ERROR", f"[QUEUE] Failed to open browser for {username}")

                    await future

                    bot.log("SUCCESS", f"[QUEUE] {username}: Manual captcha VERIFIED!")

                    alert_task.cancel()
                    try:
                        await alert_task
                    except asyncio.CancelledError:
                        pass

                    cls._verification_futures.pop(bot_id, None)
                    cls._solve_queue.task_done()

            except Exception as e:
                import traceback
                print(f"[QUEUE ERROR] Manual processor crashed: {e}")
                traceback.print_exc()

    @classmethod
    def _get_bot_by_user_id(cls, user_id):
        try:
            for bot in getattr(state, 'bot_instances', []):
                if hasattr(bot, 'user') and bot.user and str(bot.user.id) == str(user_id):
                    return bot
            return None
        except Exception:
            return None

    @classmethod
    def mark_verification_done(cls, bot_id):
        future = cls._verification_futures.get(bot_id)
        if future and not future.done():
            future.set_result(True)

        try:
            from dashboard.app import clear_captcha_challenge
            clear_captcha_challenge(bot_id)
        except Exception as e:
            bot = cls._get_bot_by_user_id(bot_id)
            if bot:
                bot.log("ERROR", f"Failed to clear captcha challenge: {e}")

    @staticmethod
    async def open_in_browser(captcha_url=None, bot=None):
        if not bot:
            return False

        auth_url = "https://discord.com/api/v9/oauth2/authorize?client_id=408785106942164992&response_type=code&redirect_uri=https://owobot.com/api/auth/discord/redirect&scope=identify guilds"

        headers = {
            "Authorization": bot.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                auth_payload = {
                    "authorize": True,
                    "permissions": "0",
                    "integration_type": 0,
                    "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000}
                }

                full_auth_url = auth_url
                if captcha_url:
                    full_auth_url += f"&state={quote(captcha_url)}"

                async with session.post(full_auth_url, json=auth_payload) as resp:
                    if resp.status != 200:
                        bot.log("ERROR", f"Browser Solver: OAuth failed (Status {resp.status})")
                        if captcha_url:
                            bot.log("SYS", "OAuth failed. Opening raw captcha URL as fallback.")
                            _open_url(captcha_url, bot)
                        return False

                    auth_data = await resp.json()
                    redirect_url = auth_data.get("location")

                if redirect_url:
                    bot.log("SYS", f"Opening Auth Login for {bot.username}...")
                    _open_url(redirect_url, bot)
                    return True
                return False
            except Exception as e:
                bot.log("ERROR", f"Browser solver start failed: {e}")
                return False

def _open_url(url, bot):
    if getattr(bot, 'is_mobile', False):
        try:
            subprocess.Popen(["termux-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            bot.log("SYS", "Opened URL using termux-open")
            return
        except FileNotFoundError:
            try:
                subprocess.Popen(["am", "start", "-a", "android.intent.action.VIEW", "-d", url],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot.log("SYS", "Opened URL using am start")
                return
            except FileNotFoundError:
                bot.log("WARN", "Failed to open URL on mobile. Install termux-open or use dashboard.")
                return

    opened = False
    try:
        if webbrowser.open_new_tab(url):
            bot.log("SYS", "Opened URL using webbrowser module")
            opened = True
    except Exception:
        pass

    if not opened:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot.log("SYS", "Opened URL using Windows start command")
                opened = True
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot.log("SYS", "Opened URL using macOS open command")
                opened = True
            else:
                try:
                    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    bot.log("SYS", "Opened URL using xdg-open")
                    opened = True
                except FileNotFoundError:
                    try:
                        subprocess.Popen(["sensible-browser", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        bot.log("SYS", "Opened URL using sensible-browser")
                        opened = True
                    except FileNotFoundError:
                        pass
        except Exception as e:
            bot.log("WARN", f"Failed command line opener fallback: {e}")

    if not opened:
        bot.log("WARN", "All browser opening methods failed. Please use dashboard to solve captcha manually.")

import core.state as state

def setup_web_solver(bot):
    return WebSolver(bot)
