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

import sys
import os

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import subprocess
import asyncio
import random
import json
import threading
import time
from rich.console import Console
from rich.align import Align

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from neura_engines.setup_engine import NeuraSetupEngine
from core.bot import NeuraBot
from dashboard.app import app as flask_app
import core.state as state
from utils import proxy_manager

console = Console()
engine = NeuraSetupEngine()

if not engine.environment_healthy():
    console.print("[yellow]Environment not healthy – running setup...[/yellow]")
    if not engine.run_full_setup(force_bootstrap=True):
        console.print("[red]Setup failed. Please run 'python neura_setup.py' manually.[/red]")
        sys.exit(1)
    console.print("[green]Setup complete. Restarting...[/green]")
    os.execv(sys.executable, [sys.executable] + sys.argv)

def show_banner():
    from neuraself_ascii import neura_ascii
    neura_ascii.show_banner('main')

def detect_platform():
    if "TERMUX_VERSION" in os.environ or "com.termux" in os.environ.get("PREFIX", ""):
        platform = "Mobile (Termux)"
        is_termux = True
    elif sys.platform.startswith("linux"):
        platform = "Linux (Server/Desktop)"
        is_termux = False
    elif sys.platform == "darwin":
        platform = "MacOS"
        is_termux = False
    elif os.name == "nt":
        platform = "PC (Windows)"
        is_termux = False
    else:
        platform = f"Unknown ({sys.platform})"
        is_termux = False
    console.print(f"[bold green]Detected Platform: {platform}[/bold green]")
    return is_termux

def run_dashboard():
    flask_app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)

async def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    while True:
        show_banner()
        is_termux = detect_platform()
        state.load_account_stats()
        console.print(f"[cyan]Config Directory:[/cyan] {state.CONFIG_DIR}")
        console.print(f"[cyan]Accounts File:[/cyan] {os.path.join(state.CONFIG_DIR, 'accounts.json')}\n")
        console.print("\n[bold cyan]1.[/bold cyan] Start NeuraSelf")
        console.print("[bold cyan]2.[/bold cyan] Manage Accounts")
        console.print("[bold cyan]3.[/bold cyan] Exit")
        from rich.prompt import Prompt
        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3"], default="1")
        if choice == "2":
            import neura_setup
            await neura_setup.account_manager()
            continue
        elif choice == "3":
            console.print("\n[yellow]Shutting down. See you next time![/yellow]")
            sys.exit(0)
        try:
            accounts = [
                a for a in proxy_manager.load_accounts()
                if a.get("enabled", True)
            ]
        except Exception:
            accounts = []
        if not accounts:
            console.print("[bold red]No active accounts? Add some in the Account Manager (Option 2).[/bold red]")
            time.sleep(2)
            continue
        import utils.history_tracker as ht
        ht.start_session()
        dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        dashboard_thread.start()
        console.print(f"[bold yellow]Initializing {len(accounts)} accounts...[/bold yellow]")
        bots = []
        tasks = []
        for i, acc in enumerate(accounts):
            token = acc.get('token')
            channels = acc.get('channels')
            if not token or "YOUR_TOKEN_HERE" in token or "PLACEHOLDER" in token:
                continue
            valid_channels = []
            if channels:
                for ch in channels:
                    if ch and "YOUR_CHANNEL_ID_HERE" not in str(ch) and "PLACEHOLDER" not in str(ch):
                        valid_channels.append(ch)
            try:
                proxy_url, proxy_auth, proxy_label = proxy_manager.resolve_account_proxy(acc)
                bot = NeuraBot(
                    token=token,
                    channels=valid_channels,
                    proxy_url=proxy_url,
                    proxy_auth=proxy_auth,
                    proxy_label=proxy_label,
                )
                state.bot_instances.append(bot)
                bots.append(bot)
                if i > 0:
                    delay = random.uniform(2.5, 4.5)
                    console.print(f"[dim]Waiting {delay:.1f}s for next account...[/dim]")
                    time.sleep(delay)
                asyncio.create_task(bot.run_bot())
                console.print(f"[green]Starting Account {i+1}/{len(accounts)} ({acc.get('name', 'Unknown')})[/green]")
            except Exception as e:
                console.print(f"[bold red]Failed to initialize Account {i+1}: {e}[/bold red]")
                continue
        console.print("[bold green]All accounts are now connecting in background...[/bold green]")
        while True:
            await asyncio.sleep(60)
        break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            import utils.history_tracker as ht
            ht.end_session()
            state.save_account_stats()
            console.print("\n[bold yellow][!] Systems shut down. History saved.[/bold yellow]")
        except Exception:
            pass
