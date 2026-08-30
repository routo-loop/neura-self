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



import time
import json
import os
import datetime
from collections import deque
import utils.history_tracker as ht

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
DATA_DIR = os.path.join(BASE_DIR, 'data')

log_config = {}
LOG_MISC_PATH = os.path.join(CONFIG_DIR, 'logmisc.json')
if os.path.exists(LOG_MISC_PATH):
    with open(LOG_MISC_PATH, 'r') as f:
        log_config = json.load(f)

bot_instances = []
bot_paused = False
active_session_start = time.time()
stats = {
    'uptime_start': time.time()
}

checking_gems = {}
missing_gems_cache = {}
STATS_FILE = os.path.join(DATA_DIR, 'stats.json')

account_stats = {}

# In-flight Send OWOCash operations, managed by cogs/send_cash.py.
send_cash_operations = {}

def get_empty_stats():
    return {
        'uptime_start': time.time(),
        'last_reset_date': datetime.datetime.now().strftime("%Y-%m-%d"),
        'start_cash': 0,
        'current_cash': 0,
        'cowoncy_history': [],
        'gems_used': 0,
        'captchas_solved': 0,
        'bans_detected': 0,
        'warnings_detected': 0,
        'hunt_count': 0,
        'battle_count': 0,
        'owo_count': 0,
        'last_captcha_msg': '',
        'current_captcha': None,
        'captchas_solved_today': 0,
        'captcha_success_count': 0,
        'pending_commands': [],
        'last_cooldown': {},
        'total_cmd_count': 0,
        'other_count': 0,
        'username': 'Unknown',
        'quest_data': [],
        'next_quest_timer': None,
        'session_hunt_count': 0,
        'session_battle_count': 0,
        'session_owo_count': 0,
        'gambling_stats': {
            'total_wins': 0,
            'total_losses': 0,
            'total_wagered': 0,
            'net_profit': 0,
            'current_streak': 0,
            'best_streak': 0,
            'worst_streak': 0,
            'biggest_win': 0,
            'last_outcome': None
        }
    }

def save_account_stats():
    try:
        serializable_stats = {}
        for uid, st in account_stats.items():
            serializable_stats[uid] = {
                'last_reset_date': st.get('last_reset_date'),
                'captchas_solved': st.get('captchas_solved', 0),
                'bans_detected': st.get('bans_detected', 0),
                'warnings_detected': st.get('warnings_detected', 0),
                'hunt_count': st.get('hunt_count', 0),
                'battle_count': st.get('battle_count', 0),
                'owo_count': st.get('owo_count', 0),
                'total_cmd_count': st.get('total_cmd_count', 0),
                'other_count': st.get('other_count', 0),
                'gems_used': st.get('gems_used', 0),
                'username': st.get('username', 'Unknown'),
                'quest_data': st.get('quest_data', []),
                'next_quest_timer': st.get('next_quest_timer'),
                'current_cash': st.get('current_cash', 0),
                'gambling_stats': st.get('gambling_stats', {
                    'total_wins': 0, 'total_losses': 0, 'total_wagered': 0,
                    'net_profit': 0, 'current_streak': 0, 'best_streak': 0,
                    'worst_streak': 0, 'biggest_win': 0, 'last_outcome': None
                })
            }
        
        os.makedirs('config', exist_ok=True)
        with open(STATS_FILE, 'w') as f:
            json.dump(serializable_stats, f, indent=4)
    except Exception as e:
        print(f"Error saving stats: {e}")

def load_account_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                saved = json.load(f)
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                for uid, st in saved.items():
                    new_st = get_empty_stats()
                    last_date = st.get('last_reset_date')
                    if last_date != today:
                        st['hunt_count'] = 0
                        st['battle_count'] = 0
                        st['owo_count'] = 0
                        st['total_cmd_count'] = 0
                        st['other_count'] = 0
                        st['gems_used'] = 0
                        st['captchas_solved_today'] = 0
                        st['last_reset_date'] = today
  
                    new_st.update(st)
                    new_st['session_hunt_count'] = 0
                    new_st['session_battle_count'] = 0
                    new_st['session_owo_count'] = 0
                    
                    account_stats[uid] = new_st
        except Exception as e:
            print(f"Error loading stats: {e}")

command_logs = deque(maxlen=1000)
full_session_history = []

def log_command(type, message, status="info", bot_name=None, bot_id=None):
    hex_color = log_config.get("colors", {}).get(type, "#ffffff")
    
    if "Sent: owo " in message:
        split_msg = message.split("Sent: owo ")
        if len(split_msg) > 1:
            cmd_part = split_msg[1].split(" ")[0].lower()
            if cmd_part in log_config.get("commands", {}):
                hex_color = log_config["commands"][cmd_part]
    elif "RPP: owo " in message:
        hex_color = log_config.get("commands", {}).get("rpp", "#00ffff")
        
    entry = {
        "time": time.strftime("%I:%M:%S %p"),
        "timestamp": time.time(),
        "type": type,
        "message": message,
        "status": status,
        "color": hex_color,
        "bot_name": bot_name,
        "bot_id": bot_id
    }
    
    command_logs.appendleft(entry)
    if len(full_session_history) >= 500:
        full_session_history.pop(0)
    full_session_history.append(entry)
    
    if type in ["CMD", "SUCCESS", "ALARM", "SECURITY"] and bot_id and bot_id in account_stats:
        st = account_stats[bot_id]
        
        if "level quote:" in message.lower() or "level grind:" in message.lower():
            return
        
        cmd = "other"
        if type == "CMD":
            parts = message.split("Sent: ")
            if len(parts) > 1:
                full_text = parts[1].lower().strip()
                if full_text.startswith("owo "):
                    cmd_parts = full_text.split()
                    cmd_text = cmd_parts[1] if len(cmd_parts) > 1 else "owo"
                else:
                    cmd_text = full_text.split()[0]
                
                if cmd_text in ["hunt", "h"]: 
                    cmd = "hunt"
                    st['hunt_count'] = st.get('hunt_count', 0) + 1
                    st['session_hunt_count'] = st.get('session_hunt_count', 0) + 1
                elif cmd_text in ["battle", "b"]: 
                    cmd = "battle"
                    st['battle_count'] = st.get('battle_count', 0) + 1
                    st['session_battle_count'] = st.get('session_battle_count', 0) + 1
                elif cmd_text == "owo" or full_text.strip() == "owo":
                    cmd = "owo"
                    st['owo_count'] = st.get('owo_count', 0) + 1
                    st['session_owo_count'] = st.get('session_owo_count', 0) + 1
                elif "autohunt" in cmd_text: 
                    cmd = "captcha"
                else:
                    st['other_count'] = st.get('other_count', 0) + 1
                
                st['total_cmd_count'] = st.get('total_cmd_count', 0) + 1
   
        msg_low = message.lower()
        if type == "SUCCESS":
            if any(k in msg_low for k in ["captcha solved", "verified", "resuming"]):
                st['captchas_solved'] = st.get('captchas_solved', 0) + 1
                st['captcha_success_count'] = st.get('captcha_success_count', 0) + 1
                st['captchas_solved_today'] = st.get('captchas_solved_today', 0) + 1
            
        elif type in ["ALARM", "SECURITY"]:
            if "ban detected" in msg_low:
                st['bans_detected'] = st.get('bans_detected', 0) + 1
            elif any(k in msg_low for k in ["captcha warning", "captcha detected", "captcha identified", "image captcha"]):
                st['warnings_detected'] = st.get('warnings_detected', 0) + 1
        
        if type in ["SUCCESS", "ALARM", "SECURITY"]:
            save_account_stats()
        
        if type == "CMD":
            history = ht.load_history()
            ht.track_command(history, cmd)

def record_snapshot(user_id):
    if user_id not in account_stats: return
    st = account_stats[user_id]
    
    if st['current_cash'] is None: return
    now = time.time()
    if st['start_cash'] == 0:
        st['start_cash'] = st['current_cash']
    st['cowoncy_history'].append((now, st['current_cash']))
    
    history = ht.load_history()
    ht.track_cash(history, st['current_cash'])
    
    if len(st['cowoncy_history']) > 100:
        st['cowoncy_history'].pop(0)