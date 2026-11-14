#!/bin/bash
# Sıvı (n-heptan) sızıntısı — 4 yerçekimli 3B: of_kosular/sizinti3d_ince/{ay,dunya} (uzay, mars mevcut), 1,0 s, 13 çekirdek.
# GÖSTERİM — deney verisiyle doğrulanmadı.
# Sıra: kurulum (ayar.json: kutu genis, bolme 1 = uzay/mars ile aynı) -> kısa test (0,02 s, Ay) -> Ay -> damla_vtk (Ay)
#       -> Ay inceltme (uzay/mars ile aynı 20 alan zamanı) -> Dünya -> damla_vtk -> inceltme
#       -> of_sizinti.py --analiz --ince (4 yerçekimi tablosu) -> pv_sizinti_4g.py (3b, kesit; TR+EN)
#       -> video denetimi (kare, süre, her panelde sıcak bölge) -> of_gorsel.py -> masaüstü.
# Her adım denetlenir (çıkış kodu; koşuda son zaman = endTime + log'da End + çökme yok); biri tutmazsa HATA, sonrakine geçilmez.
# Bekçi (dakikada bir, of_kosular/canli_3d.log): saat | koşu | adım | t | % | Δt | Tmax | Co | kalan | boş disk
#   eski zamanlardan gereksiz alanları budar; boş disk başlangıçtakinin yarısının altına inerse DİSK (durur);
#   Δt < 1e-9, Tmax > 4000 K (t > 0,03 s), 15 dk ilerleme yok / log yazılmıyor -> IRAKSADI (koşu başladıktan 2 dk sonra);
#   g != 0 koşularda ilk dakikada p_rgh çözülmüyorsa KALDIRMA_YOK.
# Başlatma:  nohup setsid ./of_kuyruk3d_4g.sh >> of_kosular/kuyruk3d_4g.log 2>&1 < /dev/null &
cd "$(dirname "$0")" || exit 1
export OMP_NUM_THREADS=1
export SIZINTI_CEKIRDEK=13
K=of_kosular
V=$K/sizinti3d_ince
CANLI=$K/canli_3d.log
DUR=$V/DURDUR_DISK_DOLU_4G
yaz() { echo "$(date '+%F %T') | $*" | tee -a "$CANLI"; }
bos_gb() { df -B1 --output=avail . | tail -1 | awk '{printf "%.2f", $1/1e9}'; }
F0=$(bos_gb)
SINIR=$(awk -v f="$F0" 'BEGIN{s=f/2; if(s<1)s=1; printf "%.2f", s}')
hata_dur() { yaz "HATA: $* — sonraki adımlara geçilmedi, kuyruk duruyor"; exit 1; }

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
      readlink "/proc/$p/cwd" 2>/dev/null | grep -q sizinti3d_ince && mp=$p && break
    done
    local bos; bos=$(bos_gb)
    if [ -z "$mp" ]; then
      echo "$(date '+%H:%M:%S') | (koşu yok: hazırlık / damla_vtk / analiz / video) | boş disk $bos GB" >> "$CANLI"
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
    h_t+=("$t"); h_s+=("$simdi"); h_n+=("$n")
    if [ ${#h_t[@]} -gt 6 ]; then h_t=("${h_t[@]:1}"); h_s=("${h_s[@]:1}"); h_n=("${h_n[@]:1}"); fi
    local hiz="?" kalan="?"
    if [ ${#h_t[@]} -ge 2 ]; then
      read -r hiz kalan <<< "$(awk -v t="$t" -v o="${h_t[0]}" -v s="$((simdi - h_s[0]))" -v n="$n" -v no="${h_n[0]}" -v b="$bit" \
        'BEGIN{ah=(n-no)/s*60; h=(t-o)/s; if(h>0){k=(b-t)/h; printf "%.0f %dsa%02ddk", ah, int(k/3600), int((k%3600)/60)} else printf "%.0f ilerlemiyor", ah}')"
    fi
    local yuzde; yuzde=$(awk -v t="$t" -v b="$bit" 'BEGIN{printf "%.1f", 100*t/b}')
    echo "$(date '+%H:%M:%S') | $ad | adım $n | t = $t / $bit s | %$yuzde | Δt = $dt s | Tmax = $Tm K | Co = $co | $hiz adım/dk | kalan ~$kalan | boş disk $bos GB" >> "$CANLI"
    python3 of_sizinti3d.py --buda "$vaka" >> $K/sizinti3d_budama.log 2>&1
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
    if [ $((simdi - bas_zaman)) -ge 120 ]; then
      [ -z "$neden" ] && [ $((simdi - son_deg)) -ge 900 ] && neden="simülasyon zamanı 15 dk ilerlemedi"
      [ -z "$neden" ] && [ "$logyas" -ge 900 ] && neden="log 15 dk yazılmadı"
    fi
    if [ -n "$neden" ]; then
      durdur "$mp" "$vaka" "IRAKSADI" "IRAKSADI: $ad durduruldu ($neden, t = $t s)."
      son_t=""
    fi
  done
}

rm -f "$DUR"
bekci &
BEKCI=$!
trap 'kill $BEKCI 2>/dev/null' EXIT
echo "$$ $BEKCI" > $K/kuyruk3d_4g.pid
yaz "===== kuyruk3d_4g (sıvı, 4 yerçekimi) başladı: kuyruk PID $$, bekçi PID $BEKCI, 13 çekirdek, boş disk $F0 GB, disk sınırı $SINIR GB ====="

# ---- 0) kurulum (uzay / mars ile birebir: ayar.json'daki kutu ve bölme)
KUTU=$(python3 -c "import json;print(json.load(open('$V/ayar.json'))['kutu'])")
BOLME=$(python3 -c "import json;print(json.load(open('$V/ayar.json'))['bolme'])")
for v in ay dunya; do
  python3 -c "
import of_sizinti3d as s
s.kur_varyant('$v', s.VARYANTLAR_TUM['$v'], '$KUTU', $BOLME)" >> $K/sizinti3d_surucu.log 2>&1 || hata_dur "$v kurulumu başarısız (bkz. $K/sizinti3d_${v}_hazirlik.log)"
  yaz "$v kuruldu (kutu $KUTU, bölme $BOLME, g = $(awk '/^value/' $V/$v/constant/g), $(grep -E '^\s*cells:' $K/sizinti3d_${v}_hazirlik.log | tail -1 | tr -s ' '), 13 alt bölge)"
done

# ---- 1) kısa test (Ay, 0,02 s): çıkış 0 + son zaman + End + çökme yok
python3 of_sizinti3d.py --test --sure 0.02 --varyant ay >> $K/sizinti3d_surucu.log 2>&1
tj=$(cat $V/test_ay.json 2>/dev/null)
yaz "kısa test (Ay, 0,02 s): $tj"
python3 -c "import json,sys; d=json.load(open('$V/test_ay.json')); sys.exit(1 if d.get('hata', True) else 0)" 2>/dev/null \
  || hata_dur "kısa test başarısız"
python3 -c "
import of_tek_damla as ot, of_sizinti3d as s
ot.guvenli_sil(s.VAKA_KOK / 'test_ay')" >> $K/sizinti3d_surucu.log 2>&1

# ---- 2) koşular: Ay sonra Dünya
for v in ay dunya; do
  [ -e "$DUR" ] && hata_dur "DİSK bayrağı var, $v başlatılmadı"
  yaz "$v: 0 -> 1,0 s başlıyor (13 çekirdek)"
  python3 of_sizinti3d.py --kos --varyant $v >> $K/sizinti3d_surucu.log 2>&1; r=$?
  python3 of_sizinti3d.py --buda $V/$v >> $K/sizinti3d_budama.log 2>&1
  [ $r -ne 0 ] && hata_dur "$v tamamlanmadı (çıkış $r; $(cat $V/$v/durum.json 2>/dev/null))"
  yaz "$v TAMAM: $(cat $V/$v/durum.json) (boş disk $(bos_gb) GB)"
  python3 -c "
import damla_vtk as d
d.VAKALAR['ince_$v'] = 'sizinti3d_ince/$v'      # damla_vtk.py değiştirilmeden, çalışma anında
d.cevir('ince_$v')" >> $K/analiz3d.log 2>&1 || hata_dur "damla_vtk ($v) başarısız"
  n=$(python3 -c "import json;print(len(json.load(open('$V/$v/damla_vtk/damla.vtp.series'))['files']))")
  [ "$n" -ge 100 ] || hata_dur "damla serisi eksik ($v: $n zaman)"
  yaz "damla_vtk ($v) TAMAM: $n zaman"
  python3 of_sizinti3d.py --temizle --varyant $v >> $K/analiz3d.log 2>&1 || hata_dur "$v inceltme başarısız"
  yaz "$v inceltildi (görüntüleyicinin 20 karesi + son; damla serisi ve postProcessing korundu), boş disk $(bos_gb) GB"
done

# ---- 3) analiz, videolar, görüntüleyici, masaüstü
python3 of_sizinti.py --analiz --ince >> $K/analiz3d.log 2>&1 || hata_dur "of_sizinti.py --analiz --ince başarısız"
[ -f of_sizinti_ince_4g_sonuc.csv ] || hata_dur "4 yerçekimi tablosu üretilmedi"
yaz "analiz TAMAM -> of_sizinti_ince_4g_sonuc.csv, of_sizinti_ince_4g(_en).png (+ of_sizinti_ince(_en).png, uzay/Mars)"
pvpython --force-offscreen-rendering pv_sizinti_4g.py >> $K/analiz3d.log 2>&1 || hata_dur "pv_sizinti_4g.py başarısız"
VID="of_gorsel/sizinti_3b_4g.mp4 of_gorsel/sizinti_3b_4g_en.mp4 of_gorsel/sizinti_kesit_4g.mp4 of_gorsel/sizinti_kesit_4g_en.mp4"
vd=$(python3 of_gaz.py --video-denetle $VID --panel4 2>&1); r=$?
while IFS= read -r s; do yaz "video: $s"; done <<< "$vd"
[ $r -eq 0 ] || hata_dur "en az bir video boş / eksik / panellerinden biri sıcak bölge içermiyor"
python3 of_gorsel.py >> $K/analiz3d.log 2>&1 || hata_dur "of_gorsel.py başarısız"
yaz "of_gorsel.py TAMAM (ince_ay, ince_dunya eklendi)"
for f in $VID; do cp -f "$f" ~/Desktop/ || hata_dur "masaüstüne kopyalanamadı: $f"; done
yaz "masaüstüne 4 video kopyalandı (~/Desktop)"
yaz "kuyruk3d_4g BİTTİ, tüm adımlar TAMAM (boş disk $(bos_gb) GB) — GÖSTERİM, deney verisiyle doğrulanmadı"
