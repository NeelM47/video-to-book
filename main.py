import yt_dlp
import torch
import gc
import whisperx
import os
import re
import ollama
from ebooklib import epub

COMPUTE_TYPE = "int8"

# --- CONFIGURATION ---
LLM_MODEL = "llama3.2"
WHISPER_MODEL = "small"
LINKS_FILE = "links.txt"

def synthesize_and_polish(yt_text, whisper_text=None):
    """
    Feeds transcripts to Llama. 
    If whisper_text is provided, it performs ensemble refinement.
    If not, it just polishes the YouTube transcript.
    """
    mode = "Ensemble Refinement" if whisper_text else "Single Refinement"
    print(f"🧠 Polishing transcript with {LLM_MODEL} ({mode})...")
    
    master_polished = []
    chunk_size = 12000 
    
    # Determine the loop range based on available text
    max_len = max(len(yt_text), len(whisper_text) if whisper_text else 0)
    
    for i in range(0, max_len, chunk_size):
        seg_yt = yt_text[i:i+chunk_size]
        
        if whisper_text:
            seg_wh = whisper_text[i:i+chunk_size]
            prompt = (
                f"You are a master scientific editor. Below are two imperfect transcripts of the same video.\n\n"
                f"TRANSCRIPT A (YouTube Captions): {seg_yt}\n\n"
                f"TRANSCRIPT B (Whisper AI): {seg_wh}\n\n"
                "INSTRUCTIONS:\n"
                "1. Cross-reference both transcripts to identify correct technical terms.\n"
                "2. Rewrite this into a highly coherent, readable book-style narrative.\n"
                "3. Fix all grammar and punctuation. OUTPUT ONLY THE CLEANED PROSE."
            )
        else:
            prompt = (
                f"You are a master scientific editor. Below is a raw transcript with poor punctuation and casing.\n\n"
                f"TRANSCRIPT: {seg_yt}\n\n"
                "INSTRUCTIONS:\n"
                "1. Rewrite this into a highly coherent, readable book-style narrative.\n"
                "2. Fix all grammar, casing, and punctuation.\n"
                "3. Maintain all technical details. OUTPUT ONLY THE CLEANED PROSE."
            )
        
        try:
            response = ollama.generate(
                    model=LLM_MODEL, 
                    prompt=prompt,
                    options={
                        "num_ctx": 8192,  # Doubles the default memory room
                        "temperature": 0.3 # Keeps the editor focused and not "creative"
                    }
            )
            master_polished.append(response['response'])
            print(f"   ✅ Processed segment {(i // chunk_size) + 1}...")
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
    
    css_path = "style/nav.css"
    if os.path.exists(css_path):
        with open(css_path, 'r') as f:
            style_content = f.read()
    else:
        # Fallback if file is missing
        style_content = 'body { font-family: sans-serif; }' 

    css = epub.EpubItem(uid="style", file_name="style/nav.css", media_type="text/css", content=style_content)

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

def get_content_from_youtube(url, base_filename, use_whisper):
    """Downloads content. Only downloads audio if use_whisper is True."""
    print(f"🎥 Processing: {url}")

    ydl_opts = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'nocheckcertificate': True,
        'outtmpl': f'{base_filename}.%(ext)s',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'quiet': True,
        'no_warnings': True,
    }

    # Only add audio extraction if we actually need it for Whisper
    if use_whisper:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        ydl_opts['skip_download'] = True # Don't download video/audio, just subs

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Untitled_Video')
            # Clean title for filename
            video_title = re.sub(r'[^\w\s-]', '', video_title).strip().replace(' ', '_')

        yt_text = ""
        # Find subtitle file (yt-dlp might append .en.vtt or .en-US.vtt)
        sub_files = [f for f in os.listdir('.') if f.startswith(base_filename) and f.endswith('.vtt')]
        
        if sub_files:
            sub_path = sub_files[0]
            with open(sub_path, 'r', encoding='utf-8') as f:
                content = f.read()
            clean_text = re.sub(r'WEBVTT|NOTE .*|STYLE.*|-->.*', '', content)
            clean_text = re.sub(r'<[^>]*>', '', clean_text)
            clean_text = re.sub(r'\d{2}:\d{2}:\d{2}.\d{3}', '', clean_text)
            yt_text = " ".join(clean_text.split())
            os.remove(sub_path)
            print("✅ YouTube captions extracted.")
        
        audio_path = f"{base_filename}.mp3" if use_whisper else None
        return video_title, yt_text, audio_path

    except Exception as e:
        print(f"❌ YouTube Access Failed: {e}")
        return None, None, None

def generate_whisperx_transcript(audio_file_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🚀 Transcribing with {WHISPER_MODEL} (Language: English)...")

    model = whisperx.load_model(WHISPER_MODEL, device, compute_type=COMPUTE_TYPE)
    audio = whisperx.load_audio(audio_file_path)

    # Force language="en" here
    result = model.transcribe(audio, batch_size=1, language="en")

    print("🎯 [WhisperX] Aligning sentences...")
    model_a, metadata = whisperx.load_align_model(language_code="en", device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

    full_text = " ".join([seg['text'] for seg in result['segments']])

    del model
    del model_a
    if device == "cuda": torch.cuda.empty_cache()
    gc.collect()

    return full_text

def main():
    # 1. Ask for mode
    choice = input("Use WhisperX for extra accuracy? (Slower, requires GPU) [y/N]: ").lower()
    use_whisper = True if choice == 'y' else False

    # 2. Check for links file
    if not os.path.exists(LINKS_FILE):
        print(f"❌ '{LINKS_FILE}' not found. Please create it and add YouTube URLs.")
        return

    with open(LINKS_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("Empty links file.")
        return

    print(f"Loaded {len(urls)} URLs. Starting processing...")

    for idx, url in enumerate(urls):
        print(f"\n--- Processing Video {idx+1}/{len(urls)} ---")
        temp_base = f"temp_vid_{idx}"
        
        video_title, yt_text, audio_file = get_content_from_youtube(url, temp_base, use_whisper)

        if not yt_text and not use_whisper:
            print(f"⚠️ Skipping {url}: No captions available and WhisperX disabled.")
            continue

        whisper_text = None
        if use_whisper and audio_file and os.path.exists(audio_file):
            whisper_text = generate_whisperx_transcript(audio_file)
            os.remove(audio_file)

        # 3. LLM Synthesis
        # If whisper_text is None, it only polishes yt_text
        final_text = synthesize_and_polish(yt_text, whisper_text)

        # 4. EPUB Generation
        filename = f"{video_title}.epub"
        create_epub(video_title, final_text, filename)
        print(f"✨ Created: {filename}")

if __name__ == "__main__":
    main()
