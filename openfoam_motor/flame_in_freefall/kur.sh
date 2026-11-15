#!/bin/bash
# Özel OpenFOAM kütüphanelerini derler. Kullanım: bash kur.sh
set -e
D="$(cd "$(dirname "$0")" && pwd)"
BASHRC="${OF_BASHRC:-/opt/openfoam14/etc/bashrc}"
[ -f "$BASHRC" ] || { echo "OpenFOAM bashrc yok: $BASHRC (OF_BASHRC ile verin)"; exit 1; }
source "$BASHRC" >/dev/null 2>&1
mkdir -p "$FOAM_USER_LIBBIN"
for k in flameInFreefallBCs flameInFreefallSolid; do
  echo "== derleniyor: $k"
  (cd "$D/src/$k" && wclean libso >/dev/null 2>&1 || true; wmake libso)
done
ls -l "$FOAM_USER_LIBBIN"/libFlameInFreefall*.so
echo "TAMAM. Şimdi: cd vakalar/_kalibrasyon && python3 -m pytest ml -q"
