import os
import subprocess
import requests
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Local Telegram Bot API Server routing
if os.getenv("LOCAL_SERVER") == "True":
  telebot.apihelper.API_URL = "http://telegram-api:8081/bot{0}/{1}"

bot = telebot.TeleBot(BOT_TOKEN)

# User states store karne ke liye dictionary (chat_id -> data)
user_sessions = {}


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  chat_id = message.chat.id
  user_sessions[chat_id] = {"step": "waiting_for_video"}
  bot.reply_to(
      message,
      "👋 **Welcome to Amazon Media Merger Bot!**\n\n🎬 **Step 1:** Pehle mujhe"
      " **Video URL** bhejo.",
      parse_mode="Markdown",
  )


@bot.message_handler(
    func=lambda message: message.text
    and ("http://" in message.text or "https://" in message.text)
)
def handle_urls(message):
  chat_id = message.chat.id
  text = message.text.strip()

  # Agar user ne bina /start kiye direct link bhej diya
  if chat_id not in user_sessions:
    bot.reply_to(
        message,
        "⚠️ Pehle `/start` command bhejo taaki process shuru ho sake!",
        parse_mode="Markdown",
    )
    return

  current_step = user_sessions[chat_id].get("step")

  # Step 1: Video URL lene ka
  if current_step == "waiting_for_video":
    user_sessions[chat_id]["video_url"] = text
    user_sessions[chat_id]["step"] = "waiting_for_audio"
    bot.reply_to(
        message,
        "✅ **Video URL saved!**\n\n🎧 **Step 2:** Ab wahi matching **Audio URL**"
        " bhejo.",
        parse_mode="Markdown",
    )

  # Step 2: Audio URL lene ka aur final process shuru karne ka
  elif current_step == "waiting_for_audio":
    video_url = user_sessions[chat_id]["video_url"]
    audio_url = text

    # Session clear kar do
    user_sessions[chat_id] = {}

    msg = bot.reply_to(
        message,
        "📥 **Downloading Video and Audio streams...** Please wait ⏳",
        parse_mode="Markdown",
    )

    vid_file = f"video_{chat_id}.mp4"
    aud_file = f"audio_{chat_id}.mp4"
    out_file = f"final_movie_{chat_id}.mp4"

    try:
      headers = {
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
          )
      }

      # 1. Download Video
      r_vid = requests.get(video_url, headers=headers, stream=True, timeout=120)
      with open(vid_file, "wb") as f:
        for chunk in r_vid.iter_content(chunk_size=1024 * 1024):
          if chunk:
            f.write(chunk)

      # 2. Download Audio
      bot.edit_message_text(
          "📥 **Downloaded Video.** Downloading Audio stream...",
          chat_id=chat_id,
          message_id=msg.message_id,
          parse_mode="Markdown",
      )
      r_aud = requests.get(audio_url, headers=headers, stream=True, timeout=120)
      with open(aud_file, "wb") as f:
        for chunk in r_aud.iter_content(chunk_size=1024 * 1024):
          if chunk:
            f.write(chunk)

      # 3. Merge using FFmpeg
      bot.edit_message_text(
          "⚙️ **Merging Video & Audio together...** (FFmpeg muxing)",
          chat_id=chat_id,
          message_id=msg.message_id,
          parse_Mode="Markdown",
      )

      # FFmpeg command to combine video and audio without re-encoding (Super Fast!)
      command = [
          "ffmpeg",
          "-i",
          vid_file,
          "-i",
          aud_file,
          "-c",
          "copy",
          out_file,
          "-y",
      ]
      subprocess.run(command, check=True)

      bot.edit_message_text(
          "📤 **Uploading final merged video to Telegram...** 🚀",
          chat_id=chat_id,
          message_id=msg.message_id,
          parse_mode="Markdown",
      )

      # 4. Send final video (Local Bot API server allows large files)
      with open(out_file, "video_file") as vf:
        # Note: file handler open mode should be "rb"
        pass

      with open(out_file, "rb") as video_to_send:
        bot.send_video(
            chat_id,
            video_to_send,
            caption=(
                "✅ **Merged Successfully!** 🎬\nYour complete video with"
                " audio is ready."
            ),
            parse_mode="Markdown",
        )

      bot.delete_message(chat_id, msg.message_id)

    except Exception as e:
      bot.edit_message_text(
          f"⚠️ **Error during processing:** `{str(e)}`",
          chat_id=chat_id,
          message_id=msg.message_id,
          parse_mode="Markdown",
      )

    # Cleanup temp files
    for f in [vid_file, aud_file, out_file]:
      if os.path.exists(f):
        os.remove(f)


print("Media Merger Bot is running smoothly...")
bot.infinity_polling(none_stop=True)
      
