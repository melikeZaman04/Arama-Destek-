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
import tempfile
from pathlib import Path

import requests
from flask import Flask, request, Response
from faster_whisper import WhisperModel

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import analyze_turn  # noqa: E402

app = Flask(__name__)

REPORT_OUT_PATH = Path(__file__).resolve().parent.parent / "frontend" / "data" / "latest_report.json"
AUDIO_OUT_DIR = Path(__file__).resolve().parent / "out"
AUDIO_OUT_DIR.mkdir(exist_ok=True)

# Model bir kez yuklenir (ilk cagrida indirir + yukler, ~1-2 dk surebilir).
# "base" hiz icin secildi; dogruluk yetersiz kalirsa WHISPER_MODEL=small ile
# degistirilebilir.
_whisper_model = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        model_size = os.environ.get("WHISPER_MODEL", "base")
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe(recording_url: str) -> str:
    """Twilio kaydini indirip yerel Whisper ile metne cevirir. API key gerekmez."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

    resp = requests.get(f"{recording_url}.wav", auth=(account_sid, auth_token))
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(resp.content)
        wav_path = f.name

    model = _get_whisper_model()
    segments, _info = model.transcribe(wav_path, language="tr")
    return " ".join(segment.text.strip() for segment in segments)


def synthesize(text: str) -> str:
    """ElevenLabs TTS: metni sese cevirir, calinabilir dosya yolunu dondurur."""
    from elevenlabs.client import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY ayarli degil (.env dosyasina ekleyin)")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(voice_id=voice_id, text=text, model_id="eleven_multilingual_v2")

    filename = f"turn_{abs(hash(text))}.mp3"
    out_path = AUDIO_OUT_DIR / filename
    with open(out_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    return filename


@app.get("/audio/<filename>")
def serve_audio(filename):
    """Twilio <Play>'in indirebilmesi icin uretilen sesi disa acar."""
    from flask import send_from_directory

    return send_from_directory(AUDIO_OUT_DIR, filename)


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

    audio_filename = synthesize(result["next_question"])
    audio_url = f"{request.url_root}audio/{audio_filename}"
    twiml = f"""<Response><Play>{audio_url}</Play><Record maxLength="15" action="/voice" /></Response>"""
    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
