"""Standalone face-match: compares a live photo against labeled references.

Uses face_recognition (dlib) — no LLM, no network call.

References: packages/voice-agent/references/
  Filename stem = label (leo.jpg → "Leo"). Images with no detectable face are skipped.

Usage (run from packages/voice-agent/):
    python3 -m app.vision_match <path-to-live-image>
    python3 -m app.vision_match --camera

Example:
    python3 -m app.vision_match /tmp/frame.jpg
"""

import sys
from pathlib import Path

import cv2
import face_recognition
import numpy as np

REFERENCES_DIR = Path(__file__).parent.parent / "references"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
TOLERANCE = 0.6


def _load_references() -> dict[str, np.ndarray]:
    """Return {label: encoding} for each reference image that contains a detectable face."""
    if not REFERENCES_DIR.exists():
        REFERENCES_DIR.mkdir(parents=True)
        return {}

    refs: dict[str, np.ndarray] = {}
    for p in sorted(REFERENCES_DIR.iterdir()):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        img = face_recognition.load_image_file(str(p))
        encs = face_recognition.face_encodings(img)
        if not encs:
            print(f"WARNING: no face detected in reference '{p.name}' — skipping")
            continue
        refs[p.stem.capitalize()] = encs[0]
    return refs


def _run_match(
    refs: dict[str, np.ndarray], rgb: np.ndarray
) -> tuple[str | None, dict[str, float]]:
    """Encode rgb and compare against pre-loaded refs.

    Returns (None, {}) if no face is detected.
    Returns (name_or_unknown, {label: distance}) otherwise.
    """
    live_encs = face_recognition.face_encodings(rgb)
    if not live_encs:
        return None, {}
    names = sorted(refs.keys())
    raw = face_recognition.face_distance([refs[n] for n in names], live_encs[0])
    distances = {n: float(d) for n, d in zip(names, raw)}
    best = min(distances, key=distances.get)
    name = best if distances[best] < TOLERANCE else "unknown"
    return name, distances


def match_rgb(rgb: np.ndarray) -> tuple[str | None, dict[str, float]]:
    """Public entry point for callers that already have an RGB numpy array.

    Loads references/ on each call.
    Returns (None, {}) if no face detected or no references found.
    Returns (name_or_unknown, {label: distance}) otherwise.
    """
    refs = _load_references()
    if not refs:
        return None, {}
    return _run_match(refs, rgb)


def match(live_path: Path) -> str:
    """Return matched label (or 'unknown')."""
    refs = _load_references()
    if not refs:
        print(f"\nNo usable reference images found in: {REFERENCES_DIR}/")
        print("Add images named after the person (e.g. leo.jpg) then re-run.\n")
        sys.exit(0)

    print(f"References : {sorted(refs.keys())}")
    print(f"Live image : {live_path}")
    print()

    rgb = face_recognition.load_image_file(str(live_path))
    name, distances = _run_match(refs, rgb)
    if name is None:
        print("no face detected")
        sys.exit(0)

    print("Distances  :", "  ".join(f"{n}={d:.4f}" for n, d in distances.items()))
    print(f"Parsed name: {name}")
    return name


def match_from_camera() -> str:
    """Capture one frame from the default webcam and return matched label (or 'unknown')."""
    refs = _load_references()
    if not refs:
        print(f"\nNo usable reference images found in: {REFERENCES_DIR}/")
        print("Add images named after the person (e.g. leo.jpg) then re-run.\n")
        sys.exit(0)

    print(f"References : {sorted(refs.keys())}")
    print(f"Live image : camera (device 0)")
    print()

    cap = cv2.VideoCapture(0)
    for _ in range(10):
        cap.read()
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("ERROR: could not read frame from camera")
        sys.exit(1)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    name, distances = _run_match(refs, rgb)
    if name is None:
        print("no face detected")
        sys.exit(0)

    print("Distances  :", "  ".join(f"{n}={d:.4f}" for n, d in distances.items()))
    print(f"Parsed name: {name}")
    return name


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--camera":
        match_from_camera()
    elif len(sys.argv) == 2:
        live = Path(sys.argv[1])
        if not live.exists():
            print(f"ERROR: file not found: {live}")
            sys.exit(1)
        match(live)
    else:
        print("Usage: python3 -m app.vision_match <live-image>")
        print("       python3 -m app.vision_match --camera")
        sys.exit(1)
