import streamlit as st
import asyncio
import edge_tts
import os
import math
import yt_dlp
import gdown
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
import moviepy.video.fx.all as vfx
from PIL import Image
import numpy as np

st.set_page_config(page_title="Mobile Movie Recap Tool", layout="wide")
st.title("📱 Mobile Movie Recap & Dubbing Tool")

os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)

# အချိန် (HH:MM:SS) ကို စက္ကန့်သို့ ပြောင်းသည့် Function
def time_to_seconds(time_str):
    parts = list(map(int, time_str.strip().split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

# ၁။ Microsoft Edge TTS
async def generate_tts(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

# ၂။ YouTube မှ ကိုယ်လိုချင်သည့် အပိုင်းကိုသာ ဖြတ်ပြီး Download ဆွဲသည့် Function
def download_youtube_section(url, start_sec, end_sec, output_path="temp/input_video.mp4"):
    if os.path.exists(output_path):
        os.remove(output_path)
        
    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
        'outtmpl': output_path,
        'overwrites': True,
        # သတ်မှတ်ထားသော အချိန်ပိုင်းကိုသာ ဒေါင်းယူရန်
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

# ၃။ Freeze Frame ကို Zoom In / Out လုပ်သည့် Function
def apply_zoom(clip, zoom_type="in", zoom_ratio=0.18):
    def fl(get_frame, t):
        img = Image.fromarray(get_frame(t))
        w, h = img.size
        progress = t / clip.duration
        
        if zoom_type == "in":
            scale = 1 + (zoom_ratio * progress)
        else:
            scale = (1 + zoom_ratio) - (zoom_ratio * progress)
            
        new_w, new_h = int(w / scale), int(h / scale)
        left = (w - new_w) // 2
        top = (h - new_h) // 2
        
        img_cropped = img.crop((left, top, left + new_w, top + new_h))
        img_resized = img_cropped.resize((w, h), Image.Resampling.LANCZOS)
        return np.array(img_resized)
    return clip.fl(fl)

# ၄။ အဓိက Video Processing Logic
def process_recap_video(video_path, audio_path, freeze_dur=2.0, chunk_minutes=5):
    audio_clip = AudioFileClip(audio_path)
    target_duration = audio_clip.duration
    
    raw_video = VideoFileClip(video_path).without_audio()
    
    # Mirror လှန်ခြင်း နှင့် Speed 0.6x ချခြင်း
    modified_video = raw_video.fx(vfx.mirror_x).fx(vfx.speedx, 0.6)
    
    clips = []
    current_video_time = 0
    accumulated_duration = 0
    clip_counter = 0
    zoom_toggle = True
    
    while accumulated_duration < target_duration:
        if current_video_time + 3 > modified_video.duration:
            current_video_time = 0
            
        # 3 စက္ကန့်စာ ဖြတ်ယူခြင်း
        sub = modified_video.subclip(current_video_time, current_video_time + 3)
        clips.append(sub)
        accumulated_duration += 3
        current_video_time += 3
        clip_counter += 1
        
        if accumulated_duration >= target_duration:
            break
            
        # 3 စက္ကန့် ၂ ခါဖြတ်ပြီးတိုင်း Freeze + Zoom In/Out
        if clip_counter % 2 == 0:
            frame = modified_video.get_frame(current_video_time)
            freeze_clip = ImageClip(frame).set_duration(freeze_dur)
            
            z_type = "in" if zoom_toggle else "out"
            freeze_zoomed = apply_zoom(freeze_clip, zoom_type=z_type)
            zoom_toggle = not zoom_toggle
            
            clips.append(freeze_zoomed)
            accumulated_duration += freeze_dur

    final_video = concatenate_videoclips(clips, method="compose")
    final_video = final_video.subclip(0, target_duration)
    final_video = final_video.set_audio(audio_clip)
    
    # ၅ မိနစ်စီ အပိုင်းလိုက် ဖြတ်ထုတ်ခြင်း
    chunk_seconds = chunk_minutes * 60
    total_parts = math.ceil(target_duration / chunk_seconds)
    output_files = []
    
    for i in range(total_parts):
        start_t = i * chunk_seconds
        end_t = min((i + 1) * chunk_seconds, target_duration)
        
        part_clip = final_video.subclip(start_t, end_t)
        out_filename = f"output/Recap_Part_{i+1}.mp4"
        
        part_clip.write_videofile(
            out_filename,
            codec="libx264",
            audio_codec="aac",
            fps=24,
            preset="ultrafast",
            threads=4
        )
        output_files.append(out_filename)
        
    raw_video.close()
    audio_clip.close()
    final_video.close()
    return output_files

# ================= Mobile Friendly UI =================
st.subheader("၁။ Video ရွေးချယ်ပြီး ဖြတ်မည့်အပိုင်း သတ်မှတ်ရန်")
input_source = st.radio("Video ရယူမည့် နည်းလမ်း (Upload တင်ရန်မလိုပါ)", ["YouTube Link (ဖြတ်ယူမည်)", "Google Drive Link"])

yt_url = ""
gdrive_url = ""

if input_source == "YouTube Link (ဖြတ်ယူမည်)":
    yt_url = st.text_input("🔗 YouTube URL ထည့်ပါ", placeholder="https://www.youtube.com/watch?v=...")
    
    # YouTube Link ထည့်လိုက်သည်နှင့် Video Player ပေါ်လာမည်
    if yt_url:
        st.video(yt_url)
        st.info("👆 အပေါ်က Video ကိုကြည့်ပြီး သင်ဖြတ်ယူလိုသော အစနှင့် အဆုံး အချိန်ကို အောက်တွင် ရိုက်ထည့်ပါ။")
        
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        start_time_str = st.text_input("စဖြတ်မည့် အချိန် (HH:MM:SS)", value="00:00:30")
    with col_t2:
        end_time_str = st.text_input("အဆုံးသတ် အချိန် (HH:MM:SS)", value="00:10:00")

else:
    gdrive_url = st.text_input("🔗 Google Drive (Anyone with link) URL ထည့်ပါ")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        start_time_str = st.text_input("စဖြတ်မည့် အချိန် (HH:MM:SS)", value="00:00:00")
    with col_t2:
        end_time_str = st.text_input("အဆုံးသတ် အချိန် (HH:MM:SS)", value="00:10:00")

st.divider()

st.subheader("၂။ Dubbing Script နှင့် Settings")
voice_options = {
    "Myanmar - Thiha (Male)": "my-MM-ThihaNeural",
    "Myanmar - Nilar (Female)": "my-MM-NilarNeural",
    "English - Guy (Male)": "en-US-GuyNeural",
    "English - Jenny (Female)": "en-US-JennyNeural"
}
selected_voice_label = st.selectbox("🎙️ TTS အသံ ရွေးချယ်ပါ", list(voice_options.keys()))
selected_voice = voice_options[selected_voice_label]

script_text = st.text_area("📝 Recap စာသား (Script) ထည့်ပါ", height=180, placeholder="ဒီနေရာမှာ ဇာတ်လမ်းအကျဉ်း ရေးပါ...")

col_s1, col_s2 = st.columns(2)
with col_s1:
    freeze_duration = st.slider("❄️ Freeze ကြာချိန် (စက္ကန့်)", 1.0, 5.0, 2.0, 0.5)
with col_s2:
    chunk_mins = st.number_input("✂️ တစ်ပိုင်းစီ ဖြတ်မည့် မိနစ်", min_value=1, max_value=30, value=5)

# Generate Button
if st.button("🚀 Start Recap Generation", type="primary", use_container_width=True):
    if not script_text.strip():
        st.error("Recap စာသား အရင်ထည့်ပါ။")
    else:
        start_sec = time_to_seconds(start_time_str)
        end_sec = time_to_seconds(end_time_str)
        
        if end_sec <= start_sec:
            st.error("အဆုံးသတ်အချိန်သည် စဖြတ်မည့်အချိန်ထက် ပိုကြီးရပါမည်။")
            st.stop()

        with st.spinner("၁/၃ - Edge TTS ဖြင့် အသံဖိုင် ထုတ်နေပါသည်..."):
            tts_path = "temp/tts_audio.mp3"
            asyncio.run(generate_tts(script_text, selected_voice, tts_path))
            st.audio(tts_path)

        input_video_path = "temp/input_video.mp4"
        with st.spinner(f"၂/၃ - Video ကို ({start_time_str} မှ {end_time_str} အထိ) ဆွဲချနေပါသည်..."):
            if input_source == "YouTube Link (ဖြတ်ယူမည်)":
                download_youtube_section(yt_url, start_sec, end_sec, input_video_path)
            else:
                raw_dl = "temp/gdrive_raw.mp4"
                gdown.download(gdrive_url, raw_dl, quiet=False, fuzzy=True)
                clip = VideoFileClip(raw_dl).subclip(start_sec, end_sec)
                clip.write_videofile(input_video_path, codec="libx264", preset="ultrafast")
                clip.close()

        with st.spinner("၃/၃ - Video Edit လုပ်ပြီး ၅ မိနစ်စီ ဖြတ်ထုတ်နေပါသည်..."):
            output_videos = process_recap_video(
                video_path=input_video_path,
                audio_path=tts_path,
                freeze_dur=freeze_duration,
                chunk_minutes=chunk_mins
            )

        st.success("✅ အားလုံး ပြီးပါပြီ! အောက်တွင် ဖုန်းထဲသို့ တိုက်ရိုက် Download ဆွဲနိုင်ပါပြီ။")
        for idx, out_file in enumerate(output_videos):
            st.markdown(f"#### 🎬 အပိုင်း ({idx + 1})")
            st.video(out_file)
            with open(out_file, "rb") as file:
                st.download_button(
                    label=f"⬇️ Download Part {idx + 1} (MP4)",
                    data=file,
                    file_name=f"Recap_Part_{idx + 1}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key=f"dl_{idx}"
                )
