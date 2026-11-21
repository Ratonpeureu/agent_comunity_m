# services/social/social_music.py
import hashlib
import random
import wave
from pathlib import Path

import numpy as np

from agent.services.social import social_assets as assets
from agent.services.social.social_config import UPLOAD_DIR

SR = 44100
MUSIC_DIR = assets.BRANDING_DIR / "music"
CACHE = Path(UPLOAD_DIR) / "_music"
EXT = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}
MOODS = {
    "energique": {"bpm": 126, "prog": [(57, "m"), (53, "M"), (60, "M"), (55, "M")], "kick": True, "hat": True},
    "inspirant": {"bpm": 108, "prog": [(60, "M"), (55, "M"), (57, "m"), (53, "M")], "kick": True, "hat": True},
    "corporate": {"bpm": 100, "prog": [(62, "M"), (57, "m"), (59, "m"), (55, "M")], "kick": True, "hat": False},
    "calme": {"bpm": 84, "prog": [(57, "m"), (53, "M"), (48, "M"), (55, "M")], "kick": False, "hat": False},
}


def _hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _tone(freq, dur, decay, harm=(1.0, .35, .12)):
    t = np.arange(int(dur * SR)) / SR
    sig = sum(a * np.sin(2 * np.pi * freq * (i + 1) * t) for i, a in enumerate(harm))
    return (sig * np.exp(-t * decay)).astype(np.float32)


def synth(duration: float, mood: str, seed: int) -> np.ndarray:
    cfg = MOODS.get(mood, MOODS["energique"])
    beat = 60.0 / cfg["bpm"]
    n = int((duration + 1.5) * SR)
    out = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(seed)

    def add(sig, t0, gain=1.0, pan=0.0):
        i = int(t0 * SR)
        if i >= n:
            return
        seg = sig[: n - i] * gain
        out[i:i + len(seg), 0] += seg * (1 - max(0, pan))
        out[i:i + len(seg), 1] += seg * (1 + min(0, pan))

    tk = np.arange(int(.28 * SR)) / SR
    kick = (np.sin(2 * np.pi * np.cumsum(45 + 95 * np.exp(-tk * 30)) / SR) * np.exp(-tk * 9)).astype(np.float32)
    th = np.arange(int(.07 * SR)) / SR
    bar = 4 * beat
    for b in range(int((duration + 1.5) / bar) + 2):
        root, q = cfg["prog"][b % 4]
        chord = [root, root + (3 if q == "m" else 4), root + 7]
        t0 = b * bar
        pad = sum(_tone(_hz(c + 12) * (1 + d), bar * 1.05, 1.1, (1.0, .2)) for c in chord for d in (-.003, .003))
        env = np.minimum(1, np.arange(len(pad)) / (SR * .35)).astype(np.float32)
        add(pad * env, t0, .06)
        for step in range(8):
            ts = t0 + step * beat / 2
            add(_tone(_hz(root - 12), beat * .48, 6.5, (1.0, .4)), ts, .30)
            add(_tone(_hz(chord[[0, 1, 2, 1][step % 4]] + 12 + (12 if step % 2 else 0)), .32, 9.0), ts, .11,
                .35 if step % 2 else -.35)
            if cfg["kick"] and step % 2 == 0:
                add(kick, ts, .55)
            if cfg["hat"] and step % 2 == 1:
                add(np.diff(rng.normal(size=len(th)), prepend=0).astype(np.float32) * np.exp(-th * 75), ts, .16, .2)
    peak = float(np.abs(out).max()) or 1.0
    out = np.tanh(out / peak * 1.35) / np.tanh(1.35) * .88
    f = int(.5 * SR)
    out[:f] *= np.linspace(0, 1, f)[:, None]
    out[-f:] *= np.linspace(1, 0, f)[:, None]
    return out


def make_track(duration: float, mood: str = "energique", seed: int = 0) -> Path:
    mood = mood if mood in MOODS else "energique"
    for d in (MUSIC_DIR / mood, MUSIC_DIR):
        if d.exists():
            files = sorted(p for p in d.iterdir() if p.suffix.lower() in EXT)
            if files:
                return random.Random(seed).choice(files)
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{mood}-{seed}-{int(duration)}".encode()).hexdigest()[:12]
    path = CACHE / f"{mood}_{key}.wav"
    if not path.exists():
        data = (synth(duration, mood, seed) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(data.tobytes())
    return path