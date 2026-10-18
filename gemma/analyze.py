"""
Dilara: Gemma analiz motoru.

Girdi: su ana kadarki gorusme transkripti (metin).
Cikti: schema/report_schema.json ile birebir eslesen bir dict.

orchestration/ bu fonksiyonu her turda cagirir:
  - turn_type == "in_progress" ise next_question'i ElevenLabs'a gonderip seslendirir.
  - turn_type == "completed" ise report'u frontend/data/ altina yazip Beyza'nin
    ekranini besler.

Ollama ile yerel Gemma modeline baglanmak icin dogrudan
http://localhost:11434/api/generate kullanilir.
"""

import json
import re

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"  # `ollama list` ciktisindaki model adiyla eslessin

REPORT_SCHEMA_KEYS = ["memnuniyet_skoru", "churn_nedeni", "alinti", "aksiyon_onerisi"]

_PROMPT_TEMPLATE = """Sen bir musteri kayip (churn) gorusmesi analiz asistanisin.

Transkript:
{transcript}

KARAR KURALI:
- Transkriptte memnuniyetsizlik, sikayet, ayrilma niyeti veya somut bir sorun varsa -> HEMEN "completed" dondur, ek soru sorma.
- Transkript tamamen bos veya "merhaba" gibi anlamsizsa -> "in_progress" dondur.

Neredeyse her zaman "completed" secmelisin. Gercek bir gorusmede musteri zaten konusmustur.

SADECE asagidaki JSON formatlarindan BIRINI dondur, baska hicbir aciklama veya metin ekleme:

Ek bilgi gerekiyorsa (cok nadir):
{{"turn_type": "in_progress", "next_question": "buraya tek bir kisa soru yaz"}}

Analiz icin yeterli bilgi varsa (neredeyse her zaman bu):
{{"turn_type": "completed", "next_question": null, "report": {{"memnuniyet_skoru": <0-10 arasi sayi, dusuk=mutsuz>, "churn_nedeni": "tek cumlelik somut neden", "alinti": "musterinin sozlerinden dogrudan bir cumle", "aksiyon_onerisi": "ekip icin somut bir aksiyon"}}}}
"""


def _call_ollama(prompt: str) -> str:
    """Ollama'ya istek gonderir, modelin urettigi metni dondurur."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["response"]


def _extract_json(text: str) -> dict:
    """Model ciktisinden JSON nesnesi cikarir."""
    # Bazen model ```json ... ``` bloku icinde dondurur
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Ya da duz JSON
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSON bulunamadi: {text[:200]}")


def _validate_and_fix(data: dict) -> dict:
    """Schemanin gerektirdigi alanlari kontrol eder, eksikleri duzeltir."""
    turn_type = data.get("turn_type")

    if turn_type == "in_progress":
        if not data.get("next_question"):
            data["next_question"] = "Yasadiginiz sorunu biraz daha anlatabilir misiniz?"
        return {"turn_type": "in_progress", "next_question": data["next_question"]}

    if turn_type == "completed":
        report = data.get("report") or {}
        # Sayisal skoru zorunlu kisitlara sok
        score = report.get("memnuniyet_skoru", 5)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 5.0
        score = max(0.0, min(10.0, score))
        return {
            "turn_type": "completed",
            "next_question": None,
            "report": {
                "memnuniyet_skoru": score,
                "churn_nedeni": report.get("churn_nedeni", "Belirtilmedi"),
                "alinti": report.get("alinti", ""),
                "aksiyon_onerisi": report.get("aksiyon_onerisi", "Takip gerekli"),
            },
        }

    # Bilinmeyen turn_type — fallback
    raise ValueError(f"Gecersiz turn_type: {turn_type!r}")


def analyze_turn(transcript_so_far: str) -> dict:
    """Transkripti Ollama/Gemma'ya gonderir, schema'ya uyan dict dondurur.

    Ollama erisilemezse veya parse hatasi olursa in_progress fallback'e duser.
    """
    prompt = _PROMPT_TEMPLATE.format(transcript=transcript_so_far.strip())
    try:
        raw = _call_ollama(prompt)
        data = _extract_json(raw)
        return _validate_and_fix(data)
    except Exception as exc:
        print(f"[analyze_turn] hata: {exc} — fallback in_progress donduruluyor")
        return _mock_in_progress()


def _mock_in_progress() -> dict:
    return {"turn_type": "in_progress", "next_question": "Entegrasyon surecinde yasadiginiz en buyuk zorluk neydi?"}


def _mock_completed() -> dict:
    return {
        "turn_type": "completed",
        "next_question": None,
        "report": {
            "memnuniyet_skoru": 6.8,
            "churn_nedeni": "Entegrasyon / API sorunlari",
            "alinti": "Entegrasyon uc haftadir tamamlanmadi, ekibimiz manuel veri girisine geri dondu.",
            "aksiyon_onerisi": "Kurumsal musteriler icin oncelikli entegrasyon SLA'si tanimlayin.",
        },
    }


if __name__ == "__main__":
    # --- Kisa transkript: gorusme devam ediyor ---
    short_transcript = "Musteri: Aboneliginizi neden iptal etmek istediniz? Musteri: Fiyatlar cok yuksek."
    print("=== Kisa transkript (in_progress bekleniyor) ===")
    result1 = analyze_turn(short_transcript)
    print(json.dumps(result1, ensure_ascii=False, indent=2))

    # --- Uzun transkript: gorusme bitti ---
    long_transcript = (
        "Temsilci: Aboneliginizi neden iptal etmek istediniz?\n"
        "Musteri: Entegrasyon uc haftadir tamamlanmadi, ekibimiz manuel veri girisine geri dondu.\n"
        "Temsilci: Bu surec sizi ne kadar etkiledi?\n"
        "Musteri: Cok olumsuz etkilendi, artik bu urunu kullanmak istemiyorum. Gorusmemiz bitti."
    )
    print("\n=== Uzun transkript (completed bekleniyor) ===")
    result2 = analyze_turn(long_transcript)
    print(json.dumps(result2, ensure_ascii=False, indent=2))
