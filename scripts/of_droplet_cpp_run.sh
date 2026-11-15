#!/bin/bash
# C++ damla vakalarını (of_kosular/damla_cpp/<vaka>) koşar. Kullanım: bash scripts/of_droplet_cpp_run.sh <vaka> <çekirdek>
# 36 bin hücrelik tek damla vakası: 15 çekirdekte paralel kazanç yok; 1-2 çekirdek yeterli.
V=$1; N=${2:-1}
KOK="$(cd "$(dirname "$0")/.." && pwd)"
D=$KOK/of_kosular/damla_cpp/$V
cd "$D" || exit 1
source /opt/openfoam14/etc/bashrc ParaView_TYPE=none >/dev/null 2>&1
export HWLOC_COMPONENTS=-gl
rm -rf processor* postProcessing sonuc.json [1-9]* 0.[0-9]*
echo "AHUT damla C++ (libFlameInFreefallDroplet): $N çekirdek, $(date)"
if [ "$N" -le 1 ]; then
  foamRun
else
  sed -i "s/^numberOfSubdomains .*/numberOfSubdomains $N;/" system/decomposeParDict
  decomposePar -force > log.decomposePar 2>&1 || { echo "decomposePar başarısız"; exit 1; }
  mpirun --oversubscribe -np $N foamRun -parallel
  reconstructPar > log.reconstructPar 2>&1
fi
rc=$?
python3 "$KOK/scripts/of_droplet_validation.py" --analiz "$PWD" || echo "analiz başarısız"
exit $rc
