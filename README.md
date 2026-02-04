# 📖 TubeToPage: AI-Powered YouTube-to-eBook Converter

**TubeToPage** is a high-performance Python tool that transforms YouTube videos into polished, professional eBooks. By leveraging state-of-the-art AI models via **Groq**, it synthesizes audio transcripts and YouTube captions into a coherent narrative, formatted specifically for "Bionic Reading."

---

## 🚀 Key Features

- **Ensemble Synthesis:** Uses **Llama 3.3 70B** to cross-reference YouTube's auto-captions with high-fidelity **Whisper-Large-v3** transcripts, ensuring technical terms and names are 100% accurate.
- **Bionic Reading Support:** Automatically formats text with **Bionic bolding**, significantly increasing reading speed and focus on e-readers.
- **Batch Processing:** Drop multiple URLs into a `links.txt` file and generate an entire library in one go.
- **Polished Prose:** Moves beyond raw transcripts. The AI acts as a scientific editor, removing filler words (uh, um) and rewriting spoken word into high-quality book-style narrative.
- **Security First:** Built to use environment variables for API management, preventing accidental exposure of sensitive keys.

---

## 🛠️ Tech Stack

- **Transcription:** [Groq](https://groq.com/) Whisper-Large-v3
- **Intelligence:** [Groq](https://groq.com/) Llama 3.3 70B
- **Extraction:** `yt-dlp` & `youtube-transcript-api`
- **Output Format:** EPUB (via `ebooklib`)
- **Language:** Python 3.11+

---

## 🏗️ How it Works

1. **Dual-Stream Retrieval:** The script extracts the official YouTube transcript and simultaneously downloads the audio stream.
2. **AI Transcription:** The audio is sent to Groq's LPUs for near-instant transcription using Whisper.
3. **Ensemble Refinement:** Both transcripts are fed into Llama 3.3. The model identifies discrepancies, fixes stutters, and synthesizes the content into textbook-quality prose.
4. **Bionic Formatting:** The text is processed to bold the "fixation points" of every word.
5. **eBook Assembly:** A structured EPUB is generated with custom CSS for perfect visibility in both light and dark modes.

---

## ⚙️ Installation & Setup

### 1. Clone the Repo
```bash
git clone https://github.com/NeelM47/video-to-book.git
cd video-to-book
```
