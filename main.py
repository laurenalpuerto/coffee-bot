import re
import os
import time
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime
import pytz
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()
print("Loaded BOT TOKEN:", os.environ.get("SLACK_BOT_TOKEN"))

# Initialize Slack app and timezone
app = App(token=os.environ["SLACK_BOT_TOKEN"])
PST = pytz.timezone("US/Pacific")
COFFEE_CHANNEL = "C08QRCC3QTS"

# --- Time check helpers ---
def is_within_ordering_hours():
    now = datetime.now(PST)
    hour = now.hour
    return (8 <= hour < 10) or (12 <= hour < 14)

def enforce_time_restriction(client, user_id, logger, reason="ordering"):
    try:
        client.chat_postMessage(
            channel=user_id,
            text="⏰ Submissions are only allowed between *8–10am* and *12–2pm PST*. Please try again during those hours!"
        )
        logger.info(f"⚠️ Notified <@{user_id}> about blocked {reason}")
    except Exception as e:
        logger.error(f"❌ Failed to DM user {user_id}: {e}")

# --- Helper to extract user ID from workflow blocks ---
def extract_user_id_from_blocks(blocks):
    def find_user_id(elements):
        for elem in elements:
            if elem.get("type") == "user":
                return elem.get("user_id")
            elif elem.get("type") == "text":
                match = re.search(r"<@([A-Z0-9]+)>", elem.get("text", ""))
                if match:
                    return match.group(1)
            elif "elements" in elem:
                user_id = find_user_id(elem["elements"])
                if user_id:
                    return user_id
        return None

    for block in blocks:
        if "elements" in block:
            user_id = find_user_id(block["elements"])
            if user_id:
                return user_id

    return None

# --- Slack Events: message handler ---
@app.event("message")
def handle_message(event, client, logger):
    print("🚀 Incoming message event:", event)
    channel_id = event.get("channel")
    subtype = event.get("subtype")
    user = event.get("user")
    text = event.get("text", "").lower()
    blocks = event.get("blocks", [])

    # Ignore deleted or invalid messages
    if not user or subtype == "message_deleted":
        return

    is_bot_workflow = subtype == "bot_message"

    # --- Block Workflow Messages Outside Hours ---
    if is_bot_workflow:
        logger.info("🤖 Workflow message detected")
        submitter_id = extract_user_id_from_blocks(blocks)
        logger.info(f"🧪 Extracted submitter ID: {submitter_id}")

        if submitter_id and not is_within_ordering_hours():
            logger.info(f"⚙️ Submitting DM to: {submitter_id} (you are: {user})")
            enforce_time_restriction(client, submitter_id, logger, reason="ordering")

    # --- Block Any Message in Coffee Channel Outside Hours ---
    if channel_id == COFFEE_CHANNEL and not is_within_ordering_hours():
        enforce_time_restriction(client, user, logger, "message")
        return

    # --- Block Coffee-Related Keywords Outside Hours ---
    if any(word in text for word in ["coffee", "order", "latte", "espresso", "cappuccino"]):
        if not is_within_ordering_hours():
            enforce_time_restriction(client, user, logger, "coffee keyword")

# --- Slack Events: reaction_added handler ---
@app.event("reaction_added")
def handle_reaction_added(event, client):
    emoji = event.get("reaction")
    valid_emojis = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]

    if emoji not in valid_emojis:
        return

    item = event.get("item", {})
    channel = item.get("channel")
    ts = item.get("ts")

    if not channel or not ts:
        return

    result = client.conversations_history(channel=channel, latest=ts, inclusive=True, limit=1)
    if result["messages"]:
        original_msg = result["messages"][0]
        user_id = original_msg.get("user")
        station_number = valid_emojis.index(emoji) + 1

        target_id = user_id
        if not target_id:
            match = re.search(r"<@([A-Z0-9]+)>", original_msg.get("text", ""))
            if match:
                target_id = match.group(1)

        if target_id:
            client.chat_postMessage(
                channel=target_id,
                text=f"🥳 Your drink is ready at station #{station_number}! Enjoy! ☕"
            )
        else:
            client.chat_postMessage(
                channel=channel,
                thread_ts=ts,
                text=f"🥳 This drink is ready at station #{station_number}! ☕"
            )

# --- Flask Keepalive Server ---
web_app = Flask("")

@web_app.route("/")
def home():
    return "☕ Coffee bot is alive."

def run_web():
    web_app.run(host="0.0.0.0", port=8080)

# --- Periodic Station Announcements ---
def send_station_announcements():
    while True:
        print("🔔 Sending station updates...")
        try:
            app.client.chat_postMessage(
                channel=os.environ["SLACK_ANNOUNCEMENT_CHANNEL"],
                text="☕ Station #2 is now serving drinks!"
            )
        except Exception as e:
            print(f"⚠️ Failed to send station update: {e}")
        time.sleep(600)

# --- App Entry Point ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=send_station_announcements).start()
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()