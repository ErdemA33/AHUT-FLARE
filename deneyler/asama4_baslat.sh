#!/bin/bash
# Aşama 4 (ayrıntılı mod, su emmeli + C_rad kalibre). OpenFOAM kuyruğu bitene kadar bekler:
# 10 dk boyunca foamRun ve of_kuyruk*.sh süreci yoksa başlar. İşçi = nproc - foamRun - 1 (en çok 15). Tavan 6 saat.
cd /path/to/ahut-flare
L=deneyler/asama4.log
echo "== bekleme başladı $(date)" > $L
bos=0
while [ $bos -lt 10 ]; do
  if [ "$(pgrep -c foamRun)" = "0" ] && ! pgrep -f "of_kuyruk" > /dev/null; then bos=$((bos+1)); else bos=0; fi
  sleep 60
done
F=$(pgrep -c foamRun); N=$(( $(nproc) - F - 1 )); [ $N -gt 15 ] && N=15; [ $N -lt 1 ] && N=1
echo "== OpenFOAM kuyruğu boş; başlıyor $(date), işçi $N" >> $L
export OMP_NUM_THREADS=1
BAS=$(date +%s)
timeout 21600 nice -n 5 python3 damla_motoru.py --kalibre-ayrintili --cekirdek $N --alt-kume 45 --butce-dk 320 --maxfev 60 >> $L 2>&1
echo "== kalibrasyon çıkış $? $(date)" >> $L
KALAN=$(( 21600 - ($(date +%s) - BAS) ))
if [ $KALAN -gt 300 ]; then
  timeout $KALAN python3 deneyler/asama4_karsilastir.py >> $L 2>&1
  timeout $KALAN python3 damla_motoru.py --ornek-ayrintili >> $L 2>&1
fi
echo "== ASAMA4 BITTI $(date)" >> $L
