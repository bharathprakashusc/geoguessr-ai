import os
import json
import re
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import ollama

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
    try:
        result = ollama.list()
        models = [m.model for m in result.models]
        return {"models": models, "default": DEFAULT_MODEL}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama not reachable: {e}")


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
            msg1 = json.dumps({"type": "thinking", "text": f"Model: {model} | Prompt: {prompt_mode}\nLoading model into memory...\n"})
            msg2 = json.dumps({"type": "thinking", "text": "Sending image to model...\n\n"})
            yield f"data: {msg1}\n\n"
            yield f"data: {msg2}\n\n"

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
                # Stream everything up to RESULT_JSON as thinking
                if "RESULT_JSON:" not in full_text:
                    yield f"data: {json.dumps({'type': 'thinking', 'text': text})}\n\n"

            # Pass 1: try to extract JSON from the raw response
            result = try_extract_json(full_text)

            if result:
                yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            else:
                # Pass 2: model didn't follow the format — ask it again with just text
                notice = json.dumps({"type": "thinking", "text": "\n\n[Model did not output structured JSON — running extraction pass...]\n"})
                yield f"data: {notice}\n\n"

                result = second_pass_json(model, full_text)
                if result:
                    yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
                else:
                    err = json.dumps({"type": "error", "message": "Could not extract a location from the model response. Try a larger model like llama3.2-vision."})
                    yield f"data: {err}\n\n"

        except Exception as e:
            err = json.dumps({"type": "error", "message": f"Ollama error: {str(e)}"})
            yield f"data: {err}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
