#!/bin/bash
# OpenFOAM kilitli motoru, BASS SIBAL test 4 (2B, 40 s), 4 cekirdek. Vaka: deneyler/ofm_bass_kur.py ile kuruldu.
# OpenFOAM kuyrugu (foamRun / of_kuyruk) bossa baslar; disk < 1.5 GB ise durdurur.
R=/path/to/ahut-flare/ofm_kosular/bass_sibal_t4
LOG=/path/to/ahut-flare/deneyler/ofm_bass.log
echo "== bekleme $(date)" >> $LOG
while pgrep -x foamRun >/dev/null || pgrep -f of_kuyruk >/dev/null; do sleep 60; done
echo "== basliyor $(date)" >> $LOG
source /opt/openfoam14/etc/bashrc >/dev/null 2>&1
export LD_LIBRARY_PATH=$R/lib:$LD_LIBRARY_PATH
cd $R/vaka
M=../motor
cp $M/kinetik/reactions $M/kinetik/chemistryProperties $M/kinetik/reactionProperties constant/fluid/
cp $M/radyasyon/radiationProperties $M/radyasyon/fvModels constant/fluid/
cp $M/piroliz/fvModels $M/piroliz/physicalProperties constant/sibal/
decomposePar -allRegions -force > log.decomposePar 2>&1 || { echo "== decomposePar HATA" >> $LOG; exit 1; }
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
python3 ofm_dogrulama.py $R/vaka --deney bass4 --cikti ofm_sonuclar >> $LOG 2>&1
echo "== OFM_BASS BITTI $(date)" >> $LOG
