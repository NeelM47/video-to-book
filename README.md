# 📺 TubeToPage: Video to Bionic E-Book Converter

**TubeToPage** is a local Python pipeline that converts educational YouTube videos into highly readable, "Bionic Reading" style EPUB books. It utilizes AI audio alignment and LLM polishing to turn messy subtitles into coherent prose.

## 🏗 Architecture

1.  **Extraction**: `yt-dlp` extracts audio/subtitles.
2.  **Transcription**: `WhisperX` (optional) provides word-level timestamps and higher accuracy than YouTube captions.
3.  **Synthesis**: `Llama 3.2` (via Ollama) rewrites the transcript into book-style narrative, fixing grammar while retaining technical details.
4.  **Formatting**: `EbookLib` compiles the text into an EPUB with Bionic Reading formatting (bolding initial letters) to improve focus.

## 🚀 Usage

### Prerequisites
*   [Ollama](https://ollama.com/) installed and running (`ollama pull llama3.2`).
*   FFmpeg installed on your system.
*   NVIDIA GPU recommended (for WhisperX).

### Installation
```bash
git clone https://github.com/NeelM47/video-to-book.git
cd video-to-book
pip install -r requirements.txt
