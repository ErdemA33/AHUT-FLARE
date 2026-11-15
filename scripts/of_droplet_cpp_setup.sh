#!/bin/bash
# FLEX damla doğrulama vakalarını C++ buharlaşma modeliyle (libFlameInFreefallDroplet, damlaBulutBuharlasma) kopyalar.
# Kaynak: of_kosular/droplet_validation/<vaka>  ->  of_kosular/damla_cpp/<vaka>
# Kullanım: bash scripts/of_droplet_cpp_setup.sh t74_221F001 t156_C03H401 ...
KOK="$(cd "$(dirname "$0")/.." && pwd)"
K=$KOK/of_kosular
TAB=${DAMLA_YAKITLAR:-$KOK/openfoam_motor/motor/damla_buharlasma/tablolar/damlaYakitlar}
for v in "$@"; do
  S=$K/droplet_validation/$v; D=$K/damla_cpp/$v
  [ -d "$S" ] || { echo "yok: $S"; continue; }
  rm -rf "$D"; mkdir -p "$D"
  cp -r "$S/0" "$S/constant" "$S/system" "$S/BILGI.json" "$S/kos.sh" "$D/"
  [ -d "$S/chemkin" ] && cp -r "$S/chemkin" "$D/"
  touch "$D/$v.foam"
  python3 - "$D" "$TAB" <<'P'
import re, sys
d, tab = sys.argv[1], sys.argv[2]
f = d + "/constant/cloudProperties"; s = open(f).read()
assert "phaseChangeModel liquidEvaporationBoil;" in s, f
s = s.replace("phaseChangeModel liquidEvaporationBoil;", "phaseChangeModel damlaBulutBuharlasma;", 1)
s = re.sub(r"liquidEvaporationBoil\s*\{[^}]*\}", "damlaBulutBuharlasma\n    {\n        enthalpyTransfer latentHeat;\n"
           "        activeLiquids    ( C7H16 );\n        yakit            NC7H16;\n        #include         \"%s\"\n    }" % tab, s, 1)
open(f, "w").write(s)
c = d + "/system/controlDict"; t = open(c).read()
if "libFlameInFreefallDroplet" not in t:
    t = t.replace("solver          multicomponentFluid;", "solver          multicomponentFluid;\n\nlibs            (\"libFlameInFreefallDroplet.so\");", 1)
open(c, "w").write(t)
P
  echo "hazır: $D"
done
