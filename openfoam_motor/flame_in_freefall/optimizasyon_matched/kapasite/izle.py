#!/usr/bin/env python3
"""Termal bekçi. kullanım: izle.py <SID> <N> <csv> <olay_log>
Her 1 s: acpitz / TCPU / x86_pkg_temp / fan / ortalama frekans / foamRun sayısı -> csv (tek yazar bu süreç).
İPTAL (oturumdaki tüm süreçlere SIGKILL):
  - acpitz >= 98 °C (tek örnek)            [kapanma eşiği 105 °C]
  - max(acpitz,TCPU,pkg) >= 97 °C, art arda 5 örnek
Oturumda süreç kalmayınca çıkar. Çıkış kodu: 0 normal, 3 iptal.
"""
import glob, os, subprocess, sys, time

SID, N, CSV, OLAY = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
ACPI_TEK = float(os.environ.get("IZLE_ACPI_TEK", 98.0))  # ortam değişkeni yalnız test için
MAX_ARDISIK, ARDISIK_N = 97.0, 5
UYARI_C, UYARI_ARA = 90.0, 60
DURUM_ARA = 300


def zon(tip):
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        if open(f"{z}/type").read().strip() == tip:
            return f"{z}/temp"
    return None


Z = {k: zon(k) for k in ("acpitz", "TCPU", "x86_pkg_temp")}
FAN = sorted(glob.glob("/sys/class/hwmon/hwmon*/fan*_input"))
FRQ = glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq")


def oku(p, bol=1000.0):
    try:
        return int(open(p).read()) / bol
    except Exception:
        return float("nan")


def olay(msg):
    with open(OLAY, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + f"[N={N}] " + msg + "\n")


def say(ad=None):
    """Oturumdaki canlı (zombi olmayan) süreç sayısı; ad verilirse yalnız o komut."""
    r = subprocess.run(["ps", "-e", "-o", "sid=,stat=,comm="], capture_output=True, text=True)
    n = 0
    for s in r.stdout.splitlines():
        p = s.split(None, 2)
        if len(p) == 3 and p[0] == str(SID) and not p[1].startswith("Z") and (ad is None or p[2] == ad):
            n += 1
    return n


yeni = not os.path.exists(CSV)
f = open(CSV, "a", buffering=1)
if yeni:
    f.write("t,N,acpitz,TCPU,pkg,fan1,fan2,frek_MHz,foamRun\n")
t0 = time.time()
ardisik, son_uyari, son_durum = 0, 0.0, t0
olay(f"bekçi başladı SID={SID}")
while True:
    a, c, p = (oku(Z[k]) if Z[k] else float("nan") for k in ("acpitz", "TCPU", "x86_pkg_temp"))
    fans = [oku(x, 1) for x in FAN[:2]] + [float("nan")] * (2 - len(FAN[:2]))
    frek = sum(oku(x) for x in FRQ) / max(len(FRQ), 1)
    nf = say("foamRun")
    now = time.time()
    f.write(f"{now:.1f},{N},{a:.1f},{c:.1f},{p:.1f},{fans[0]:.0f},{fans[1]:.0f},{frek:.0f},{nf}\n")
    T = max(x for x in (a, c, p) if x == x)
    ardisik = ardisik + 1 if T >= MAX_ARDISIK else 0
    if a >= ACPI_TEK or ardisik >= ARDISIK_N:
        subprocess.run(["pkill", "-KILL", "-s", str(SID)])
        olay(f"IPTAL acpitz={a:.0f} TCPU={c:.0f} pkg={p:.0f} ardisik={ardisik} -> oturum öldürüldü "
             f"(t+{now - t0:.0f} s)")
        open(CSV + ".iptal", "w").write(f"{a} {c} {p} {now - t0:.0f}\n")
        sys.exit(3)
    if T >= UYARI_C and now - son_uyari >= UYARI_ARA:
        olay(f"UYARI acpitz={a:.0f} TCPU={c:.0f} pkg={p:.0f} frek={frek:.0f} MHz (t+{now - t0:.0f} s)")
        son_uyari = now
    if now - son_durum >= DURUM_ARA:
        olay(f"durum acpitz={a:.0f} TCPU={c:.0f} pkg={p:.0f} fan={fans[0]:.0f} frek={frek:.0f} MHz "
             f"foamRun={nf} (t+{now - t0:.0f} s)")
        son_durum = now
    if say() == 0:
        olay(f"bekçi bitti (t+{now - t0:.0f} s)")
        sys.exit(0)
    time.sleep(max(0.0, 1.0 - (time.time() - now)))
