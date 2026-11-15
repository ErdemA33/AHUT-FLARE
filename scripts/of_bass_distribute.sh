#!/bin/bash
# scripts/of_bass_distribute.sh — BASS SIBAL vakalarını boşalan bilgisayarlara dağıtır (.56'da çalışır).
#
# Ortak kuyruk: user(.55):/mnt/data/ahut_kosular/bass_sibal/<vaka>. Bir vakayı alan, .55'te <vaka>/KILIT
# klasörünü açar (mkdir atomik: iki makine aynı vakayı alamaz). Bitince sonuç .55'e geri yazılır
# (processor* hariç: analiz postProcessing'den yapılır) ve TAMAM ya da HATA konur.
#
#   bash scripts/of_bass_distribute.sh yerel   # .56: makinede başka OpenFOAM süreci 10 dk yoksa (sıvı kuyruğu bitti) 1 vaka
#   bash scripts/of_bass_distribute.sh wsl     # 221: ~/ahut_uzak/BASS_ACIK varsa ve 10 dk OpenFOAM yoksa 1 vaka (gaz bitince açılır)
#
# Koşu: bash kos.sh (vaka 4 çekirdeğe bölünmüş). 221 için bashrc ParaView_TYPE=none, HWLOC_COMPONENTS=-gl.
set -u
MOD=${1:?yerel|wsl}
KAYNAK_HOST=${AHUT_KAYNAK:-kaynak-makine}     # vakaların durduğu makine (ssh)
KAYNAK=/mnt/data/ahut_kosular/bass_sibal
WSL=${AHUT_UZAK:-kullanici@uzak-makine}      # uzak koşu makinesi (ssh)
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
case $MOD in
  yerel) IS=$HOME/bass_is; SLOT=1 ;;   # .56 diski küçük (vaka ~1 GB yazar)
  wsl)   IS=ahut_uzak/bass_sibal; SLOT=1 ;;
  *) echo "mod: yerel|wsl"; exit 1 ;;
esac
LOG=$HOME/nasaspaceapp/of_kosular/bass_dagit_$MOD.log
gun() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# makinede bu betiğin koşuları DIŞINDA OpenFOAM süreci var mı
dis_foam() {
  local kod='for p in $(pgrep -x foamRun; pgrep -x foamMultiRun); do d=$(readlink /proc/$p/cwd); case "$d" in *bass_is*|*ahut_uzak/bass_sibal*) ;; *) echo x;; esac; done | wc -l'
  if [ $MOD = yerel ]; then bash -c "$kod"; else $SSH $WSL "$kod" < /dev/null; fi
}
acik_mi() { [ $MOD = yerel ] && return 0; $SSH $WSL 'test -f ~/ahut_uzak/BASS_ACIK' < /dev/null; }

bos_bekle() {          # 10 ardışık dakika boşta (ve açık) olmalı
  local n=0
  while [ $n -lt 10 ]; do
    if acik_mi && [ "$(dis_foam 2>/dev/null || echo 1)" = 0 ]; then n=$((n+1)); else n=0; fi
    sleep 60
  done
}

kilitle() {            # sıradaki vakayı al; adını yazar (yoksa boş)
  $SSH $KAYNAK_HOST "cd $KAYNAK && for d in \$(ls -d b*/ | sed 's#/##'); do [ -f \$d/TAMAM ] && continue; mkdir \$d/KILIT 2>/dev/null && { echo $MOD-\$(date +%F_%T) > \$d/KILIT/sahip; echo \$d; break; }; done" < /dev/null
}

kos() {                # $1 = vaka
  local v=$1 rc
  gun "başla $v"
  if [ $MOD = yerel ]; then
    mkdir -p "$IS" && rm -rf "$IS/$v"
    $SSH $KAYNAK_HOST "tar c -C $KAYNAK --exclude='processor*' --exclude='log.*' --exclude=KILIT --exclude=HATA $v" < /dev/null | tar x -C "$IS"
    sed -i 's#^source /opt/openfoam14/etc/bashrc #source /opt/openfoam14/etc/bashrc ParaView_TYPE=none #' "$IS/$v/kos.sh"
    (cd "$IS/$v" && HWLOC_COMPONENTS=-gl bash kos.sh > log.run 2>&1); rc=$?
    tar c -C "$IS" --exclude='processor*' "$v" | $SSH $KAYNAK_HOST "tar x -C $KAYNAK"
    [ $? = 0 ] && rm -rf "$IS/$v"
  else
    $SSH $WSL "mkdir -p $IS && rm -rf $IS/$v" < /dev/null
    $SSH $KAYNAK_HOST "tar c -C $KAYNAK --exclude='processor*' --exclude='log.*' --exclude=KILIT --exclude=HATA $v" < /dev/null | $SSH $WSL "tar x -C $IS"
    $SSH $WSL "cd $IS/$v && sed -i 's#^source /opt/openfoam14/etc/bashrc #source /opt/openfoam14/etc/bashrc ParaView_TYPE=none #' kos.sh && HWLOC_COMPONENTS=-gl bash kos.sh > log.run 2>&1" < /dev/null; rc=$?
    $SSH $WSL "tar c -C $IS --exclude='processor*' $v" < /dev/null | $SSH $KAYNAK_HOST "tar x -C $KAYNAK"
    [ $? = 0 ] && $SSH $WSL "rm -rf $IS/$v" < /dev/null
  fi
  if [ $rc = 0 ]; then $SSH $KAYNAK_HOST "touch $KAYNAK/$v/TAMAM" < /dev/null; else $SSH $KAYNAK_HOST "echo $rc > $KAYNAK/$v/HATA" < /dev/null; fi
  gun "bitti $v rc=$rc"
}

gun "dağıtıcı başladı ($MOD, $SLOT yuva): boşalmayı bekliyor"
bos_bekle
gun "makine boş: vaka almaya başlıyor"
bos_gb() {             # çalışma diskinde boş GB
  local kod="df -BG --output=avail \$HOME | tail -1 | tr -dc 0-9"
  if [ $MOD = yerel ]; then bash -c "$kod"; else $SSH $WSL "$kod" < /dev/null; fi
}
isci() {
  while true; do
    until [ "$(bos_gb 2>/dev/null || echo 0)" -ge 3 ]; do gun "yuva $1: disk 3 GB'tan az boş, bekliyor"; sleep 600; done
    v=$(kilitle)
    [ -z "$v" ] && { gun "yuva $1: alınacak vaka kalmadı"; return; }
    kos "$v"
  done
}
for i in $(seq 1 $SLOT); do isci $i & sleep 20; done
wait
gun "dağıtıcı bitti"
