from flask import Flask, request
import threading 
import requests 
from scripts.test_bot import ask_chatbot

# TELEGRAM IMPORTS
import os
import logging
import html
import traceback
from dotenv import load_dotenv
from pydub import AudioSegment
from groq import Groq
from twilio.twiml.messaging_response import MessagingResponse

from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    AIORateLimiter
)



app = Flask(__name__)

# --- CONFIG ---
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


# TELEGRAM CONFIG
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEVELOPER_CHAT_ID = "YOUR_TELEGRAM_ID"

groq_client = Groq(api_key=GROQ_API_KEY)
def process_voice_file(audio_path):

    with open(audio_path, "rb") as audio_file:
        transcript = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file
        )

    user_text = transcript.text

    print("Voice Transcribed:", user_text)

    reply_text = ask_chatbot(user_text)

    return reply_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# TELEGRAM BOT HANDLERS
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Hello! I am your *IAC Assistant*.\n\n"
        "I can help you with:\n"
        "• Text inquiries\n"
        "• Voice notes transcription\n\n"
        "_How can I assist you today?_"
    )
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=constants.ChatAction.TYPING
    )

    user_text = update.message.text
    bot_response = ask_chatbot(user_text)

    await update.message.reply_text(bot_response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=constants.ChatAction.TYPING
    )

    voice_file = await context.bot.get_file(update.message.voice.file_id)

    ogg_path = "temp_voice.ogg"
    mp3_path = "temp_voice.mp3"

    await voice_file.download_to_drive(custom_path=ogg_path)

    audio = AudioSegment.from_ogg(ogg_path)
    audio.export(mp3_path, format="mp3")

    bot_response = process_voice_file(mp3_path)

    reply = bot_response

    await update.message.reply_text(reply)

    os.remove(ogg_path)
    os.remove(mp3_path)


def start_telegram_bot():

    rate_limiter = AIORateLimiter()

    application = ApplicationBuilder().token(TOKEN).rate_limiter(rate_limiter).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Telegram bot running...")

    application.run_polling()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # 1. Handle Handshake (Verification)
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == "my_bot_secret_123":
            return request.args.get("hub.challenge")
        return "Invalid token", 403
    
    
    # 2. Handle Messages
    if request.method == 'POST':
        data = request.get_json()
        print("Incoming Data:", data) 
        if not data: 
            return "No data received", 400
        
        # --- INSTAGRAM & FACEBOOK MESSENGER LOGIC ---
        
        if data.get("object") in ["page", "instagram"]:
            for entry in data.get("entry", []):
                
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event["sender"]["id"]
                    
                    if "message" in messaging_event and "text" in messaging_event["message"]:
                        user_text = messaging_event["message"]["text"]
                        reply_text = ask_chatbot(user_text)
                        
                        # Use same Graph API endpoint for both IG and FB Messenger
                        
                        url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"

                        payload = {
                            "recipient": {"id": sender_id},
                            "message": {"text": reply_text}
                            }
                        response = requests.post(url, json=payload)
                        print(f"Meta Response Body: {response.text}")
                    elif "message" in messaging_event and "attachments" in messaging_event["message"]:
                        attachment = messaging_event["message"]["attachments"][0]
                        if attachment["type"] in ["audio","voice"]:
                            audio_url = attachment["payload"]["url"]
                            audio_data = requests.get(audio_url).content
                            audio_path = "temp_meta_audio.ogg"
                            with open(audio_path, "wb") as f:
                                f.write(audio_data)
                            reply_text = process_voice_file(audio_path)
                            url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
                            payload = {
                                "recipient": {"id": sender_id},
                                "message": {"text": reply_text}
                            }
                            response = requests.post(url, json=payload)
                            print("Meta Voice Reply:", response.text)

        

        # --- WHATSAPP LOGIC ---
        elif data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        message = value["messages"][0]
                        sender_id = message["from"]
                        # TEXT MESSAGE
                        if message["type"] == "text":
                            user_text = message["text"]["body"]
                            reply_text = ask_chatbot(user_text)
                        # VOICE MESSAGE
                        elif message["type"] == "audio":
                            media_id = message["audio"]["id"]
                            # Step 1 — Get media URL
                            media_info_url = f"https://graph.facebook.com/v21.0/{media_id}"
                            headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
                            media_info = requests.get(media_info_url, headers=headers).json()
                            audio_url = media_info["url"]
                            # Step 2 — Download audio WITH TOKEN
                            audio_response = requests.get(audio_url, headers=headers)
                            ogg_path = "temp_whatsapp_audio.ogg"
                            mp3_path = "temp_whatsapp_audio.mp3"
                            with open(ogg_path, "wb") as f:
                                f.write(audio_response.content)
                            # Check if file downloaded correctly
                            import os
                            if os.path.getsize(ogg_path) == 0:
                                print("Audio file empty!")
                                return "ok"
                            # Convert to mp3
                            audio = AudioSegment.from_ogg(ogg_path)
                            audio.export(mp3_path, format="mp3")
                            # Transcribe
                            reply_text = process_voice_file(mp3_path)
                            os.remove(ogg_path)
                            os.remove(mp3_path)
                        else:
                            return "OK", 200
                        url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
                        payload = {
                            "messaging_product": "whatsapp",
                            "to": sender_id,
                            "type": "text",
                            "text": {"body": reply_text}
                        }
                        headers = {
                            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                            "Content-Type": "application/json"
                        }
                        response = requests.post(url, json=payload, headers=headers)
                        print("WhatsApp Status:", response.status_code)
        
        return "OK", 200
if __name__ == "__main__":
    telegram_thread = threading.Thread(target=start_telegram_bot)
    telegram_thread.start()
    print("Flask server running...")
    app.run(port=5000)