/*---------------------------------------------------------------------------*\
    DamlaBulutBuharlasma — bkz. .H
\*---------------------------------------------------------------------------*/

#include "DamlaBulutBuharlasma.H"
#include "specie.H"
#include "mathematicalConstants.H"

// * * * * * * * * * * * * Protected Member Functions  * * * * * * * * * * * //

template<class CloudType>
Foam::scalar Foam::DamlaBulutBuharlasma<CloudType>::Sh
(
    const scalar Re,
    const scalar Sc
) const
{
    return 2.0 + 0.6*Foam::sqrt(Re)*cbrt(Sc);
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class CloudType>
Foam::DamlaBulutBuharlasma<CloudType>::DamlaBulutBuharlasma
(
    const dictionary& dict,
    CloudType& owner
)
:
    PhaseChangeModel<CloudType>(dict, owner, typeName),
    liquids_(owner.thermo().liquids()),
    activeLiquids_(this->typeDict().lookup("activeLiquids")),
    liqToCarrierMap_(activeLiquids_.size(), -1),
    liqToLiqMap_(activeLiquids_.size(), -1),
    y_()
{
    const word yakit(this->typeDict().template lookup<word>("yakit"));
    const dictionary& yd = this->typeDict().subDict(yakit);
    y_.M = yd.template lookup<scalar>("M");
    y_.Tb = yd.template lookup<scalar>("Tb");
    y_.Tc = yd.template lookup<scalar>("Tc");
    y_.Lb = yd.template lookup<scalar>("Lb");
    y_.rhoL = yd.template lookup<scalar>("rhoL");
    y_.cL = yd.template lookup<scalar>("cL");

    Info<< "damlaBulutBuharlasma: DM formulleri, yakit " << yakit
        << " (M " << y_.M << ", Tb " << y_.Tb << ", Lb " << y_.Lb << ")"
        << endl;

    forAll(activeLiquids_, i)
    {
        liqToCarrierMap_[i] =
            owner.composition().carrierId(activeLiquids_[i]);
    }

    const label idLiquid = owner.composition().idLiquid();
    forAll(activeLiquids_, i)
    {
        liqToLiqMap_[i] =
            owner.composition().localId(idLiquid, activeLiquids_[i]);
    }
}


template<class CloudType>
Foam::DamlaBulutBuharlasma<CloudType>::DamlaBulutBuharlasma
(
    const DamlaBulutBuharlasma<CloudType>& pcm
)
:
    PhaseChangeModel<CloudType>(pcm),
    liquids_(pcm.owner().thermo().liquids()),
    activeLiquids_(pcm.activeLiquids_),
    liqToCarrierMap_(pcm.liqToCarrierMap_),
    liqToLiqMap_(pcm.liqToLiqMap_),
    y_(pcm.y_)
{}


// * * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * //

template<class CloudType>
void Foam::DamlaBulutBuharlasma<CloudType>::calculate
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
) const
{
    const label celli = p.cell();
    const auto& carrier = this->owner().composition().carrier();
    const PtrList<volScalarField>& Yc = carrier.Y();

    // hücre karışım mol kütlesi
    scalar sYW = 0;
    forAll(Yc, k)
    {
        sYW += Yc[k][celli]/carrier.WiValue(k);
    }
    const scalar Wmix = 1.0/max(sYW, rootVSmall);

    forAll(activeLiquids_, i)
    {
        const label gid = liqToCarrierMap_[i];
        const label lid = liqToLiqMap_[i];

        // DM:1273-1275 — yakıt dışı türlerin ortalama mol kütlesi
        scalar s = 0, sm = 0;
        forAll(Yc, k)
        {
            if (k == gid) continue;
            s += Yc[k][celli];
            sm += Yc[k][celli]/carrier.WiValue(k);
        }
        const scalar Mdig = s > 0 ? s/sm : 28.0;

        const scalar Td = damla::TlSinirla(T, y_);              // DM:1267
        const scalar Yfs = damla::Yfs(Td, pc, Mdig, y_);        // DM:1272-1276
        const scalar Yinf = Yc[gid][celli];
        const scalar BM = (Yfs - Yinf)/max(1.0 - Yfs, 1e-6);    // DM:1277 biçimi

        if (BM > 0)
        {
            const scalar Dab = liquids_.properties()[lid].D(pc, Ts);
            const scalar Sc = nu/(Dab + rootVSmall);
            const scalar rhos = pc*Wmix/(RR*Ts);

            dMassPC[lid] +=
                constant::mathematical::pi*d*Sh(Re, Sc)*Dab*rhos
               *log(1.0 + BM)*dt;
        }
    }
}


template<class CloudType>
Foam::scalar Foam::DamlaBulutBuharlasma<CloudType>::dh
(
    const label idc,
    const label idl,
    const scalar p,
    const scalar T
) const
{
    typedef PhaseChangeModel<CloudType> parent;

    switch (parent::enthalpyTransfer_)
    {
        case (parent::etLatentHeat):
        {
            return damla::LBuhar(damla::TlSinirla(T, y_), y_);  // DM:249-251
        }
        case (parent::etEnthalpyDifference):
        {
            const scalar hc =
                this->owner().composition().carrier().hai(idc, p, T);
            const scalar hp = liquids_.properties()[idl].ha(p, T);
            return hc - hp;
        }
        default:
        {
            FatalErrorInFunction
                << "Unknown enthalpyTransfer type" << abort(FatalError);
        }
    }

    return 0;
}


template<class CloudType>
Foam::scalar Foam::DamlaBulutBuharlasma<CloudType>::Tvap
(
    const scalarField& X
) const
{
    return liquids_.Tpt(X);
}


template<class CloudType>
Foam::scalar Foam::DamlaBulutBuharlasma<CloudType>::TMax
(
    const scalar p,
    const scalarField& X
) const
{
    // p'deki kaynama noktası, Clausius-Clapeyron tersi (DM:430 biçimi)
    const scalar Tk =
        1.0/(1.0/y_.Tb - damla::R_U/(y_.Lb*y_.M)*log(p/damla::P0));
    return min(Tk, y_.Tc - 1.0);
}


// ************************************************************************* //
