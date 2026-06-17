import yt_dlp
import json
import hashlib
import os
import re
import tempfile
import shutil
import concurrent.futures
import time
from groq import Groq
from ebooklib import epub
import subprocess

# --- COMPILED REGEXES ---

WORD_RE = re.compile(r'\b\w+\b')
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
VTT_CLEANUP_RE = re.compile(r'WEBVTT|NOTE .*|STYLE.*|-->.*')
HTML_TAG_RE = re.compile(r'<[^>]*>')
TIMECODE_RE = re.compile(r'\d{2}:\d{2}:\d{2}\.\d{3}')
TITLE_CLEANUP_RE = re.compile(r'[^\w\s-]')

# --- CONFIGURATION ---

CACHE_FILE = "cache.json"
GROQ_API_KEY = None
LINKS_FILE = "links.txt"

def get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("🔑 Groq API Key not found in system environment.")
        api_key = input("👉 Please enter your Groq API Key: ").strip()
    if not api_key:
        raise ValueError("The Groq API Key is required to run this program.")
    return Groq(api_key=api_key)

# --- CACHE ---

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def cache_key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def synthesize_and_polish(client, whisper_text, yt_text):
    print("🧠 Synthesizing transcripts with Llama 3.3 (Ensemble Refinement)...")

    wh_words = whisper_text.split()
    yt_words = yt_text.split() if yt_text else []
    WORD_CHUNK = 1000

    segments = []
    for i in range(0, len(wh_words), WORD_CHUNK):
        seg_wh = " ".join(wh_words[i:i + WORD_CHUNK])
        seg_yt = " ".join(yt_words[i:i + WORD_CHUNK]) if yt_words else "Not available."
        segments.append((seg_wh, seg_yt))

    total = len(segments)
    results = [None] * total

    def process(idx, seg_wh, seg_yt):
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
        for attempt in range(3):
            try:
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a professional editor specializing in ensemble transcript refinement."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                )
                return completion.choices[0].message.content
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    match = re.search(r'try again in ([\d.]+)s', err_str)
                    wait = float(match.group(1)) + 1 if match else 5
                    print(f"   ⏳ Rate limited, retrying segment {idx+1} in {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    print(f"   ❌ Error with LLM on segment {idx+1}/{total}: {e}")
                    return None
        print(f"   ❌ Failed after 3 retries for segment {idx+1}/{total}")
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process, i, s[0], s[1]): i for i, s in enumerate(segments)}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            content = future.result()
            if content:
                print(f"   ✅ Synthesized segment {idx+1}/{total}...")
            results[idx] = content

    return " ".join(r for r in results if r)

def bionic_format(text):
    def bold_word(match):
        word = match.group(0)
        if len(word) >= 2:
            mid = (len(word) + 1) // 2
            return f"<b>{word[:mid]}</b>{word[mid:]}"
        return word
    return WORD_RE.sub(bold_word, text)

def create_epub(title, text, filename):
    print(f"📚 Building EPUB: {filename}...")
    os.makedirs("outputs", exist_ok=True)
    filepath = os.path.join("outputs", filename)
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
    epub.write_epub(filepath, book)

def bionic_format_md(text):
    def bold_word(match):
        word = match.group(0)
        if len(word) >= 2:
            mid = (len(word) + 1) // 2
            return f"**{word[:mid]}**{word[mid:]}"
        return word
    return WORD_RE.sub(bold_word, text)

def create_markdown(title, text, video_url, filename):
    print(f"📄 Building Markdown: {filename}...")

    words = text.split()
    total_words = len(words)
    reading_time = max(1, round(total_words / 200))
    WORDS_PER_CHAPTER = 400
    word_chunks = []
    for i in range(0, total_words, WORDS_PER_CHAPTER):
        word_chunks.append(" ".join(words[i:i+WORDS_PER_CHAPTER]))
    total_chapters = len(word_chunks)

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"reading_time: {reading_time} min")
    lines.append(f"chapters: {total_chapters}")
    lines.append(f"words: {total_words}")
    lines.append(f"source: {video_url}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    bar_len = 12

    for idx, chunk in enumerate(word_chunks):
        chap_num = idx + 1
        pct = int((chap_num / total_chapters) * 100)
        filled = round((chap_num / total_chapters) * bar_len)
        bar = "●" * filled + "○" * (bar_len - filled)
        lines.append(f"## Chapter {chap_num} — [{chap_num}/{total_chapters}] {bar} {pct}%")
        lines.append("")

        sentences = SENTENCE_SPLIT_RE.split(chunk)
        sentence_groups = []
        for s in range(0, len(sentences), 3):
            sentence_groups.append(" ".join(sentences[s:s+3]))

        for group in sentence_groups:
            bionic = bionic_format_md(group)
            lines.append(bionic)
            lines.append("")

        if chap_num < total_chapters:
            lines.append("---")
            lines.append("")

    content = "\n".join(lines)
    os.makedirs("outputs", exist_ok=True)
    filepath = os.path.join("outputs", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"   ✅ Saved: {filepath}")

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
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '32'}],
        'quiet': True,
        'no_warnings': True,
        'retries': 5,
        'fragment_retries': 5,
        'socket_timeout': 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Untitled_Video')
            video_title = TITLE_CLEANUP_RE.sub('', video_title).strip().replace(' ', '_')

        yt_text = ""
        sub_files = [f for f in os.listdir('.') if f.startswith(base_filename) and f.endswith('.vtt')]
        if sub_files:
            with open(sub_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
            clean_text = VTT_CLEANUP_RE.sub('', content)
            clean_text = HTML_TAG_RE.sub('', clean_text)
            clean_text = TIMECODE_RE.sub('', clean_text)
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

    print(f"📦 File is large ({file_size_mb:.2f}MB). Splitting into chunks...")

    temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    try:
        chunk_prefix = os.path.join(temp_dir, "chunk_")
        cmd = [
            'ffmpeg', '-i', audio_file_path,
            '-f', 'segment', '-segment_time', '900',
            '-c', 'copy', f'{chunk_prefix}%03d.mp3'
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        chunk_files = sorted([
            os.path.join(temp_dir, f) for f in os.listdir(temp_dir)
            if f.startswith("chunk_") and f.endswith(".mp3")
        ])
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

        return " ".join(full_transcript)

    except Exception as e:
        print(f"❌ Chunked Transcription error: {e}")
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    client = get_groq_client()
    cache = load_cache()

    if not os.path.exists(LINKS_FILE):
        print(f"❌ '{LINKS_FILE}' not found."); return

    with open(LINKS_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(urls)} URLs. Starting ensemble processing...")

    for idx, url in enumerate(urls):
        print(f"\n--- Processing Video {idx+1}/{len(urls)} ---")
        key = cache_key(url)

        if key in cache and cache[key].get("final_text"):
            print(f"📦 Using cached result for {url}")
            video_title = cache[key].get("title", "Untitled_Video")
            final_text = cache[key]["final_text"]
        else:
            temp_base = f"temp_vid_{idx}"

            if key in cache and cache[key].get("whisper_text"):
                print("📦 Using cached transcript (skipping download + transcription)")
                whisper_text = cache[key]["whisper_text"]
                yt_text = cache[key].get("yt_text", "")
                video_title = cache[key].get("title", "Untitled_Video")
            else:
                video_title, yt_text, audio_file = get_content_from_youtube(url, temp_base)
                if not audio_file or not os.path.exists(audio_file):
                    print(f"⚠️ Failed to get audio for {url}. Skipping.")
                    continue

                whisper_text = generate_groq_whisper(client, audio_file)
                if os.path.exists(audio_file):
                    os.remove(audio_file)

                if not whisper_text:
                    print(f"⚠️ Failed to transcribe audio. Skipping.")
                    continue

                cache[key] = {"whisper_text": whisper_text, "yt_text": yt_text, "title": video_title}
                save_cache(cache)

            final_text = synthesize_and_polish(client, whisper_text, yt_text)
            cache[key]["final_text"] = final_text
            save_cache(cache)

        epub_filename = f"{video_title}.epub"
        create_epub(video_title, final_text, epub_filename)
        print(f"✨ Created Ensemble Book: outputs/{epub_filename}")

        md_filename = f"{video_title}.md"
        create_markdown(video_title, final_text, url, md_filename)
        print(f"✨ Created Markdown: outputs/{md_filename}")

if __name__ == "__main__":
    main()
