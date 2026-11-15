#!/bin/bash
# Metan (gaz) sızıntısı OpenFOAM kuyruğu (internetsiz, gözetimsiz) — GÖSTERİM, deney verisiyle doğrulanmadı.
#   0) damla oturumunun bootstrap işleri bitene kadar bekler (pgrep -f, yalnız python süreçleri: komut satırı
#      "python3 ... scripts/droplet_engine.py --bootstrap" ile BAŞLAYAN; metninde bu yazı geçen kabuklar sayılmaz), sonra 15 çekirdek
#   1) kısa testler (15 çekirdek, 0,05 s, 6 vaka) -> scripts/of_gas.py --plan (toplam > 9 sa ise 2B kabalaşır)
#   2) koşular (1,0 s): 3B uzay -> 3B Mars -> 2B g = 0 -> 1,62 -> 3,73 -> 9,81
#   3) scripts/of_gas.py --analiz -> scripts/pv_gas_video.py (3 video, TR+EN) -> scripts/of_visual.py -> videolar masaüstüne
# v2 (v1 02:41'de çöken koşulara rağmen 'hata 0' dedi): HER adım denetlenir — foamRun çıkış kodu, son zaman = endTime,
#   log'da 'End', çökme izi yok; videolar > 1 MB. Biri tutmazsa HATA yazılır, sonraki adımlara GEÇİLMEZ.
# Bekçi (her dakika, canlı log of_kosular/canli_gaz.log):
#   saat | koşu | adım | t | % | Δt | Tmax | Co | kalan | boş disk
#   - eski zamanlardan gereksiz alanları siler (scripts/of_gas.py --buda)
#   - boş disk başlangıçtakinin yarısının altına (ya da < 1 GB) inerse: DİSK — koşu ve kuyruk durur
#   - Δt < 1e-9 s, Tmax > 4000 K (t > 0,03 s), 15 dk ilerleme yok / log yazılmıyor -> IRAKSADI (sıradakine geç)
#   - kaldırmalı koşularda (g != 0) ilk dakikada p_rgh çözülmüyorsa -> KALDIRMA_YOK
# Başlatma:  nohup setsid ./scripts/of_queue_gas.sh >> of_kosular/kuyruk_gaz.log 2>&1 < /dev/null &
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
    python3 scripts/of_gas.py --buda "$vaka" >> $K/gaz_budama.log 2>&1
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
echo "$$ $BEKCI" > $K/kuyruk_gaz.pid
yaz "kuyruk_gaz başladı: kuyruk PID $$, bekçi PID $BEKCI, boş disk $F0 GB, disk sınırı $SINIR GB (yarısı)"

# ---- 0) damla bootstrap'i bekle
BS_DESEN='^python[0-9.]* +([^ ]*/)?droplet_engine\.py +--bootstrap'
bekle_bas=$(date +%s); son_rapor=0
while pgrep -f "$BS_DESEN" > /dev/null; do
  simdi=$(date +%s)
  if [ $((simdi - son_rapor)) -ge 600 ]; then
    yaz "bekleniyor: damla bootstrap işleri sürüyor ($(pgrep -fc "$BS_DESEN") süreç, $(( (simdi - bekle_bas) / 60 )) dk)"
    son_rapor=$simdi
  fi
  sleep 60
done
yaz "damla bootstrap işleri bitti (pgrep boş), $(( ($(date +%s) - bekle_bas) / 60 )) dk beklendi. 15 çekirdekle başlıyor."
sleep 30

# ---- 1) kısa testler (0,05 s, 6 vaka) + plan.  Her test: rc 0, son zaman = endTime, log'da End, çökme yok
hata_dur() { yaz "HATA: $* — sonraki adımlara geçilmedi, kuyruk duruyor"; exit 1; }
rm -f $K/gaz3d_ince/test_*.json $K/gaz2d/test_*.json
yaz "kısa testler (15 çekirdek, 0,05 s): 3b_uzay 3b_mars 2b_0 2b_1.62 2b_3.73 2b_9.81"
python3 scripts/of_gas.py --test --vaka 3b_uzay 3b_mars 2b_0 2b_1.62 2b_3.73 2b_9.81 --sure 0.05 >> $K/gaz_surucu.log 2>&1
ozet=$(python3 - <<'PYEOF'
import json, glob
kotu, satir = [], []
for f in sorted(glob.glob("of_kosular/gaz3d_ince/test_*.json") + glob.glob("of_kosular/gaz2d/test_*.json")):
    d = json.load(open(f))
    satir.append(f"{d['vaka']} rc {d['rc']} son {d['son_zaman']} End {d['End']} çökme {d['cokme']} "
                 f"{(d['s_per_sim_s'] or -1):.0f} s/sim-s Co {d['courant_max']}")
    if d["hata"]:
        kotu.append(d["vaka"])
print(("KOTU:" + ",".join(kotu) + " | " if kotu else "TAMAM | ") + " ; ".join(satir) + f" | n={len(satir)}")
PYEOF
)
yaz "testler: $ozet"
case "$ozet" in TAMAM*n=6) ;; *) hata_dur "kısa testlerden en az biri başarısız ya da eksik";; esac
python3 scripts/of_gas.py --plan >> $K/gaz_surucu.log 2>&1 || hata_dur "plan başarısız (bkz. $K/gaz_surucu.log)"
yaz "plan: $(cat $K/gaz_plan.json | tr -d '\n ')"
python3 scripts/of_gas.py --test-temizle >> $K/gaz_surucu.log 2>&1

# ---- 2) koşular: scripts/of_gas.py --kos ancak rc 0 + son zaman = endTime + End + çökme yok ise 0 döner
for v in 3b_uzay 3b_mars 2b_0 2b_1.62 2b_3.73 2b_9.81; do
  [ -e "$DUR" ] && hata_dur "DİSK bayrağı var, $v başlatılmadı"
  yaz "$v: 0 -> 1,0 s başlıyor (15 çekirdek)"
  python3 scripts/of_gas.py --kos --vaka $v >> $K/gaz_surucu.log 2>&1
  r=$?
  case $v in 3b_*) d=$K/gaz3d_ince/${v#3b_};; *) d=$K/gaz2d/${v#2b_};; esac
  python3 scripts/of_gas.py --buda $d >> $K/gaz_budama.log 2>&1
  [ $r -ne 0 ] && hata_dur "$v tamamlanmadı (çıkış $r; $(cat $d/durum.json 2>/dev/null))"
  yaz "$v TAMAM: $(cat $d/durum.json)"
done

# ---- 3) analiz -> videolar (her biri > 1 MB) -> görüntüleyici -> masaüstü
python3 scripts/of_gas.py --analiz >> $K/gaz_analiz.log 2>&1 || hata_dur "scripts/of_gas.py --analiz başarısız"
yaz "analiz TAMAM -> of_gas_map_3b/2b(_en).png, of_gas_comparison(_en).png, data/of_gas_result.csv, data/of_gas_engine_comparison.csv"
pvpython --force-offscreen-rendering scripts/pv_gas_video.py >> $K/gaz_analiz.log 2>&1 || hata_dur "scripts/pv_gas_video.py başarısız"
VID="of_visual/gaz_uzay_mars.mp4 of_visual/gaz_uzay_mars_en.mp4 of_visual/gaz_3b.mp4 of_visual/gaz_3b_en.mp4 of_visual/gaz2d_4g.mp4 of_visual/gaz2d_4g_en.mp4"
# boş video denetimi: kare >= 100, süre >= 9,5 s, > 150 kB, orta karede parlak piksel >= %0,3 (scripts/of_gas.py --video-denetle)
# ('> 1 MB' eşiği koyu arka planlı geçerli kesit videosunu da reddediyordu: v2'de 51 karelik geçerli video 0,16 MB)
vd=$(python3 scripts/of_gas.py --video-denetle $VID 2>&1); r=$?
while IFS= read -r s; do yaz "video: $s"; done <<< "$vd"
[ $r -eq 0 ] || hata_dur "en az bir video boş / eksik (yukarıdaki satırlar)"
python3 scripts/of_visual.py >> $K/gaz_analiz.log 2>&1 || hata_dur "scripts/of_visual.py başarısız"
yaz "scripts/of_visual.py TAMAM -> of_gorsel.html (Gaz sızıntısı grubu)"
for f in $VID; do cp -f "$f" ~/Desktop/ || hata_dur "masaüstüne kopyalanamadı: $f"; done
yaz "masaüstüne 6 video kopyalandı (~/Desktop)"
yaz "kuyruk_gaz BİTTİ, tüm adımlar TAMAM (boş disk $(bos_gb) GB) — GÖSTERİM, deney verisiyle doğrulanmadı"
