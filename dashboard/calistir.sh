#!/usr/bin/env bash
# AHUT FLARE — Linux başlatıcısı (sudo gerekmez).
#   ./calistir.sh               uygulamayı açar
#   ./calistir.sh --sinama      pencere açmadan kendini sınar
#   ./calistir.sh --kur         .venv'i kurar / pywebview'i yükler, sonra açar
# İlk çalıştırmada .venv yoksa kendisi kurar: sistem Python'unun paketleri (numpy, scikit-learn 1.4.1,
# GTK için python3-gi) görünür kalır (--system-site-packages), yalnız pywebview .venv'e pip ile girer.
# Gerekenler (dağıtımdan; bu bilgisayarda kurulu): python3 3.12, python3-gi, gir1.2-webkit2-4.1.
set -euo pipefail
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$KOK/.venv"
PY="${YANGIN_PYTHON:-python3}"

kur() {
  if [ ! -x "$VENV/bin/python" ]; then
    echo "[kurulum] $VENV oluşturuluyor (--system-site-packages)"
    "$PY" -m venv --system-site-packages "$VENV"
  fi
  if ! "$VENV/bin/python" -c "import webview" 2>/dev/null; then
    echo "[kurulum] pywebview yükleniyor (pip, .venv içine)"
    "$VENV/bin/pip" install --quiet "pywebview>=5.0"
  fi
}

if [ "${1:-}" = "--kur" ]; then
  shift
  kur
elif [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import webview" 2>/dev/null; then
  kur
fi

"$VENV/bin/python" - <<'EOF' || { echo "Eksik paket: pip install -r gereksinimler.txt (ya da dağıtım paketleri)"; exit 1; }
import sys, sklearn, numpy, gi
gi.require_version("WebKit2", "4.1")
assert sys.version_info[:2] == (3, 12), "Python 3.12 gerekli (model scikit-learn 1.4.1 ile eğitildi)"
assert sklearn.__version__.startswith("1.4.1"), f"scikit-learn 1.4.1 gerekli, bulunan {sklearn.__version__}"
EOF

cd "$KOK"
exec "$VENV/bin/python" "$KOK/ahut_flare.py" "$@"
