"""
Dilara: Gemma analiz motoru.

Girdi: su ana kadarki gorusme transkripti (metin).
Cikti: schema/report_schema.json ile birebir eslesen bir dict.

orchestration/ bu fonksiyonu her turda cagirir:
  - turn_type == "in_progress" ise next_question'i ElevenLabs'a gonderip seslendirir.
  - turn_type == "completed" ise report'u frontend/data/ altina yazip Beyza'nin
    ekranini besler.

Ollama ile yerel Gemma modeline baglanmak icin dogrudan
http://localhost:11434/api/generate HTTP API'si kullanilir.
Ollama acik degilse ya da hata olusursa sistem mock veriye dusuyor, hic cormuyor.
"""

import json
import os
import urllib.request
import urllib.error

REPORT_SCHEMA_KEYS = ["memnuniyet_skoru", "churn_nedeni", "alinti", "aksiyon_onerisi"]

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

SYSTEM_PROMPT = """Sen bir musteri gorusmesi analiz asistanisin.
Gorusme metnini analiz et ve asagidaki JSON formatinda yanit ver:
{
  "turn_type": "completed",
  "next_question": null,
  "report": {
    "memnuniyet_skoru": <0-10 arasi sayi>,
    "churn_nedeni": "<kisa neden>",
    "alinti": "<musteriden dogrudan bir cumle>",
    "aksiyon_onerisi": "<sirket icin somut oneri>"
  }
}
Sadece JSON don, baska aciklama ekleme."""


def analyze_turn(transcript_so_far: str) -> dict:
    """Ollama/Gemma ile transkripti analiz eder.

    Ollama acik degilse veya herhangi bir hata olursa mock veriye geri doner.
    Sunum aninda hicbir kosulda program corumez.
    """
    try:
        return _call_ollama(transcript_so_far)
    except Exception as e:
        print(f"[Gemma] Ollama erisilemedi ({e}), mock veriye donuluyor...")
        return _mock_completed()


def _call_ollama(transcript: str) -> dict:
    """Ollama HTTP API'sine istek gonderir, JSON cevabi parse eder."""
    prompt = f"{SYSTEM_PROMPT}\n\nGorusme transkripti:\n{transcript}"
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }).encode("utf-8")

    url = f"{OLLAMA_HOST}/api/generate"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    # Ollama yaniti {"response": "...JSON string..."} seklinde geliyor
    response_text = raw.get("response", "")
    result = json.loads(response_text)

    # Beklenen alanlari dogrula
    if "turn_type" not in result:
        raise ValueError("Ollama yaniti beklenen formatta degil")

    return result


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
    # Dogrudan calistirinca once Ollama'yi, olmazsa mock'u gosterir
    result = analyze_turn("Musterinin sesi burada olacak.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
