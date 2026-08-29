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

TieredCaptchaSolver - automatic multi-tier hCaptcha solving.

Tier order (fixed):
    1. Nopecha     (always first - low solving rate)
    2. YesCaptcha
    3. Captchaly
    4. AntiCaptcha
    5. Local AI ONNX solver (letterword captchas only)

Rules:
    - A tier is automatically activated when its API key is present.
    - Each activated tier tries `retries` (default 3) times before
      falling through to the next tier.
    - Balance gating: tiers with too-low balance are skipped.
"""

import asyncio

from modules.services.yescaptcha import YesCaptchaService
from modules.services.nopecha import NopeCaptchaService
from modules.services.anticaptcha import AntiCaptchaService
from modules.services.captchaly import CaptchalyService


class TieredCaptchaSolver:
    # Fixed tier order. Nopecha always first.
    TIER_ORDER = [
        ("captchaly", "captchaly_api_key", CaptchalyService),
        ("yescaptcha", "yescaptcha_api_key", YesCaptchaService),
        ("nopecha", "nopecha_api_key", NopeCaptchaService),
        ("anticaptcha", "anticaptcha_api_key", AntiCaptchaService),
    ]

    # Minimum balance required for a tier to be used.
    MIN_BALANCE = {
        "nopecha": 1,
        "yescaptcha": 30,
        "captchaly": 0.005,
        "anticaptcha": 0.5,
    }

    def __init__(self, bot):
        self.bot = bot
        self.site_key = "a6a1d5ce-612d-472d-8e37-7601408fbc09"
        self.retries = 3
        self.active_tiers = []

    def reload(self):
        cfg = self.bot.config.get('security', {}).get('captcha_solver', {})
        self.retries = int(cfg.get('tier_retries', 3))
        self.active_tiers = self._active_tiers(cfg)
        return self.active_tiers

    def _active_tiers(self, cfg):
        """Return activated tiers based on which API keys are present."""
        active = []
        for name, key_field, _cls in self.TIER_ORDER:
            key = cfg.get(key_field, '') or cfg.get('api_key', '')
            if key:
                active.append(name)
        return active

    def _build_service(self, name):
        cfg = self.bot.config.get('security', {}).get('captcha_solver', {})
        for tier_name, key_field, cls in self.TIER_ORDER:
            if tier_name == name:
                key = cfg.get(key_field, '') or cfg.get('api_key', '')
                return cls(self.bot, key, self.site_key)
        return None

    async def get_balance(self):
        """Balance for every activated tier: {name: balance}."""
        self.reload()
        balances = {}
        for name in self.active_tiers:
            service = self._build_service(name)
            if service:
                balances[name] = await service.get_balance()
        return balances

    async def solve_hcaptcha(self, retries=None):
        """Try each activated tier in order; each gets `retries` attempts."""
        self.reload()
        retries = retries or self.retries

        if not self.active_tiers:
            self.bot.log("ERROR", "No captcha API keys present. Tier system inactive.")
            return None

        self.bot.log("SYS", f"Tiered solver active. Active tiers: {', '.join(self.active_tiers)}")

        for name in self.active_tiers:
            service = self._build_service(name)
            if not service:
                continue

            # Balance gating.
            try:
                balance = await service.get_balance()
                min_bal = self.MIN_BALANCE.get(name, 0)
                if balance < min_bal:
                    self.bot.log("WARN", f"[Tier] {name} skipped: balance {balance} < {min_bal}")
                    continue
            except Exception as e:
                self.bot.log("ERROR", f"[Tier] {name} balance check failed: {e}")

            self.bot.log("SYS", f"[Tier] Trying {name} ({retries} attempts)...")
            try:
                solution = await service.solve_hcaptcha(retries)
            except Exception as e:
                self.bot.log("ERROR", f"[Tier] {name} raised an exception: {e}")
                solution = None

            if solution:
                self.bot.log("SUCCESS", f"[Tier] Solved via {name}.")
                return solution

            self.bot.log("WARN", f"[Tier] {name} failed all {retries} attempts. Falling through.")

        self.bot.log("ERROR", "All captcha tiers failed.")
        return None

    async def solve_letterword(self, url, letter_count=5):
        """Local AI ONNX solver - last-resort tier for letterword captchas."""
        solver = getattr(self.bot, 'captcha_solver', None)
        if not solver or not getattr(solver, 'onnx_session', None):
            self.bot.log("ERROR", "Local AI solver unavailable (onnxruntime/model missing).")
            return None
        self.bot.log("SYS", "[Tier] Falling through to Local AI ONNX solver (letterword).")
        return await solver.solve_image(url, letter_count)


def setup_tiered_solver(bot):
    return TieredCaptchaSolver(bot)
