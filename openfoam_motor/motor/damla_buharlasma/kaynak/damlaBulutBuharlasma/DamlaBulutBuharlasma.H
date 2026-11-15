/*---------------------------------------------------------------------------*\
    DamlaBulutBuharlasma — sprey (Lagrangian) parsel buharlaşması, DM formülleri

    damlaBuharlasma (yüzey çözümlü tek damla) ile aynı formüller
    (damlaFonksiyonlari.H): T_l kesmesi DM:1267, p_doyma DM:244-246,
    Xfs ≤ 0.98 ve Yfs DM:1272-1276, L Watson DM:249-251.
    Parsel ağ hücresinden küçük olduğu için yüzey akısı
    m'' = a (Yfs - Y_inf)/(1 - Yfs) (DM:1277) küre etrafında yarı-durağan
    integralle verilir:  dm/dt = pi d Sh rho D ln(1 + B_M),
    B_M = (Yfs - Y_inf)/(1 - Yfs),  Sh = 2 + 0.6 Re^1/2 Sc^1/3.
    D: OpenFOAM sıvı özelliklerinden (liquidEvaporationBoil ile aynı),
    rho: hücre karışım mol kütlesi ile pc W/(RR Ts).
    Kalıp: OpenFOAM 14 LiquidEvaporationBoil (yeni adla yeniden yazıldı).

    Girdi (cloudProperties, subModels):
        phaseChangeModel damlaBulutBuharlasma;
        damlaBulutBuharlasmaCoeffs
        {
            enthalpyTransfer latentHeat;     // L = DM Watson
            activeLiquids    (C7H16);
            yakit            NC7H16;
            #include         "<PAKET>/tablolar/damlaYakitlar"
        }
\*---------------------------------------------------------------------------*/

#ifndef DamlaBulutBuharlasma_H
#define DamlaBulutBuharlasma_H

#include "PhaseChangeModel.H"
#include "liquidMixtureProperties.H"
#include "damlaFonksiyonlari.H"

namespace Foam
{

template<class CloudType>
class DamlaBulutBuharlasma
:
    public PhaseChangeModel<CloudType>
{
protected:

        const liquidMixtureProperties& liquids_;
        List<word> activeLiquids_;
        List<label> liqToCarrierMap_;
        List<label> liqToLiqMap_;
        damla::yakitSabitleri y_;

        scalar Sh(const scalar Re, const scalar Sc) const;

public:

    TypeName("damlaBulutBuharlasma");

        DamlaBulutBuharlasma(const dictionary& dict, CloudType& cloud);

        DamlaBulutBuharlasma(const DamlaBulutBuharlasma<CloudType>& pcm);

        virtual autoPtr<PhaseChangeModel<CloudType>> clone() const
        {
            return autoPtr<PhaseChangeModel<CloudType>>
            (
                new DamlaBulutBuharlasma<CloudType>(*this)
            );
        }

    virtual ~DamlaBulutBuharlasma() {}

        virtual void calculate
        (
            const typename CloudType::parcelType& p,
            const typename CloudType::parcelType::trackingData& td,
            const scalar dt,
            const scalar Re,
            const scalar Pr,
            const scalar d,
            const scalar nu,
            const scalar T,
            const scalar Ts,
            const scalar pc,
            const scalar Tc,
            const scalarField& X,
            scalarField& dMassPC
        ) const;

        virtual scalar dh
        (
            const label idc,
            const label idl,
            const scalar p,
            const scalar T
        ) const;

        virtual scalar Tvap(const scalarField& X) const;

        virtual scalar TMax(const scalar p, const scalarField& X) const;
};

} // End namespace Foam

#ifdef NoRepository
    #include "DamlaBulutBuharlasma.C"
#endif

#endif
