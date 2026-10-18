"""
Melike: Faz 2 demo - mock veriyle uctan uca zincir.

Twilio/gercek arama olmadan, arama+ElevenLabs tarafinin calistigini
kanitlayan en kucuk demo:

  sabit mock transkript -> gemma.analyze (mock) -> ElevenLabs TTS -> ses dosyasi

Calistirmak icin:
  pip install -r requirements.txt
  export ELEVENLABS_API_KEY=...
  python orchestration/demo_mock.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import _mock_in_progress  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(exist_ok=True)


def synthesize(text: str, out_path: Path) -> Path:
    """ElevenLabs TTS: metni sese cevirip out_path'e yazar (dogrudan REST cagrisi)."""
    import requests

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY ortam degiskeni ayarli degil")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # Sarah - varsayilan ornek ses

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return out_path


def main():
    mock_result = _mock_in_progress()
    question = mock_result["next_question"]
    print(f"[Gemma mock] soru: {question}")

    out_path = OUT_DIR / "demo_soru.mp3"
    synthesize(question, out_path)
    print(f"[ElevenLabs] ses uretildi: {out_path}")


if __name__ == "__main__":
    main()
