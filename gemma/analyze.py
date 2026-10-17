"""
Dilara: Gemma analiz motoru.

Girdi: su ana kadarki gorusme transkripti (metin).
Cikti: schema/report_schema.json ile birebir eslesen bir dict.

orchestration/ bu fonksiyonu her turda cagirir:
  - turn_type == "in_progress" ise next_question'i ElevenLabs'a gonderip seslendirir.
  - turn_type == "completed" ise report'u frontend/data/ altina yazip Beyza'nin
    ekranini besler.

Ollama ile yerel Gemma modeline baglanmak icin `ollama` python paketi veya
dogrudan http://localhost:11434/api/generate kullanilabilir.
"""

import json

REPORT_SCHEMA_KEYS = ["memnuniyet_skoru", "churn_nedeni", "alinti", "aksiyon_onerisi"]

SYSTEM_PROMPT = """Sen bir musteri gorusmesi analiz asistanisin. Gorusme devam
ediyorsa bir sonraki soruyu uret. Gorusme bittiyse sadece su alanlari iceren
JSON uret: memnuniyet_skoru (0-10), churn_nedeni, alinti, aksiyon_onerisi."""


def analyze_turn(transcript_so_far: str) -> dict:
    """TODO(Dilara): Ollama/Gemma cagrisini burada yap.

    Su an sabit bir ornek donduruyor; gercek entegrasyon oncesi
    orchestration ve frontend bu sozlesmeyle test edebilsin diye.
    """
    raise NotImplementedError("Ollama/Gemma cagrisini buraya ekle")


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
    print(json.dumps(_mock_completed(), ensure_ascii=False, indent=2))
