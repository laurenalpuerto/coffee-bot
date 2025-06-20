import re
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime
import pytz
import time
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"])
PST = pytz.timezone("US/Pacific")

COFFEE_CHANNEL = "C08QRCC3QTS"


def is_within_ordering_hours():
    now = datetime.now(PST)
    hour = now.hour
    return (8 <= hour < 10) or (12 <= hour < 14)


@app.event("message")
def handle_message(event, client, logger):
    channel_id = event.get("channel")
    subtype = event.get("subtype")
    user = event.get("user")
    text = event.get("text", "").lower()
    blocks = event.get("blocks", [])

    if subtype == "bot_message" and channel_id == COFFEE_CHANNEL:
        logger.info(f"🤖 Workflow message detected")

        submitter_id = None
        match = re.search(r"<@([A-Z0-9]+)>", text)
        if match:
            submitter_id = match.group(1)
        else:
            for block in blocks:
                block_text = block.get("text", {}).get("text", "")
                match = re.search(r"<@([A-Z0-9]+)>", block_text)
                if match:
                    submitter_id = match.group(1)
                    break

        if submitter_id and not is_within_ordering_hours():
            try:
                client.chat_postMessage(
                    channel=submitter_id,
                    text=
                    "☕ You submitted a coffee order outside of *8–10am* and *12–2pm PST*. Please try again during those hours!"
                )
                logger.info(
                    f"⚠️ Notified <@{submitter_id}> about blocked order")
            except Exception as e:
                logger.error(f"❌ Failed to DM user: {e}")
        return

    # 🧍 Handle regular user messages
    if not user or subtype == "bot_message":
        return

    if any(word in text
           for word in ["coffee", "order", "latte", "espresso", "cappuccino"]):
        if not is_within_ordering_hours():
            try:
                client.chat_postMessage(
                    channel=user,
                    text=
                    "☕ Coffee orders are only accepted between *8–10am* and *12–2pm PST*. Please try again later!"
                )
                logger.info(f"☕ Blocked manual request by <@{user}>")
            except Exception as e:
                logger.error(f"❌ Failed to notify user: {e}")


@app.event("reaction_added")
def handle_reaction_added(event, client):
    emoji = event["reaction"]
    valid_emojis = [
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
    ]

    if emoji not in valid_emojis:
        return

    channel = event["item"]["channel"]
    ts = event["item"]["ts"]

    result = client.conversations_history(channel=channel,
                                          latest=ts,
                                          inclusive=True,
                                          limit=1)
    if result["messages"]:
        original_msg = result["messages"][0]
        user_id = original_msg.get("user")
        station_number = valid_emojis.index(emoji) + 1

        target_id = user_id or re.search(
            r"<@([A-Z0-9]+)>", original_msg.get(
                "text", "")).group(1) if re.search(
                    r"<@([A-Z0-9]+)>", original_msg.get("text", "")) else None

        if target_id:
            client.chat_postMessage(
                channel=target_id,
                text=
                f"🥳 Your drink is ready at station #{station_number}! Enjoy! ☕"
            )
        else:
            client.chat_postMessage(
                channel=channel,
                thread_ts=ts,
                text=f"🥳 This drink is ready at station #{station_number}! ☕")


# 🌀 Flask ping server to keep alive
web_app = Flask("")


@web_app.route("/")
def home():
    return "☕ Coffee bot is alive."


def run_web():
    web_app.run(host="0.0.0.0", port=8080)


def send_station_announcements():
    while True:
        print("🔔 Sending station updates...")
        try:
            app.client.chat_postMessage(
                channel=os.environ["SLACK_ANNOUNCEMENT_CHANNEL"],
                text="☕ Station #2 is now serving drinks!")
        except Exception as e:
            print(f"⚠️ Failed to send station update: {e}")
        time.sleep(600)


if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=send_station_announcements).start()
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
