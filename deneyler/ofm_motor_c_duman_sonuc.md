# OpenFOAM motor_c — derleme, damla karşılaştırması, duman testi (2026-11-14)

Aslı `~/Desktop/motor_c`; çalışılan kopya `~/motor_c_deneme` (git'te değil). OpenFOAM 14, nice 19, derleme 2 çekirdek.
Test sırasında başka bir oturum 12 çekirdekte `foamRun` koşturuyordu; süreler yük altındadır.

## Derleme
| bileşen | sonuç |
|---|---|
| piroliz `libFlameInFreefallSolid.so` | derlendi, md5 `MOTOR_KILIT.json` ile aynı (ddea5b2b…) |
| damla `libFlameInFreefallDroplet.so` | derlendi, uyarı/hata yok |
| `damlaBirimTest` | derlendi |

## Damla C++ ↔ Python
C++ paketinde yalnız damla ilkelleri var (pDoyma, LBuhar, Yfs, mpp, TlAdim, rsAdim) ve OpenFOAM parçacık/sınır koşulları;
`test_vektorleri.json`'un hızlı mod çıktıları (yanma, K, sönme çapı, en az O2, sönme türü) C++'ta hesaplanmıyor,
bu yüzden 40 vaka C++ ile karşılaştırılamaz. Karşılaştırılabilen ilkeller: 5 yakıt × 7 T × 4 p = 140 nokta,
en büyük bağıl fark 0 (4 büyüklükte de), 1e-9 üstü nokta yok.

## Duman testi (en çok 120 s duvar saati, 4 çekirdek)
| vaka | modüller | başladı | çöktü | sim. süre | Δt | Tmax (gaz / sibal / tel) | tutuşma | hız | tam koşu |
|---|---|---|---|---|---|---|---|---|---|
| katı Saffire-III S1 | piroliz + kinetik + radyasyon (fvDOM) | evet | hayır | 0,0244 s (2465 adım) | 1e-6 → 2e-5 (üst sınır) | 317,9 / 307,7 / 320,0 K | yok (tutuşma ~1,9 s'de beklenir, erişilmedi) | 116 s / 0,0244 sim-s ≈ 4760 s/sim-s (artış evresi dahil, kötümser); 0,047 s/adım | adım sabitlenince 10 s ≈ 500 000 adım ≈ 6,5 saat (kaba) |
| sıvı: damla + kinetik + radyasyon | — | koşulmadı: pakette damla vakası yok | | | | | | | |
| gaz: kinetik + radyasyon | — | koşulmadı: pakette gaz vakası yok | | | | | | | |
