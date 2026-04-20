"""
One-time script: runs the 5 sample images through Claude claude-sonnet-4-5
and writes real pre_thinking + result data back into data/samples.json.
"""

import os
import sys
import json
import base64
import re
from pathlib import Path

import anthropic

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
SAMPLES_JSON = ROOT / "data" / "samples.json"
IMAGES_DIR   = ROOT / "static" / "samples"

# ── country → flag emoji ───────────────────────────────────────────────────────
COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫", "Albania": "🇦🇱", "Algeria": "🇩🇿", "Argentina": "🇦🇷",
    "Armenia": "🇦🇲", "Australia": "🇦🇺", "Austria": "🇦🇹", "Azerbaijan": "🇦🇿",
    "Bangladesh": "🇧🇩", "Belarus": "🇧🇾", "Belgium": "🇧🇪", "Bolivia": "🇧🇴",
    "Bosnia": "🇧🇦", "Botswana": "🇧🇼", "Brazil": "🇧🇷", "Bulgaria": "🇧🇬",
    "Cambodia": "🇰🇭", "Canada": "🇨🇦", "Chile": "🇨🇱", "China": "🇨🇳",
    "Colombia": "🇨🇴", "Croatia": "🇭🇷", "Czech Republic": "🇨🇿", "Czechia": "🇨🇿",
    "Denmark": "🇩🇰", "Ecuador": "🇪🇨", "Egypt": "🇪🇬", "Estonia": "🇪🇪",
    "Ethiopia": "🇪🇹", "Finland": "🇫🇮", "France": "🇫🇷", "Georgia": "🇬🇪",
    "Germany": "🇩🇪", "Ghana": "🇬🇭", "Greece": "🇬🇷", "Guatemala": "🇬🇹",
    "Hungary": "🇭🇺", "Iceland": "🇮🇸", "India": "🇮🇳", "Indonesia": "🇮🇩",
    "Iran": "🇮🇷", "Iraq": "🇮🇶", "Ireland": "🇮🇪", "Israel": "🇮🇱",
    "Italy": "🇮🇹", "Japan": "🇯🇵", "Jordan": "🇯🇴", "Kazakhstan": "🇰🇿",
    "Kenya": "🇰🇪", "Kosovo": "🇽🇰", "Kyrgyzstan": "🇰🇬", "Laos": "🇱🇦",
    "Latvia": "🇱🇻", "Lithuania": "🇱🇹", "Malaysia": "🇲🇾", "Mexico": "🇲🇽",
    "Moldova": "🇲🇩", "Mongolia": "🇲🇳", "Montenegro": "🇲🇪", "Morocco": "🇲🇦",
    "Myanmar": "🇲🇲", "Nepal": "🇳🇵", "Netherlands": "🇳🇱", "New Zealand": "🇳🇿",
    "Nigeria": "🇳🇬", "North Macedonia": "🇲🇰", "Norway": "🇳🇴", "Pakistan": "🇵🇰",
    "Paraguay": "🇵🇾", "Peru": "🇵🇪", "Philippines": "🇵🇭", "Poland": "🇵🇱",
    "Portugal": "🇵🇹", "Romania": "🇷🇴", "Russia": "🇷🇺", "Rwanda": "🇷🇼",
    "Saudi Arabia": "🇸🇦", "Senegal": "🇸🇳", "Serbia": "🇷🇸", "Singapore": "🇸🇬",
    "Slovakia": "🇸🇰", "Slovenia": "🇸🇮", "South Africa": "🇿🇦", "South Korea": "🇰🇷",
    "Spain": "🇪🇸", "Sri Lanka": "🇱🇰", "Sweden": "🇸🇪", "Switzerland": "🇨🇭",
    "Taiwan": "🇹🇼", "Tanzania": "🇹🇿", "Thailand": "🇹🇭", "Tunisia": "🇹🇳",
    "Turkey": "🇹🇷", "Türkiye": "🇹🇷", "Uganda": "🇺🇬", "Ukraine": "🇺🇦",
    "United Kingdom": "🇬🇧", "UK": "🇬🇧", "United States": "🇺🇸", "USA": "🇺🇸",
    "Uruguay": "🇺🇾", "Uzbekistan": "🇺🇿", "Venezuela": "🇻🇪", "Vietnam": "🇻🇳",
    "Zambia": "🇿🇲", "Zimbabwe": "🇿🇼",
}

GRADIENTS = [
    ("linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)", "#e94560"),
    ("linear-gradient(135deg, #2c3e50 0%, #3d5a80 50%, #98c1d9 100%)", "#e8c547"),
    ("linear-gradient(135deg, #134e5e 0%, #71b280 100%)",               "#f7dc6f"),
    ("linear-gradient(135deg, #3d1c02 0%, #8b4513 50%, #cd853f 100%)", "#4ade80"),
    ("linear-gradient(135deg, #2d1b69 0%, #8b2fc9 50%, #c9184a 100%)", "#ff6b6b"),
]

SYSTEM_PROMPT = """You are an expert GeoGuessr player. Analyze the street view image systematically.

Think out loud, step by step:
- SCRIPT/LANGUAGE: Any text visible? Latin, Cyrillic, Arabic, Asian script?
- DRIVING SIDE: Left or right-hand traffic?
- ROAD MARKINGS: Yellow or white center lines?
- BOLLARDS: Color and style of any road posts or delineators?
- VEGETATION: Tropical, temperate, boreal, Mediterranean, desert, savanna?
- TERRAIN: Flat, hilly, mountainous, coastal, plateau?
- ARCHITECTURE: Building styles, materials, condition?
- SIGNS: Colors, shapes, language, any specific text?
- INFRASTRUCTURE: Utility pole type, road quality, guardrails?
- OTHER: Vehicles, soil color, sun angle, anything distinctive?
- CONCLUSION: Reason from the evidence to the most specific location possible.

COORDINATE RULES:
- ALWAYS provide your best lat/lng guess, even with very low confidence. Never output 0.0, 0.0.
- Coordinates MUST point to land — a road, town, or city. Never place in ocean, sea, or large lake.
- Aim for city or district level. Use 4 decimal places.

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


def extract_json(text: str) -> dict | None:
    m = re.search(r"RESULT_JSON:\s*(\{[\s\S]*?\})\s*(?:\n|$)", text)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    m = re.search(r"RESULT_JSON:\s*(\{[\s\S]*\})", text)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    for m in reversed(list(re.finditer(r"\{[\s\S]*?\}", text))):
        try:
            obj = json.loads(m.group())
            if any(k in obj for k in ("country", "latitude", "location_name")):
                return obj
        except: continue
    return None


def get_flag(country: str) -> str:
    for name, flag in COUNTRY_FLAGS.items():
        if name.lower() in country.lower() or country.lower() in name.lower():
            return flag
    return "🌍"


def analyze_image(client: anthropic.Anthropic, image_path: Path, idx: int) -> dict:
    print(f"\n{'='*60}")
    print(f"[{idx}/5] Analyzing {image_path.name} ...")

    image_data = image_path.read_bytes()
    b64 = base64.standard_b64encode(image_data).decode()

    full_text = ""
    print("  Streaming response", end="", flush=True)

    with client.messages.stream(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": "Analyze this street view image and predict the location. Think step by step, then output the RESULT_JSON."},
            ],
        }],
    ) as stream:
        for text in stream.text_stream:
            full_text += text
            print(".", end="", flush=True)

    print(" done")

    result = extract_json(full_text)
    if not result:
        print("  ⚠️  Could not parse JSON — raw response saved as pre_thinking only")
        return None

    # Split thinking from JSON section
    thinking_part = full_text
    marker_pos = full_text.find("RESULT_JSON:")
    if marker_pos > 0:
        thinking_part = full_text[:marker_pos].strip()

    country  = result.get("country", "Unknown")
    region   = result.get("region", "")
    name     = f"{region}, {country}" if region else country
    flag     = get_flag(country)
    gradient, accent = GRADIENTS[(idx - 1) % len(GRADIENTS)]

    print(f"  ✅  {name}  {flag}  ({result.get('latitude')}, {result.get('longitude')})  [{result.get('confidence')} confidence]")

    return {
        "id": str(idx),
        "name": name,
        "country": country,
        "flag": flag,
        "gradient": gradient,
        "accent": accent,
        "image": f"{idx}.png",
        "pre_thinking": thinking_part,
        "result": result,
    }


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌  ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Parse --only flag: python analyze_samples.py --only 2
    only = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        only = int(sys.argv[idx + 1])

    # Load existing samples to patch into
    existing = []
    if SAMPLES_JSON.exists():
        with open(SAMPLES_JSON, encoding="utf-8") as f:
            existing = json.load(f)
    existing_by_id = {s["id"]: s for s in existing}

    targets = [only] if only else list(range(1, 6))

    for i in targets:
        image_path = IMAGES_DIR / f"{i}.png"
        if not image_path.exists():
            print(f"⚠️  {image_path} not found — skipping")
            continue

        entry = analyze_image(client, image_path, i)
        if entry:
            existing_by_id[str(i)] = entry

    samples = [existing_by_id[str(i)] for i in range(1, 6) if str(i) in existing_by_id]

    if not samples:
        print("\n❌  No results — nothing written.")
        sys.exit(1)

    with open(SAMPLES_JSON, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    print(f"\n✅  Saved {len(samples)} samples to {SAMPLES_JSON}")
    for s in samples:
        print(f"   {s['flag']}  {s['name']}")


if __name__ == "__main__":
    main()
