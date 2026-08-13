"""
Interactive STT (Speech-To-Text) Testing & Comparison Tool for Raphael.

Compare transcription accuracy and speed between:
  1. moonshine/base (Useful Sensors local STT model)
  2. Groq whisper-large-v3 (cloud API via settings.toml)

Usage:
    python test_stt.py
"""

import os
import warnings
warnings.filterwarnings("ignore")

os.environ["KERAS_BACKEND"] = "torch"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

import logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.utils._deprecation").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.file_download").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

import sys
import time
import wave
import io
from pathlib import Path

# Ensure project root is on sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import numpy as np
import sounddevice as sd
import requests

LAST_RECORDING_PATH = root_dir / "last_recording.wav"

# Try importing moonshine
try:
    import moonshine
    HAS_MOONSHINE = True
except Exception as e:
    HAS_MOONSHINE = False
    MOONSHINE_ERR = str(e)


def load_groq_config():
    """Load Groq endpoint settings from ~/.raphael/settings.toml."""
    try:
        import tomllib
        settings_path = Path.home() / ".raphael" / "settings.toml"
        if not settings_path.exists():
            return None
        with open(settings_path, "rb") as f:
            data = tomllib.load(f)
        for ep in data.get("endpoints", []):
            if ep.get("name") == "Groq" and ep.get("api_key") and ep.get("stt_model"):
                return {
                    "base_url": ep.get("base_url", "https://api.groq.com/openai/v1"),
                    "api_key": ep.get("api_key"),
                    "model": ep.get("stt_model", "whisper-large-v3"),
                }
    except Exception as e:
        print(f"[WARN] Failed to load Groq config: {e}")
    return None


def save_audio_wav(audio_float32: np.ndarray, filepath: Path, sample_rate=16000):
    """Save float32 audio array to 16kHz mono WAV file."""
    pcm16 = (np.clip(audio_float32, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    print(f"💾 Saved audio recording to '{filepath.name}' ({len(audio_float32)/sample_rate:.2f}s)")


def load_audio_wav(filepath: Path) -> np.ndarray:
    """Load float32 audio array from a WAV file."""
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return np.array([], dtype=np.float32)

    with wave.open(str(filepath), "rb") as wf:
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    pcm16 = np.frombuffer(frames, dtype=np.int16)
    if n_channels > 1:
        pcm16 = pcm16[::n_channels]
    audio_float32 = pcm16.astype(np.float32) / 32768.0

    if framerate != 16000 and len(audio_float32) > 0:
        new_len = int(len(audio_float32) * 16000 / framerate)
        audio_float32 = np.interp(
            np.linspace(0, len(audio_float32), new_len, endpoint=False),
            np.arange(len(audio_float32)),
            audio_float32,
        ).astype(np.float32)

    return audio_float32


def record_audio(sample_rate=16000) -> np.ndarray:
    """Record audio from mic until ENTER is pressed, and save to last_recording.wav."""
    print("\n" + "=" * 60)
    print("🎤 Press ENTER to START recording...")
    input()
    print("🔴 RECORDING... Speak now! Press ENTER to STOP recording.")

    frames = []

    def callback(indata, frame_count, time_info, status):
        if status:
            print(f"[Audio Warning] {status}", file=sys.stderr)
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        callback=callback,
    )

    with stream:
        input()

    print("⏹️ RECORDING STOPPED.")

    if not frames:
        return np.array([], dtype=np.float32)

    audio = np.concatenate(frames, axis=0).flatten()
    duration_sec = len(audio) / sample_rate
    print(f"📊 Captured {duration_sec:.2f} seconds of audio.")
    save_audio_wav(audio, LAST_RECORDING_PATH, sample_rate=sample_rate)
    return audio


def transcribe_moonshine(audio_float32: np.ndarray, model_name: str = "moonshine/base") -> tuple[str, float]:
    """Transcribe using local Moonshine model."""
    if not HAS_MOONSHINE:
        return f"[ERROR: moonshine import failed - {MOONSHINE_ERR}]", 0.0

    t0 = time.time()
    audio_2d = np.atleast_2d(audio_float32)
    try:
        results = moonshine.transcribe(audio_2d, model_name)
        duration_ms = (time.time() - t0) * 1000
        if isinstance(results, list):
            text = " ".join([r.strip() if isinstance(r, str) else str(r) for r in results]).strip()
        else:
            text = str(results).strip()
        return text, duration_ms
    except Exception as e:
        return f"[ERROR: {e}]", (time.time() - t0) * 1000


def transcribe_groq(audio_float32: np.ndarray, groq_cfg: dict, sample_rate=16000) -> tuple[str, float]:
    """Transcribe using Groq Cloud STT API (whisper-large-v3)."""
    if not groq_cfg:
        return "[ERROR: Groq endpoint not configured in settings.toml]", 0.0

    t0 = time.time()
    pcm16 = (np.clip(audio_float32, -1.0, 1.0) * 32767).astype(np.int16)
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    wav_bytes = wav_io.getvalue()

    url = f"{groq_cfg['base_url'].rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {groq_cfg['api_key']}"}
    files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
    data = {"model": groq_cfg["model"]}

    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=15)
        duration_ms = (time.time() - t0) * 1000
        if resp.status_code == 200:
            result_json = resp.json()
            return result_json.get("text", "").strip(), duration_ms
        else:
            return f"[API Error {resp.status_code}: {resp.text[:200]}]", duration_ms
    except Exception as e:
        return f"[ERROR: {e}]", (time.time() - t0) * 1000


def run_all_backends(audio: np.ndarray, groq_cfg: dict):
    """Run audio clip through Moonshine Base and Groq Cloud."""
    print("\n🔄 Running transcriptions (Moonshine Base vs Groq Cloud)...\n")

    # 1. Moonshine Base
    print("⏳ Transcribing with moonshine/base...")
    txt_m_base, time_m_base = transcribe_moonshine(audio, "moonshine/base")

    # 2. Groq Whisper Large v3
    txt_groq, time_groq = "[Skipped]", 0.0
    if groq_cfg:
        print(f"⏳ Transcribing with Groq Cloud ({groq_cfg['model']})...")
        txt_groq, time_groq = transcribe_groq(audio, groq_cfg)

    print("\n" + "═" * 75)
    print("                      RESULTS COMPARISON                       ")
    print("═" * 75)
    print(f"📌 [Moonshine / Base]    (Local, {time_m_base:.0f} ms):")
    print(f"   ➜ \"{txt_m_base}\"")
    print("-" * 75)
    print(f"📌 [Groq Cloud Whisper]  (Cloud, {time_groq:.0f} ms):")
    print(f"   ➜ \"{txt_groq}\"")
    print("═" * 75)


def run_comparison():
    groq_cfg = load_groq_config()
    print("\n" + "=" * 65)
    print("     RAPHAEL STT COMPARISON: MOONSHINE BASE vs GROQ CLOUD       ")
    print("=" * 65)
    print(f"Moonshine Base status : {'AVAILABLE' if HAS_MOONSHINE else 'UNAVAILABLE'}")
    print(f"Groq Cloud STT status : {'AVAILABLE (' + groq_cfg['model'] + ')' if groq_cfg else 'NOT CONFIGURED'}")
    print(f"Last Recording File   : {LAST_RECORDING_PATH.name} ({'EXISTS' if LAST_RECORDING_PATH.exists() else 'NONE'})")

    while True:
        print("\nChoose an option:")
        print("  1. Record NEW speech & Compare (Moonshine Base vs Groq Cloud)")
        print("  2. Re-test LAST saved recording ('last_recording.wav')")
        print("  3. Load & test custom WAV file")
        print("  4. Test Moonshine Base only")
        print("  5. Exit")

        choice = input("\nEnter choice (1-5): ").strip()

        if choice == "5" or choice.lower() == "exit":
            print("Exiting STT Tester.")
            break

        if choice == "1":
            audio = record_audio()
            if len(audio) < 1600:
                print("⚠️ Audio too short or silent. Please try again.")
                continue
            run_all_backends(audio, groq_cfg)

        elif choice == "2":
            if not LAST_RECORDING_PATH.exists():
                print("⚠️ No saved recording found ('last_recording.wav'). Record audio first with option 1.")
                continue
            print(f"📂 Loading '{LAST_RECORDING_PATH.name}'...")
            audio = load_audio_wav(LAST_RECORDING_PATH)
            if len(audio) < 1600:
                print("⚠️ Loaded audio is invalid or silent.")
                continue
            run_all_backends(audio, groq_cfg)

        elif choice == "3":
            wav_path_str = input("Enter path to WAV file: ").strip().strip('"')
            path = Path(wav_path_str)
            audio = load_audio_wav(path)
            if len(audio) < 1600:
                continue
            run_all_backends(audio, groq_cfg)

        elif choice == "4":
            use_last = False
            if LAST_RECORDING_PATH.exists():
                ans = input("Use last recorded audio ('last_recording.wav')? (y/n): ").strip().lower()
                if ans == 'y':
                    use_last = True

            audio = load_audio_wav(LAST_RECORDING_PATH) if use_last else record_audio()
            if len(audio) < 1600:
                continue

            txt, t_ms = transcribe_moonshine(audio, "moonshine/base")
            print(f"\n📌 [Moonshine / Base] ({t_ms:.0f} ms):\n➜ \"{txt}\"")


if __name__ == "__main__":
    run_comparison()
