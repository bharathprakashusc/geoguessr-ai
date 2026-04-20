import os
import json
import re
import base64
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import ollama
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

CLAUDE_MODELS = [
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-haiku-4-5",
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

METAS_PATH = Path(__file__).parent / "data" / "metas.json"
with open(METAS_PATH) as f:
    METAS = json.load(f)

SAMPLES_PATH = Path(__file__).parent / "data" / "samples.json"
with open(SAMPLES_PATH, encoding="utf-8") as f:
    SAMPLES = json.load(f)

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2-vision")

# ── SHORT PROMPT (no metas DB, ~400 tokens) ──────────────────────────────────
SHORT_SYSTEM_PROMPT = """You are an expert GeoGuessr player. Analyze the street view image systematically.

Think out loud, step by step:
- SCRIPT/LANGUAGE: Any text visible? Latin, Cyrillic, Arabic, Asian script?
- DRIVING SIDE: Left or right-hand traffic?
- ROAD MARKINGS: Yellow or white center lines? (Yellow = Americas/Japan/Korea/Australia)
- BOLLARDS: Color and style of any road posts or delineators?
- VEGETATION: Tropical, temperate, boreal, Mediterranean, desert, savanna?
- TERRAIN: Flat, hilly, mountainous, coastal, plateau?
- ARCHITECTURE: Building styles, materials, condition?
- SIGNS: Colors, shapes, language, any specific text?
- INFRASTRUCTURE: Utility pole type, road quality, guardrails?
- OTHER: Vehicles, soil color, sun angle, anything distinctive?
- CONCLUSION: Reason from the evidence to the most specific location possible.

COORDINATE RULES (critical):
- ALWAYS provide your best lat/lng guess, even with very low confidence. Never output 0.0, 0.0.
- Coordinates MUST point to land — a road, town, or city. Never place in ocean, sea, or large lake.
- Be as specific as possible. Aim for city or district level, not country centroid.
- If very uncertain about region, use the country's capital city coordinates as fallback.
- Provide 4 decimal places of precision.

After your thinking, output this exact block:

RESULT_JSON:
{
  "clues": {
    "script_language": "...",
    "driving_side": "left/right/unclear",
    "road_lines": "...",
    "bollards": "...",
    "vegetation": "...",
    "terrain": "...",
    "architecture": "...",
    "signs": "...",
    "infrastructure": "...",
    "other": "..."
  },
  "reasoning": "One paragraph summary of reasoning",
  "country": "Most likely country",
  "region": "Most likely region/state/province",
  "confidence": "high/medium/low",
  "latitude": 0.0000,
  "longitude": 0.0000,
  "location_name": "Specific city or area name, Country",
  "alternatives": [
    {"country": "...", "region": "...", "latitude": 0.0000, "longitude": 0.0000, "reason": "..."}
  ]
}"""

# ── LONG PROMPT (full metas DB, ~8000 tokens) ────────────────────────────────
LONG_SYSTEM_PROMPT = f"""You are an expert GeoGuessr player with deep knowledge of global geography, road infrastructure, vegetation, architecture, and cultural visual cues. You analyze street-view images to pinpoint locations.

You have access to this structured knowledge base of GeoGuessr metas:

{json.dumps(METAS, indent=2)}

When analyzing an image, follow this two-part format EXACTLY:

PART 1 — Write your thinking out loud, step by step, in plain English. Work through each of these:
- SCRIPT/LANGUAGE: What text or script can you see?
- DRIVING SIDE: Which side of the road is traffic on?
- ROAD MARKINGS: Are center lines yellow or white?
- BOLLARDS: Describe any road posts, bollards, delineators visible.
- VEGETATION: What plants and trees are visible?
- TERRAIN: Flat, hilly, mountainous, coastal, plateau?
- ARCHITECTURE: Buildings visible? Style, materials, age?
- SIGNS: Any signs? Color, shape, language, specific text?
- INFRASTRUCTURE: Utility poles, road quality, guardrails?
- OTHER CLUES: Vehicles, sun angle, soil color, distinctive objects?
- CONCLUSION: Reason through the evidence to narrow down the location.

COORDINATE RULES (critical):
- ALWAYS provide your best lat/lng guess, even with very low confidence. Never output 0.0, 0.0.
- Coordinates MUST point to land — a road, town, or city. Never place in ocean, sea, or large lake.
- Be as specific as possible. Aim for city or district level, not country centroid.
- If very uncertain about region, use the country's capital city coordinates as fallback.
- Provide 4 decimal places of precision.

PART 2 — After your thinking, output this exact block:

RESULT_JSON:
{{
  "clues": {{
    "script_language": "...",
    "driving_side": "left/right/unclear",
    "road_lines": "...",
    "bollards": "...",
    "vegetation": "...",
    "terrain": "...",
    "architecture": "...",
    "signs": "...",
    "infrastructure": "...",
    "other": "..."
  }},
  "reasoning": "One paragraph summary of reasoning",
  "country": "Most likely country",
  "region": "Most likely region/state/province",
  "confidence": "high/medium/low",
  "latitude": 0.0000,
  "longitude": 0.0000,
  "location_name": "Specific city or area name, Country",
  "alternatives": [
    {{"country": "...", "region": "...", "latitude": 0.0000, "longitude": 0.0000, "reason": "why this is possible"}}
  ]
}}"""


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/models")
async def list_models():
    models = []

    # Ollama models
    try:
        result = ollama.list()
        models += [m.model for m in result.models]
    except Exception:
        pass  # Ollama offline — still return Claude models if key exists

    # Claude models (only if API key is configured)
    if anthropic_client:
        models += CLAUDE_MODELS

    if not models:
        raise HTTPException(status_code=503, detail="No models available. Start Ollama or set ANTHROPIC_API_KEY.")

    return {
        "models": models,
        "default": DEFAULT_MODEL,
        "claude_available": anthropic_client is not None,
    }


@app.get("/health")
async def health():
    try:
        result = ollama.list()
        model_names = [m.model for m in result.models]
        return {
            "ollama": "connected",
            "models": model_names,
            "active_model": DEFAULT_MODEL,
            "model_ready": any(DEFAULT_MODEL in name for name in model_names),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama not reachable: {e}")


@app.get("/samples")
async def get_samples():
    samples_dir = Path("static/samples")
    result = []
    for s in SAMPLES:
        image_path = samples_dir / s["image"]
        s_copy = {k: v for k, v in s.items() if k not in ("pre_thinking", "result")}
        s_copy["has_image"] = image_path.exists()
        s_copy["image_url"] = f"/static/samples/{s['image']}" if image_path.exists() else None
        result.append(s_copy)
    return result


@app.get("/samples/{sample_id}")
async def get_sample(sample_id: str):
    sample = next((s for s in SAMPLES if s["id"] == sample_id), None)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@app.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
    prompt_mode: str = Form("short"),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_data = await file.read()
    if len(image_data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 20MB)")

    system_prompt = LONG_SYSTEM_PROMPT if prompt_mode == "long" else SHORT_SYSTEM_PROMPT
    is_claude = model.startswith("claude-")

    def try_extract_json(text: str) -> dict | None:
        """Try multiple strategies to extract a valid location JSON from text."""
        # Strategy 1: RESULT_JSON marker
        m = re.search(r"RESULT_JSON:\s*(\{[\s\S]*?\})\s*(?:\n|$)", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2: RESULT_JSON with greedy match (model may add extra text after)
        m = re.search(r"RESULT_JSON:\s*(\{[\s\S]*\})", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: any JSON object that has location-like keys
        for m in reversed(list(re.finditer(r"\{[\s\S]*?\}", text))):
            try:
                obj = json.loads(m.group())
                if any(k in obj for k in ("country", "latitude", "location_name")):
                    return obj
            except json.JSONDecodeError:
                continue

        return None

    def second_pass_json(model_name: str, analysis_text: str) -> dict | None:
        """Ask the model to convert its plain-text analysis into JSON."""
        prompt = (
            "You analyzed a street view image and wrote this:\n\n"
            f"{analysis_text[:1500]}\n\n"
            "Now output ONLY a JSON object with NO other text, markdown, or explanation:\n"
            '{"country":"...","region":"...","latitude":0.0,"longitude":0.0,'
            '"confidence":"low","location_name":"...","reasoning":"...",'
            '"clues":{"script_language":"...","driving_side":"...","vegetation":"...","other":"..."},'
            '"alternatives":[]}'
        )
        try:
            resp = ollama.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 600},
            )
            return try_extract_json(resp.message.content)
        except Exception:
            return None

    def stream_response():
        full_text = ""
        try:
            header = json.dumps({"type": "thinking", "text": f"Model: {model} | Prompt: {prompt_mode}\nSending image to model...\n\n"})
            yield f"data: {header}\n\n"

            # ── CLAUDE (Anthropic API) ────────────────────────────────────────
            if is_claude:
                if not anthropic_client:
                    err = json.dumps({"type": "error", "message": "ANTHROPIC_API_KEY not set. Add it to your environment and restart."})
                    yield f"data: {err}\n\n"
                    return

                media_type = file.content_type if file.content_type in ("image/jpeg", "image/png", "image/gif", "image/webp") else "image/jpeg"
                b64_image = base64.standard_b64encode(image_data).decode("utf-8")

                with anthropic_client.messages.stream(
                    model=model,
                    max_tokens=3000,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                            {"type": "text", "text": "Analyze this street view image and predict the location. Think step by step, then output the RESULT_JSON."},
                        ],
                    }],
                ) as stream:
                    for text in stream.text_stream:
                        full_text += text
                        if "RESULT_JSON:" not in full_text:
                            yield f"data: {json.dumps({'type': 'thinking', 'text': text})}\n\n"

            # ── OLLAMA (local) ────────────────────────────────────────────────
            else:
                for chunk in ollama.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": "Analyze this street view image and predict the location. Think step by step, then output the RESULT_JSON.",
                            "images": [image_data],
                        },
                    ],
                    stream=True,
                    options={"temperature": 0.1, "num_predict": 3000},
                ):
                    text = chunk.message.content
                    full_text += text
                    if "RESULT_JSON:" not in full_text:
                        yield f"data: {json.dumps({'type': 'thinking', 'text': text})}\n\n"

            # ── JSON extraction (same for both backends) ──────────────────────
            result = try_extract_json(full_text)

            if result:
                yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            else:
                notice = json.dumps({"type": "thinking", "text": "\n\n[Structured JSON not found — running extraction pass...]\n"})
                yield f"data: {notice}\n\n"
                result = second_pass_json(model, full_text)
                if result:
                    yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
                else:
                    err = json.dumps({"type": "error", "message": "Could not extract a location. Try a larger model."})
                    yield f"data: {err}\n\n"

        except Exception as e:
            backend = "Anthropic" if is_claude else "Ollama"
            err = json.dumps({"type": "error", "message": f"{backend} error: {str(e)}"})
            yield f"data: {err}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
