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

import discord
from discord.ext import commands
import asyncio
import time
import random

from component_v2_neura import parse_v2_message, get_boss_battle_id
import json
import os
import re


class Boss(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_file = "data/boss_state.json"
        self._load_state()
        self.enabled = self.bot.config.get("boss", {}).get("enabled", True)
        self.join_chance = self.bot.config.get("boss", {}).get("join_chance", 100)
        self.target_guilds = [str(g) for g in self.bot.config.get("boss", {}).get("target_guilds", [])]
        self.ignore_guilds = [str(g) for g in self.bot.config.get("boss", {}).get("ignore_guilds", [])]
        self.playing_guild_ids = set()
        self._update_playing_guilds()

    def _update_playing_guilds(self):
        self.playing_guild_ids.clear()
        for c_id in self.bot.channels:
            try:
                ch = self.bot.get_channel(int(c_id))
            except (TypeError, ValueError):
                ch = None
            if ch and ch.guild:
                self.playing_guild_ids.add(str(ch.guild.id))

        if hasattr(self.bot, "guild_id") and self.bot.guild_id:
            self.playing_guild_ids.add(str(self.bot.guild_id))

    async def register_actions(self):
        cfg = self.bot.config.get("boss", {})
        self.enabled = cfg.get("enabled", True)
        self.join_chance = cfg.get("join_chance", 100)
        self.target_guilds = [str(g) for g in cfg.get("target_guilds", []) if str(g).strip()]
        self.ignore_guilds = [str(g) for g in cfg.get("ignore_guilds", []) if str(g).strip()]
        self._update_playing_guilds()
        self.bot.log(
            "SYS",
            f"Boss settings refreshed: enabled={self.enabled}, targets={len(self.target_guilds)}, "
            f"ignored={len(self.ignore_guilds)}, chance={self.join_chance}%"
        )

    def _load_state(self):
        self.tickets = 3
        self.last_reset = 0
        self.joined_ids = set()
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.tickets = data.get("tickets", 3)
                    self.last_reset = data.get("last_reset", 0)
                    self.joined_ids = set(data.get("joined_ids", []))
            except Exception as e:
                self.bot.log("ERROR", f"Boss state load failed: {e}")

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump({
                    "tickets": self.tickets,
                    "last_reset": self.last_reset,
                    "joined_ids": list(self.joined_ids)
                }, f)
        except Exception as e:
            self.bot.log("ERROR", f"Boss state save failed: {e}")

    def _check_reset(self):
        now = time.time()
        if now - self.last_reset > 72000:
            self.tickets = 3
            self.last_reset = now
            self.joined_ids.clear()
            self._save_state()
            self.bot.log("BOSS", "Boss ticket state reset to 3/3.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if str(message.author.id) != self.bot.owo_bot_id:
            return
        if message.channel.id != self.bot.channel_id:
            return

        if not self.bot.is_message_for_me(message):
            return

        full_content = self.bot.get_full_content(message)
        sync_happened = False
        if "you currently have" in full_content and "/3 boss ticket" in full_content:
            match = re.search(r'(\d+)/3 boss ticket', full_content)
            if match:
                self.tickets = int(match.group(1))
                self.last_reset = time.time()
                sync_happened = True
        elif "ran out of boss tickets" in full_content:
            self.tickets = 0
            self.last_reset = time.time()
            sync_happened = True

        if sync_happened:
            self.bot.log("BOSS", f"Synced tickets with OwO: {self.tickets}/3")
            self._save_state()

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        if not self.enabled:
            return
        if self.bot.paused:
            return
        if isinstance(msg, bytes):
            return

        try:
            raw_data = json.loads(msg)
        except Exception:
            return

        if raw_data.get("t") != "MESSAGE_CREATE":
            return

        data = raw_data.get("d", {})
        author_id = str(data.get("author", {}).get("id") or "")
        if author_id != str(self.bot.owo_bot_id):
            return

        message_id = str(data.get("id") or "")
        channel_id_raw = data.get("channel_id")
        guild_id = str(data.get("guild_id") or "")
        if not channel_id_raw:
            self.bot.log("BOSS", f"SKIP message={message_id}: missing channel_id")
            return

        try:
            channel_id = int(channel_id_raw)
        except (TypeError, ValueError):
            self.bot.log("BOSS", f"SKIP message={message_id}: invalid channel_id={channel_id_raw!r}")
            return

        components = parse_v2_message(data)
        content = (data.get("content") or "").lower()
        v2_text = " ".join(
            c.content for c in components if c.name == "text_display" and c.content
        ).lower()
        full_text = f"{content} {v2_text}"
        is_spawn = "runs away" in full_text or "guild boss" in full_text
        fight_buttons = [
            c for c in components
            if c.name == "button" and c.custom_id
        ]
        fight_btn = next((c for c in fight_buttons if c.custom_id == "guildboss_fight"), None)

        # Only emit detailed diagnostics for messages that look Boss-related.
        # This keeps the terminal useful while still exposing why a Boss was missed.
        if is_spawn or fight_btn:
            button_ids = [str(c.custom_id) for c in fight_buttons]
            self.bot.log(
                "BOSS",
                f"DETECT message={message_id} guild={guild_id or '-'} channel={channel_id} "
                f"components={len(components)} buttons={button_ids} "
                f"spawn={is_spawn} fight_button={'YES' if fight_btn else 'NO'}"
            )

        if not components:
            if is_spawn:
                self.bot.log("BOSS", f"SKIP message={message_id}: Boss-like message has no parseable components")
            return

        if not is_spawn and not fight_btn:
            if "already joined" in v2_text:
                self.bot.log("BOSS", f"SKIP message={message_id}: already joined")
            return

        # Blacklist always wins.
        if guild_id in self.ignore_guilds:
            self.bot.log("BOSS", f"SKIP message={message_id}: guild {guild_id} is ignored")
            return

        # Only explicitly targeted guilds are eligible.
        if guild_id not in self.target_guilds:
            self.bot.log(
                "BOSS",
                f"SKIP message={message_id}: guild {guild_id} is not targeted "
                f"(targets={','.join(self.target_guilds) or 'none'})"
            )
            return

        if not fight_btn:
            self.bot.log(
                "BOSS",
                f"SKIP message={message_id}: Boss detected in targeted guild but "
                f"custom_id 'guildboss_fight' was not found"
            )
            return

        battle_id = get_boss_battle_id(components)
        if battle_id and battle_id in self.joined_ids:
            self.bot.log("BOSS", f"SKIP message={message_id}: battle {battle_id} already processed")
            return

        tracking_id = battle_id or f"msg_{message_id}"

        self._check_reset()
        if self.tickets <= 0:
            self.bot.log("BOSS", f"SKIP message={message_id}: no boss tickets left (0/3)")
            return

        if random.randint(1, 100) > self.join_chance:
            self.bot.log(
                "BOSS",
                f"SKIP message={message_id}: join_chance={self.join_chance}% rejected this spawn"
            )
            self.joined_ids.add(tracking_id)
            self._save_state()
            return

        self.bot.log(
            "BOSS",
            f"JOIN attempt message={message_id} guild={guild_id} channel={channel_id} "
            f"battle={tracking_id} ticket={self.tickets}/3 custom_id={fight_btn.custom_id}"
        )

        delay = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay)

        if self.bot.paused:
            self.bot.log("BOSS", f"ABORT message={message_id}: bot paused during {delay:.2f}s delay")
            return

        success = await self.bot.interactions.click_button_raw(
            custom_id=fight_btn.custom_id,
            message_id=message_id,
            channel_id=channel_id,
            author_id=author_id,
            guild_id=guild_id,
            flags=data.get("flags", 0)
        )

        if success:
            self.tickets = max(0, self.tickets - 1)
            self.joined_ids.add(tracking_id)
            self._save_state()
            self.bot.log(
                "SUCCESS",
                f"Joined Boss Battle! guild={guild_id} battle={tracking_id} tickets={self.tickets}/3"
            )
        else:
            # Do not mark the battle as joined when the actual interaction failed.
            # A later MESSAGE_CREATE/retry path can still attempt it.
            self.bot.log(
                "ERROR",
                f"JOIN FAILED message={message_id} guild={guild_id} battle={tracking_id} "
                f"custom_id={fight_btn.custom_id}"
            )


async def setup(bot):
    await bot.add_cog(Boss(bot))
