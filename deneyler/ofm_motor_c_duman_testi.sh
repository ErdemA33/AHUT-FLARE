#!/bin/bash
# OpenFOAM motor_c duman testi: kopyada (~/motor_c_deneme) derle, 4 çekirdek, en çok 120 s duvar saati Saffire-III S1.
# Aslı (~/Desktop/motor_c) değişmez. Kullanım: bash ofm_motor_c_duman_testi.sh
set -e
source /opt/openfoam14/etc/bashrc >/dev/null 2>&1
[ -d ~/motor_c_deneme ] || cp -r ~/Desktop/motor_c ~/motor_c_deneme
cd ~/motor_c_deneme
export WM_NCOMPPROCS=2
(cd piroliz/kaynak && nice -n 19 wmake libso)
(cd damla_buharlasma/kaynak && nice -n 19 wmake libso && cd birimTest && nice -n 19 wmake)
cd vaka; M=..
cp $M/kinetik/reactions $M/kinetik/chemistryProperties $M/kinetik/reactionProperties constant/fluid/
cp $M/radyasyon/radiationProperties $M/radyasyon/fvModels constant/fluid/
cp $M/piroliz/fvModels $M/piroliz/physicalProperties constant/sibal/
nice -n 19 decomposePar -allRegions -force > log.decomposePar 2>&1
nice -n 19 timeout 120 mpirun --oversubscribe -np 4 foamMultiRun -parallel > log.run 2>&1 || true
grep -E "^\s*Time = " log.run | tail -1; grep -E "ExecutionTime" log.run | tail -1
