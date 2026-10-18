"""
Melike: Twilio + Whisper + ElevenLabs orkestrasyonu.

Akis (turn-based, gercek zamanli streaming DEGIL):
  1. Twilio musteriyi arar/musteriden gelen aramayi karsilar.
  2. TwiML <Record> ile musterinin cevabini kaydeder, bu webhook'u tekrar cagirir.
  3. Kaydedilen ses -> Whisper ile metne cevrilir.
  4. Metin -> gemma.analyze.analyze_turn() -> bir sonraki soru ya da rapor.
  5. next_question varsa -> ElevenLabs TTS -> <Play> ile calinir, dongu devam eder.
  6. report varsa -> frontend/data/latest_report.json'a yazilir, arama kapanir.

DEMO MODU (Twilio olmadan, sunum icin):
  - /api/simulate-call endpoint'i sabit bir transkripti analiz edip raporu yazar.
  - Frontend bu sunucudan servis edilir (login -> report akisi dahil).

Kurulum:
  pip install -r requirements.txt
  python orchestration/app.py
  -> http://localhost:5000
"""

import json
import os
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request, Response, jsonify, send_from_directory
from faster_whisper import WhisperModel

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from gemma.analyze import analyze_turn, _mock_completed  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = Flask(__name__, static_folder=None)

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
REPORT_OUT_PATH = FRONTEND_DIR / "data" / "latest_report.json"
AUDIO_OUT_DIR = Path(__file__).resolve().parent / "out"
AUDIO_OUT_DIR.mkdir(exist_ok=True)


# =========================================================
# FRONTEND SUNUMU (tek porttan hem API hem HTML)
# =========================================================

@app.get("/")
def index():
    index_path = FRONTEND_DIR / "index.html"
    target = "index.html" if index_path.is_file() else "report.html"
    return send_from_directory(FRONTEND_DIR, target)


@app.get("/<path:filename>")
def serve_frontend(filename):
    """login.html, report.html, register.html ve data/ klasorunu sunar."""
    target = FRONTEND_DIR / filename
    if target.is_file():
        return send_from_directory(FRONTEND_DIR, filename)
    return f"Dosya bulunamadi: {filename}", 404


# =========================================================
# TELEFON OLMADAN DEMO: sabit transkript -> gercek zincir
# =========================================================

DEMO_TRANSCRIPTS = [
    "Entegrasyon ucuncu haftaya geldi, API dokumantasyonu yetersiz, "
    "ekibimiz manuel veri girisine geri donduk. Cok memnun degiliz.",
    "Webhooklar duzgun calismiyor, her gun en az uc-dort hata aliyoruz. "
    "Destek ekibiniz gec donuyor. Fiyat artisi da cabasi oldu, ayrilmak uzere.",
    "Hizmetten genel olarak memnunuz ama mobil entegrasyon hala beta asamada. "
    "Rakiplerde bu ozellik cok daha olgun, dusunmemiz gerekiyor.",
]
_demo_cursor = 0


@app.post("/api/analyze-and-speak")
def analyze_and_speak():
    """Transcript al -> Gemma analiz et -> in_progress ise ElevenLabs seslendir.

    Donus:
      { turn_type, next_question, audio_url (varsa), report (varsa) }
    """
    body = request.get_json(silent=True) or {}
    transcript = (body.get("transcript") or "").strip()
    if not transcript:
        return jsonify({"error": "transcript bos"}), 400

    try:
        result = analyze_turn(transcript)
    except Exception as e:
        print(f"[analyze-and-speak] analyze_turn hatasi: {e}")
        result = _mock_completed()

    response = {
        "turn_type": result.get("turn_type"),
        "next_question": result.get("next_question"),
        "report": result.get("report"),
        "audio_url": None,
    }

    # in_progress ise soruyu seslendir
    if result.get("turn_type") == "in_progress" and result.get("next_question"):
        try:
            filename = synthesize(result["next_question"])
            response["audio_url"] = f"{request.url_root}audio/{filename}"
        except Exception as e:
            print(f"[analyze-and-speak] ElevenLabs hatasi: {e}")

    # completed ise raporu kaydet ve aksiyon önerisini seslendir
    if result.get("turn_type") == "completed" and result.get("report"):
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(
            json.dumps(result["report"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Aksiyon önerisini ElevenLabs ile seslendir
        aksiyon = result["report"].get("aksiyon_onerisi", "")
        skor = result["report"].get("memnuniyet_skoru", "")
        speak_text = f"Memnuniyet skoru {skor} üzerinden {skor}. {aksiyon}"
        try:
            filename = synthesize(speak_text)
            response["audio_url"] = f"{request.url_root}audio/{filename}"
        except Exception as e:
            print(f"[analyze-and-speak] ElevenLabs completed ses hatasi: {e}")

    return jsonify(response)


@app.post("/api/simulate-call")
def simulate_call():
    """Telefon olmadan gercek zinciri (Gemma analiz -> JSON rapor) calistirir.

    analyze_turn() herhangi bir nedenle patlarsa mock'a duser, sunum
    sirasinda hicbir kosulda sistem cokmez.
    """
    global _demo_cursor
    body = request.get_json(silent=True) or {}
    transcript = body.get("transcript") or DEMO_TRANSCRIPTS[_demo_cursor % len(DEMO_TRANSCRIPTS)]
    _demo_cursor += 1

    try:
        result = analyze_turn(transcript)
    except Exception as e:
        print(f"[simulate-call] analyze_turn hatasi: {e} - mock'a dusuluyor")
        result = _mock_completed()

    report = (result.get("report") if result.get("turn_type") == "completed" else None) or _mock_completed()["report"]

    REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"status": "ok", "report": report})


# =========================================================
# WHISPER (sadece Twilio modu icin)
# =========================================================

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


# =========================================================
# ELEVENLABS TTS (gercek REST cagrisi, hata toleransli)
# =========================================================

def synthesize(text: str) -> str:
    """ElevenLabs TTS: metni sese cevirir, calinabilir dosya adini dondurur.

    API key yoksa ya da cagri basarisiz olursa, sunum sirasinda sistem
    cokmesin diye bos bir mock mp3'e duser.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # Sarah

    try:
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY tanimli degil")

        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
        )
        resp.raise_for_status()

        filename = f"turn_{abs(hash(text))}.mp3"
        (AUDIO_OUT_DIR / filename).write_bytes(resp.content)
        return filename
    except Exception as e:
        print(f"[ElevenLabs] {e} - mock mp3 olusturuluyor")
        filename = f"mock_{abs(hash(text))}.mp3"
        (AUDIO_OUT_DIR / filename).write_bytes(b"//ID3 MOCK AUDIO STREAM")
        return filename


@app.get("/audio/<filename>")
def serve_audio(filename):
    """Twilio <Play>'in indirebilmesi icin uretilen sesi disa acar."""
    return send_from_directory(AUDIO_OUT_DIR, filename)


# =========================================================
# TWILIO WEBHOOK (sadece gercek telefon modu)
# =========================================================

@app.post("/voice")
def voice_webhook():
    """Twilio bu endpoint'i her tur icin cagirir."""
    recording_url = request.form.get("RecordingUrl")

    if not recording_url:
        twiml = """<Response><Record maxLength="15" action="/voice" /></Response>"""
        return Response(twiml, mimetype="text/xml")

    transcript_chunk = transcribe(recording_url)
    result = analyze_turn(transcript_chunk)

    if result.get("turn_type") == "completed":
        REPORT_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT_PATH.write_text(json.dumps(result["report"], ensure_ascii=False, indent=2))
        twiml = """<Response><Say language="tr-TR">Tesekkurler, gorusmeniz tamamlandi.</Say></Response>"""
        return Response(twiml, mimetype="text/xml")

    audio_filename = synthesize(result["next_question"])
    audio_url = f"{request.url_root}audio/{audio_filename}"
    twiml = f"""<Response><Play>{audio_url}</Play><Record maxLength="15" action="/voice" /></Response>"""
    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    print("[Yanki] Sunucu basliyor -> http://localhost:5000")
    print("[Yanki] Demo endpoint: POST http://localhost:5000/api/simulate-call")
    app.run(host="0.0.0.0", port=5000, debug=True)
