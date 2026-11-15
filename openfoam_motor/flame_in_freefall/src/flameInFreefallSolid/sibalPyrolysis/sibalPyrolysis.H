/*---------------------------------------------------------------------------*\
    sibalPyrolysis — SIBAL kumas kati bolgesinde iki adimli piroliz (fvModel)

    Kaynaklar:
      Zhao vd. 2017, Proc. Combust. Inst. 36, 2971-2978, Tablo 1 (GPYRO bicimi)
      Li & Liao 2018, Combust. Sci. Technol. 190, 2082-2096, Tablo 2
      Olson vd. (UCL 10164340): Cs pamuk/cam elyaf agirlikli ortalamasi

    Reaksiyonlar (hacimsel, [kg/m^3/s]):
      R1: bakir pamuk -> (1-nu) buhar + nu ara kati (char)
          w1 = A1 rho01 (rhoV/rho01)^n1 exp(-E1/(R T))
      R2: ara kati -> buhar
          w2 = A2 rho02 (rhoCh/rho02)^n2 exp(-E2/(R T))

    Enerji (kati e = Cv T, conservative ddt(rho,e)):
      kaynak = -mVap*(XL(T) + cpComb*T),  XL(T) = XL0 + (cpF - Cv)(T - TL)
      cpComb*T kismi he uzerinden ortuk: -mVap*cpComb/Cv * e

    Kati termo (constSolidThermo) rho ve Cv'si her adimda guncellenir:
      rho = rhoInert + rhoV + rhoCh
      Cv  = (rhoInert*cpInert + (rhoV + rhoCh)*cpComb)/rho

    Ayrilan buhar, her hucrenin x-kolonundaki aray uz yuzune (interfacePatch)
    kutle akisi olarak yazilir: mDotPyro [kg/m^2/s] patch degeri. Akiskan
    bolgesi bunu coupledPyrolysis* BC'leriyle okur.

    Adim basina explicit (T adim basi), nOuter>1 icin idempotent.
\*---------------------------------------------------------------------------*/

#ifndef sibalPyrolysis_H
#define sibalPyrolysis_H

#include "fvModel.H"
#include "volFields.H"

namespace Foam
{
namespace fv
{

class sibalPyrolysis
:
    public fvModel
{
    // Parametreler
        scalar A1_, E1_, n1_, rho01_;
        scalar A2_, E2_, n2_, rho02_;
        scalar nu_;
        scalar rhoInert_, cpInert_, cpComb_;
        scalar XL0_, TL_, cpF_;
        word interfacePatchName_;

    // Alanlar
        mutable volScalarField rhoV_;
        mutable volScalarField rhoCh_;
        mutable volScalarField mDotPyro_;
        mutable volScalarField::Internal mVap_;

    // Adim basi kopyalar
        mutable scalarField rhoV0_;
        mutable scalarField rhoCh0_;
        mutable label timeIndex_;

    // Kolon eslemesi (global): bu islemcinin aray uz yuzlerine katki yapan
    // (kaynak islemci, kaynak hucre) -> yerel yuz
        label patchi_;
        labelList srcProc_;
        labelList srcCell_;
        labelList dstFace_;

    void readCoeffs(const dictionary& dict);
    void buildColumnMap();
    void updateThermo() const;

public:

    TypeName("sibalPyrolysis");

    sibalPyrolysis
    (
        const word& name,
        const word& modelType,
        const fvMesh& mesh,
        const dictionary& dict
    );

    virtual ~sibalPyrolysis() {}

    virtual wordList addSupFields() const;

    virtual void addSup
    (
        const volScalarField& he,
        fvMatrix<scalar>& eqn
    ) const;

    virtual void addSup
    (
        const volScalarField& rho,
        const volScalarField& he,
        fvMatrix<scalar>& eqn
    ) const;

    virtual void correct();

    virtual bool movePoints() { return true; }
    virtual void topoChange(const polyTopoChangeMap&) {}
    virtual void mapMesh(const polyMeshMap&) {}
    virtual void distribute(const polyDistributionMap&) {}

    virtual bool read(const dictionary& dict);
};

} // namespace fv
} // namespace Foam

#endif
