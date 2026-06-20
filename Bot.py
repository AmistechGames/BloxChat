# =========================================================
# APP VERSION
# =========================================================

APP_VERSION = "2.0.4"
UPDATE_URL = "https://amistechgames.github.io/BloxChat/version.json"

# =========================================================

import os
import sys
import json
import threading
import asyncio
import logging
import time
import requests
import webview
import keyboard
import win32com.client

from dotenv import load_dotenv
from flask import Flask, send_file, jsonify
from twitchio.ext import commands
from collections import deque

# =========================================================
# PATH
# =========================================================

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv(resource_path(".env"))

OAUTH = os.getenv("TWITCH_OAUTH")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")

CHANNELS = os.getenv("CHANNELS", "")
RAW_CHANNEL_LIST = [c.strip().lower() for c in CHANNELS.split(",") if c.strip()]

# =========================================================
# HARD LIMIT (10 CHANNELS MAX)
# =========================================================

CHANNEL_LIST = RAW_CHANNEL_LIST[:10]

if len(RAW_CHANNEL_LIST) > 10:
    print("[WARNING] Max 10 channels allowed. Extra ignored.")

# =========================================================
# STATE
# =========================================================

class AppState:
    def __init__(self):
        self.channels = {}
        self.selected_channel = None
        self.msg_id = 0

STATE = AppState()

for ch in CHANNEL_LIST:
    STATE.channels[ch] = {
        "messages": deque(maxlen=50)
    }

if CHANNEL_LIST:
    STATE.selected_channel = CHANNEL_LIST[0]

# =========================================================
# UPDATE SYSTEM
# =========================================================

def check_for_updates():
    try:
        print("[UPDATE] Checking...")

        r = requests.get(UPDATE_URL, timeout=5)
        data = r.json()

        latest = data.get("version")
        url = data.get("url")

        if not latest or not url:
            return

        if latest == APP_VERSION:
            print("[UPDATE] Already latest version")
            return

        print(f"[UPDATE] New version found: {latest}")

        exe_data = requests.get(url, timeout=20).content

        new_file = "BloxChat_update.exe"

        with open(new_file, "wb") as f:
            f.write(exe_data)

        print("[UPDATE] Downloaded update")

        os.startfile(new_file)

        time.sleep(1)
        sys.exit()

    except Exception as e:
        print("[UPDATE ERROR]", e)

# =========================================================
# TTS FIX
# =========================================================

def fix_screams(text: str) -> str:
    text = text.strip()

    if not text:
        return text

    cleaned = text.replace(" ", "")

    if len(cleaned) > 2 and len(set(cleaned)) == 1:
        return " ".join(list(cleaned)) + "!!!"

    return text

# =========================================================
# TTS ENGINE
# =========================================================

class TTSManager:
    def __init__(self):

        self.voice = win32com.client.Dispatch("SAPI.SpVoice")

        self.queue = deque(maxlen=100)
        self.lock = threading.Lock()

        self.voice.Rate = 1

        self.running = True

        threading.Thread(target=self.loop, daemon=True).start()

        print("[TTS] Ready")

    def speak(self, text: str):

        if not text:
            return

        text = fix_screams(text)
        self.queue.append(text)

    def loop(self):

        while self.running:
            try:
                if not self.queue:
                    time.sleep(0.02)
                    continue

                text = self.queue.popleft()

                with self.lock:
                    self.voice.Speak(text)

            except Exception as e:
                print("[TTS ERROR]", e)
                time.sleep(0.2)

tts = TTSManager()

# =========================================================
# TWITCH BOT
# =========================================================

class StreamBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=OAUTH,
            prefix="!",
            initial_channels=CHANNEL_LIST
        )

        self.chat_channels = set()

        print("[BOT] Running...")

    async def event_ready(self):
        print(f"[READY] Logged in as {self.nick}")

    async def event_message(self, message):

        if message.echo:
            return

        channel = message.channel.name.lower()

        if channel not in STATE.channels:
            STATE.channels[channel] = {"messages": deque(maxlen=50)}

        STATE.msg_id += 1

        STATE.channels[channel]["messages"].append({
            "id": STATE.msg_id,
            "user": message.author.name,
            "message": message.content,
            "channel": channel
        })

        print(f"[{channel}] {message.author.name}: {message.content}")

        await self.handle_commands(message)

    async def event_channel_joined(self, channel):
        self.chat_channels.add(channel)

    # =====================================================
    # TTS COMMAND (ONLY SELECTED CHANNEL)
    # =====================================================

    @commands.command(name="tts")
    async def tts_cmd(self, ctx):

        text = ctx.message.content.replace("!tts", "").strip()

        if not text:
            return

        if ctx.channel.name.lower() == STATE.selected_channel:
            tts.speak(f"{ctx.author.name} says {text}")

# =========================================================
# FLASK OVERLAY
# =========================================================

app = Flask(__name__)
logging.getLogger("werkzeug").disabled = True

@app.route("/")
def overlay():
    return send_file(resource_path("overlay.html"))

@app.route("/messages")
def messages():

    ch = STATE.selected_channel

    if not ch:
        return jsonify([])

    return jsonify(list(STATE.channels[ch]["messages"]))

@app.route("/channels")
def channels():
    return jsonify(list(STATE.channels.keys()))

@app.route("/select/<channel>")
def select_channel(channel):

    channel = channel.lower()

    if channel in STATE.channels:
        STATE.selected_channel = channel
        print("[CHANNEL] Switched to:", channel)
        return "ok"

    return "invalid", 404

@app.route("/clear")
def clear():

    ch = STATE.selected_channel

    if ch:
        STATE.channels[ch]["messages"].clear()

    STATE.msg_id = 0
    return "ok"

def run_web():
    print("[WEB] http://127.0.0.1:5000")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )

# =========================================================
# OVERLAY WINDOW
# =========================================================

overlay_window = None
overlay_visible = True

def start_overlay_window():

    global overlay_window

    overlay_window = webview.create_window(
        "BloxChat Overlay",
        "http://127.0.0.1:5000",
        width=420,
        height=650,
        frameless=True,
        on_top=True,
        easy_drag=True
    )

    webview.start(gui="edgechromium")

# =========================================================
# TOGGLE
# =========================================================

def toggle_overlay():

    global overlay_visible

    if not overlay_window:
        return

    overlay_visible = not overlay_visible

    if overlay_visible:
        overlay_window.show()
    else:
        overlay_window.hide()

# =========================================================
# HOTKEYS
# =========================================================

def hotkeys():
    keyboard.add_hotkey("ctrl+shift+o", toggle_overlay)
    keyboard.wait()

# =========================================================
# CONSOLE CHAT
# =========================================================

def console_loop(bot):

    print("[CONSOLE READY] Type messages")

    while True:
        msg = input()

        if not msg.strip():
            continue

        selected = STATE.selected_channel

        for ch in list(bot.chat_channels):

            if ch.name.lower() != selected:
                continue

            try:
                asyncio.run_coroutine_threadsafe(
                    ch.send(msg),
                    bot.loop
                )
            except:
                pass

        print(f"[BOT -> {selected}] {msg}")

# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    if not OAUTH or not CHANNEL_LIST:
        print("[ERROR] Missing .env values")
        sys.exit(1)

    check_for_updates()

    bot = StreamBot()

    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=bot.run, daemon=True).start()
    threading.Thread(target=console_loop, args=(bot,), daemon=True).start()
    threading.Thread(target=hotkeys, daemon=True).start()

    start_overlay_window()