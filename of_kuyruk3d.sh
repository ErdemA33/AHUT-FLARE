#!/bin/bash
# Ayrıntılı 3B sızıntı kuyruğu (internetsiz, gözetimsiz): of_kosular/sizinti3d_ince/{uzay,mars}, 1,0 s, 15 çekirdek.
# Sıra: uzay -> Mars -> damla_vtk.py -> of_sizinti.py --analiz --ince -> of_gorsel.py -> pv_video.py sizinti_ince
#       -> (hepsi başarılıysa) kullanılmayan processor zamanları silinir.
# Bekçi (her dakika): Δt < 1e-9 s, Tmax > 4000 K (t > 0,03 s), 15 dk ilerleme yok -> IRAKSADI (sıradakine geç);
#   boş disk < 1 GB -> DİSK DOLU (koşu ve kuyruk durur); Mars'ta ilk dakikada p_rgh çözülmüyorsa -> KALDIRMA YOK.
#   Ayrıca eski zaman klasörlerinden analizde gerekmeyen alanları siler (of_sizinti3d.py --buda).
# Canlı log (dakikada bir satır): of_kosular/canli_3d.log
# Başlatma:  nohup setsid ./of_kuyruk3d.sh >> of_kosular/kuyruk3d.log 2>&1 < /dev/null &
cd "$(dirname "$0")" || exit 1
K=of_kosular
CANLI=$K/canli_3d.log
DUR=$K/sizinti3d_ince/DURDUR_DISK_DOLU
yaz() { echo "$(date '+%F %T') $*" | tee -a "$CANLI"; }
bos_gb() { df -B1 --output=avail . | tail -1 | awk '{printf "%.2f", $1/1e9}'; }

durdur() {   # $1 mpirun pid, $2 vaka, $3 etiket, $4 mesaj
  yaz "$3: $4"
  echo "$3: $4" > "$2/$3"
  kill "$1" 2>/dev/null; sleep 30; kill -0 "$1" 2>/dev/null && kill -9 "$1"
  pkill -9 -x foamRun 2>/dev/null
}

bekci() {
  local son_t="" son_deg=$(date +%s) onc_vaka="" bas_vaka="" bas_zaman=0 prgh_kontrol=""
  local -a h_t=() h_s=() h_n=()
  while true; do
    sleep 60
    local mp="" p
    for p in $(pgrep -x mpirun); do
      readlink "/proc/$p/cwd" 2>/dev/null | grep -q sizinti3d_ince && mp=$p && break
    done
    local bos; bos=$(bos_gb)
    if [ -z "$mp" ]; then
      echo "$(date '+%H:%M:%S') | çalışan koşu yok (hazırlık/analiz/bekleme) | boş disk $bos GB" >> "$CANLI"
      son_t=""; h_t=(); h_s=(); h_n=(); continue
    fi
    local vaka logf ad bit simdi
    vaka=$(readlink "/proc/$mp/cwd"); logf=$(readlink "/proc/$mp/fd/1"); ad=$(basename "$vaka")
    bit=$(awk '/^endTime/{gsub(";","",$2);print $2}' "$vaka/system/controlDict")
    simdi=$(date +%s)
    if [ "$vaka" != "$onc_vaka" ]; then onc_vaka=$vaka; bas_zaman=$simdi; prgh_kontrol=""; h_t=(); h_s=(); h_n=(); son_deg=$simdi; fi
    local ozet t dt co n
    ozet=$(tail -c 600000 "$logf" | awk '/^Courant Number mean/{c=$6} /^Time = /{t=$3; sub("s$","",t)} /^deltaT = /{d=$3} END{print t, d, c}')
    read -r t dt co <<< "$ozet"
    n=$(grep -c '^Time = ' "$logf")
    local dat Tm
    dat=$(ls -d "$vaka"/postProcessing/cellMax\(T\)/* 2>/dev/null | sort -V | tail -1)
    Tm=$(grep -v '^#' "$dat/volFieldValue.dat" 2>/dev/null | tail -1 | awk '{printf "%.0f", $2}')
    [ -z "$t" ] && t=0; [ -z "$dt" ] && dt=1; [ -z "$Tm" ] && Tm=0; [ -z "$co" ] && co="?"
    # son 5 dakikalık pencere: adım/dk ve kalan süre
    h_t+=("$t"); h_s+=("$simdi"); h_n+=("$n")
    if [ ${#h_t[@]} -gt 6 ]; then h_t=("${h_t[@]:1}"); h_s=("${h_s[@]:1}"); h_n=("${h_n[@]:1}"); fi
    local hiz="?" kalan="?"
    if [ ${#h_t[@]} -ge 2 ]; then
      read -r hiz kalan <<< "$(awk -v t="$t" -v o="${h_t[0]}" -v s="$((simdi - h_s[0]))" -v n="$n" -v no="${h_n[0]}" -v b="$bit" \
        'BEGIN{ah=(n-no)/s*60; h=(t-o)/s; if(h>0){k=(b-t)/h; printf "%.0f %dsa%02ddk", ah, int(k/3600), int((k%3600)/60)} else printf "%.0f ilerlemiyor", ah}')"
    fi
    local yuzde; yuzde=$(awk -v t="$t" -v b="$bit" 'BEGIN{printf "%.1f", 100*t/b}')
    echo "$(date '+%H:%M:%S') | $ad | adım $n | t = $t / $bit s | %$yuzde | Δt = $dt s | Tmax = $Tm K | Co = $co | $hiz adım/dk | kalan ~$kalan | boş disk $bos GB" >> "$CANLI"
    # gereksiz alanları buda (son iki zaman tam kalır)
    python3 of_sizinti3d.py --buda "$vaka" >> $K/sizinti3d_budama.log 2>&1
    # kontroller
    if [ "$t" != "$son_t" ]; then son_t=$t; son_deg=$simdi; fi
    local logyas=$((simdi - $(stat -c %Y "$logf")))
    if awk -v b="$bos" 'BEGIN{exit !(b<1.0)}'; then
      touch "$DUR"
      durdur "$mp" "$vaka" "DISK_DOLU" "DİSK DOLU: boş disk $bos GB < 1 GB, $ad durduruldu (t = $t s). Kuyruk duruyor."
      son_t=""; continue
    fi
    if [ "$ad" = "mars" ] && [ -z "$prgh_kontrol" ] && [ $((simdi - bas_zaman)) -ge 60 ] && [ "$n" -gt 0 ]; then
      prgh_kontrol=1
      if ! grep -q "Solving for p_rgh" "$logf"; then
        durdur "$mp" "$vaka" "KALDIRMA_YOK" "KALDIRMA YOK: mars ilk dakikada p_rgh çözmedi, durduruldu (t = $t s)."
        son_t=""; continue
      fi
      echo "$(date '+%H:%M:%S') | mars: p_rgh çözülüyor (kaldırma açık) ✓" >> "$CANLI"
    fi
    local neden=""
    awk -v d="$dt" 'BEGIN{exit !(d<1e-9)}' && neden="zaman adımı $dt s < 1e-9 s"
    if [ -z "$neden" ] && awk -v T="$Tm" -v t="$t" 'BEGIN{exit !(T>4000 && t>0.03)}'; then neden="Tmax $Tm K > 4000 K"; fi
    [ -z "$neden" ] && [ $((simdi - son_deg)) -ge 900 ] && neden="simülasyon zamanı 15 dk ilerlemedi"
    [ -z "$neden" ] && [ "$logyas" -ge 900 ] && neden="log 15 dk yazılmadı"
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
echo "$$ $BEKCI" > $K/kuyruk3d.pid
yaz "kuyruk3d başladı: kuyruk PID $$, bekçi PID $BEKCI, boş disk $(bos_gb) GB"

for v in uzay mars; do
  [ -e "$DUR" ] && { yaz "DİSK DOLU bayrağı var, $v başlatılmadı"; break; }
  yaz "$v: 0 -> 1,0 s başlıyor"
  python3 of_sizinti3d.py --kos --varyant $v >> $K/sizinti3d_surucu.log 2>&1
  yaz "$v bitti, çıkış $?  (son zaman: $(ls $K/sizinti3d_ince/$v/processor0 | grep -E '^[0-9.e+-]+$' | sort -g | tail -1) s)"
  python3 of_sizinti3d.py --buda $K/sizinti3d_ince/$v >> $K/sizinti3d_budama.log 2>&1
done
[ -e "$DUR" ] && { yaz "DİSK DOLU: son işlemler yapılmadı, kuyruk bitti"; exit 1; }

hata=0
python3 damla_vtk.py ince_uzay ince_mars >> $K/analiz3d.log 2>&1; r=$?; hata=$((hata+r)); yaz "damla_vtk.py çıkış $r"
python3 of_sizinti.py --analiz --ince >> $K/analiz3d.log 2>&1; r=$?; hata=$((hata+r)); yaz "of_sizinti.py --analiz --ince çıkış $r  -> of_sizinti_ince.png, _en.png"
python3 of_gorsel.py >> $K/analiz3d.log 2>&1; r=$?; hata=$((hata+r)); yaz "of_gorsel.py çıkış $r  -> of_gorsel.html"
pvpython --force-offscreen-rendering pv_video.py sizinti_ince >> $K/analiz3d.log 2>&1; r=$?; hata=$((hata+r)); yaz "pv_video.py çıkış $r  -> of_gorsel/sizinti_ince_uzay_mars.mp4"
if [ $hata -eq 0 ]; then
  python3 of_sizinti3d.py --temizle >> $K/analiz3d.log 2>&1; yaz "kullanılmayan processor zamanları silindi, çıkış $?  (boş disk $(bos_gb) GB)"
else
  yaz "bir adım hata verdi: processor zamanları SİLİNMEDİ (yeniden çalıştırılabilsin diye)"
fi
yaz "kuyruk3d bitti"
