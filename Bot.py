# =========================================================
# APP VERSION
# =========================================================

APP_VERSION = "2.0.0"

UPDATE_URL = "https://0wv3zrqf-5000.use2.devtunnels.ms/version.json"
# version.json format:
# {
#   "version": "1.0.1",
#   "url": "https://your-domain.com/BloxChat.exe"
# }

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


# =========================================================
# PYINSTALLER SAFE PATH
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
CHANNEL_LIST = [c.strip() for c in CHANNELS.split(",") if c.strip()]

# =========================================================
# STATE
# =========================================================

class AppState:
    def __init__(self):
        self.messages = []
        self.msg_id = 0

STATE = AppState()

# =========================================================
# AUTO UPDATE SYSTEM
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
# WINDOWS TTS (STABLE SAPI)
# =========================================================

class TTSManager:
    def __init__(self):

        self.voice = win32com.client.Dispatch("SAPI.SpVoice")

        self.queue = []
        self.lock = threading.Lock()
        self.running = True

        self.voice.Rate = 1

        threading.Thread(target=self.loop, daemon=True).start()

        print("[TTS] Ready")

    def speak(self, text: str):

        if not text:
            return

        if len(self.queue) > 100:
            self.queue.pop(0)

        self.queue.append(text)

    def loop(self):

        while self.running:

            try:
                if not self.queue:
                    time.sleep(0.02)
                    continue

                text = self.queue.pop(0)

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

        print("[BOT] Running and Active...")

    async def event_ready(self):
        print(f"[READY] Logged in as {self.nick}")

    async def event_message(self, message):

        if message.echo:
            return

        STATE.msg_id += 1

        STATE.messages.append({
            "id": STATE.msg_id,
            "user": message.author.name,
            "message": message.content,
            "channel": message.channel.name
        })

        if len(STATE.messages) > 50:
            STATE.messages.pop(0)

        print(f"[{message.channel.name}] {message.author.name}: {message.content}")

        await self.handle_commands(message)

    async def event_channel_joined(self, channel):
        self.chat_channels.add(channel)

    # =====================================================
    # TTS COMMAND
    # =====================================================

    @commands.command(name="tts")
    async def tts_cmd(self, ctx):

        text = ctx.message.content.replace("!tts", "").strip()

        if text:
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
    return jsonify(STATE.messages[-25:])

@app.route("/clear")
def clear():
    STATE.messages.clear()
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

    try:
        if not overlay_window:
            return

        overlay_visible = not overlay_visible

        if overlay_visible:
            overlay_window.show()
        else:
            overlay_window.hide()

    except Exception as e:
        print("[TOGGLE ERROR]", e)

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

        for ch in list(bot.chat_channels):
            try:
                asyncio.run_coroutine_threadsafe(
                    ch.send(msg),
                    bot.loop
                )
            except:
                pass

        print(f"[BOT -> CHAT] {msg}")

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