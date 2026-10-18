"""
Melike: Twilio + Whisper + ElevenLabs orkestrasyonu.

Akis (turn-based, gercek zamanli streaming DEGIL):
  1. Twilio musteriyi arar/musteriden gelen aramayi karsilar.
  2. TwiML <Record> ile musterinin cevabini kaydeder, bu webhook'u tekrar cagirir.
  3. Kaydedilen ses -> Whisper ile metne cevrilir.
  4. Metin -> gemma.analyze.analyze_turn() -> bir sonraki soru ya da rapor.
  5. next_question varsa -> ElevenLabs TTS -> <Play> ile calinir, dongu devam eder.
  6. report varsa -> frontend/data/latest_report.json'a yazilir, arama kapanir.

DEMO MODU (TWILIO_FALLBACK=true veya hicbir Twilio env yoksa):
  - /api/simulate-call endpoint'i gercek bir transkripti analiz edip raporu yazar.
  - Telefon/ngrok gerektirmez, sunum icin idealdir.

Kurulum:
  pip install flask requests faster-whisper
  python orchestration/app.py
  -> http://localhost:5000
"""

import json
import os
import tempfile
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import analyze_turn, _mock_completed  # noqa: E402

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from flask import Flask, request, Response, send_from_directory, jsonify
except ImportError:
    raise RuntimeError("Flask yuklu degil. Calistir: pip install flask")

app = Flask(__name__, static_folder=None)

# Proje kok dizini
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
REPORT_OUT_PATH = FRONTEND_DIR / "data" / "latest_report.json"
AUDIO_OUT_DIR = Path(__file__).resolve().parent / "out"
AUDIO_OUT_DIR.mkdir(exist_ok=True)

# Twilio modu mu, yoksa demo modu mu?
TWILIO_FALLBACK = (
    os.environ.get("TWILIO_FALLBACK", "").lower() in ("1", "true", "yes")
    or not os.environ.get("TWILIO_ACCOUNT_SID")
)

# =========================================================
# FRONTEND SUNUMU (tek porttan hem API hem HTML)
# =========================================================

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_frontend(filename):
    """login.html, report.html, register.html ve data/ klasorunu sunar."""
    target = FRONTEND_DIR / filename
    if target.is_file():
        return send_from_directory(FRONTEND_DIR, filename)
    return f"Dosya bulunamadi: {filename}", 404


# =========================================================
# DEMO / SIMULATE ENDPOINT (Twilio olmadan)
# =========================================================

# Sabit demo transkriptleri - her cagirda farkli bir senaryo donebilir
DEMO_TRANSCRIPTS = [
    "Entegrasyon ucuncu haftaya geldi, API dokumantasyonu yetersiz, "
    "ekibimiz manuel veri girisine geri donduk. Cok memnun degiliz.",

    "Webhooklar duzgun calismiyor, her gun en az uc-dort hata aliyoruz. "
    "Destek ekibiniz gec donuyor. Fiyat artisi da cabasi oldu, ayrilmak uzere.",

    "Hizmetten genel olarak memnunuz ama mobil entegrasyon hala beta asama. "
    "Rakiplerde bu ozellik cok daha olgun, dusunmemiz gerekiyor.",
]

_demo_cursor = 0


@app.post("/api/simulate-call")
def simulate_call():
    """
    Telefon olmadan gercek zinciri (Gemma analiz -> JSON rapor) calistirir.
    Frontend'deki 'Aramayı Simüle Et' butonu bu endpoint'i cagirir.
    Yanit: { "status": "ok", "report": {...} }
    """
    global _demo_cursor

    # Istekte ozel transkript gonderilmisse onu kullan
    body = request.get_json(silent=True) or {}
    transcript = body.get("transcript") or DEMO_TRANSCRIPTS[_demo_cursor % len(DEMO_TRANSCRIPTS)]
    _demo_cursor += 1

    result = analyze_turn(transcript)

    if result.get("turn_type") == "completed" and result.get("report"):
        report = result["report"]
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return jsonify({"status": "ok", "report": report})
    else:
        # Ollama in_progress ya da beklenmedik yanit -> mock'a don
        fallback = _mock_completed()["report"]
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(
            json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return jsonify({"status": "ok (fallback)", "report": fallback})


# =========================================================
# WHISPER (sadece Twilio modu icin)
# =========================================================

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            model_size = os.environ.get("WHISPER_MODEL", "base")
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except ImportError:
            return None
    return _whisper_model


def transcribe(recording_url: str) -> str:
    """Twilio kaydini indirip yerel Whisper ile metne cevirir."""
    if not HAS_REQUESTS:
        return "requests paketi yuklu degil, transkript atlaniyor."

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

    resp = requests.get(f"{recording_url}.wav", auth=(account_sid, auth_token))
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(resp.content)
        wav_path = f.name

    model = _get_whisper_model()
    if model is None:
        return "Whisper yuklu degil, transkript atlaniyor."

    segments, _info = model.transcribe(wav_path, language="tr")
    return " ".join(segment.text.strip() for segment in segments)


# =========================================================
# ELEVENLABS TTS (hata toleransli)
# =========================================================

def synthesize(text: str) -> str:
    """ElevenLabs TTS: metni sese cevirir. API yoksa mock mp3 dondurur."""
    try:
        from elevenlabs.client import ElevenLabs
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY tanimli degil")

        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            voice_id=voice_id, text=text, model_id="eleven_multilingual_v2"
        )
        filename = f"turn_{abs(hash(text))}.mp3"
        out_path = AUDIO_OUT_DIR / filename
        with open(out_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        return filename
    except Exception as e:
        print(f"[ElevenLabs] {e} — mock mp3 olusturuluyor.")
        filename = f"mock_{abs(hash(text))}.mp3"
        out_path = AUDIO_OUT_DIR / filename
        out_path.write_bytes(b"//ID3 MOCK AUDIO STREAM")
        return filename


@app.get("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_OUT_DIR, filename)


# =========================================================
# TWİLİO WEBHOOK (sadece Twilio modu)
# =========================================================

@app.post("/voice")
def voice_webhook():
    """Twilio bu endpoint'i her tur icin cagirir."""
    recording_url = request.form.get("RecordingUrl")

    if not recording_url:
        twiml = "<Response><Record maxLength=\"15\" action=\"/voice\" /></Response>"
        return Response(twiml, mimetype="text/xml")

    transcript_chunk = transcribe(recording_url)
    result = analyze_turn(transcript_chunk)

    if result.get("turn_type") == "completed":
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(
            json.dumps(result["report"], ensure_ascii=False, indent=2)
        )
        twiml = "<Response><Say language=\"tr-TR\">Tesekkurler, gorusmeniz tamamlandi.</Say></Response>"
        return Response(twiml, mimetype="text/xml")

    audio_filename = synthesize(result["next_question"])
    audio_url = f"{request.url_root}audio/{audio_filename}"
    twiml = (
        f"<Response>"
        f"<Play>{audio_url}</Play>"
        f"<Record maxLength=\"15\" action=\"/voice\" />"
        f"</Response>"
    )
    return Response(twiml, mimetype="text/xml")


# =========================================================
# BASLANGIC
# =========================================================

if __name__ == "__main__":
    mode = "DEMO (Twilio devre disi)" if TWILIO_FALLBACK else "Twilio AKTIF"
    print(f"[Yanki] Sunucu basliyor... Mod: {mode}")
    print(f"[Yanki] Adres: http://localhost:5000")
    print(f"[Yanki] Simulate endpoint: POST http://localhost:5000/api/simulate-call")
    app.run(host="0.0.0.0", port=5000, debug=True)
