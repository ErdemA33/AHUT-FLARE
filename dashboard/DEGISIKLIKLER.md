# AHUT FLARE — değişiklikler (backend ekibinden, 2026-11-13)

Dashboard ekibinin kodu (`~/Downloads/ahut_flare`) bu klasöre kopyalandı ve güncel backend'e bağlandı. Tasarım dili
korundu: yeni ekranlar yalnız var olan sınıfları (`kart`, `vaka-kart`, `cubuk`, `etiket`, `uyari-satir`,
`table.veri`, `pencereAc`) kullanır; CSS'e yeni kural eklenmedi. Git: `dashboard` dalı.

## Çalıştırma (Ubuntu)

```bash
cd ~/nasaspaceapp/dashboard
./calistir.sh              # ilk açılışta .venv (system-site-packages) + pywebview; sudo gerekmez
./calistir.sh --sinama     # pencere açmadan kendini sınar
```

Ekran görüntüleri / uçtan uca deneme (ekran kilitliyken de çalışsın diye iç içe X sunucusunda):

```bash
Xephyr :77 -screen 1700x1060 -nolisten tcp -br &
DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python ekran_al.py --videosuz   # sekme görüntüleri -> ../of_gorsel/ekran/
DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python uctan_uca.py --videosuz  # 15 senaryo -> ../of_gorsel/ekran/uctan_uca/
```

## Bağlantı (1. aşama)

| konu | değişiklik |
|---|---|
| `motor/` | `motor_esitle.py` ana klasördeki güncel backend'i kopyalar (DASHBOARD.md §5 + malzeme kütüphanesi). `mock_backend.py`, `BACKEND_API.md` sizin. |
| yazılabilir veri | `YANGIN_VERI_KLASORU` = `veri/`: malzeme önbelleği, `topluluk/topluluk.sqlite`, `loglar/tahmin_kayit.jsonl`, `malzemeler_kullanici.json`. `motor/` salt okunur olabilir. |
| `os.chdir` | kaldırıldı; backend yollarını kendi klasörüne bağlıyor. |
| anahtar | kopyada `evren_anahtar.txt` yok (`evren_anahtar_ORNEK.txt`); yerel denemede bir üst klasördeki okunur, kopyalanmaz. `profil.json` jetonu boşaltıldı. |
| Linux | `pencere_motoru()` (Windows edgechromium, Linux gtk). pywebview 6 `eval` / `new Function` kullanıyor, sayfanın CSP'si engelliyor: `pywebview_hazirla()` bunları eval'siz karşılıklarla değiştirir (CSP gevşetilmedi). Arayüz + `render/` aynı yerel kökenden (WSGI, 127.0.0.1) sunulur, yoksa `file://` videolar yüklenmez. Windows yolu değişmedi. |
| `.bat` | sabit `C:\Anaconda3\...` yolları yerine `python_bul.bat`. |
| PyInstaller | `motor/` alt klasörleri (`gaz_veri/`, `modeller/`) ve yeni modüller dahil. |
| videolar | `render_eslesme.csv` + `render_esle.py`: 37 OpenFOAM videosu/GIF'i `render/` adlandırmasıyla; sızıntılar `_dogrulanmadi`. |

## Backend'de yeni (mevcut alanlar değişmedi)

- **Malzeme kütüphanesi** (`malzeme_kutuphanesi.json`, 44 malzeme): eş anlamlılar, varsayılanlar, motordaki benzer
  malzeme, kaynaklı özellikler (NIST WebBook, SFPE El Kitabı 5. baskı, `chemicals`), durum, uzayda kullanım.
  Uydurma değer yok; boş alan = kaynakta yok.
- **Tanıma**: bilinen listede olmayan ad önce kütüphanede aranır (LLM'e sorulmaz). `tahmin.kutuphane_eslesme` yeni
  alan; `adimlar[no=2].ayrinti.kaynak` = `liste | kutuphane | kullanici_kutuphanesi | llm | onbellek`.
  Kalibre değilse motor ağırlığı 0 + uyarı; zayıf eşlemede `zayıf eşleme: <benzer>`; benzeri yoksa motor çalışmaz.
- Tanınan ama varsayılanı olmayan malzeme (etilen, etan, propan …) varsayılanını kütüphaneden alır
  (etilen -> gaz / flat_burner; önceden katı motoruna gidiyordu).
- `llm_analiz.malzeme_oner(ad)`: kullanıcı malzemesi formu için öneri; KARAR satırı v2 güveni yazar.
- Kalibre malzemelerde sayılar birebir aynı (10 vaka karşılaştırması; damla/gaz testleri).

## Arayüz maddeleri (onaylı liste)

| # | ne yapıldı | nerede |
|---|---|---|
| 1 | numune listesine `flat_burner`, `porous_sphere`; gaz geometrisi -> yakıt türü `gaz`; varsayılanlar kütüphaneden | Vaka Kurulumu > Malzeme |
| 2 | model / motor ağırlık çubuğu (`agirliklar`); motor 0 ise boş + "motor kalibre değil — ağırlık 0" | Risk Özeti |
| 3 | "yonlendirici" yerine `motor_kaynagi` (hafif / damla / gaz / OpenFOAM tablosu) + `motor_auc` | Risk Özeti, Güven, Çözüm Ayarları |
| 4 | ana sayı birleşik ihtimal; model ve motor yanında ağırlıklarıyla | Risk Özeti |
| 5 | otomatik vaka başlığı her çözümde yenilenir (elle yazılan korunur) | ağaç |
| 6 | güven v2 ana skor (bant rengi), bileşen çubukları, cezalar, kaynak tablosu, tek cümle sebep | Risk Özeti, Güven Analizi |
| 7 | 12 adımlık `tahmin.adimlar` tablosu | Çözüm, Günlük |
| 8 | KARAR kalın, "Doğrulanamayan sayılar" sarı kutu, girdiler değiştiyse eski yorum gizli, "LLM malzemeyi tanıyor (~30 s)" | Yapay Zeka Yorumu |
| 9 | kullanıcı malzemesi formu: LLM önerisi (her alan "LLM önerisi, doğrulanmadı") -> düzelt -> onayla; onaysız hiçbir hesaba girmez; onaylıda motor ağırlığı 0 + uyarı; internetsiz / reddedildi ayrı mesaj | Kütüphane > Malzemeler, Risk Özeti |
| 10 | Motor Ayrıntıları: damlada K, sönme çapı, soğuk alev, ±belirsizlik; gazda alev boyu/yarıçapı, sönme türü, kalibre değil uyarısı; kütüphaneden LFL/UFL, parlama noktası | Sonuçlar > Motor Ayrıntıları |
| 11 | Topluluk > Deney verisi: form, CSV, şablon, liste + durum renkleri, moderatör onayı, dışa/içe aktar, "modele girmez" notu, kullanıcı malzemesi paylaşımı; örnek vakalar yeni backend'le yeniden çözüldü (`ornek_guncelle.py`) | Topluluk |

## Köprüde (cekirdek/kopru.py) yeni metotlar

`malzeme_kutuphanesi`, `malzeme_tani`, `malzeme_oner`, `kullanici_malzeme_kaydet / onayla / sil / disa_aktar /
ice_aktar`, `tv_ekle / listele / onayla / reddet / csv_yukle / sablon / disa_aktar / ice_aktar`.

## Uçtan uca deneme (2026-11-13, `uctan_uca.py`, 25 görüntü, hata yok)

| senaryo | tanıma | motor (ağırlık) | birleşik | güven v2 |
|---|---|---|---|---|
| PMMA Mars %30 70 kPa | liste | hafif (0,38) | 0,969 | 16 düşük |
| metanol ISS | liste | damla (0,44) | 0,987 | 87 yüksek |
| heptan Mars | liste | damla (0,50) | 0,990 | 19 düşük |
| etilen ISS | liste | gaz (0,54) | 0,446 | 76 yüksek |
| metan ISS | liste | gaz (0, jet kalibre değil) | 0,969 | 32 düşük |
| Lexan | kütüphane | hafif / PMMA (0) | 0,955 | 15 düşük |
| IPA | kütüphane | damla / 1-propanol (0) | 0,997 | 48 düşük |
| kevlar | kütüphane | hafif / Nomex (0) | 0,442 | 39 düşük |
| hidrazin | kütüphane | yok (uygun motor yok) | 0,988 | 9 düşük |
| asdfgh | önbellek: reddedildi | — | tanınmadı (sonuç üretilmez) | — |
| internetsiz PMMA ISS | liste | hafif (0,38) | 0,971 | 85 yüksek; yorum: "bağlantı hatası" |

Süpürme 17 nokta (2,3 s, hata 0); vaka kaydet / aç; topluluk kaydı ekle -> `celiski` etiketi -> moderatör onayı ->
dışa aktarım; kullanıcı malzemesi (aerogel) LLM önerisi -> onay -> tahminde tanındı. Testler: `--sinama` BAŞARILI,
`entegrasyon_test.py` 35/35, `gaz_test.py` 14/14 (değişiklik yok), `damla_test.py`: kalibre heptan/metanol aynı;
değişen yalnız kalibre olmayan etanol (p 0,994 -> 0,998) ve n-dekan (sönme sınırı %6,5 -> %5,0) — yakıt türü artık
kütüphaneden "sivi" geliyor (madde 1), hidrolik yağı (kütüphaneden tanınıyor, motor ağırlığı 0).

## Malzeme kütüphanesi 2. genişletme (2026-11-13): 44 -> 106 malzeme

Kurallar aynı: özellik uydurulmadı (SFPE El Kitabı tabloları kaynak metinde denetlenir, NIST WebBook, `chemicals`,
veri seti); kaynak yoksa alan boş. Eski 44 kaydın içeriği birebir aynı (yalnız `kategori` ve `ozel` alanı eklendi).

- **Yeni alanlar:** `kategori` (13 grup) ve `ozel` (`oksitleyici` | `yanmaz` | `pil`). Kütüphane JSON'unda `sayim` özeti.
- **Sayım:** toplam 106 · katı 68, sıvı 23, gaz 15 · plastik 18, gaz 15, kıyafet/kumaş 12, elektronik/kablo 9,
  yakıt/itici 8, kauçuk/conta 7, yalıtım/köpük 7, akışkan/yağ 7, ambalaj/diğer 6, temizlik/çözücü 5,
  kompozit/yapı 5, pil 4, yiyecek 3 · motorda kalibre 9, veri setinde nokta var 30, veri yok 67 ·
  özel: oksitleyici 3 (O₂, N₂O, H₂O₂), yanmaz 3 (PFPE, saf cam elyaf, alüminyum), pil 1 (Li-ion hücre).
- **Tanıma:** eş anlamlılar otomatik bağlı (üretici çakışmada durur). `tahmin()` özel durumda **sayı üretmez**:
  `ozel_durum` alanı + uyarı döner; arayüz "Oksitleyici / Yanıcı değil / Pil" ekranını gösterir, grafikler çizilmez.
- **Arayüz:** Kütüphane > Malzemeler'de kategori süzgeci (sayılarıyla), kartta kategori ve özel durum etiketi,
  ayrıntıda Kategori / Özel durum satırları.
- **Sınama:** kalibre malzemelerde 18 vaka + oksijen/akış eğrileri eski kodla birebir aynı; `entegrasyon_test.py`
  35/35; `--sinama` BAŞARILI. Görüntüler: `of_gorsel/ekran/kutuphane2/` (`ekran_kutuphane.py`).
- **Kaynak metin yolu:** SFPE metinleri harici diskte; `malzeme_kutuphanesi_uret.py` önce `MALZEME_METIN`, sonra
  `/mnt/ssd/nasaspaceapp/metinler`, sonra `/media/user/Extreme Pro/nasaspaceapp/metinler` arar.
- **Sınır:** benzeri olmayan (motor yok) ama özel olmayan malzemelerde (silikon yağı, UDMH, H₂S) risk modeli
  malzemeyi tanımadan çalışır (hidrazindeki gibi); uyarı bunu söyler.

## Düzeltmeler (2026-11-13, kütüphane 2. genişletmeden sonra)

- **Aerojel (silika)** özel durum `yanmaz` (not: organik katkılı/elyaflı battaniye türleri farklı olabilir);
  kullanıcı kütüphanesindeki "aerojel" kopyası silindi (107 -> 106). Silikon yağı, UDMH, H₂S yanıcı (özel değil);
  motor benzeri olmayan bütün kütüphane malzemelerinde uyarı: "Motor yok, model bu malzemeyi tanımıyor".
- **Gaz, numune tipi verilmeden:** varsayılan numune `porous_sphere` (sızıntı, küre; önceden etilende düz brülör,
  metanda jet). Debi bilinmediği için gaz motoru çalıştırılmaz (ağırlık 0), uyarı "Debi bilinmiyor; gaz motoru
  kullanılmadı", sonuçta `gaz_motoru_kullanilmadi`. Etilen ISS: birleşik 0,446 -> **0,961 (= model)**; metan ISS
  0,969 -> 0,946 (numune değişti, model girdisi). Numune tipi seçilirse (ör. `flat_burner`) eski davranış: 0,446.
  Akış eğrisi de bu durumda motor değeri vermez.
- **Sönme türü "su emme":** alkol damlasında (metanol, etanol, propanol) sönme `kimyasal` çıkıp su emme kapatılınca
  (k_w -> 0) sönme kalkıyor ya da sönme çapı yarıdan fazla küçülüyorsa etiket `su_emme` (yalnız etiket; motor.py
  sarmalayıcısında, motor sayıları değişmedi).
- **± yalnız kalibre yakıtta:** Motor Ayrıntıları'nda kalibre edilmemiş yakıtta (etanol, dekan, kalibre değil gaz
  geometrisi, kütüphane eşlemesi) ± bandı gösterilmez; yerine açıklama.
- **Düşük güven cümlesi:** arka uç artık v2 skorunu ve somut sebepleri yazar: "Güven düşük (16/100): bu koşula yakın
  NASA deneyi yok; kalibrasyon kapsamı dışı." (NASA deneyi yok/az, cezalar, motor kullanılmadı / zayıf). Arayüz aynı
  kuralı izler.

## Bilinen sınırlar

- (Giderildi) Etilen ISS numune tipi verilmeden birleşik %45 idi; artık gaz motoru debisiz kullanılmıyor: %96.
- Windows'ta (Edge WebView2) pywebview 6 ile `file://` videoların ve eval'in davranışı denenmedi.
- pywebview GTK `evaluate_js` uzunluğu karakterle verir, WebKit bayt bekler: ASCII dışı karakterli betik kesilir.
  `pywebview_hazirla` yamaladı (\uXXXX kaçışı); uygulamanın kendi çağrıları zaten ASCII (json.dumps).
- Ekran kilitliyken GTK penceresi çizmez: görüntü sürücüleri Xephyr'de çalışır. Xephyr'de (GPU yok) oynayan video
  WebKit'i kilitler: `--videosuz`. Video oynatma gerçek oturumda (Wayland) doğrulandı: readyState 4, 10,1 s.
- Tanınmayan malzemede (asdfgh) sonuç üretilmez; Risk Özeti "Malzeme tanınmadı" ekranı gösterir.

## ayrıntılı OpenFOAM motoru — 2026-11-14
Ayrı kaynak; hızlı motor ve model sayıları değişmedi (OpenFOAM koşusu yokken `tahmin` çıktısı birebir aynı). İçe aktarma `ofm_ice_aktar.py`
(katı/sıvı/gaz, `BILGI.json`), analiz `ofm_analiz.analiz_tur`, deney karşılaştırması `ofm_karsilastir.py`, yönlendirici `ofm_motor.py`
(mesafe ≤ 1,5; ağırlık = min(0,5; doğrulama başarısı × (1 − mesafe/1,5)); doğrulama yoksa ağırlık 0 + uyarı).
Arayüz: Çözüm > Ayrıntılı Motor (OpenFOAM), Motor Ayrıntıları yan yana tablo, Kütüphane > Ayrıntılı koşular, "OpenFOAM motoruyla koş" (kuyruk, 2 çekirdek).
Testler: `python3 ofm_test.py` (19/19, sahte koşular), `dashboard/ofm_arayuz_test.py` (Xephyr), `entegrasyon_test.py` 35/35, `--sinama`.
Çözüm İzleyici ve sağ paneli sadeleştirme: bkz. `js/izleyici.js`, `cekirdek/izleyici.py`.

### Çözüm türü: Ayrıntılı (varsayılan) | Hızlı — 2026-11-14
Araç çubuğunda ve Analiz Ayarları'nda "Çözüm türü"; vaka dosyasına kaydedilir. ÇÖZ, Ayrıntılı'da (`js/ayrintili.js`): destek denetimi (şimdilik katı/SIBAL,
kalınlık OpenFOAM vaka ağına ±%5) → başlatma penceresi (tahmini süre, çekirdek varsayılanı nproc−2, başka foamRun uyarısı) → OpenFOAM vakasının KOPYASINDA
(`ofm_vaka.py`: O2, basınç, akış; g>0'da constant/fluid/g + 0/fluid/p_rgh, ilk dakikada günlükten kaldırma denetimi) koşu, Çözüm İzleyici kuyruğunda →
bitince otomatik analiz (içe aktarma) → Risk Özeti'nde ana sonuç OpenFOAM motorundan (yandı/söndü, tutuşma, yayılma, Tmax), risk modeli ve hızlı motor "karşılaştırma";
güven = deney doğrulaması (yoksa "doğrulanmadı"). Koşu sürerken hızlı çözüm "ön tahmin" bandıyla (açık/kapalı). 0,5 ağırlık tavanı yalnız Hızlı birleşik ihtimalde.
Desteklenmeyen vakada "Hızlı çözümle devam". Test: `dashboard/ayrintili_test.py` (Xephyr), `ofm_test.py` 29/29.

### 3B görüntüleyici (ANSYS benzeri) — 2026-11-14
Girdi düğümlerinde (Ortam, Malzeme, Numune, Akış) ortadaki tablo yerine 3B sahne (`js/sahne3b.js`, three.js r160 YEREL `vendor/three.min.js`):
levha + tutucu + tel / fiberde damla + ateşleyiciler / gözenekli küre, jet, düz brülör; kabin kutusu, ölçüler (mm), zemin ızgarası, g oku (bant), akış okları,
O₂/basınç etiketi; ön/üst/yan/izometrik, sığdır, tel çerçeve, ağ (SIBAL: OpenFOAM polyMesh, 33 320 kenar); seçili düğüm vurgulanır. SIBAL'de boyutlar
OpenFOAM vakasından, diğerlerinde "temsili". Sonuç: "3B Alan Sonucu" düğümü — `of_3b_disa_aktar.py` (pvpython, ResampleToImage, uint16, <30 MB)
çıktısından izo yüzeyleri (tarayıcıda marching tetrahedra, ~70 ms), z kesiti, damlalar, renk ölçeği, zaman + oynat, alan (T/O₂/yakıt/U), kesit konumu,
izo değerleri, "ParaView'da aç" (pv_3b.py ya da Decomposed Case betiği). Koşu TAMAM bitince dışa aktarma arka planda başlar (Çözüm İzleyici kancası).
Test: `dashboard/sahne3b_test.py` (Xephyr).
