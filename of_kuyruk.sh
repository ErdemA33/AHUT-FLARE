#!/bin/bash
# OpenFOAM uzun koşu kuyruğu (internetsiz, gözetimsiz). Aynı anda tek OpenFOAM koşusu.
# Sıra (kaldırma düzeltmesi, 2026-11-10): sızıntı uzay 0.4 -> 1.0 s (devam) -> sızıntı Mars 0 -> 1.0 s (p_rgh ile
#   baştan) -> of_sizinti.py --analiz -> sızıntı önbellekleri silinir -> of_gorsel.py
# (Önceki sıra: A ışınımsız -> B sızıntı 0.4 s -> P1 devam; hepsi 2026-11-10 09:11'de bitti.)
# Bekçi (arka planda, her dakika): Δt < 1e-9 s, Tmax > 4000 K (sızıntıda ateşleyici darbesi t<0.03 s hariç)
#   ya da simülasyon zamanı/log 15 dk ilerlemezse koşuyu durdurur, "IRAKSADI" yazar; sürücü sıradakine geçer.
# Canlı özet (dakikada bir satır): of_kosular/canli.log
# Başlatma:  nohup setsid ./of_kuyruk.sh >> of_kosular/kuyruk.log 2>&1 &
cd "$(dirname "$0")" || exit 1
K=of_kosular
CANLI=$K/canli.log
yaz() { echo "$(date '+%F %T') $*" | tee -a "$CANLI"; }

bekci() {
  local son_t="" son_deg=$(date +%s) onc_t="" onc_zaman=""
  while true; do
    sleep 60
    local mp="" p
    for p in $(pgrep -x mpirun); do [ -r "/proc/$p/cwd" ] && readlink "/proc/$p/fd/1" >/dev/null 2>&1 && mp=$p && break; done
    if [ -z "$mp" ]; then echo "$(date '+%F %T') çalışan OpenFOAM koşusu yok (hazırlık/analiz/bekleme)" >> "$CANLI"; son_t=""; continue; fi
    local vaka logf ad bit simdi
    vaka=$(readlink "/proc/$mp/cwd"); logf=$(readlink "/proc/$mp/fd/1")
    ad="$(basename "$(dirname "$vaka")")/$(basename "$vaka")"
    bit=$(awk '/^endTime/{gsub(";","",$2);print $2}' "$vaka/system/controlDict")
    simdi=$(date +%s)
    local ozet t dt
    ozet=$(tail -c 400000 "$logf" | awk '/^Time = /{t=$3} /^deltaT = /{d=$3} END{print t, d}')
    t=${ozet% *}; dt=${ozet#* }
    local dat Tm
    dat=$(ls -d "$vaka"/postProcessing/cellMax\(T\)/* 2>/dev/null | sort -V | tail -1)
    Tm=$(grep -v '^#' "$dat/volFieldValue.dat" 2>/dev/null | tail -1 | awk '{print $2}')
    [ -z "$t" ] && t=0; [ -z "$dt" ] && dt=1; [ -z "$Tm" ] && Tm=0
    # kalan süre: son dakikadaki ilerleme hızından
    local kalan="?"
    if [ -n "$onc_t" ] && [ "$onc_vaka" = "$vaka" ]; then
      kalan=$(awk -v t="$t" -v o="$onc_t" -v s="$((simdi-onc_zaman))" -v b="$bit" \
        'BEGIN{h=(t-o)/s; if(h>0) printf "%.2f sa", (b-t)/h/3600; else print "ilerlemiyor"}')
    fi
    onc_t=$t; onc_zaman=$simdi; onc_vaka=$vaka
    echo "$(date '+%F %T') koşu $ad | t = $t s / $bit | Δt = $dt s | Tmax = $Tm K | kalan ~$kalan (üst sınıra göre)" >> "$CANLI"
    # ilerleme takibi
    if [ "$t" != "$son_t" ]; then son_t=$t; son_deg=$simdi; fi
    local logyas=$((simdi - $(stat -c %Y "$logf")))
    local neden=""
    awk -v d="$dt" 'BEGIN{exit !(d<1e-9)}' && neden="zaman adımı $dt s < 1e-9 s"
    if [ -z "$neden" ] && awk -v T="$Tm" -v t="$t" -v a="$ad" 'BEGIN{exit !(T>4000 && !(a ~ /^sizinti/ && t<0.03))}'; then
      neden="Tmax $Tm K > 4000 K"; fi
    [ -z "$neden" ] && [ $((simdi - son_deg)) -ge 900 ] && neden="simülasyon zamanı 15 dk ilerlemedi (t = $t s)"
    [ -z "$neden" ] && [ "$logyas" -ge 900 ] && neden="log 15 dk yazılmadı"
    if [ -n "$neden" ]; then
      local msg="IRAKSADI: $ad durduruldu ($neden, t = $t s). Sıradakine geçiliyor."
      yaz "$msg"
      case "$ad" in sizinti/*) echo "$(date '+%F %T') $msg" >> $K/sizinti_ilerleme.log;;
                    *) echo "$(date '+%F %T') $msg" >> $K/tek_damla_ilerleme.log;; esac
      echo "$msg" > "$vaka/IRAKSADI"
      kill "$mp"; sleep 30; kill -0 "$mp" 2>/dev/null && kill -9 "$mp"
      pkill -9 -x foamRun 2>/dev/null
      son_t=""; onc_t=""
    fi
  done
}

bekci &
BEKCI=$!
trap 'kill $BEKCI 2>/dev/null' EXIT
echo $$ > $K/kuyruk.pid
yaz "kuyruk (bekçili, kaldırma düzeltmesi) başladı, PID $$, bekçi PID $BEKCI"

yaz "sızıntı uzay: 0.4 s'den 1.0 s'ye devam"
python3 of_sizinti.py --kos --varyant uzay >> $K/sizinti_surucu.log 2>&1; yaz "sızıntı uzay bitti, çıkış $?"
yaz "sızıntı Mars: p_rgh (gaz kaldırması) ile 0'dan 1.0 s'ye"
python3 of_sizinti.py --kos --varyant mars >> $K/sizinti_surucu.log 2>&1; yaz "sızıntı Mars bitti, çıkış $?"

python3 of_sizinti.py --analiz >> $K/analiz.log 2>&1; yaz "sızıntı analizi çıkış $?  -> of_sizinti.png, of_sizinti_en.png"
rm -f of_gorsel/onbellek_sizinti_uzay.npz of_gorsel/onbellek_sizinti_mars.npz
python3 of_gorsel.py >> $K/analiz.log 2>&1; yaz "of_gorsel.py çıkış $?  -> of_gorsel.html, of_gorsel/*.gif, *.png"
yaz "kuyruk bitti"
