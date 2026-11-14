#!/bin/bash
# Kullanim: ./izle_T.sh        (tek seferlik)   |   watch -n 5 ./izle_T.sh
D="$(cd "$(dirname "$0")" && pwd)"
CLK=$(tail -c 20000 "$D/log.run" | grep -a 'ClockTime' | tail -n 1 | sed -E 's/.*ClockTime = ([0-9]+) s.*/\1/')
CLK=${CLK:-0}
DT=$(tail -c 20000 "$D/log.run" | grep -a 'deltaT =' | tail -n 1 | sed -E 's/.*deltaT = ([0-9.e+-]+).*/\1/')
cd "$D/postProcessing" || exit 1
son() { tail -n 1 "$1"/0/volFieldValue.dat | awk -v s="$2" -v c="$CLK" '{printf "%-11s t = %8.4f s  (clock %6d s = %5.2f saat)   T = %7.1f K\n", s, $1, c, c/3600, $2}'; }
son tel/telT          "tel maks"
son tel/telTort       "tel ort"
son sibal/sibalMaxT   "sibal maks"
son fluid/gazMax      "gaz maks"
echo "${DT:-0}" | awk '{printf "%-11s dt = %.10f s  (%.2f mikrosaniye)\n", "adim", $1, $1*1e6}'
