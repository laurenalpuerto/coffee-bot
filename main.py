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

app = App(token=os.environ["SLACK_BOT_TOKEN"])
PST = pytz.timezone("US/Pacific")
COFFEE_CHANNEL = "C08QRCC3QTS"

# --- Time Check ---
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
        logger.error(f"❌ Failed to DM user <@{user_id}>: {e}")

# --- Extract Submitter ID ---
def extract_user_id_from_blocks(blocks):
    for block in blocks:
        if block.get("type") == "rich_text":
            for el in block.get("elements", []):
                if el.get("type") == "rich_text_section":
                    for sub_el in el.get("elements", []):
                        if sub_el.get("type") == "user":
                            return sub_el.get("user_id")
                        elif sub_el.get("type") == "text":
                            match = re.search(r"<@([A-Z0-9]+)>", sub_el.get("text", ""))
                            if match:
                                return match.group(1)
    return None

# --- Handle Messages ---
@app.event("message")
def handle_message(event, client, logger):
    print("🚀 Incoming message event:", event)

    channel_id = event.get("channel")
    subtype = event.get("subtype")
    user = event.get("user")
    blocks = event.get("blocks", [])
    text = event.get("text", "").lower()

    if not user or subtype == "message_deleted":
        return

    is_bot_workflow = subtype == "bot_message"

    # --- Block Workflow Messages Outside Hours ---
    if is_bot_workflow:
        logger.info("🤖 Workflow message detected")
        submitter_id = extract_user_id_from_blocks(blocks)
        logger.info(f"🕵️ Extracted submitter ID: {submitter_id}")

        if submitter_id and not is_within_ordering_hours():
            enforce_time_restriction(client, submitter_id, logger, reason="workflow")

            # --- Delete message from channel ---
            try:
                client.chat_delete(channel=channel_id, ts=event["ts"])
                logger.info(f"🗑 Deleted workflow message from <@{submitter_id}>")
            except Exception as e:
                logger.error(f"❌ Failed to delete workflow message: {e}")
        return

    # --- Block Any Message in Coffee Channel Outside Hours ---
    if channel_id == COFFEE_CHANNEL and not is_within_ordering_hours():
        enforce_time_restriction(client, user, logger, "message")
        return

    # --- Block Coffee-Related Keywords Outside Hours ---
    if any(word in text for word in ["coffee", "order", "latte", "espresso", "cappuccino"]):
        if not is_within_ordering_hours():
            enforce_time_restriction(client, user, logger, "coffee keyword")

# --- Reactions Handler ---
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

# --- Disable announcement thread for testing ---
def send_station_announcements():
    while False:  # <-- DISABLED for testing
        print("🔔 Sending station updates...")
        try:
            app.client.chat_postMessage(
                channel=os.environ["SLACK_ANNOUNCEMENT_CHANNEL"],
                text="☕ Station #2 is now serving drinks!"
            )
        except Exception as e:
            print(f"⚠️ Failed to send station update: {e}")
        time.sleep(600)

# --- Main ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    # Thread(target=send_station_announcements).start()  # DISABLED
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
