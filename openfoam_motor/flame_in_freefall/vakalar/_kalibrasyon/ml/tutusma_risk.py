"""Tutusma riski: kalan Faz A noktalarinin gaz kinetigi kenar payi (CFD calistirmaz).

Olculen iki referans (ayni mesh, ayni solver):
  TUTUSTU   sensorlu_hedef02: theta_g1 = 15.1064, Ta1 = 24358, t_ign = 3.686 s
  TUTUSMADI faz_a_01:         theta_g1 = 14.6749, Ta1 = 21287.3 (ufuk 7.5 s, gaz maks T 1339 K)
Olcut: ln k1(T) = theta_g1 - Ta1*(1/T - 1/1350), T = 1250, 1300, 1339 K (tutusmayan kosuda gaz maks T araligi).
pay(T) = ln k(aday) - ln k(TUTUSMADI). Pay <= 0: tutusmayan kosudan daha yavas -> RISKLI.
pay >= ln k(TUTUSTU) - ln k(TUTUSMADI) (her T icin): tutusan kosu kadar hizli -> GUVENLI. Aradaki bolge: BELIRSIZ.
SINIRLAR [bilinmiyor]: yalnizca gaz kinetigi; piroliz akisi ve eps de degisiyor (faz_a_01'de yakit akisi referanstan
dusuk degildi). Iki referans noktasi esik bulmaya yetmez; sonuc bir siralama/uyari, tahmin degil.
"""
import numpy as np

from . import param as P

T_LISTESI = (1250.0, 1300.0, 1339.0)
TUTUSTU = dict(theta_g1=15.1064, Ta1=24358.0)
TUTUSMADI = dict(theta_g1=14.6748599706483, Ta1=21287.3267190475)


def ln_k(theta_g1, Ta1, T):
    return theta_g1 - Ta1 * (1.0 / T - 1.0 / 1350.0)


def risk(x):
    f = P.fiziksel(x)
    ayr = {}
    sinif = []
    for T in T_LISTESI:
        a = ln_k(f["theta_g1"], f["Ta1"], T)
        bad = ln_k(TUTUSMADI["theta_g1"], TUTUSMADI["Ta1"], T)
        good = ln_k(TUTUSTU["theta_g1"], TUTUSTU["Ta1"], T)
        pay = a - bad
        ust = good - bad
        ayr[T] = (pay, ust)
        sinif.append("RISKLI" if pay <= 0 else ("GUVENLI" if pay >= ust else "BELIRSIZ"))
    if "RISKLI" in sinif:
        s = "RISKLI"
    elif all(c == "GUVENLI" for c in sinif):
        s = "GUVENLI"
    else:
        s = "BELIRSIZ"
    return s, ayr


def tablo(X):
    sat = []
    for i, x in enumerate(X):
        s, ayr = risk(x)
        f = P.fiziksel(x)
        sat.append((i, f"{f['theta_g1']:.3f}", f"{f['Ta1']:.0f}", *[f"{ayr[T][0]:+.3f}" for T in T_LISTESI], s))
    return sat
