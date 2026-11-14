# BASS planı: OpenFOAM motorunun kilitli motorunun başka bir deneyde dürüst testi (2026-11-12)

**Karar:**
- Saffire koşusu bizim tarafta yapılmıyor (OpenFOAM 3B'yi kendi bilgisayarında koşuyor). Bekleyen 10 s Saffire başlatıcısı
  iptal edildi; koşu hiç başlamadı (`deneyler/ofm_v2.log`).
- BASS'te (PSI-26) SIBAL testi **var**: 12 ISS testi, 16 koşul satırı, hepsi "yandı" (`psi_etiketli_bass1.csv`,
  BASS test matrix.xlsx "as run"). Bu yüzden BASS planı uygulandı.

## Neden dürüst test
- Motor Saffire-III S1'in ilk 10 s'sine kalibre edildi ve parametreleri kilitlendi (`MOTOR_KILIT.json`).
- BASS SIBAL testleri kalibrasyonda kullanılmadı.
- Aynı malzeme, ama deney farklı: başka numune boyutu (2,2 × 10 cm, Saffire 40,6 × 94 cm), başka akış (5–44 cm/s)
  ve başka kanal.

## Seçilen test: as-run 4
| | değer | kaynak |
|---|---|---|
| numune | SIBAL 2 cm (2,2 × 10 cm), uçtan sıcak telle ateşleme | NASA 20160000593; test matrisi |
| akış | 10 cm/s, eş yönlü (concurrent) | test matrisi |
| O₂ | %21,9 (hacim) | test matrisi |
| basınç | 0,97 atm (98,3 kPa) | test matrisi |
| CO₂ | 3,12 mm Hg | test matrisi |
| gözlem | "~40 s burn" → ortalama yayılma ≈ 10 cm / 40 s = **2,5 mm/s** (kaba) | test matrisi gözlem sütunu |

- **Yedek testler** (`ofm_bass_kur.py --test 5 | 12`):
  - test 5: 5 cm/s, "~60 s burn" (≈ 1,7 mm/s);
  - test 12: 22 cm/s, "26 s burn" (≈ 3,8 mm/s).
- Üçü birlikte akışa bağlı bir eğilim verir. Test 4'ün sonucu görülmeden ikisi başlatılmadı.

## Motor değişmedi, vaka değişti
- **Değişmeyenler:** kinetik, piroliz, ışınım, sayısal ayarlar ve kütüphane (md5 kilitle aynı, `ddea5b2b…`).
- **Değişenler** (`deneyler/ofm_bass_kur.py`, ayrıntı `ofm_kosular/bass_sibal_t4/BASS_VAKA.json`):
  - geometri: numune x = 0,10–0,20 m, alan 0–0,40 m;
  - ortam: test 4 koşulları;
  - Saffire sensör probları çıkarıldı;
  - endTime 40 s.
- **Varsayımlar** (BASS belgelerinde yok; sonuç bunlara duyarlı olabilir):
  1. kanal yarı yüksekliği 0,038 m (SPICE kanal kesiti bulunamadı);
  2. tel ön kenardan 6,25 mm'de; ateşleyicinin birim genişlik gücü ve 7,986 s kapanma Saffire ile aynı
     (BASS'teki "saw tooth hotwire" gücü bulunamadı);
  3. tutucu, yani kaymasız taban, numunenin önünde ve arkasında 0,01 m;
  4. H₂O mol kesri 0,0116 ve T 294,32 K Saffire ile aynı;
  5. 2B simetrik model, yani iki yüzlü numune.
     - BASS'te 2 cm numunelerin bir kısmı tek yüzlü; test 4'ün hangisi olduğu belgede yok.
  6. ağ: üst satır hücre tavanı 16 mm → 2 mm (kanal 0,30 → 0,038 m); duvar yanı çözünürlük aynı.
- **Kurulum sorunları** (çözüldü; hatalı vakalar `of_kosular/bass_sibal_t4_*` altında):
  - 5 cm'lik ön bölge ağın büyüme dizisine sığmadı;
  - 16 mm hücre tavanı kanala sığmadı;
  - OpenFOAM 14'te `splitMeshRegions -cellZones` bölge listesi istiyor; README'deki `-cellZones -overwrite` bu sürümde çalışmıyor.

## Ölçütler
`ofm_analiz.py` ve `ofm_dogrulama.py --deney bass4` ile hesaplanacak:
- tutuşma var mı (gaz max T > 1500 K);
- alev ucunun konum–zaman eğrisi ve yayılma hızı; deney ≈ 2,5 mm/s (kaba);
- model "yanma süresi": alev ucunun numune sonuna (x = 0,20 m) vardığı an; deney ~40 s;
- kütle kaybı.

**Başarı ölçütü:** yayılma hızı ve yanma süresi deney değerinin ±%50'si içinde. Deney değeri gözlemcinin tahmini süreden
türetildiği ve varsayımlar büyük olduğu için daha sıkı bir eşik anlamlı değil.

## Koşu
- `deneyler/ofm_bass_baslat.sh` (nohup, 4 çekirdek; kuyruk boşsa başlar, disk < 1,5 GB ise durur).
- Başlangıç 2026-11-12 23:34.
- **Hız:** tutuşma öncesinde simülasyon saniyesi başına yaklaşık 1180 s duvar zamanı.
  - 40 s'lik koşu en az ~13 saat sürer; tutuşmadan sonra adımlar küçüleceği için daha uzun olabilir (tahmin 13–30 saat).
- **Bitince otomatik:** `ofm_analiz.py` ve `ofm_dogrulama.py`; çıktılar `ofm_sonuclar/` altında, log
  `deneyler/ofm_bass.log`.
- **Durdurmak için:** `pkill -f ofm_bass_baslat.sh; pkill foamMultiRun`.
