"""
Melike: Faz 2 demo - mock veriyle uctan uca zincir.

Twilio/gercek arama olmadan, arama+ElevenLabs tarafinin calistigini
kanitlayan en kucuk demo:

  sabit mock transkript -> gemma.analyze (mock) -> ElevenLabs TTS -> ses dosyasi

Calistirmak icin:
  pip install elevenlabs
  export ELEVENLABS_API_KEY=...
  python orchestration/demo_mock.py
"""

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import _mock_in_progress  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(exist_ok=True)


def synthesize(text: str, out_path: Path) -> Path:
    """ElevenLabs TTS: metni sese cevirip out_path'e yazar.
    API anahtari veya paket yoksa mock ses dosyasi olusturur.
    """
    try:
        from elevenlabs.client import ElevenLabs
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            print("[Bilgi] ELEVENLABS_API_KEY tanimli degil, mock mp3 olusturuluyor...")
            out_path.write_bytes(b"//ID3 MOCK AUDIO STREAM")
            return out_path

        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        return out_path
    except ImportError:
        print("[Bilgi] elevenlabs paketi yuklu degil, mock mp3 olusturuluyor...")
        out_path.write_bytes(b"//ID3 MOCK AUDIO STREAM")
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
