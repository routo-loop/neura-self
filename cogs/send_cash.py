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


"""
Send OWOCash — Transfer Coordinator.

Transfers cowoncy from every managed account to a single destination account by
reusing the existing bot interaction architecture (no new protocol):

    1. The source account sends `owo give <amount> <@destination>` through the
       existing send_message / NeuraQueue mechanism, which already handles
       throttle, cooldown, rate-limit and pause behaviour.
    2. OwO replies with its cash-transfer form message carrying the
       `give_accept` button component.
    3. The existing InteractionManager clicks that button through the Discord
       interactions endpoint (type 3 / component_type 2) — the exact same
       mechanism used by the boss, quest and battle flows.

No IDs (guild / channel / message / session / application / nonce) are
hardcoded here: every value is taken live from the OwO message payload and the
active account session at runtime. A single integer amount per flow is never
double-fired: each account processes one confirmation at a time under a
per-account lock, and resolved futures are removed immediately.
"""

import asyncio
import json
import random
import time
import uuid

from discord.ext import commands

import core.state as state
from component_v2_neura import parse_v2_message

# Custom id of the OwO "give" confirmation button. This is the component the
# bot sends in its cash-transfer form and the click we answer through the API.
GIVE_ACCEPT_CUSTOM_ID = "give_accept"
GIVE_CONFIG_KEY = "send_cash"

DEFAULT_GIVE_COMMAND = "{prefix}give {amount} {target}"
DEFAULT_CONFIRM_TIMEOUT = 60.0  # seconds


class SendCash(commands.Cog):
    """Handles one account's side of an OWOCash transfer operation."""

    def __init__(self, bot):
        self.bot = bot
        # destination account id -> confirmation entry waiting to be resolved
        self._pending_gives = {}
        # One give flows at a time per account (existing sequential behaviour).
        self._give_lock = asyncio.Lock()

    # ---------------------------------------------------------------- #
    # Confirmation watcher (raw socket, like the boss/quest flows)
    # ---------------------------------------------------------------- #

    def _find_accept_component(self, components):
        for comp in components:
            cid = comp.custom_id
            if cid and (cid == GIVE_ACCEPT_CUSTOM_ID or cid.startswith("give_")):
                return comp
        return None

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        if not self._pending_gives:
            return
        if isinstance(msg, bytes):
            return
        # Note: confirmations are resolved even while paused — the click is a
        # plain HTTP interaction (not a chat send) and completes a transfer the
        # user already ordered, so a captcha pause should not strand it.
        try:
            raw = json.loads(msg)
        except Exception:
            return
        if raw.get("t") not in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
            return

        data = raw.get("d", {}) or {}
        if str(data.get("author", {}).get("id")) != str(self.bot.owo_bot_id):
            return

        components = parse_v2_message(data)
        button = self._find_accept_component(components)
        if button is None:
            return

        await self._confirm_give(data, button)

    async def _confirm_give(self, data, button):
        if not self._pending_gives:
            return

        # Transfers are fully sequential per account, so the oldest pending
        # entry is the one waiting for this confirmation.
        target_id = sorted(self._pending_gives, key=lambda k: self._pending_gives[k]["ts"])[0]
        pending = self._pending_gives.get(target_id)
        if not pending or pending.get("resolved"):
            return

        pending["resolved"] = True

        if getattr(button, "disabled", False):
            self._resolve_pending(target_id, False, "OwO give confirmation is disabled.")
            return

        # Small human-like pause, consistent with the boss/quest interactions.
        await asyncio.sleep(random.uniform(0.5, 1.4))

        # Reuse the existing interaction layer. All ids come from the live OwO
        # message payload; session handling stays inside InteractionManager.
        ok = await self.bot.interactions.click_button_raw(
            custom_id=button.custom_id,
            message_id=data.get("id"),
            channel_id=data.get("channel_id"),
            author_id=data.get("author", {}).get("id"),
            guild_id=data.get("guild_id"),
            flags=data.get("flags", 0),
        )

        if ok:
            self._resolve_pending(target_id, True, None)
        else:
            self._resolve_pending(target_id, False, "Discord interaction failed.")

    def _resolve_pending(self, target_id, ok, reason):
        pending = self._pending_gives.pop(str(target_id), None)
        if not pending:
            return
        future = pending.get("future")
        if future and not future.done():
            future.set_result((ok, reason))

    # ---------------------------------------------------------------- #
    # Single-account transfer execution
    # ---------------------------------------------------------------- #

    async def execute_give(self, amount, destination_id):
        """Send `amount` OWOCash from this account to `destination_id`.

        Returns a result entry for the batch tracker:
            {'status': 'success'}  or  {'status': 'failed', 'reason': '...'}
        """
        bot = self.bot
        account_id = str(bot.user.id) if bot.user else str(getattr(bot, "user_id", ""))

        if not account_id or not bot.is_ready or not bot.user:
            return {"status": "failed", "reason": "Account is offline or not ready."}
        if bot.paused:
            return {"status": "failed", "reason": "Account is paused."}

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return {"status": "failed", "reason": "Invalid amount."}
        if amount <= 0:
            return {"status": "failed", "reason": "Amount must be greater than zero."}

        async with self._give_lock:
            cfg = bot.config.get("commands", {}).get(GIVE_CONFIG_KEY, {})
            cmd_template = cfg.get("command", DEFAULT_GIVE_COMMAND)
            timeout = float(cfg.get("confirm_timeout", DEFAULT_CONFIRM_TIMEOUT))

            target_mention = "<@{}>".format(destination_id)
            command = cmd_template.format(
                prefix=bot.prefix or "owo ",
                amount=str(amount),
                target=target_mention,
            )

            loop = bot.loop or asyncio.get_event_loop()
            future = loop.create_future()
            self._pending_gives[str(destination_id)] = {
                "future": future,
                "amount": amount,
                "ts": time.time(),
                "resolved": False,
            }

            try:
                sent = await bot.send_message(command, skip_typing=True, priority=True)
                if not sent:
                    bot.log("SEND_CASH", "Account {}: give command could not be sent (busy or paused).".format(account_id))
                    return {"status": "failed", "reason": "Failed to send the give command (account busy or paused)."}

                bot.log("SEND_CASH", "Account {}: give command sent ({} OWOCash).".format(account_id, amount))

                try:
                    ok, reason = await asyncio.wait_for(future, timeout=timeout)
                except asyncio.TimeoutError:
                    bot.log("ERROR", "Account {}: OwO confirmation timed out for give of {} OWOCash.".format(account_id, amount))
                    return {"status": "failed", "reason": "OwO did not confirm the transfer (timed out)."}
                except Exception as e:
                    bot.log("ERROR", "Account {}: confirmation wait error: {}".format(account_id, e))
                    return {"status": "failed", "reason": "Internal confirmation error."}

                if not ok:
                    reason = reason or "OwO declined the transfer (interaction failed)."
                    bot.log("ERROR", "Account {}: give failed -> {}".format(account_id, reason))
                    return {"status": "failed", "reason": reason}
            finally:
                # Never leave a stale entry so a re-run can not reuse a future.
                self._pending_gives.pop(str(destination_id), None)

        # Success — update the balance using the application's single source of
        # truth (state.account_stats), mirroring the shop cog behaviour.
        try:
            st = state.account_stats.get(account_id)
            if st is not None:
                current = st.get("current_cash")
                if isinstance(current, (int, float)) and current is not None:
                    st["current_cash"] = max(0, int(current) - amount)
                    st["last_cash_update"] = time.time()
                    state.save_account_stats()
        except Exception:
            pass

        bot.log("SUCCESS", "Account {}: sent {} OWOCash to {}.".format(account_id, amount, target_mention))
        return {"status": "success"}

    # This module has no scheduled actions.
    async def register_actions(self):
        return


# ------------------------------------------------------------------- #
# Module-level helpers (shared by every account / used by the dashboard)
# ------------------------------------------------------------------- #


def get_managed_accounts():
    """Return all online managed accounts with their current OWOCash balance.

    Uses the application's existing source of truth (state.account_stats) —
    the same registry the dashboard already reads — no second balance system.
    """
    result = []
    for bot in state.bot_instances:
        if not bot.user or not bot.is_ready:
            continue
        uid = str(bot.user.id)
        st = state.account_stats.get(uid, {})
        result.append({
            "id": uid,
            "username": getattr(bot, "username", uid) or uid,
            "cash": st.get("current_cash"),
            "cash_known": bool(st.get("last_cash_update")),
            "paused": bool(bot.paused),
            "ready": bool(bot.is_ready),
        })
    return result


def evaluate_accounts(accounts, amount):
    """Split accounts into eligible / insufficient / unsynced-balance buckets.

    An account is eligible only when `account.cash >= requestedAmount`.
    Accounts whose balance has never been synced are kept separate so they are
    never treated as having money they might not really have.
    """
    eligible, insufficient, unknown = [], [], []
    for acc in accounts:
        cash = acc.get("cash")
        if not acc.get("cash_known") or cash is None:
            unknown.append(acc)
        elif cash < amount:
            insufficient.append(acc)
        else:
            eligible.append(acc)
    return eligible, insufficient, unknown


def build_preview(destination_id, amount):
    """Server-side preview + validation for a send operation."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    accounts = get_managed_accounts()
    destination_id = str(destination_id)
    destination = next((a for a in accounts if str(a["id"]) == destination_id), None)

    # The destination account is never a source for its own transfer.
    sources = [a for a in accounts if str(a["id"]) != destination_id]
    eligible, insufficient, unknown = evaluate_accounts(sources, amount)

    return {
        "destination": destination,
        "amount": amount,
        "sources": sources,
        "eligible": eligible,
        "insufficient": insufficient,
        "unknown": unknown,
    }


def _update_op_totals(op):
    totals = {"success": 0, "failed": 0, "skipped": 0, "total_sent": 0}
    for res in op.get("results", {}).values():
        status = res.get("status")
        if status == "success":
            totals["success"] += 1
            totals["total_sent"] += op.get("amount", 0)
        elif status == "failed":
            totals["failed"] += 1
        elif status == "skipped":
            totals["skipped"] += 1
    op["totals"] = totals


def start_send_operation(destination_id, amount, account_ids=None, destination_name=""):
    """Register a send operation and dispatch it onto the shared bot loop."""
    op_id = "send_{}".format(uuid.uuid4().hex[:12])

    accounts = get_managed_accounts()
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0

    eligible, insufficient, unknown = evaluate_accounts(accounts, amount)
    eligible_ids = [str(a["id"]) for a in eligible if str(a["id"]) != str(destination_id)]

    if account_ids:
        wanted = {str(a) for a in account_ids}
        eligible_ids = [aid for aid in eligible_ids if aid in wanted]

    insufficient_ids = {str(a["id"]) for a in insufficient}
    unknown_ids = {str(a["id"]) for a in unknown}

    results = {}
    for acc in accounts:
        aid = str(acc["id"])
        if aid == str(destination_id):
            continue
        if aid in eligible_ids:
            results[aid] = {"status": "pending"}
        else:
            reason = "Insufficient balance."
            if aid in unknown_ids:
                reason = "Balance not synced yet."
            if aid not in insufficient_ids and aid not in unknown_ids:
                reason = "Not selected as a source."
            results[aid] = {"status": "skipped", "reason": reason}

    op = {
        "id": op_id,
        "created": time.time(),
        "destination_id": str(destination_id),
        "destination_name": destination_name or str(destination_id),
        "amount": amount,
        "status": "running",
        "progress": 0,
        "results": results,
        "totals": {"success": 0, "failed": 0, "skipped": 0, "total_sent": 0},
    }
    state.send_cash_operations[op_id] = op
    _update_op_totals(op)

    loop = None
    for bot in state.bot_instances:
        if bot.user and bot.is_ready:
            loop = bot.loop
            break
    if loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(run_send_batch(op), loop)
        except Exception as e:
            op["status"] = "failed"
            op["error"] = str(e)
    else:
        op["status"] = "failed"
        op["error"] = "No online account is available to run the operation."

    return op


async def run_send_batch(op):
    """Execute the transfer for every eligible account, one by one."""
    try:
        pending_ids = [aid for aid, res in op.get("results", {}).items() if res.get("status") == "pending"]
        destination_id = op.get("destination_id")
        amount = op.get("amount", 0)

        for index, aid in enumerate(pending_ids):
            if op.get("status") == "cancelled":
                break

            bot = next((b for b in state.bot_instances if b.user and str(b.user.id) == aid), None)
            if not bot:
                op["results"][aid] = {"status": "failed", "reason": "Account is offline."}
                _update_op_totals(op)
                continue

            cog = bot.get_cog("SendCash")
            if not cog:
                op["results"][aid] = {"status": "failed", "reason": "Send module unavailable for this account."}
                _update_op_totals(op)
                continue

            if bot.paused or not bot.is_ready:
                op["results"][aid] = {"status": "failed", "reason": "Account is paused or not ready."}
                _update_op_totals(op)
                continue

            try:
                result = await cog.execute_give(amount, destination_id)
            except Exception as e:
                result = {"status": "failed", "reason": "Unexpected internal error."}
                bot.log("ERROR", "Send OWOCash batch error on {}: {}".format(aid, e))

            entry = {"status": result.get("status", "failed")}
            if result.get("reason"):
                entry["reason"] = result["reason"]
            op["results"][aid] = entry
            _update_op_totals(op)

            op["progress"] = int(round((index + 1) / max(1, len(pending_ids)) * 100))

        op["status"] = "completed"
        op["completed"] = time.time()
        _update_op_totals(op)
    except Exception as e:
        op["status"] = "failed"
        op["error"] = str(e)


async def setup(bot):
    cog = SendCash(bot)
    await bot.add_cog(cog)