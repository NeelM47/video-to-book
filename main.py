import torch
import typing
import collections
import functools
import yt_dlp
import gc
import whisperx
import os
import re
from groq import Groq
from ebooklib import epub
from icecream import ic
import subprocess

# --- THE "MASTER KEY" FOR PYTORCH 2.6+ ---

import torch.serialization
original_load = torch.load

def patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return original_load(*args, **kwargs)

torch.load = patched_load

try:
    import omegaconf
    torch.serialization.add_safe_globals([
        typing.Any, typing.Dict, typing.List,
        omegaconf.listconfig.ListConfig,
        omegaconf.dictconfig.DictConfig,
        omegaconf.base.Metadata,
        omegaconf.base.ContainerMetadata,
        collections.defaultdict,
        collections.deque
    ])
except Exception:
    pass

ic.configureOutput(prefix=f'Debug | ', includeContext=True)

# --- CONFIGURATION ---

COMPUTE_TYPE = "int8"
GROQ_API_KEY = None
WHISPER_MODEL = "small"
LINKS_FILE = "links.txt"

def get_groq_client():
    # 1. Try to get it from the system environment
    api_key = os.environ.get("GROQ_API_KEY")

    # 2. If not found, look for the variable you might have defined at the top
    if not api_key:
        try:
            api_key = GROQ_API_KEY  # This looks at the variable at line 40ish
        except NameError:
            api_key = None

    # 3. If still not found, ask the user (Secure prompt)
    if not api_key:
        print("🔑 Groq API Key not found in system environment.")
        api_key = input("👉 Please enter your Groq API Key: ").strip()

    if not api_key:
        raise ValueError("The Groq API Key is required to run this program.")

    return Groq(api_key=api_key)

def synthesize_and_polish(client, whisper_text, yt_text):
    """
    Feeds BOTH transcripts to Llama to create a master version.
    """
    print("🧠 Synthesizing transcripts with Llama 3.3 (Ensemble Refinement)...")

    master_polished = []
    # We use a smaller step because the prompt contains TWO transcripts
    chunk_size = 6000 

    # Determine the loop range based on the primary (Whisper) text
    for i in range(0, len(whisper_text), chunk_size):
        seg_wh = whisper_text[i : i + chunk_size]
        seg_yt = yt_text[i : i + chunk_size] if yt_text else "Not available."
        
        prompt = (
            f"You are a master scientific editor and technical writer. Below are two imperfect transcripts of the same video.\n\n"
            f"TRANSCRIPT A (Whisper AI): {seg_wh}\n\n"
            f"TRANSCRIPT B (YouTube Captions): {seg_yt}\n\n"
            "INSTRUCTIONS:\n"
            "1. Cross-reference both transcripts to identify the correct technical terms and names.\n"
            "2. Resolve any stutters or inaccuracies by comparing the two sources.\n"
            "3. Rewrite the content into a highly coherent, readable book-style narrative.\n"
            "4. Explain the concepts clearly as if writing a masterclass summary.\n"
            "5. Fix all grammar and punctuation. Remove filler words (uh, um, you know).\n"
            "OUTPUT ONLY THE CLEANED PROSE. NO INTRO OR EXPLANATIONS."
        )
        
        try:
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a professional editor specializing in ensemble transcript refinement."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
            )
            master_polished.append(completion.choices[0].message.content)
            print(f"   ✅ Synthesized segment {(i // chunk_size) + 1}...")
        except Exception as e:
            print(f"   ❌ Error with LLM on segment: {e}")

    return " ".join(master_polished)

def bionic_format(text):
    def bold_word(match):
        word = match.group(0)
        if len(word) >= 2:
            mid = (len(word) + 1) // 2
            return f"<b>{word[:mid]}</b>{word[mid:]}"
        return word
    return re.sub(r'\b\w+\b', bold_word, text)

def create_epub(title, text, filename):
    print(f"📚 Building EPUB: {filename}...")
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language('en')

    style = 'body { font-family: sans-serif; line-height: 1.6; padding: 5%; } b { font-weight: bold; }'
    css = epub.EpubItem(uid="style", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(css)

    words = text.split()
    chapters = []
    for i in range(0, len(words), 1000):
        chunk = " ".join(words[i:i+1000])
        bionic = bionic_format(chunk)
        idx = (i//1000)+1
        c = epub.EpubHtml(title=f"Part {idx}", file_name=f"chap_{idx}.xhtml")
        c.content = f"<html><body><p>{bionic.replace(chr(10), '<br/>')}</p></body></html>"
        c.add_item(css)
        book.add_item(c)
        chapters.append(c)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters
    epub.write_epub(filename, book)

def get_content_from_youtube(url, base_filename):
    """Downloads BOTH audio and subtitles."""
    print(f"🎥 Downloading content from: {url}")
    ydl_opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'nocheckcertificate': True,
        'outtmpl': f'{base_filename}.%(ext)s',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '64'}],
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Untitled_Video')
            video_title = re.sub(r'[^\w\s-]', '', video_title).strip().replace(' ', '_')

        yt_text = ""
        sub_files = [f for f in os.listdir('.') if f.startswith(base_filename) and f.endswith('.vtt')]
        if sub_files:
            with open(sub_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
            clean_text = re.sub(r'WEBVTT|NOTE .*|STYLE.*|-->.*', '', content)
            clean_text = re.sub(r'<[^>]*>', '', clean_text)
            clean_text = re.sub(r'\d{2}:\d{2}:\d{2}.\d{3}', '', clean_text)
            yt_text = " ".join(clean_text.split())
            os.remove(sub_files[0])
            print("✅ YouTube captions extracted.")
        
        audio_path = f"{base_filename}.mp3"
        return video_title, yt_text, audio_path
    except Exception as e:
        print(f"❌ YouTube Access Failed: {e}")
        return None, None, None

def generate_groq_whisper(client, audio_file_path):
    """Uses Groq Whisper API for transcription."""
    print("⚡ Transcribing audio (Groq Whisper-Large-v3)...")
    MAX_SIZE_MB = 24
    file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
    if file_size_mb <= MAX_SIZE_MB:
        try:
            with open(audio_file_path, "rb") as file:
                transcription = client.audio.transcriptions.create(
                    file=(audio_file_path, file.read()),
                    model="whisper-large-v3",
                    language="en"
                )
            return transcription.text
        except Exception as e:
            print(f"❌ Whisper Transcription Error: {e}")
            return None

    # CASE 2: File is too large, need to chunk
    print(f"📦 File is large ({file_size_mb:.2f}MB). Splitting into chunks...")
    
    # Create a temp folder for chunks
    chunk_prefix = "temp_chunk_"
    # ffmpeg command: split into 15-minute segments (900 seconds)
    # 15 mins at 64kbps is ~7MB, very safe for Groq
    cmd = [
        'ffmpeg', '-i', audio_file_path, 
        '-f', 'segment', '-segment_time', '900', 
        '-c', 'copy', f'{chunk_prefix}%03d.mp3'
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Identify all created chunks
        chunk_files = sorted([f for f in os.listdir('.') if f.startswith(chunk_prefix) and f.endswith('.mp3')])
        full_transcript = []

        for i, cf in enumerate(chunk_files):
            print(f"   ⚡ Transcribing chunk {i+1}/{len(chunk_files)}...")
            with open(cf, "rb") as file:
                response = client.audio.transcriptions.create(
                    file=(cf, file.read()),
                    model="whisper-large-v3",
                    language="en"
                )
                full_transcript.append(response.text)
            os.remove(cf) # Clean up chunk immediately to save disk space

        return " ".join(full_transcript)

    except Exception as e:
        print(f"❌ Chunked Transcription error: {e}")
        # Clean up any remaining chunks if it fails
        for f in os.listdir('.'):
            if f.startswith(chunk_prefix): os.remove(f)
        return None

def main():
    client = get_groq_client()

    if not os.path.exists(LINKS_FILE):
        print(f"❌ '{LINKS_FILE}' not found."); return

    with open(LINKS_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(urls)} URLs. Starting ensemble processing...")

    for idx, url in enumerate(urls):
        print(f"\n--- Processing Video {idx+1}/{len(urls)} ---")
        temp_base = f"temp_vid_{idx}"
        
        # 1. Download both Audio and YT Subtitles
        video_title, yt_text, audio_file = get_content_from_youtube(url, temp_base)

        if not audio_file or not os.path.exists(audio_file):
            print(f"⚠️ Failed to get audio for {url}. Skipping."); continue

        # 2. Transcribe Audio
        whisper_text = generate_groq_whisper(client, audio_file)
        if os.path.exists(audio_file):
            os.remove(audio_file)

        if not whisper_text:
            print(f"⚠️ Failed to transcribe audio. Skipping."); continue

        # 3. Master Synthesis (AI processes both Whisper and YT Transcript)
        final_text = synthesize_and_polish(client, whisper_text, yt_text)
        
        # 4. EPUB Generation
        filename = f"{video_title}.epub"
        create_epub(video_title, final_text, filename)
        print(f"✨ Created Ensemble Book: {filename}")

if __name__ == "__main__":
    main()
