# Metan (gaz) sızıntısı OpenFOAM koşuları — rapor (2026-11-12)

**GÖSTERİM — deney verisiyle doğrulanmadı.**

## 1) v1 neden "hata 0" ile bitti?

**Kök neden: koşular hiç tamamlanmadı.** Altı koşunun hepsi çıkış kodu 136 (SIGFPE) ile çöktü:

| koşu | çöktüğü an |
|---|---|
| 3B uzay | t = 0.0665 s |
| 3B Mars | t ≈ 0.06 s |
| 2B (dört koşu) | t ≈ 0.04 s |

Hata kimya çözücüsünde: seulex ODE içinde `IrreversibleReaction::kf`, yani `exp(-Ta/T)` taşması (ODE iç durumunda T < 0).

v1'de iki sorun üst üste bindi:

1. **Tutuşturucu fazla güçlüydü.** Yarım alanda 10 W verilmişti; 1500 K'de 6 mm'lik kürenin iletim kaybı ~3.6 W olduğu için çekirdek durmadan ısındı. Tmax 0.06 s'de 2714 K'e çıktı, bu metanın T_ad'ından da yüksek.
2. **Sonlu hızlı tek adım kimya kararsızdı.** counterFlowFlame2D'nin Arrhenius'u tutuşma anında kararsız.

   Tutuşturucuyu 2 W / 0.10 s'ye indirip 250–2800 K sıcaklık sınırı ekledikten sonra Tmax 1080–1470 K'de kaldı, ama koşular tutuşma anında yine çöktü. Denenenler (`of_kosular/gaz_denemeler/`):

   | deneme | ayar | sonuç |
   |---|---|---|
   | A | seulex, sıkı tolerans | t = 0.083 s'de çöktü |
   | B | rodas23, sıkı tolerans | t = 0.078 s'de çöktü |
   | C | maxDeltaT 1e-4 | t = 0.078 s'de çöktü |
   | D | maxDeltaT 2e-5 | t = 0.077 s'de çöktü |
   | E | smallPoolFire3D'nin özgün infinitelyFastChemistry'si | 0.15 s'yi çökmeden bitirdi |

**Kuyruk ve bekçi neden yakalamadı?**
- Kuyruk koşunun çıkış kodunu yalnız loga yazıp sıradakine geçti. Analiz, video ve kopya adımları yalnız kendi çıkış kodlarına bakıyordu. Çöken koşuların 2–5 karelik verisiyle boş videolar üretildi (40–65 kB, 0.2–0.3 s).
- Bekçi dakikada bir bakıyor; koşular 20–50 s'de çöktüğü için hiç görmedi.

**Düzeltmeler**

Kimya:
- smallPoolFire3D'nin özgün infinitelyFastChemistry'si; görevdeki "kimya smallPoolFire3D temelli" isteğine de uygun.
- Bedeli: alev karışımla sınırlı, sönme ve tutuşma gecikmesi yok, tutuşturucu yalnız görsel. Bu, gaz_motoru'nun Roper alev boyu varsayımıyla (karışımla sınırlı) aynı.

Vaka:
- Tutuşturucu 2 W / 0.10 s.
- `limitTemperature` 250–2800 K.
- Yazma aralığı 0.01 s (101 kare / 10 s video, sıvı sızıntısı videolarıyla aynı).

Denetim (`of_kuyruk_gaz.sh` v2/v3):
- Her koşu için çıkış kodu 0, son yazılmış zaman = endTime, logda `End` ve çökme izi yok şartı (`of_gaz.py: bitti_mi`, `durum.json`).
- Kısa testler (6 vaka × 0.05 s) aynı denetimle.
- Biri tutmazsa "HATA" yazılır ve sonraki adımlara geçilmez (`hata_dur`).
- Video denetimi: ≥ 100 kare, ≥ 9.5 s, ≥ 150 kB ve orta karede parlak (luminans > 60) piksel ≥ %0.3 (`of_gaz.py --video-denetle`).

**Görevdeki "> 1 MB" eşiğinden sapma.** Bu eşik geçerli videoyu da reddetti: v2'deki 51 karelik doğru kesit videosu 0.16 MB'tı. Koyu arka plan ve sade içerik H.264'te çok iyi sıkışıyor. Bu yüzden boşluğu doğrudan ölçen denetim kullanıldı; boyutlar aşağıda ayrıca veriliyor. Sıvı sızıntısı videoları 3B yüzeyler içerdiği için 2+ MB.

## 2) v3 koşuları (08:30–08:54)

Hepsi TAMAM: çıkış 0, son zaman 1.0 s, `End` var, çökme yok.

| koşu | hücre | duvar süresi |
|---|---|---|
| 3B uzay | 77 675 | 4.0 dk |
| 3B Mars | 77 675 | 3.6 dk |
| 2B g = 0 | 25 600 | 1.5 dk |
| 2B Ay (1.62) | 25 600 | 1.4 dk |
| 2B Mars (3.73) | 25 600 | 2.0 dk |
| 2B Dünya (9.81) | 25 600 | 3.2 dk |

Toplam kuyruk süresi 24 dk.

Disk: başlangıçta 8.58 GB boştu, en çok 3.7 GB yazıldı (sınır 4.29 GB). Videolar ve analiz bittikten sonra kullanılmayan zaman klasörleri silindi; görüntüleyicinin 20 karesi ve son zaman kaldı. Şu an gaz verisi 1.6 GB, boş disk 6.4 GB. Videoları yeniden çizmek ~25 dk'lık yeniden koşu gerektirir.

## 3) Videolar (of_gorsel/ ve ~/Desktop)

| video | süre | kare | boyut | içerik (parlak piksel) |
|---|---|---|---|---|
| gaz_uzay_mars.mp4 / _en | 10.0 s | 100 | 0.22 MB | %4.5 |
| gaz_3b.mp4 / _en | 10.0 s | 100 | 0.70 MB | %2.5 |
| gaz2d_4g.mp4 / _en | 10.0 s | 100 | 0.28 MB | %4.9 |
| sizinti_ince_3b.mp4 / _en (sıvı, mevcut) | 10.1 s | 101 | 2.13 / 2.14 MB | %12.4 |

Sıvı 3B videosu vardı ve 1 MB'tan büyüktü, yeniden üretilmedi.

Kare kontrolleri (t ≈ 0.8 s):
- **kesit:** Uzayda delik çevresinde top biçimli alev, stokiyometrik çizgi deliği sarıyor. Mars'ta dikey alev ve tavana ulaşan tüy.
- **3B:** Uzayda yalnız 1200 K yüzeyi var (soğuk alev topu). Mars'ta 1200 K sarı ve 1800 K kırmızı ince alev.
- **2B 4 g:** g = 0'da halka biçimli alev. Ay, Mars ve Dünya'da g arttıkça daralan dik alev; Ay'da ilk tutuşmadan kopan ikinci bir tüy.
- **sıvı 3B (t = 0.60 s):** Uzayda kabini dolduran alev, Mars'ta tavan tabakası.

Her videoda "GÖSTERİM — deney verisiyle doğrulanmadı" notu var. Görüntüleyiciye (of_gorsel.html) "Gaz sızıntısı (metan) — GÖSTERİM" grubu eklendi; 6 koşu var ve yakıt düğmesi "Yakıt (metan)".

## 4) gaz_motoru – OpenFOAM alev boyu (son 0.3 s ortalaması)

| | 3B uzay | 3B Mars |
|---|---|---|
| gaz_motoru jet: L_f (mm), yanma | 59.2, 0.98 | 46.7, 0.94 |
| gaz_motoru küre (sızıntı): R_f (mm), yanma | 84.3, 0.00 (ışınımla sönme) | 6.5, 0.97 |
| OpenFOAM: Qdot ≥ %5 bölgesinin uzunluğu (mm) | **35.7** | **62.5** |
| OpenFOAM: T ≥ 1200 K uzunluğu (mm) | 33.7 | 100 (tavana kadar) |
| OpenFOAM Tmax (K) | 1563 | 1946 |
| oran OpenFOAM / motor jet | **0.60** | **1.34** |

2B, g = 0 / 1.62 / 3.73 / 9.81 için:
- alev boyu: 63 / 118 / 101 / 100 mm,
- Tmax: 1651 / 1943 / 2011 / 2095 K.

2B ısı salımı birim derinlik başına verildiği için doğrudan 3B ile kıyaslanmaz.

Yorum:
- **Sıralama ters.** Motor µg alevini Mars'takinden uzun öngörüyor (+%28 µg uzaması). OpenFOAM'da tersi oluyor: 18 cm/s'lik bu sızıntının momentumu çok küçük, µg'de ince bir jet oluşmuyor, deliği saran soğuk bir alev topu oluşuyor (Tmax 1563 K). Mars'ta kaldırma alevi dikey olarak uzatıyor.
- **Jet modeli bu rejimde geçerli değil.** Roper jet modeli momentumlu jet varsayıyor.
- **Küre modeli de tutmuyor.** µg'de R_f'yi fazla buluyor (84 mm'ye karşı ~36 mm) ve ışınımla sönme öngörüyor; OpenFOAM'da alev yanıyor. Ama OpenFOAM'da sönme olamaz (sonsuz hızlı kimya) ve gri fvDOM ışınımı kullanılıyor; bu yüzden bu fark sönme konusunda kanıt sayılmaz.
- **İkisi de kalibre değil:** gaz_motoru jet ve küre modelleri metan için etiketli veriyle kalibre edilmedi.

## 5) Bilinen sınırlar
- Sonsuz hızlı kimya: sönme ve tutuşma gecikmesi yok; tutuşturucu yalnız görsel.
- Sonlu hızlı tek adım CH4 bu kurulumda tutuşma anında kararsız (5 denemede çözülmedi). Sönme incelenecekse çok adımlı mekanizma ya da EDC/PaSR denenebilir.
- 3B yarım alan (z = 0 simetri); 2B'de delik yarık oluyor, 3B ile nicel kıyas yapılamaz.
- Mars ve 2B kaldırmalı koşularda alev tavana (havalandırma çıkışına) ulaşıyor; alev boyu tavanla sınırlı (T ≥ 1200 K uzunluğu 100 mm = tavan).

## Dosyalar
- Koşu altyapısı: `of_gaz.py`, `of_kuyruk_gaz.sh`, `pv_gaz_video.py`
- Analiz çıktıları: `of_gaz_sonuc.csv`, `of_gaz_motor_karsilastirma.csv`, `of_gaz_ozet.json`, `of_gaz_harita_3b/2b(_en).png`, `of_gaz_karsilastirma(_en).png`
- Loglar: `of_kosular/canli_gaz.log`, `of_kosular/gaz_*.log`, `of_kosular/gaz3d_ince/*/durum.json`
- Görüntüleyici: of_gorsel.py, of_gorsel_veri.py ve şablona yalnız ekleme yapıldı; eski halleri `of_gorsel/*_gaz_oncesi*`
- motor.py, tahmin.py ve damla dosyalarına dokunulmadı; git kullanılmadı; eski koşular silinmedi.

---
# Ek (2026-11-12 akşam): 4 yerçekimli 3B videolar, 2B etiket düzeltmesi, sıvı tahmini

## Koşular
Yeni koşular: `of_kosular/gaz3d_ince/{ay,dunya}` (g = 1.62 ve 9.81). Kurulum uzay/Mars ile birebir aynı: ızgara, sızıntı, infinitelyFastChemistry, p_rgh, tavan çıkışı, tutuşturucu.

Uzay ve Mars da aynı kurulumla yeniden koşuldu. Nedeni: önceki inceltmede yalnız 20 kare kalmıştı; 10 s video tam seri istiyor. 2B dört koşu da aynı nedenle yeniden koşuldu.

Bütün koşular `of_kuyruk_gaz4g.sh` ile, 15 çekirdekle ve sırayla yapıldı. Denetimler aynı: çıkış 0, son zaman = endTime, `End`, çökme yok. Hepsi TAMAM; 3B ~4 dk, 2B ~1.5–3 dk.

Bir yanlış alarm: 2b_9.81, bekçi tarafından başlangıçta "log 15 dk yazılmadı" diye durduruldu.
- Nedeni: koşu eski v3 loguna ekleme yapıyordu; bekçi ilk satırdan önce eski logun değişiklik zamanını gördü.
- Düzeltme: sıfırdan başlayan koşuda eski log `.onceki` adıyla kenara alınıyor; bekçinin takılma denetimleri ilk 2 dakika uygulanmıyor. Koşu yeniden yapıldı ve TAMAM.

| vaka | Tmax (K) | Q (W, tam kabin) | alev boyu Qdot ≥ %5 (mm) | alev merkezi y (mm) | gaz_motoru jet L_f (mm) | oran OF / motor |
|---|---|---|---|---|---|---|
| 3B uzay | 1563 | 106 | 35.7 | 0.3 | 59.2 | 0.60 |
| 3B Ay | 1910 | 151 | 64.3 | 16.0 | 47.2 | 1.36 |
| 3B Mars | 1946 | 150 | 62.5 | 16.2 | 46.7 | 1.34 |
| 3B Dünya | 1994 | 150 | 60.1 | 16.5 | 46.4 | 1.29 |

g > 0'da alev boyu ~60–64 mm ve g'den hemen hemen bağımsız. Roper'ın kaldırmalı laminer alevler için öngördüğü de bu; mutlak değer motordan %30 uzun. µg'de alev top biçimli ve soğuk: motorun jet modeli bu rejimde geçerli değil.

## Videolar (of_gorsel/ ve ~/Desktop; TR + EN, 1920×1080, 10 kare/s, H.264 yuv420p)

| video | kare | süre | boyut | sıcak bölge, panel başına (sol üst / sağ üst / sol alt / sağ alt) |
|---|---|---|---|---|
| gaz_3b_4g(_en) | 100 | 10.0 s | 0.89 MB | 1.5 / 2.4 / 1.4 / 2.2 % |
| gaz_kesit_4g(_en) | 100 | 10.0 s | 0.20 MB | 1.1 / 2.4 / 1.4 / 1.9 % |
| gaz2d_4g(_en) | 100 | 10.0 s | 0.36 MB | 2.1 / 3.4 / 3.4 / 2.4 % |

Düzen: 2 × 2, sol üst uzay, sağ üst Mars, sol alt Ay, sağ alt Dünya. Ortak başlık, t göstergesi, sağda tek T renk çubuğu, altta açıklama ve GÖSTERİM notu.

- **gaz_3b_4g:**
  - aynalanmış tam kabin ve çerçeve;
  - 900 K ve 1400 K yarı saydam izo yüzeyler, renk çubuğunda işaretli;
  - stokiyometrik yüzey yeşil tel olarak;
  - dört görünümde aynı ve bağlı kamera, ~90° dönüş.

  İlk sürümde 1400 K opak olduğu için tel içinde kalıyordu; 1400 K yarı saydam yapıldı ve 3B yeniden üretildi. Tel küçük görünüyor, çünkü sonsuz hızlı kimyada yakıtça zengin çekirdek deliğin önünde ~10–15 mm.
- **gaz_kesit_4g:** z = 1 mm kesiti, aynı düzen, yeşil stokiyometrik çizgi.
- **gaz2d_4g:** panel etiketleri alanın üstündeki 46 px'lik banda taşındı; artık tavandaki aleve binmiyor.

  Ayrıca eski 2B videoda yeşil çizgi görünmüyordu. Tek hücre kalın dilimde kontur, kameraya yandan bakan bir şeritti. Artık dilimin orta düzlemi kesilip kontur oradan alınıyor; çizgi dört panelde de görünüyor.

Kare kontrolleri (t = 0.51 s):
- uzay top biçimli alev;
- Ay eğik / kıvrılan alev ve kopan ikinci tüy;
- Mars ve Dünya'da g arttıkça incelen dik alev;
- 2B'de dört panelde stokiyometrik çizgi.

## Sıvı (n-heptan) sızıntısı için 4 yerçekimli 3B video — süre tahmini (BAŞLATILMADI)
Veri: ince ızgara koşuları (`sizinti3d_ince`, 15 çekirdek):
- uzay: 4703 adım, 2.04 sa (1.56 s/adım);
- Mars: 6940 adım, 2.63 sa (1.37 s/adım).

Adım sayısı kaldırma hızıyla artıyor. Courant sınırında Δt ∝ 1/u ve u ∝ √g varsayımıyla:

| koşu | adım | süre (≈1.4 s/adım) |
|---|---|---|
| Ay | ~6200 | **~2.4 sa** (2.2–2.8) |
| Dünya | ~8300 | **~3.2 sa** (2.8–4.0); Dünya'da daha güçlü kaldırma, dar Δt riski |

Ek işler:
- 2 × refineMesh hazırlığı ~10 dk;
- damla_vtk ve 4 panelli 3B video çizimi ~20–30 dk; pv_3b_video.py'nin 2 × 2 sürümünün yazılması gerekiyor.
- Uzay ve Mars yeniden koşulmaz: alanlar 20 zamanda saklı, damla serisi tam (102 kare). Mevcut sıvı 3B videosu da böyle üretildi; video en yakın alan zamanını gösteriyor.

**Toplam: ~6 saat (5.5–7.5 sa).** Disk: koşu başına budamadan sonra ~0.9 GB, en çok ~2 GB (şu an 6.3 GB boş).
