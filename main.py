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

load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"])

PST = pytz.timezone("US/Pacific")


def is_within_ordering_hours():
    now = datetime.now(PST)
    hour = now.hour
    return (8 <= hour < 10) or (12 <= hour < 14)


# Coffee order time enforcement
@app.event("message")
def handle_workflow_message(event, client, logger):
    user = event.get("user")
    subtype = event.get("subtype")
    text = event.get("text", "").lower()

    if subtype == "bot_message" or not user:
        return

    # Keywords that imply coffee workflow attempt
    coffee_keywords = ["coffee", "order", "latte", "espresso", "cappuccino"]

    if any(word in text for word in coffee_keywords):
        if not is_within_ordering_hours():
            try:
                # Just notify the user, don't delete the message
                client.chat_postMessage(
                    channel=user,
                    text=(
                        "☕ Coffee orders are only accepted between *8–10am* "
                        "and *12–2pm PST*. Please try again later!"
                    )
                )
                logger.info(f"Blocked coffee request by <@{user}> outside hours.")
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")


# Reaction-to-station handling
@app.event("reaction_added")
def handle_reaction_added(event, client):
    print("🔁 Reaction event received:", event)

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
        print("📩 Reacted message:", original_msg)

        user_id = original_msg.get("user")
        station_number = valid_emojis.index(emoji) + 1

        if user_id:
            # DM directly if user is available
            client.chat_postMessage(
                channel=user_id,
                text=
                f"🥳 Your drink is ready at station #{station_number}! Enjoy! ☕"
            )
        else:
            # Try to extract from the message text using the [user_id:<@U12345678>] format
            text = original_msg.get("text", "")
            match = re.search(r"<@([A-Z0-9]+)>", text)
            if match:
                extracted_user = match.group(1)
                client.chat_postMessage(
                    channel=extracted_user,
                    text=
                    f"🥳 Your drink is ready at station #{station_number}! Enjoy! ☕"
                )
            else:
                # Fallback: reply in thread
                client.chat_postMessage(
                    channel=channel,
                    thread_ts=ts,
                    text=
                    f"🥳 This drink is ready at station #{station_number}! ☕")


# 🔁 Keep-alive Flask web server for UptimeRobot
web_app = Flask("")


@web_app.route("/")
def home():
    return "☕ Coffee bot is alive."


def run_web():
    web_app.run(host="0.0.0.0", port=8080)


def send_station_announcements():
    while True:
        print("🔔 Sending station updates...")

        # ✅ Replace with your real logic if needed
        app.client.chat_postMessage(
            channel="#general",  # or a specific user ID
            text="☕ Station #2 is now serving drinks!")

        time.sleep(600)  # Wait 10 minutes before next message


if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=send_station_announcements).start()
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
