"""Eski kosularin (TC9 probu) agi/cozucusu mevcut sablonla ayni mi? (T13)

Her eski kosu icin ayni parametrelerle vaka_kur(decompose=False) ile referans vaka uretilir (gecici dizin, CFD YOK) ve
system/ ile constant/ dosyalari karsilastirilir. Beklenen farklar (kosuya gore degisen anahtarlar) normalize edilir:
  - system/controlDict: endTime, writeInterval, maxDeltaT, startFrom, maxCo satirlari yok sayilir
  - system/functions: eski kosuda sensorler olmayabilir -> eski dosya, referansin on eki olmali (BASE icerigiyle baslamali)
Uyumsuz herhangi bir dosya -> koşu uygunsuz (neden listelenir).
"""
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import orkestrator as O

SATIR_YOKSAY = re.compile(r"^(endTime|writeInterval|maxDeltaT|startFrom|maxCo)\b")


def _hash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _norm_controldict(p):
    return [l for l in Path(p).read_text().splitlines() if not SATIR_YOKSAY.match(l.strip())]


def uygunluk(ad, kayit=None):
    """Dondurur (uygun: bool, farklar: [str])."""
    kayit = kayit or next((r for r in json.load(open(O.SONUC)) if r["ad"] == ad), None)
    if kayit is None:
        return False, ["sonuclar.json'da kayit yok"]
    legacy = O.RUNS / ad
    if not legacy.exists():
        return False, ["kosu dizini yok"]
    tmp = Path(tempfile.mkdtemp(prefix="legacy_ref_"))
    eski_runs = O.RUNS
    try:
        O.RUNS = tmp
        ref = O.vaka_kur("ref", kayit["A"], kayit["Ta"], "sifir", kayit.get("ufuk") or 6.0,
                         kayit.get("maxDeltaT") or 2e-5, decompose=False)
    finally:
        O.RUNS = eski_runs
    farklar = []
    for alt in ("constant", "system"):
        for f in sorted((ref / alt).rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(ref)
            g = legacy / rel
            if not g.exists():
                farklar.append(f"eksik: {rel}")
                continue
            if str(rel) == "system/controlDict":
                if _norm_controldict(f) != _norm_controldict(g):
                    farklar.append(f"fark: {rel}")
            elif str(rel) == "system/functions":
                base_fn = (O.BASE / "system/functions").read_text()
                if not g.read_text().startswith(base_fn.rstrip()[:200]):
                    farklar.append(f"fark: {rel} (BASE on eki yok)")
            elif _hash(f) != _hash(g):
                farklar.append(f"fark: {rel}")
    shutil.rmtree(tmp, ignore_errors=True)
    return len(farklar) == 0, farklar
