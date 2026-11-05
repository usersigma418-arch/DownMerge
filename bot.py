import json
import os
import subprocess
import requests
import telebot

# Apna asli Bot Token yahan daalein
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
bot = telebot.TeleBot(BOT_TOKEN)

user_sessions = {}


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  chat_id = message.chat.id
  user_sessions[chat_id] = {"step": "waiting_for_video"}
  bot.reply_to(
      message,
      "👋 **Welcome!**\n\n🎬 **Step 1:** Pehle mujhe **Video URL** bhejo.",
      parse_mode="Markdown",
  )


@bot.message_handler(
    func=lambda message: message.text
    and ("http://" in message.text or "https://" in message.text)
)
def handle_urls(message):
  chat_id = message.chat.id
  text = message.text.strip()

  if chat_id not in user_sessions:
    bot.reply_to(
        message,
        "⚠️ Pehle `/start` command bhejo taaki process shuru ho sake!",
        parse_mode="Markdown",
    )
    return

  current_step = user_sessions[chat_id].get("step")

  if current_step == "waiting_for_video":
    user_sessions[chat_id]["video_url"] = text
    user_sessions[chat_id]["step"] = "waiting_for_audio"
    bot.reply_to(
        message,
        "✅ **Video URL saved!**\n\n🎧 **Step 2:** Ab wahi matching **Audio URL**"
        " bhejo.",
        parse_mode="Markdown",
    )

  elif current_step == "waiting_for_audio":
    video_url = user_sessions[chat_id]["video_url"]
    audio_url = text
    user_sessions[chat_id] = {}

    msg = bot.reply_to(
        message,
        "📥 **Downloading Video & Audio streams...** Please wait ⏳",
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
          parse_mode="Markdown",
      )

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

      file_size_mb = os.path.getsize(out_file) / (1024 * 1024)

      # Smart Size-Based Splitting (>45MB) - Minimum parts closest to 44MB limit
      if file_size_mb > 45:
        bot.edit_message_text(
            f"📦 File size is `{round(file_size_mb, 2)} MB`. Optimizing and"
            " splitting into max-size parts (~44MB each)...",
            chat_id=chat_id,
            message_id=msg.message_id,
            parse_mode="Markdown",
        )

        probe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            out_file,
        ]
        probe_res = subprocess.run(
            probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        probe_data = json.loads(probe_res.stdout)
        total_duration = float(probe_data["format"]["duration"])

        target_part_size_mb = 44.0
        num_parts = int(file_size_mb // target_part_size_mb) + 1
        segment_duration = total_duration / num_parts

        output_pattern = f"part_{chat_id}_%03d.mp4"
        subprocess.run([
            "ffmpeg",
            "-i",
            out_file,
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(segment_duration),
            "-reset_timestamps",
            "1",
            output_pattern,
        ])

        parts = sorted(
            [p for p in os.listdir(".") if p.startswith(f"part_{chat_id}_")]
        )
        bot.delete_message(chat_id, msg.message_id)

        for i, part in enumerate(parts):
          bot.send_message(
              chat_id,
              f"📤 Sending Optimized Part **{i+1}** of **{len(parts)}** 🚀",
              parse_mode="Markdown",
          )
          with open(part, "rb") as pf:
            bot.send_video(
                chat_id,
                pf,
                caption=(
                    f"Part {i+1}/{len(parts)} (~{round(os.path.getsize(part)/(1024*1024), 1)}MB)"
                    " 🎬"
                ),
            )
          os.remove(part)

      else:
        bot.edit_message_text(
            "📤 **Uploading merged video to Telegram...** 🚀",
            chat_id=chat_id,
            message_id=msg.message_id,
            parse_mode="Markdown",
        )
        with open(out_file, "rb") as video_to_send:
          bot.send_video(
              chat_id,
              video_to_send,
              caption="✅ **Merged & Sent Successfully!** 🎬",
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

    for f in [vid_file, aud_file, out_file]:
      if os.path.exists(f):
        os.remove(f)


print("Clearing webhooks and starting bot...")
bot.remove_webhook()
bot.infinity_polling(none_stop=True)
