"""
Melike: Twilio + Whisper + ElevenLabs orkestrasyonu.

Akis (turn-based, gercek zamanli streaming DEGIL):
  1. Twilio musteriyi arar/musteriden gelen aramayi karsilar.
  2. TwiML <Record> ile musterinin cevabini kaydeder, bu webhook'u tekrar cagirir.
  3. Kaydedilen ses -> Whisper ile metne cevrilir.
  4. Metin -> gemma.analyze.analyze_turn() -> bir sonraki soru ya da rapor.
  5. next_question varsa -> ElevenLabs TTS -> <Play> ile calinir, dongu devam eder.
  6. report varsa -> frontend/data/latest_report.json'a yazilir, arama kapanir.

45 dk kontrol noktasinda uctan uca calismiyorsa: TWILIO_FALLBACK=true yapip
RECORDED_AUDIO_PATH altindaki hazir ses dosyasiyla ayni zinciri (Whisper->
Gemma->ElevenLabs) calistir, telefon hattini devre disi birak.
"""

import json
import os
from pathlib import Path

from flask import Flask, request, Response

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import analyze_turn  # noqa: E402

app = Flask(__name__)

REPORT_OUT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "data" / "latest_report.json"


def transcribe(audio_path: str) -> str:
    """TODO(Melike): Whisper cagrisi (lokal whisper.cpp ya da openai whisper)."""
    raise NotImplementedError


def synthesize(text: str) -> str:
    """TODO(Melike): ElevenLabs TTS cagrisi, donen ses dosyasinin yolunu dondur."""
    raise NotImplementedError


@app.post("/voice")
def voice_webhook():
    """Twilio bu endpoint'i her tur icin cagirir."""
    recording_url = request.form.get("RecordingUrl")

    if not recording_url:
        # Ilk cagri: sadece kayit baslat.
        twiml = """<Response><Record maxLength="15" action="/voice" /></Response>"""
        return Response(twiml, mimetype="text/xml")

    transcript_chunk = transcribe(recording_url)
    result = analyze_turn(transcript_chunk)

    if result["turn_type"] == "completed":
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(json.dumps(result["report"], ensure_ascii=False, indent=2))
        twiml = """<Response><Say language="tr-TR">Tesekkurler, gorusmeniz tamamlandi.</Say></Response>"""
        return Response(twiml, mimetype="text/xml")

    audio_path = synthesize(result["next_question"])
    twiml = f"""<Response><Play>{audio_path}</Play><Record maxLength="15" action="/voice" /></Response>"""
    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
