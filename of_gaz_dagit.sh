#!/bin/bash
# of_gaz_dagit.sh — gaz BRE AUC vakalarını (of_kosular/gaz_bre/auc40/<test>) 221'e ve .56'ya dağıtır (.56'da çalışır).
# Vaka alma: auc40/<test>/KILIT (mkdir atomik). Sıra: SIRA dizisi (önce erken sönenler: çarpan erken sınanır).
#   bash of_gaz_dagit.sh wsl     # 221: makinede en çok 2 gaz koşusu (4'er çekirdek)
#   bash of_gaz_dagit.sh yerel   # .56: sıvı (gaz_bre dışı OpenFOAM) bitince en çok 3 gaz koşusu
# Bitince: auc40/<test>/TAMAM (ya da HATA) ve .56'da of_gaz_bre.py --analiz -> sonuc.json.
set -u
MOD=${1:?wsl|yerel}
KOK=$HOME/nasaspaceapp
AUC=$KOK/of_kosular/gaz_bre/auc40
WSL=${AHUT_UZAK:-kullanici@uzak-makine}      # uzak koşu makinesi (ssh)
UZ=ahut_uzak/gaz_bre/auc40
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
SIRA="39G1 39D1 39H1 94A1 51K1 63D1 87K1 94G1 70L1 87D1 51A1"
case $MOD in wsl) KAP=2 ;; yerel) KAP=3 ;; *) exit 1 ;; esac
LOG=$KOK/of_kosular/gaz_dagit_$MOD.log
gun() { echo "$(date '+%F %T') $*" >> "$LOG"; }

say() {   # $1=hepsi|yabanci : makinedeki foamRun süreç sayısı (yabanci = gaz_bre dışı)
  local kod
  if [ "$1" = hepsi ]; then kod='pgrep -cx foamRun || true'
  else kod='for p in $(pgrep -x foamRun; pgrep -x foamMultiRun); do case "$(readlink /proc/$p/cwd)" in *gaz_bre*) ;; *) echo x;; esac; done | wc -l'; fi
  if [ $MOD = wsl ]; then $SSH $WSL "$kod" < /dev/null; else bash -c "$kod"; fi
}
yer_var() {   # bir koşu daha sığar mı
  local n; n=$(say hepsi 2>/dev/null) || return 1
  [ $MOD = yerel ] && { [ "$(say yabanci 2>/dev/null || echo 1)" = 0 ] || return 1; }
  [ $(( (n + 3) / 4 )) -lt $KAP ]
}
kilitle() { for t in $SIRA; do [ -f $AUC/$t/TAMAM ] && continue; mkdir $AUC/$t/KILIT 2>/dev/null && { echo "$MOD $(date +%T)" > $AUC/$t/KILIT/sahip; echo $t; return; }; done; }

kos() {
  local t=$1 rc
  gun "başla $t"
  if [ $MOD = wsl ]; then
    $SSH $WSL "mkdir -p $UZ" < /dev/null
    rsync -a --exclude KILIT $AUC/$t/ $WSL:$UZ/$t/
    $SSH $WSL "cd $UZ/$t && bash kos.sh 4 > log.run 2>&1" < /dev/null; rc=$?
    rsync -a --exclude 'processor*' $WSL:$UZ/$t/ $AUC/$t/
  else
    (cd $AUC/$t && bash kos.sh 4 > log.run 2>&1); rc=$?
  fi
  (cd $KOK && python3 of_gaz_bre.py --analiz $AUC/$t >> "$LOG" 2>&1)
  if [ $rc = 0 ]; then touch $AUC/$t/TAMAM; else echo $rc > $AUC/$t/HATA; fi
  gun "bitti $t rc=$rc"
}

gun "dağıtıcı başladı ($MOD, en çok $KAP koşu)"
yuva() {
  sleep $(( $1 * 45 ))
  while true; do
    until yer_var; do sleep 60; done
    t=$(kilitle); [ -z "$t" ] && { gun "yuva $1: vaka kalmadı"; return; }
    kos $t
  done
}
for i in $(seq 0 $((KAP - 1))); do yuva $i & done
wait
gun "dağıtıcı bitti"
