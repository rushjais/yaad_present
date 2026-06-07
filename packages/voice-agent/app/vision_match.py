"""Standalone face-match validation.

Loads labeled reference images from  packages/voice-agent/references/
(filename stem = person label: leo.jpg → "Leo"), then asks a vision model
which reference matches a live photo supplied as a CLI argument.

No memory lookup, no webcam, no pipeline — just images in, name out.

Usage (run from packages/voice-agent/):
    python3 -m app.vision_match <path-to-live-image>

Example:
    python3 -m app.vision_match /tmp/frame.jpg
"""

import asyncio
import base64
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── constants (swap model here if needed) ─────────────────────────────────────
VISION_MODEL = "gpt-4o"               # full gpt-4o via OpenAI direct (TrueFoundry uses "openai/gpt-4o")
MAX_PX = 512                      # downscale longest edge to this before encoding
REFERENCES_DIR = Path(__file__).parent.parent / "references"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# ── image helpers ─────────────────────────────────────────────────────────────

def _encode(path: Path) -> str:
    """Load image, downscale to MAX_PX on longest side, return base64 data URL."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_PX:
        scale = MAX_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _load_references() -> list[tuple[str, str]]:
    """Return [(label, data_url), …] for every image in REFERENCES_DIR."""
    if not REFERENCES_DIR.exists():
        REFERENCES_DIR.mkdir(parents=True)
        return []
    return [
        (p.stem.capitalize(), _encode(p))
        for p in sorted(REFERENCES_DIR.iterdir())
        if p.suffix.lower() in IMAGE_EXTS
    ]


# ── core ──────────────────────────────────────────────────────────────────────

def _vision_client():
    """Return an AsyncOpenAI client for the vision model.

    Prefers OPENAI_API_KEY (direct to OpenAI, which provides gpt-4o).
    Falls back to TrueFoundry if only that key is present — but note that
    TrueFoundry on this account only has gpt-4o-mini, which has poor
    face-discrimination accuracy.
    """
    import openai
    oai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if oai_key:
        return openai.AsyncOpenAI(api_key=oai_key)

    base_url = os.environ.get("TRUEFOUNDRY_BASE_URL", "").strip()
    tf_key   = os.environ.get("TRUEFOUNDRY_API_KEY",  "").strip()
    if base_url and tf_key:
        return openai.AsyncOpenAI(api_key=tf_key, base_url=base_url)

    print("ERROR: set OPENAI_API_KEY (preferred) or TRUEFOUNDRY_BASE_URL + TRUEFOUNDRY_API_KEY")
    sys.exit(1)


async def match(live_path: Path) -> str:
    """Return matched label (or 'unknown')."""
    refs = _load_references()
    if not refs:
        print(f"\nNo reference images found in:  {REFERENCES_DIR}/")
        print("Add images named after the person (e.g. leo.jpg, sarah.png) then re-run.\n")
        sys.exit(0)

    print(f"References : {[name for name, _ in refs]}")
    print(f"Live image : {live_path}")
    print(f"Model      : {VISION_MODEL}")
    print()

    # Build one multimodal user message: all references, then the live photo
    content: list[dict] = []
    for name, data_url in refs:
        content.append({"type": "text", "text": f"Reference photo labeled '{name}':"})
        content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})

    content.append({"type": "text", "text": "New photo to identify:"})
    content.append({"type": "image_url", "image_url": {"url": _encode(live_path), "detail": "low"}})
    content.append({
        "type": "text",
        "text": (
            "Which of the labeled people is the person in the new photo? "
            "Reply with ONLY the name, or 'unknown' if none match."
        ),
    })

    client = _vision_client()
    resp = await client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=20,
        temperature=0.0,
    )

    raw = (resp.choices[0].message.content or "").strip()

    # Match against known labels (case-insensitive, strip stray punctuation)
    known = {name.lower(): name for name, _ in refs}
    parsed_key = raw.lower().strip(".,!? ")
    result = known.get(parsed_key, "unknown")

    print(f"Model reply : {raw!r}")
    print(f"Parsed name : {result}")
    return result


# ── debug: can the model see images at all? ───────────────────────────────────

async def debug_image(img_path: Path) -> None:
    """Send one image and ask for a one-sentence description — proves delivery."""
    data_url = _encode(img_path)
    print(f"Image      : {img_path}")
    print(f"Model      : {VISION_MODEL}")
    print(f"Payload    : {len(data_url)} chars (base64 data URL)")
    print()

    client = _vision_client()
    resp = await client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
            {"type": "text",      "text": "Describe this image in one sentence."},
        ]}],
        max_tokens=60,
        temperature=0.0,
    )
    reply = (resp.choices[0].message.content or "").strip()
    print(f"Model reply: {reply!r}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--debug":
        img = Path(sys.argv[2])
        if not img.exists():
            print(f"ERROR: file not found: {img}")
            sys.exit(1)
        asyncio.run(debug_image(img))
    elif len(sys.argv) == 2:
        live = Path(sys.argv[1])
        if not live.exists():
            print(f"ERROR: file not found: {live}")
            sys.exit(1)
        asyncio.run(match(live))
    else:
        print("Usage:")
        print("  python3 -m app.vision_match <live-image>")
        print("  python3 -m app.vision_match --debug <any-image>")
        sys.exit(1)
