# GeoAI — Street View Location Analyzer

An AI-powered GeoGuessr assistant that analyzes street view screenshots and predicts the location on a map. Drop an image, watch the AI reason through visual clues in real time, and get a pinned latitude/longitude result.

![GeoAI Screenshot](screenshot.png)

---

## Features

- **Image input** — drag and drop, click to browse, or paste directly with `Ctrl+V`
- **Live AI thinking stream** — watch the model reason through clues in real time as it analyzes script/language, driving side, road markings, bollards, vegetation, terrain, architecture, and more
- **Interactive map** — prediction pinned on a dark Leaflet map with alternatives shown as secondary markers
- **Model selector** — switch between any installed Ollama vision model without restarting
- **Prompt toggle** — Short mode (~400 tokens, faster) or Long mode (full GeoGuessr meta knowledge base, more accurate)
- **Expected time estimate** — shows predicted analysis time based on selected model and prompt mode
- **Live elapsed timer** — see exactly how long the current analysis has been running
- **Completion notifications** — in-app toast + browser notification when a result is ready
- **Two-pass JSON extraction** — if the model skips the structured format, a second lightweight pass extracts the result automatically

---

## How It Works

1. You upload a street view screenshot
2. The image is sent to a local vision model via [Ollama](https://ollama.com)
3. The model is prompted to analyze visual clues systematically:
   - Script and language on signs
   - Driving side
   - Road line colors (yellow = Americas/Japan/Korea/Australia, white = Europe/Africa)
   - Bollard styles (highly country-specific)
   - Vegetation and terrain type
   - Architecture style
   - Infrastructure details
4. The reasoning streams to the UI in real time
5. A structured result (country, region, lat/lng, confidence, alternatives) is parsed and pinned on the map

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Uvicorn |
| AI | Ollama (local vision models) |
| Frontend | Vanilla HTML/CSS/JS |
| Map | Leaflet.js + CartoDB dark tiles |

---

## Setup

### 1. Install Ollama

Download from [ollama.com](https://ollama.com) and install.

### 2. Pull a vision model

```bash
# Best accuracy (~8GB)
ollama pull llama3.2-vision

# Fastest / smallest (~1.7GB)
ollama pull moondream
```

### 3. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/geoguessr-ai.git
cd geoguessr-ai
pip install -r requirements.txt
```

### 4. Run

```bash
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

---

## Model Comparison

| Model | Size | Speed (CPU) | Accuracy |
|-------|------|-------------|----------|
| `moondream` | ~1.7 GB | ~1–2 min | Low — struggles with structured output |
| `llava:7b` | ~4 GB | ~3–6 min | Medium |
| `minicpm-v` | ~5 GB | ~2–4 min | Medium–High |
| `llama3.2-vision` | ~8 GB | ~2–5 min | Best |

> **GPU users:** Ollama automatically uses your GPU, which is ~8x faster than CPU.

---

## Knowledge Base

The long prompt mode includes a structured `data/metas.json` knowledge base covering ~60 countries with:

- Road line color conventions
- Driving side by country
- Bollard styles by country
- Sign color and script systems
- Vegetation zones
- Architecture styles
- Google Street View camera generations
- License plate conventions
- Terrain types
- Country-specific clues (PARE vs STOP vs ALTO, soil colors, unique landmarks)

---

## Project Structure

```
geoguessr-ai/
├── main.py           # FastAPI backend — streaming SSE, Ollama integration
├── requirements.txt
├── data/
│   └── metas.json    # GeoGuessr meta knowledge base
└── static/
    └── index.html    # Frontend — 3-column layout, map, live thinking stream
```

---

## Switching to Anthropic Claude (Optional)

For significantly faster results (5–10 seconds vs minutes) and higher accuracy, the backend can be swapped to use the Anthropic API. With `claude-sonnet-4-6` vision, $20 of API credits gives approximately 500 analyses.

---

## License

MIT
