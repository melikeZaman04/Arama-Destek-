# Yankı — Arama Destek

Sessiz Kalem ile aynı tema: şirketin/müşterinin verisi dışarı çıkmadan ("temizlenmiş veriyle") analiz. Yankı, müşteri görüşmelerinden (memnuniyet, churn nedeni, entegrasyon sorunu) içgörü çıkarıp şirkete otomatik aylık rapor üreten bir araç.

Mock rapor örneği: `frontend/report.html` (tasarımın son hali — veri kaynağı değişecek, görünüm sabit kalacak).

## Mimari (turn-based, gerçek zamanlı streaming DEĞİL)

```
Müşteri arar → Twilio numarası
  → orchestration/app.py (Flask webhook, ngrok ile dışa açık)
  → TwiML <Record> ile müşterinin cevabı kaydedilir
  → ses → Whisper (STT) → metin
  → metin → gemma/analyze.py → bir sonraki soru ya da rapor JSON'u
  → next_question varsa → ElevenLabs (TTS) → <Play> ile çalınır, döngü sürer
  → report varsa → frontend/data/latest_report.json'a yazılır → frontend/report.html bunu okur
```

Gerçek zamanlı, kesintisiz telefon hattı (Twilio Media Streams) **kapsam dışı** — haftalar sürer. Bunun yerine her turda kaydet → işle → çal döngüsü var, bu 2 saatte kurulabilir.

**45 dakika kontrol noktası:** Twilio ucu uçtan uca çalışmıyorsa, telefon hattını bırakıp önceden kaydedilmiş bir ses dosyasıyla aynı zinciri (Whisper → Gemma → ElevenLabs) gösterin. Rapor ekranı ve anlatı aynı kalır, risk sıfırlanır.

## Ortak sözleşme

`schema/report_schema.json` — üç kişinin de üzerinde anlaştığı JSON biçimi. Herhangi biri bunu değiştirmeden önce diğer ikisine haber versin.

## Görevler

**Dilara — `gemma/analyze.py`**
Ollama/Gemma çağrısını `analyze_turn()` içine yaz. Girdi: transkript parçası. Çıktı: şemadaki JSON. Sabit örnek transkriptle test et, çıktısını paylaş.

**Melike — `orchestration/app.py`**
Twilio webhook + Whisper (`transcribe`) + ElevenLabs (`synthesize`) fonksiyonlarını doldur. İskelet zaten `analyze_turn()`'ü çağırıyor ve raporu `frontend/data/latest_report.json`'a yazıyor.

**Beyza — `frontend/report.html`**
Şu an sabit (mock) değerlerle. `frontend/data/latest_report.json`'u okuyup sayfadaki ilgili alanları (memnuniyet skoru, churn nedeni, alıntı, aksiyon önerisi) dinamik doldur. `frontend/data/sample_report.json` test için örnek veri.

## Kurulum

```bash
pip install flask
# Whisper, ElevenLabs SDK, Ollama client: her kişi kendi parçasında ekler
cd orchestration && python app.py
# başka bir terminalde: ngrok http 5000
```

`.env` için `TWILIO_*`, `ELEVENLABS_API_KEY` değişkenlerini kullanın — commit etmeyin.
