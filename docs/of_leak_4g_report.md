# Sıvı (n-heptan) sızıntısı — 4 yerçekimli 3B koşular ve videolar (2026-11-15)
**GÖSTERİM — deney verisiyle doğrulanmadı.**

## Koşular (scripts/of_queue3d_4g.sh)
| koşu | çekirdek | süre | durum |
|---|---|---|---|
| ay (g = 1.62) | 13 | 2.63 sa (17:41–20:19) | TAMAM: çıkış 0, son zaman 1.0 s, End, çökme yok |
| dunya (g = 9.81) | 15 | 2.06 sa (20:19–22:22) | TAMAM |

- Dünya: başlamadan önce pgrep ile ağır python işi bulunmadı, 15 çekirdek seçildi (numberOfSubdomains 15).
- Kurulum uzay/Mars ile birebir: kutu genis, bölme 1, 113 900 hücre, yarım alan, 2.5 mm, p_rgh, tavan çıkışı.
- Kısa test (Ay, 0.02 s) geçti; kaldırma açık (p_rgh çözülüyor).
- Damla serileri scripts/droplet_vtk.py ile üretildi, 101 zaman. Dosya değiştirilmedi; çalışma anında koşu listesine eklendi.
- Ay ve Dünya, damla serisinden sonra uzay/Mars ile aynı 20 alan zamanına inceltildi; postProcessing ve damla serisi korundu.
- Disk: başlangıçta 6.27 GB boştu, en düşük 4.73 GB'a indi (sınır 3.13 GB), şimdi 5.60 GB.

## 4 yerçekimi tablosu (data/of_leak_thin_4g_result.csv, of_sizinti_ince_4g(_en).png)
| koşu | g | tutuşma (s) | Tmax t > 0.03 s (K) | Q maks (kW) | y_alev ort. 0.40–0.65 s (mm) | y_alev son (mm) | üst/orta/alt T, t ≈ 0.55 s (K) | t = 1.0 s (K) |
|---|---|---|---|---|---|---|---|---|
| Uzay | 0 | 0.018 | 3130 | 29.0 | −6.5 | 0.8 | 1506 / 1768 / 1843 | 2107 / 2059 / 1968 |
| Ay | 1.62 | 0.018 | 2947 | 27.9 | −2.4 | 17.9 | 779 / 765 / 675 | 1527 / 1006 / 681 |
| Mars | 3.73 | 0.018 | 3031 | 27.8 | 31.2 | 8.6 | 1349 / 903 / 319 | 588 / 641 / 466 |
| Dünya | 9.81 | 0.018 | 2852 | 22.9 | 40.6 | 54.8 | 361 / 315 / 307 | 322 / 303 / 300 |

Yorum: tutuşma g'den bağımsız; püskürme ve tutuşturucu darbesi g'den çok hızlı. g arttıkça:
- sıcak gaz yukarı çıkıyor (alev merkezi yükseliyor),
- tavandaki havalandırma çıkışından daha erken atılıyor.

Dünya'da kabin 0.55 s'de neredeyse soğumuş (alt 307 K). Uzayda kaldırma yok; sıcak gaz kabinde kalıyor (1.0 s'de her yerde ~2000 K).

Tmax değerleri (2850–3130 K) tek adım kimyanın ayrışma içermemesinden yüksek. Tutuşturucu darbesi sırasında (t < 0.03 s) ~5600 K'e fırlama fiziksel değil.

## Videolar (of_visual/ ve ~/Desktop; TR + EN, 1920×1080, 10 kare/s, H.264 yuv420p)
| video | kare | süre | boyut | sıcak bölge, panel başına (sol üst / sağ üst / sol alt / sağ alt) |
|---|---|---|---|---|
| sizinti_3b_4g(_en) | 101 | 10.1 s | 2.36 MB | 16.8 / 8.4 / 15.0 / 2.3 % |
| sizinti_kesit_4g(_en) | 101 | 10.1 s | 1.22 MB | 24.6 / 12.0 / 6.2 / 1.1 % |

Panel yerleşimi:
- sol üst: uzay
- sağ üst: Mars
- sol alt: Ay
- sağ alt: Dünya

Ortak başlık, t göstergesi, sağda tek T çubuğu (1200 / 2400 K işaretli) ve altta GÖSTERİM notu var.

Sıcaklık alanı 20 zamanda saklı, damlalar her karede kendi zamanında. Üstte "sıcaklık alanı: t = …" yazıyor.

Kare kontrolleri (of_visual/screen/video_sizinti_*_4g_t0.15.png, _t0.55.png):
- **t = 0.15 s:** dört panelde püskürme konisi ve alev cephesi. Dünya'da damlalar ve alev aşağı-yukarı ayrışıyor; damlalar düşüyor.
- **t = 0.55 s:**
  - uzayda alev kabini dolduruyor;
  - Ay'da sıcak gaz sağ duvar boyunca yükseliyor;
  - Mars'ta sıcak tabaka tavanda;
  - Dünya'da sıcak gaz büyük ölçüde tahliye olmuş, yalnız sağ duvarda ince bir artık alev var. Bu yüzden Dünya panelinin sıcak bölge oranı en düşük (%1.1–2.3), ama eşiğin (%0.3) üstünde.

## Görüntüleyici
of_gorsel.html'e ince_ay ve ince_dunya eklendi; "Sızıntı — ince ızgara" grubunda.

Dokunulmayanlar: scripts/engine.py, scripts/predict.py ve damla dosyaları (scripts/droplet_vtk.py yalnız içe aktarılarak kullanıldı). Git kullanılmadı.
