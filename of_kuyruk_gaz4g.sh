#!/bin/bash
# Metan (gaz) sızıntısı — 4 yerçekimli 3B ve 2B videolar için kuyruk (of_kuyruk_gaz.sh'den; bekçi ve denetimler aynı).
# Sıra: 3B uzay / Mars / Ay / Dünya (15 çekirdek, sırayla; uzay ve Mars yeniden: önceki inceltmede 20 kare kalmıştı)
#   -> gaz_3b_4g, gaz_kesit_4g videoları -> video denetimi (panel başına) -> 3B inceltme
#   -> 2B ×4 yeniden (etiketleri panel üstüne taşınmış 2B video için tam seri) -> gaz2d_4g -> denetim -> 2B inceltme
#   -> analiz (8 koşu) -> of_gorsel.py -> masaüstü.  Her adım denetlenir; biri tutmazsa HATA, sonrakine geçilmez.
# Başlatma:  nohup setsid ./of_kuyruk_gaz4g.sh >> of_kosular/kuyruk_gaz4g.log 2>&1 < /dev/null &
# ---- (aşağısı of_kuyruk_gaz.sh v3 ile aynı başlık / bekçi)
#   0) damla oturumunun bootstrap işleri bitene kadar bekler (pgrep -f, yalnız python süreçleri: komut satırı
#      "python3 ... damla_motoru.py --bootstrap" ile BAŞLAYAN; metninde bu yazı geçen kabuklar sayılmaz), sonra 15 çekirdek
#   1) kısa testler (15 çekirdek, 0,05 s, 6 vaka) -> of_gaz.py --plan (toplam > 9 sa ise 2B kabalaşır)
#   2) koşular (1,0 s): 3B uzay -> 3B Mars -> 2B g = 0 -> 1,62 -> 3,73 -> 9,81
#   3) of_gaz.py --analiz -> pv_gaz_video.py (3 video, TR+EN) -> of_gorsel.py -> videolar masaüstüne
# v2 (v1 02:41'de çöken koşulara rağmen 'hata 0' dedi): HER adım denetlenir — foamRun çıkış kodu, son zaman = endTime,
#   log'da 'End', çökme izi yok; videolar > 1 MB. Biri tutmazsa HATA yazılır, sonraki adımlara GEÇİLMEZ.
# Bekçi (her dakika, canlı log of_kosular/canli_gaz.log):
#   saat | koşu | adım | t | % | Δt | Tmax | Co | kalan | boş disk
#   - eski zamanlardan gereksiz alanları siler (of_gaz.py --buda)
#   - boş disk başlangıçtakinin yarısının altına (ya da < 1 GB) inerse: DİSK — koşu ve kuyruk durur
#   - Δt < 1e-9 s, Tmax > 4000 K (t > 0,03 s), 15 dk ilerleme yok / log yazılmıyor -> IRAKSADI (sıradakine geç)
#   - kaldırmalı koşularda (g != 0) ilk dakikada p_rgh çözülmüyorsa -> KALDIRMA_YOK
# Başlatma:  nohup setsid ./of_kuyruk_gaz.sh >> of_kosular/kuyruk_gaz.log 2>&1 < /dev/null &
cd "$(dirname "$0")" || exit 1
export OMP_NUM_THREADS=1
K=of_kosular
CANLI=$K/canli_gaz.log
DUR=$K/gaz_DURDUR_DISK
yaz() { echo "$(date '+%F %T') | $*" | tee -a "$CANLI"; }
bos_gb() { df -B1 --output=avail . | tail -1 | awk '{printf "%.2f", $1/1e9}'; }
F0=$(bos_gb)
SINIR=$(awk -v f="$F0" 'BEGIN{s=f/2; if(s<1)s=1; printf "%.2f", s}')

durdur() {   # $1 mpirun pid, $2 vaka, $3 etiket, $4 mesaj
  yaz "$3: $4"
  echo "$3: $4" > "$2/$3"
  kill "$1" 2>/dev/null; sleep 30; kill -0 "$1" 2>/dev/null && kill -9 "$1"
  for p in $(pgrep -x foamRun); do readlink "/proc/$p/cwd" | grep -q "$2" && kill -9 "$p"; done
}

bekci() {
  local son_t="" son_deg=$(date +%s) onc_vaka="" bas_zaman=0 prgh_kontrol=""
  local -a h_t=() h_s=() h_n=()
  while true; do
    sleep 60
    local mp="" p
    for p in $(pgrep -x mpirun); do
      readlink "/proc/$p/cwd" 2>/dev/null | grep -qE "gaz3d_ince|gaz2d" && mp=$p && break
    done
    local bos; bos=$(bos_gb)
    if [ -z "$mp" ]; then
      echo "$(date '+%H:%M:%S') | (koşu yok: bekleme / hazırlık / analiz) | boş disk $bos GB" >> "$CANLI"
      son_t=""; h_t=(); h_s=(); h_n=(); continue
    fi
    local vaka logf ad bit simdi
    vaka=$(readlink "/proc/$mp/cwd"); logf=$(readlink "/proc/$mp/fd/1")
    ad="$(basename "$(dirname "$vaka")")/$(basename "$vaka")"
    bit=$(awk '/^endTime/{gsub(";","",$2);print $2}' "$vaka/system/controlDict")
    simdi=$(date +%s)
    if [ "$vaka" != "$onc_vaka" ]; then onc_vaka=$vaka; bas_zaman=$simdi; prgh_kontrol=""; h_t=(); h_s=(); h_n=(); son_deg=$simdi; fi
    local ozet t dt co n
    ozet=$(tail -c 400000 "$logf" | awk '/^Courant Number mean/{c=$6} /^Time = /{t=$3; sub("s$","",t)} /^deltaT = /{d=$3} END{print t, d, c}')
    read -r t dt co <<< "$ozet"
    n=$(grep -c '^Time = ' "$logf")
    local dat Tm
    dat=$(ls -d "$vaka"/postProcessing/cellMax\(T\)/* 2>/dev/null | sort -V | tail -1)
    Tm=$(grep -v '^#' "$dat/volFieldValue.dat" 2>/dev/null | tail -1 | awk '{printf "%.0f", $2}')
    [ -z "$t" ] && t=0; [ -z "$dt" ] && dt=1; [ -z "$Tm" ] && Tm=0; [ -z "$co" ] && co="?"
    h_t+=("$t"); h_s+=("$simdi"); h_n+=("$n")
    if [ ${#h_t[@]} -gt 6 ]; then h_t=("${h_t[@]:1}"); h_s=("${h_s[@]:1}"); h_n=("${h_n[@]:1}"); fi
    local kalan="?"
    if [ ${#h_t[@]} -ge 2 ]; then
      kalan=$(awk -v t="$t" -v o="${h_t[0]}" -v s="$((simdi - h_s[0]))" -v b="$bit" \
        'BEGIN{h=(t-o)/s; if(h>0){k=(b-t)/h; printf "%dsa%02ddk", int(k/3600), int((k%3600)/60)} else printf "ilerlemiyor"}')
    fi
    local yuzde; yuzde=$(awk -v t="$t" -v b="$bit" 'BEGIN{printf "%.1f", 100*t/b}')
    echo "$(date '+%H:%M:%S') | $ad | adım $n | t = $t s | %$yuzde | Δt = $dt s | Tmax = $Tm K | Co = $co | kalan ~$kalan | boş disk $bos GB" >> "$CANLI"
    python3 of_gaz.py --buda "$vaka" >> $K/gaz_budama.log 2>&1
    if [ "$t" != "$son_t" ]; then son_t=$t; son_deg=$simdi; fi
    local logyas=$((simdi - $(stat -c %Y "$logf")))
    if awk -v b="$bos" -v s="$SINIR" 'BEGIN{exit !(b<s)}'; then
      touch "$DUR"
      durdur "$mp" "$vaka" "DISK_DOLU" "DİSK: boş disk $bos GB < sınır $SINIR GB (başlangıç $F0 GB'nin yarısı), $ad durduruldu (t = $t s). Kuyruk duruyor."
      son_t=""; continue
    fi
    local g; g=$(awk '/^value/{gsub(/[();]/," "); print $3}' "$vaka/constant/g")
    if [ -z "$prgh_kontrol" ] && [ $((simdi - bas_zaman)) -ge 60 ] && [ "$n" -gt 0 ] && awk -v g="$g" 'BEGIN{exit !(g!=0)}'; then
      prgh_kontrol=1
      if ! grep -q "Solving for p_rgh" "$logf"; then
        durdur "$mp" "$vaka" "KALDIRMA_YOK" "KALDIRMA YOK: $ad (g = $g) ilk dakikada p_rgh çözmedi, durduruldu (t = $t s)."
        son_t=""; continue
      fi
      echo "$(date '+%H:%M:%S') | $ad: g = $g, p_rgh çözülüyor (kaldırma açık) ✓" >> "$CANLI"
    fi
    local neden=""
    awk -v d="$dt" 'BEGIN{exit !(d<1e-9)}' && neden="zaman adımı $dt s < 1e-9 s"
    if [ -z "$neden" ] && awk -v T="$Tm" -v t="$t" 'BEGIN{exit !(T>4000 && t>0.03)}'; then neden="Tmax $Tm K > 4000 K"; fi
    # takılma denetimleri koşu başladıktan 2 dk sonra (yeni koşunun ilk satırından önce eski log zamanı görünmesin)
    if [ $((simdi - bas_zaman)) -ge 120 ]; then
      [ -z "$neden" ] && [ $((simdi - son_deg)) -ge 900 ] && neden="simülasyon zamanı 15 dk ilerlemedi"
      [ -z "$neden" ] && [ "$logyas" -ge 900 ] && neden="log 15 dk yazılmadı"
    fi
    if [ -n "$neden" ]; then
      durdur "$mp" "$vaka" "IRAKSADI" "IRAKSADI: $ad durduruldu ($neden, t = $t s). Sıradakine geçiliyor."
      son_t=""
    fi
  done
}

rm -f "$DUR"
bekci &
BEKCI=$!
trap 'kill $BEKCI 2>/dev/null' EXIT
echo "$$ $BEKCI" > $K/kuyruk_gaz4g.pid
hata_dur() { yaz "HATA: $* — sonraki adımlara geçilmedi, kuyruk duruyor"; exit 1; }
yaz "===== kuyruk_gaz4g başladı: kuyruk PID $$, bekçi PID $BEKCI, boş disk $F0 GB, disk sınırı $SINIR GB; boş çekirdek $(python3 -c 'import gaz_motoru as g; print(g.bos_cekirdek(16))')/16 ====="

testler() {   # $@: vakalar
  for v in "$@"; do case $v in 3b_*) rm -f $K/gaz3d_ince/test_$v.json;; *) rm -f $K/gaz2d/test_$v.json;; esac; done
  python3 of_gaz.py --test --vaka "$@" --sure 0.05 >> $K/gaz_surucu.log 2>&1
  local oz
  oz=$(python3 - "$@" <<'PYEOF'
import json, sys
kotu, satir = [], []
for v in sys.argv[1:]:
    f = ("of_kosular/gaz3d_ince/" if v.startswith("3b") else "of_kosular/gaz2d/") + f"test_{v}.json"
    try:
        d = json.load(open(f))
    except Exception:
        kotu.append(v); continue
    satir.append(f"{v} rc {d['rc']} son {d['son_zaman']} End {d['End']} çökme {d['cokme']}")
    if d["hata"]:
        kotu.append(v)
print(("KOTU:" + ",".join(kotu) if kotu else "TAMAM") + " | " + " ; ".join(satir))
PYEOF
)
  yaz "testler (0,05 s): $oz"
  case "$oz" in TAMAM*) ;; *) hata_dur "kısa testlerden en az biri başarısız: $oz";; esac
  python3 of_gaz.py --test-temizle >> $K/gaz_surucu.log 2>&1
}
kosular() {   # $@: vakalar (sırayla, 15 çekirdek; of_gaz.py --kos: rc 0 + son zaman = endTime + End + çökme yok)
  local v d r
  for v in "$@"; do
    [ -e "$DUR" ] && hata_dur "DİSK bayrağı var, $v başlatılmadı"
    yaz "$v: 0 -> 1,0 s başlıyor (15 çekirdek)"
    python3 of_gaz.py --kos --vaka $v >> $K/gaz_surucu.log 2>&1; r=$?
    case $v in 3b_*) d=$K/gaz3d_ince/${v#3b_};; *) d=$K/gaz2d/${v#2b_};; esac
    python3 of_gaz.py --buda $d >> $K/gaz_budama.log 2>&1
    [ $r -ne 0 ] && hata_dur "$v tamamlanmadı (çıkış $r; $(cat $d/durum.json 2>/dev/null))"
    yaz "$v TAMAM: $(cat $d/durum.json) (boş disk $(bos_gb) GB)"
  done
}
videolar() {  # $1: tür(ler) (pvpython), sonra mp4 dosyaları
  local turler=$1; shift
  pvpython --force-offscreen-rendering pv_gaz_video.py $turler >> $K/gaz_analiz.log 2>&1 || hata_dur "pv_gaz_video.py $turler başarısız"
  local vd r s
  vd=$(python3 of_gaz.py --video-denetle "$@" --panel4 2>&1); r=$?
  while IFS= read -r s; do yaz "video: $s"; done <<< "$vd"
  [ $r -eq 0 ] || hata_dur "en az bir video boş / eksik / panellerinden biri sıcak bölge içermiyor"
}

V3="3b_uzay 3b_mars 3b_ay 3b_dunya"
V2="2b_0 2b_1.62 2b_3.73 2b_9.81"
# DEVAM_2B="2b_9.81": kaldığı yerden — 3B bölümü ve 2B kurulumu atlanır, yalnız verilen 2B koşular (yeniden) koşulur
if [ -n "$DEVAM_2B" ]; then
  yaz "DEVAM: 3B bölümü tamamdı (videolar denetimden geçti), 2B'de yalnız $DEVAM_2B yeniden koşuluyor"
  for v in $DEVAM_2B; do python3 of_gaz.py --kur --vaka $v >> $K/gaz_surucu.log 2>&1 || hata_dur "$v kurulum başarısız"; done
  kosular $DEVAM_2B
else
# ---- 1) 3B dört yerçekimi
python3 of_gaz.py --kur --vaka $V3 >> $K/gaz_surucu.log 2>&1 || hata_dur "3B kurulum başarısız"
yaz "3B kuruldu: $V3 (uzay ve Mars v3 ile birebir aynı kurulum, yeniden)"
testler $V3
kosular $V3
if [ -n "$SADECE_3B4" ]; then   # yalnız 3B izo-yüzey videosu yeniden (kesit ve 2B videolar değişmez)
  videolar "3b4" of_gorsel/gaz_3b_4g.mp4 of_gorsel/gaz_3b_4g_en.mp4
  python3 of_gaz.py --incelt $V3 >> $K/gaz_surucu.log 2>&1 || hata_dur "3B inceltme başarısız"
  for f in gaz_3b_4g gaz_3b_4g_en; do cp -f of_gorsel/$f.mp4 ~/Desktop/ || hata_dur "masaüstüne kopyalanamadı: $f.mp4"; done
  python3 of_gorsel.py >> $K/gaz_analiz.log 2>&1 || hata_dur "of_gorsel.py başarısız"
  yaz "kuyruk_gaz4g BİTTİ (SADECE_3B4: 3B yeniden koşuldu, gaz_3b_4g(_en).mp4 yeniden üretildi, masaüstüne kopyalandı; boş disk $(bos_gb) GB)"
  exit 0
fi
videolar "3b4 kesit4" of_gorsel/gaz_3b_4g.mp4 of_gorsel/gaz_3b_4g_en.mp4 of_gorsel/gaz_kesit_4g.mp4 of_gorsel/gaz_kesit_4g_en.mp4
python3 of_gaz.py --incelt $V3 >> $K/gaz_surucu.log 2>&1 || hata_dur "3B inceltme başarısız"
yaz "3B inceltildi (görüntüleyicinin 20 karesi + son; postProcessing korundu), boş disk $(bos_gb) GB"
# ---- 2) 2B (etiketleri panel üstüne taşınmış video için tam seri)
python3 of_gaz.py --kur --vaka $V2 >> $K/gaz_surucu.log 2>&1 || hata_dur "2B kurulum başarısız"
yaz "2B kuruldu: $V2 (v3 ile birebir aynı kurulum, yeniden)"
testler 2b_9.81
kosular $V2
fi
videolar "2d4" of_gorsel/gaz2d_4g.mp4 of_gorsel/gaz2d_4g_en.mp4
python3 of_gaz.py --incelt $V2 >> $K/gaz_surucu.log 2>&1 || hata_dur "2B inceltme başarısız"
yaz "2B inceltildi, boş disk $(bos_gb) GB"
# ---- 3) analiz, görüntüleyici, masaüstü
python3 of_gaz.py --analiz >> $K/gaz_analiz.log 2>&1 || hata_dur "of_gaz.py --analiz başarısız"
yaz "analiz TAMAM (8 koşu) -> of_gaz_sonuc.csv, of_gaz_motor_karsilastirma.csv, of_gaz_harita_3b/2b(_en).png, of_gaz_karsilastirma(_en).png"
python3 of_gorsel.py >> $K/gaz_analiz.log 2>&1 || hata_dur "of_gorsel.py başarısız"
yaz "of_gorsel.py TAMAM"
for f in gaz_3b_4g gaz_3b_4g_en gaz_kesit_4g gaz_kesit_4g_en gaz2d_4g gaz2d_4g_en; do
  cp -f of_gorsel/$f.mp4 ~/Desktop/ || hata_dur "masaüstüne kopyalanamadı: $f.mp4"
done
yaz "masaüstüne 6 video kopyalandı (~/Desktop)"
yaz "kuyruk_gaz4g BİTTİ, tüm adımlar TAMAM (boş disk $(bos_gb) GB) — GÖSTERİM, deney verisiyle doğrulanmadı"
