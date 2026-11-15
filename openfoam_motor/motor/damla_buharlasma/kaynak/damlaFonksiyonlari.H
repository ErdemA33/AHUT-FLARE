/*---------------------------------------------------------------------------*\
    damlaFonksiyonlari.H — OpenFOAM alanı istemeyen saf damla fonksiyonları

    Kaynak: referans/damla_cpp_paketi/referans/damla_motoru.py (DM)
      pDoyma   DM:244-246   P0 exp(Lb M / R_u (1/Tb - 1/T))
      LBuhar   DM:249-251   Lb (max(Tc - T, 1)/(Tc - Tb))^0.38
      TlSinirla DM:1267     min(max(Tl, 200), Tc - 1)
      Yfs      DM:1272-1276 Xfs = min(pDoyma/p, 0.98);
                            Yfs = Xfs M / (Xfs M + (1 - Xfs) Mdiger)
      Mdiger   DM:1273-1275 sum(Y_k, k!=F) / sum(Y_k/M_k, k!=F), boşsa 28
      mpp      DM:1277      max(a (Yfs - Y1)/max(1 - Yfs, 1e-6), 0)
      TlAdim   SPEC §3      m_l c_l dTl/dt = A q_s - mdot L(Tl), açık Euler
      rsAdim   SPEC §3      drs/dt = -mpp/rhoL, açık Euler

    R_u ve P0 DM ile aynı sayılar (DM:61, DM:63). OpenFOAM'ın kendi
    RR / Pstd değerleri kullanılmaz (fark birimTest'te ölçülür).
\*---------------------------------------------------------------------------*/

#ifndef damlaFonksiyonlari_H
#define damlaFonksiyonlari_H

#include <cmath>
#include <algorithm>

namespace damla
{

// DM:61, DM:63
constexpr double R_U = 8314.462618;     // J/(kmol K)
constexpr double P0  = 101325.0;        // Pa
constexpr double PI  = 3.14159265358979323846;

// Yakıt sabitleri (damlaYakitlar sözlüğünden okunur)
struct yakitSabitleri
{
    double M;       // kg/kmol
    double Tb;      // K
    double Tc;      // K
    double Lb;      // J/kg
    double rhoL;    // kg/m3
    double cL;      // J/(kg K)
};

// DM:1267
inline double TlSinirla(const double Tl, const yakitSabitleri& y)
{
    return std::min(std::max(Tl, 200.0), y.Tc - 1.0);
}

// DM:244-246 — Clausius-Clapeyron (sabit Lb), Pa
inline double pDoyma(const double T, const yakitSabitleri& y)
{
    return P0*std::exp(y.Lb*y.M/R_U*(1.0/y.Tb - 1.0/T));
}

// DM:249-251 — Watson (1943), J/kg
inline double LBuhar(const double T, const yakitSabitleri& y)
{
    return y.Lb*std::pow(std::max(y.Tc - T, 1.0)/(y.Tc - y.Tb), 0.38);
}

// DM:1273-1275 — yakıt dışı türlerin ortalama mol kütlesi
// Y, M: n elemanlı diziler; iF: yakıt indisi
inline double Mdiger(const double* Y, const double* M, const int n, const int iF)
{
    double s = 0, sm = 0;
    for (int k = 0; k < n; k++)
    {
        if (k == iF) continue;
        s += Y[k];
        sm += Y[k]/M[k];
    }
    return s > 0 ? s/sm : 28.0;
}

// DM:1272 — yüzeyde yakıt mol kesri
inline double Xfs(const double Tl, const double p, const yakitSabitleri& y)
{
    return std::min(pDoyma(Tl, y)/p, 0.98);
}

// DM:1276 — yüzeyde yakıt kütle kesri
inline double Yfs
(
    const double Tl,
    const double p,
    const double Mdig,
    const yakitSabitleri& y
)
{
    const double X = Xfs(Tl, p, y);
    return X*y.M/(X*y.M + (1.0 - X)*Mdig);
}

// DM:1277 — buharlaşma kütle akısı, kg/(m2 s); a = rho D_F / delta
inline double mpp(const double a, const double Yfs_, const double Y1)
{
    return std::max(a*(Yfs_ - Y1)/std::max(1.0 - Yfs_, 1e-6), 0.0);
}

// SPEC §3 — sıvı enerji, açık Euler (adım başı değerlerle)
// qs: yüzeyde gazdan sıvıya ısı akısı lambda dT/dr|_s [W/m2]
inline double TlAdim
(
    const double Tl,
    const double rs,
    const double qs,
    const double mpp_,
    const double dt,
    const yakitSabitleri& y
)
{
    const double A = 4.0*PI*rs*rs;
    const double ml = 4.0/3.0*PI*rs*rs*rs*y.rhoL;
    const double mdot = A*mpp_;
    return Tl + dt*(A*qs - mdot*LBuhar(Tl, y))/(ml*y.cL);
}

// SPEC §3 — yarıçap, açık Euler
inline double rsAdim
(
    const double rs,
    const double mpp_,
    const double dt,
    const yakitSabitleri& y
)
{
    return rs - dt*mpp_/y.rhoL;
}

} // End namespace damla

#endif
