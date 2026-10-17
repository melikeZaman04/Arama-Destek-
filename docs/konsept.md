# Akıllı Müşteri Görüşmesi Analiz Asistanı — Konsept ve Çalışma Prensibi

**Durum: VİZYON / YOL HARİTASI dokümanıdır, bugün (2 saatlik pencerede) baştan
sona inşa edilecek bir sistem değildir.** Bu doküman, ekibin kendi Claude
oturumlarına okutup "nereden başlayıp nereye gideceğini" güvenle anlaması
için yazıldı. Gerçekçi bugünkü kapsam §9'da ayrıca ve net şekilde işaretli.

## 1. Problem

Şirketler müşterileriyle (aktif ya da kaybedilmiş/churn) destek ekibi
üzerinden telefonla konuşuyor. Bu görüşmelerde çok değerli bir sinyal var:
memnuniyet, ayrılma sebebi, entegrasyon sorunları, özellik talepleri. Ama bu
sinyal şu an sistematik olarak toplanmıyor çünkü:

- İnsan destek ekibinin her görüşmeden sonra yapılandırılmış not çıkarması
  pahalı ve tutarsız.
- Şirket, bu görüşmelerin ham içeriğini (müşteri adı, şikayet detayı) bir
  bulut AI servisine göndermek istemiyor olabilir — bu da Sessiz Kalem'in
  çözdüğü sorunla aynı aile: **hassas veri, analiz için dışarı çıkmadan
  işlenebilmeli.**

## 2. Çözüm fikri (özet)

Müşteriyle (telefonla) doğrudan konuşan, önceden tanımlı bir soru seti
etrafında esnek bir sohbet yürüten, görüşmeyi transkribe edip yapılandırılmış
içgörüye çeviren ve şirkete **periyodik (aylık) bir büyüme/churn raporu**
sunan bir asistan. Hedef: insan destek ekibinin yapmadığı/yapamadığı
sistematik "çıkış görüşmesi / memnuniyet taraması" işini, insan gücü
gerektirmeden ölçeklendirmek.

## 3. Hedef kullanıcı / senaryo

İki ayrı konuşma senaryosu var (ikisi de hedef, ayrı akış/soru seti ister):

| Senaryo | Kime | Amaç | Örnek açılış sorusu |
|---|---|---|---|
| Churn / çıkış | Yakın zamanda ayrılmış müşteri | Ayrılma sebebini öğrenmek | "Bizimle neden devam etmediniz?" |
| Aktif memnuniyet | Hâlâ müşteri olan hesap | Erken uyarı sinyali, entegrasyon sorunu | "Ürünümüzle ilgili bir sorun yaşıyor musunuz?" |

## 4. Uçtan uca akış

```
[CRM / müşteri listesi]
        │  (hangi müşteri aranacak, hangi senaryo)
        ▼
[Giden arama başlatılır]  ── Telefon şebekesi (SIP/PSTN) ──> [Müşteri telefonu]
        │                                                          │
        │  "Bu görüşme bir yapay zekâ ile yapılmaktadır,          │
        │   kaydedilmektedir" açıklaması + onay                    │
        │ <────────────────────── canlı ses akışı ─────────────────┤
        ▼
[STT: Whisper] ── müşterinin konuşmasını metne çevirir (gerçek zamanlı)
        │
        ▼
[Diyalog motoru / LLM] ── bir sonraki soruyu/cevabı üretir
        │   - önceden tanımlı soru seti + müşterinin cevabına göre dallanma
        │   - "insanla görüşmek istiyorum" gibi çıkış ifadelerini tanır
        ▼
[TTS: ElevenLabs] ── cevabı sese çevirir, müşteriye geri gönderilir
        │
        ▼
 (döngü: müşteri susana kadar konuşur → VAD algılar → yukarıdaki üç adım tekrar)
        │
        ▼
[Görüşme biter] ── tam transkript diskte/sunucuda tutulur (ham, hassas)
        │
        ▼
[Yerel analiz motoru (Gemma)] ── transkripti tarar:
        │   - kategorize eder (fiyat, özellik eksikliği, destek kalitesi, rakip geçişi...)
        │   - sentiment / aciliyet skoru çıkarır
        │   - KİŞİSEL VERİYİ (ad, telefon, hesap no) transkriptten ayıklar/maskeler
        ▼
[Toplulaştırma / agregasyon] ── tüm görüşmeler kategori bazında birleştirilir
        │   (burada artık TEK bir müşterinin kişisel verisi yok, yalnızca sayılar)
        ▼
[Aylık rapor] ── şirkete: "bu ay 42 çıkış görüşmesi, %38'i fiyat, %21'i
                  özellik eksikliği, %15'i rakip X'e geçiş..." gibi
                  toplulaştırılmış, kişisel veri içermeyen bir rapor
```

**Kritik tasarım kararı**: ham transkript (kişisel veri içerir) ile aylık
rapor (içermez) arasında net bir sınır var — Sessiz Kalem'deki "rapor gerçek
değer içermez" prensibiyle birebir aynı mantık, burada da uygulanıyor.

## 5. Mimari bileşenler ve çalışma prensibi

| Bileşen | Seçim | Ne yapar / neden |
|---|---|---|
| Telefon hattı | Twilio Voice (Media Streams) ya da kendi barındırılan SIP (Asterisk/FreeSWITCH) + SIP trunk | Ses verisinin PSTN'e/müşteriye fiziksel olarak ulaşmasını sağlar. Bu bir "bulut AI" değil, bir telekom geçişidir — gizlilik iddiasını bozmaz, normal bir telefon hattından farksızdır. |
| STT (konuşmadan metne) | Whisper (yerelde `faster-whisper`/`whisper.cpp`, gerçek zamanlı/streaming modda) | Müşteri sesini metne çevirir. Yerelde çalışabilir — bu, "ses verisi işlenmek için 3. parti AI servisine gitmiyor" iddiasının dayanağı. |
| Diyalog motoru | Gemma (yerel, Ollama) — ya da gecikme toleransı yoksa hızlı bir model | Transkript + konuşma geçmişine bakıp bir sonraki soruyu/cevabı üretir. Canlı konuşmada gecikme kritik: saniyenin altında cevap üretmesi gerekir. |
| TTS (metinden sese) | ElevenLabs (bulut) | Cevabı doğal sese çevirir. **Not: bu adım bulut servisi — "tamamen yerel" iddiası burada geçerli değil, dürüstçe belirtilmeli.** |
| Turn-taking / VAD | Silero VAD (yerel, hafif) | Müşterinin ne zaman konuşmayı bitirdiğini algılar — bu olmadan asistan ya araya girer ya da "ölü hava" oluşur. |
| Orkestrasyon | Pipecat ya da LiveKit Agents (hazır framework, sıfırdan yazılmaz) | STT→LLM→TTS zincirini, araya girmeyi (barge-in), gecikmeyi yönetir. Bu framework'ler yerel model backend'lerini (Ollama, faster-whisper) zaten destekliyor. |
| Analiz / rapor motoru | Gemma (yerel) | Görüşme bittikten SONRA, gerçek zamanlı baskısı olmadan transkripti analiz eder — burada Sessiz Kalem'in kazanımları (yerel tespit, kanıt doğrulama) doğrudan yeniden kullanılabilir. |

## 6. Gizlilik/yerellik çerçevesi — dürüst sınırlar

"Tamamen yerel" iddiası **kısmen** doğru olacak, bunu net ayırmak gerekiyor:

- ✅ **Yerelde kalan**: konuşmanın anlaşılması (STT), diyalog kararı (LLM),
  görüşme sonrası analiz/rapor üretimi (Gemma). Hiçbiri bulut AI servisine
  gitmiyor.
- ⚠️ **Yerelde kalmayan**: ses sentezi (ElevenLabs, bulut) ve telefon
  şebekesi geçişi (PSTN/SIP — bu bir AI servisi değil, telekom altyapısı,
  normal bir telefon görüşmesinden farkı yok).

Doğru pazarlama cümlesi: *"Görüşmeyi anlama, karar verme ve analiz etme
tamamen şirketin kendi altyapısında çalışır; hiçbir konuşma verisi ya da
transkript bir yapay zekâ bulut servisine gönderilmez."* (ElevenLabs'ın
yalnızca metni sese çevirdiğini, transkripti/analizi görmediğini netleştirin.)

## 7. Konuşma tasarımı / soru akışı

Örnek bir churn görüşmesi iskeleti (gerçek script bu değil, yapı örneği):

1. **Açılış + onay**: "Merhaba, ben [Şirket]'in yapay zekâ asistanıyım, bu
   görüşme kalite amacıyla kaydedilmektedir, 2 dakikanızı alabilir miyim?"
   (Hayır derse: nazikçe kapat, "reddetti" olarak işaretle.)
2. **Ana soru**: "Hizmetimizi neden sonlandırdınız?" (açık uçlu, serbest cevap)
3. **Dallanma**: cevaba göre 1-2 takip sorusu (örn. "fiyat" derse: "hangi
   aralıkta bir fiyat sizin için uygun olurdu?")
4. **Çıkış kontrolü**: "Bir insanla görüşmek ister misiniz?" (her zaman
   sorulmalı — bu, yasal/etik bir gereklilik, bkz. §10)
5. **Kapanış + teşekkür**

İnsana geçiş tetikleyicileri (her zaman dinlenmeli): müşteri sinirlenirse,
"insanla konuşmak istiyorum" derse, asistan 2 kez art arda cevabı anlamazsa.

## 8. Çıktı: Aylık Rapor (örnek şema)

```json
{
  "donem": "2026-10",
  "toplam_gorusme": 42,
  "kategori_dagilimi": {
    "fiyat": 16,
    "ozellik_eksikligi": 9,
    "destek_kalitesi": 5,
    "rakibe_gecis": 6,
    "diger": 6
  },
  "ortalama_memnuniyet_skoru": 2.8,
  "aciliyet_yuksek_sayisi": 4,
  "insana_yonlendirilen": 3,
  "one_cikan_temalar": [
    "Fiyat artışı sonrası iptallerde belirgin artış",
    "Mobil uygulama entegrasyonu en çok şikayet edilen özellik"
  ]
}
```

**Not**: Bu raporda hiçbir kişisel veri (isim, telefon, hesap no) yok —
Sessiz Kalem'in rapor prensibiyle birebir aynı: toplulaştırılmış, paylaşılabilir.

## 9. BUGÜN (2 saatlik pencere) için gerçekçi kapsam

Gerçek telefon görüşmesi altyapısını (Twilio/SIP + canlı STT/LLM/TTS
zinciri) bugün ÇALIŞIR HALDE kurmak gerçekçi değildir — bu haftalar sürer.
Sunum "çalışan ürün istemiyoruz, sunun yeterli, demo varsa bonus" dediği
için önerilen kapsam:

1. **Yukarıdaki akış ve mimari slayt/anlatı olarak sunulur** (bu doküman
   bunun temelini oluşturuyor).
2. **Düşük riskli, hızlı bir "demo"**: gerçek telefon yerine, önceden
   yazılmış sahte bir görüşme transkripti alıp, §8'deki rapor şemasına
   dönüştüren basit bir script/sayfa — bu, "sistem bir transkripti böyle
   bir rapora çevirir" iddiasını SOMUT olarak gösterir, dakikalar sürer,
   telefon/ses entegrasyonu gerektirmez.
3. Zaman gerçekten kalırsa: tek bir sentetik transkriptte Gemma ile gerçek
   bir kategorizasyon/sentiment çıkarımı denenebilir (Sessiz Kalem'deki
   Ollama kurulumu zaten hazır, aynı altyapı kullanılabilir).

## 10. Riskler ve açık kararlar (jüri sorarsa / ileride çözülecek)

- **Yasal**: arama kaydı rızası, "AI ile görüştüğünüzü" açıkça belirtme
  zorunluluğu (KVKK + bazı ülkelerde ek robocall düzenlemeleri), arama
  saati kısıtları, "insanla görüşmek istiyorum" çıkışının her zaman sunulması.
- **Latency/UX**: canlı ses pipeline'ında STT+LLM+TTS toplam gecikmesi
  >1-2 sn olursa konuşma "robotik" hisseder — bu, projenin en zor
  mühendislik problemi, barge-in/VAD doğru yapılmazsa daha da kötüleşir.
  (Pipecat/LiveKit bu tür sorunları çözmek için var.)
  Veritabanı/skala: gerçek bir donanım/altyapı planı henüz yok.
- **"Tam otomasyon" iddiası dikkatli kullanılmalı**: Sessiz Kalem'in kendi
  kuralı ("tamamen güvenli", "hiç kaçırmaz" gibi cümlelerden kaçının)
  burada da geçerli — "tam otomasyon" yerine "insan onayına gerek kalmadan
  ölçeklenen" gibi daha savunulabilir bir dil tercih edilebilir.

## 11. Sessiz Kalem ile ilişkisi

Aynı ekip, aynı etkinlik, ortak tema (yerel işleme, hassas veri dışarı
çıkmadan analiz) ama **ayrı repo** — mimari ve bağımlılıklar (telefoni,
ses, bulut TTS) tamamen farklı, aynı repoda karıştırılmamalı. Sessiz
Kalem'in kural katmanı ve kanıt doğrulama mantığı, bu projenin "görüşme
sonrası analiz" aşamasında yeniden kullanılabilir bir referans.
