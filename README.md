```
# 📖 TubeToPage: AI-Powered YouTube-to-eBook Converter

**TubeToPage** is a high-performance Python tool that transforms YouTube videos into polished, professional eBooks. By leveraging state-of-the-art AI models via **Groq**, it synthesizes audio transcripts and YouTube captions into a coherent narrative, formatted specifically for "Bionic Reading."

---

## 🚀 Key Features

- **Ensemble Synthesis:** Uses **Llama 3.3 70B** to cross-reference YouTube's auto-captions with high-fidelity **Whisper-Large-v3** transcripts, ensuring technical terms and names are 100% accurate.
- **Bionic Reading Support:** Automatically formats text with **Bionic bolding**, significantly increasing reading speed and focus on e-readers.
- **Batch Processing:** Drop multiple URLs into a `links.txt` file and generate an entire library overnight.
- **Polished Prose:** Moves beyond raw transcripts. The AI acts as a scientific editor, removing filler words (uh, um) and rewriting spoken word into high-quality book-style narrative.
- **Cloud Optimized:** Engineered to handle IP blocks and PyTorch 2.6+ security constraints for seamless deployment.

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
git clone https://github.com/YourUsername/tubetopage-cloud.git
cd tubetopage-cloud
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configuration
Set your Groq API Key:
```python
# In main.py
GROQ_API_KEY = "your_key_here"
```

### 4. Run
Add your YouTube links to `links.txt` and execute:
```bash
python main.py
```

---

## 🛡️ PyTorch 2.6 Fix
This project includes a built-in patch for the recent PyTorch 2.6 security update (`weights_only=True` changes) that previously broke `whisperx` and `pyannote` models. It uses a custom `patched_load` strategy to ensure model weights load correctly in production environments.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/YourUsername/tubetopage-cloud/issues).

## 📜 License
[MIT](https://choosealicense.com/licenses/mit/)
```

