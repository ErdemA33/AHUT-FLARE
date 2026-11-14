#!/bin/bash
# OpenFOAM kilitli motoru (MOTOR_KILIT 1), Saffire-III S1, 10 s, 4 cekirdek. Kopyada kosar (ofm_motor_v2 salt okunur).
# Kosul: OpenFOAM kuyrugu (foamRun / of_kuyruk) art arda 10 dk bos ve saat >= 23:30. Disk < 1.5 GB ise durdurur.
R=/path/to/ahut-flare/ofm_kosular/v2_10s
LOG=/path/to/ahut-flare/deneyler/ofm_v2.log
echo "== bekleme basladi $(date)" >> $LOG
bos=0
while true; do
  if pgrep -x foamRun >/dev/null || pgrep -f of_kuyruk >/dev/null || pgrep -x foamMultiRun >/dev/null; then bos=0; else bos=$((bos+1)); fi
  saat=$(date +%H%M)
  if [ $bos -ge 10 ] && { [ "$saat" -ge 2330 ] || [ "$saat" -lt 1200 ]; }; then break; fi
  sleep 60
done
echo "== kuyruk bos; basliyor $(date)" >> $LOG
source /opt/openfoam14/etc/bashrc >/dev/null 2>&1
export LD_LIBRARY_PATH=$R/lib:$LD_LIBRARY_PATH
cd $R/vaka
M=../motor
cp $M/kinetik/reactions $M/kinetik/chemistryProperties $M/kinetik/reactionProperties constant/fluid/
cp $M/radyasyon/radiationProperties $M/radyasyon/fvModels constant/fluid/
cp $M/piroliz/fvModels $M/piroliz/physicalProperties constant/sibal/
decomposePar -allRegions -force > log.decomposePar 2>&1
date +%s > baslangic.txt
nice -n 5 mpirun -np 4 -x LD_LIBRARY_PATH foamMultiRun -parallel > log.run 2>&1 &
PID=$!
while kill -0 $PID 2>/dev/null; do
  bosyer=$(df --output=avail -k / | tail -1)
  if [ "$bosyer" -lt 1500000 ]; then echo "== disk az ($bosyer kB), durduruluyor $(date)" >> $LOG; kill $PID; break; fi
  sleep 120
done
wait $PID; echo "rc=$?" > bitis.txt; date +%s >> bitis.txt
echo "== kosu bitti $(date) $(grep -a '^Time = ' log.run | tail -1)" >> $LOG
cd /path/to/ahut-flare
python3 ofm_analiz.py $R/vaka --cikti ofm_sonuclar >> $LOG 2>&1
python3 ofm_sonuc_donustur.py ofm_sonuclar/v2_10s_vaka.json --cikti ofm_sonuclar/openfoam_sonuclar_ofm.csv >> $LOG 2>&1
echo "== OFM_V2 BITTI $(date)" >> $LOG
