"""
Telegram Notifier for Trading Alerts
Sends messages to your Telegram when trades occur.
"""
import requests

def send_telegram_alert(token, chat_id, message):
    """
    Sends a message to your Telegram chat.

    Args:
        token (str): Bot API Token
        chat_id (str): Your Chat ID
        message (str): The text to send
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"  # Allows Bold/Italic text
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"📤 Telegram alert sent successfully.")
        else:
            print(f"⚠️ Failed to send alert: {response.text}")
    except Exception as e:
        print(f"❌ Error connecting to Telegram: {e}")