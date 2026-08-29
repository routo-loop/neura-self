# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Author: Routo
NeuraSelf-UwU - https://github.com/routo-loop/neura-self
"""

import aiohttp
import json
import base64
import uuid
import time
import re
import random
from datetime import datetime


class InteractionManager:
    def __init__(self, bot):
        self.bot = bot
        self._build_number = 310000
        self._last_fetch = 0
        self._installation_id = str(uuid.uuid4()).replace('-', '')[:32]
        self.chrome_version = f"{random.randint(124, 127)}.0.0.0"
        self.user_agent = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.chrome_version} Safari/537.36"
        )

    async def _fetch_build_number(self):
        now = time.time()
        if now - self._last_fetch < 43200 and self._build_number > 310000:
            return self._build_number

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://discord.com/login", timeout=10) as resp:
                    text = await resp.text()

                match = re.search(r"assets/(sentry\.\w+)\.js", text)
                if not match:
                    match = re.search(r"assets/(\d+\.\w+)\.js", text)

                if match:
                    url = f"https://static.discord.com/assets/{match.group(1)}.js"
                    async with session.get(url, timeout=10) as resp:
                        js = await resp.text()

                    b_match = re.search(r'buildNumber\D+(\d+)"', js)
                    if b_match:
                        self._build_number = int(b_match.group(1))
                        self._last_fetch = now
        except Exception:
            pass
        return self._build_number

    def _generate_super_properties(self, build_number):
        major_ver = self.chrome_version.split('.')[0]
        props = {
            "os": "Windows",
            "browser": "Chrome",
            "device": "",
            "system_locale": "en-US",
            "browser_user_agent": self.user_agent,
            "browser_version": self.chrome_version,
            "os_version": "10",
            "referrer": "",
            "referring_domain": "",
            "referrer_current": "",
            "referring_domain_current": "",
            "release_channel": "stable",
            "client_build_number": build_number,
            "client_event_source": None,
            "has_client_mods": False,
            "client_launch_id": str(uuid.uuid4()),
            "launch_signature": str(uuid.uuid4()),
            "client_app_state": "focused",
            "client_heartbeat_session_id": str(uuid.uuid4())
        }
        return base64.b64encode(json.dumps(props, separators=(',', ':')).encode()).decode()

    async def _get_headers(self, channel_id=None, guild_id=None):
        bn = await self._fetch_build_number()
        sp = self._generate_super_properties(bn)
        tz = datetime.now().astimezone().tzname() or "UTC"

        referer = "https://discord.com/channels/@me"
        if guild_id and channel_id:
            referer = f"https://discord.com/channels/{guild_id}/{channel_id}"
        elif channel_id:
            referer = f"https://discord.com/channels/@me/{channel_id}"

        major_ver = self.chrome_version.split('.')[0]
        return {
            "Authorization": self.bot.token,
            "Content-Type": "application/json",
            "X-Super-Properties": sp,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": tz,
            "User-Agent": self.user_agent,
            "Origin": "https://discord.com",
            "Referer": referer,
            "Sec-CH-UA": f'"Not/A)Brand";v="8", "Chromium";v="{major_ver}", "Google Chrome";v="{major_ver}"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-CH-UA-Platform-Version": '"15.0.0"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Debug-Options": "bugReporterEnabled",
            "X-Discord-Features": "quests",
            "X-Installation-Id": self._installation_id
        }

    async def click_button(self, custom_id, message, guild_id=None):
        if not custom_id or not message:
            return False

        return await self.click_button_raw(
            custom_id=custom_id,
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=guild_id or (message.guild.id if message.guild else None),
            author_id=message.author.id,
            flags=message.flags.value
        )

    async def click_button_raw(self, custom_id, message_id, channel_id, author_id, guild_id=None, flags=0):
        if not custom_id:
            self.bot.log("ERROR", "Interaction rejected locally: empty custom_id")
            return False

        payload = {
            "type": 3,
            "application_id": str(author_id),
            "guild_id": str(guild_id) if guild_id else None,
            "channel_id": str(channel_id),
            "message_id": str(message_id),
            "session_id": self.bot.ws.session_id if hasattr(self.bot, 'ws') else None,
            "message_flags": flags,
            "data": {
                "component_type": 2,
                "custom_id": custom_id
            }
        }

        headers = await self._get_headers(channel_id=channel_id, guild_id=guild_id)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://discord.com/api/v9/interactions",
                    json=payload,
                    headers=headers
                ) as resp:
                    if resp.status == 204:
                        self.bot.log(
                            "INTERACTION",
                            f"Button accepted: custom_id={custom_id} message={message_id} "
                            f"channel={channel_id} guild={guild_id or '-'}"
                        )
                        return True

                    error_text = await resp.text()
                    # Keep enough response context to diagnose stale buttons, invalid payloads,
                    # authentication/session issues, or Discord-side rejection.
                    compact_error = error_text.replace("\n", " ")[:1000]
                    self.bot.log(
                        "ERROR",
                        f"Interaction failed HTTP {resp.status}: custom_id={custom_id} "
                        f"message={message_id} channel={channel_id} guild={guild_id or '-'} "
                        f"response={compact_error}"
                    )
                    return False
        except Exception as e:
            self.bot.log(
                "ERROR",
                f"Interaction exception: custom_id={custom_id} message={message_id} "
                f"channel={channel_id} guild={guild_id or '-'} error={e}"
            )
            return False


def setup_interactions(bot):
    return InteractionManager(bot)
