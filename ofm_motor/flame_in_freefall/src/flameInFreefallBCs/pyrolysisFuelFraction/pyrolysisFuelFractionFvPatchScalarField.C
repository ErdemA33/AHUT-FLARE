/*---------------------------------------------------------------------------*\
    pyrolysisFuelFractionFvPatchScalarField (adim 2)

    Yakit turunun (CH4) kutle kesri icin Robin tipi piroliz sinir kosulu,
    mixedFvPatchScalarField ile kodlanmistir.

    Yuzey yakit-tur dengesi (dis normal nf; piroliz gazi saf yakit):
        toplam_dis_akis(yakit) = -m_dot
      =>  snGrad = alpha*(1 - Y_f),   alpha = m_dot/(rho*D)   [1/m]

    OF mixed formu  Y_f = f*refValue + (1-f)*(Y_c + refGrad/deltaCoeffs)
    ile eslesmesi icin:
        refValue      = 1          (saf yakit)
        refGrad       = 0
        valueFraction = alpha/(alpha + deltaCoeffs)
    m_dot=0 iken f=0 (saf zeroGradient); m_dot buyurken f->1 (saf yakit).

    Bu BC rho_s'i SAHIPLENIR: adim basina bir kez Euler ileri adimiyla
    gunceller (lookupObjectRef) ve mesh'e geri yazar. Diger iki BC salt-okur.

    rho*D (tur kutle yayinirligi): cozucunun etkin DEff'i
    (fluidThermophysicalTransportModel::DEff(Yi, patchi)).
\*---------------------------------------------------------------------------*/

#include "pyrolysisFuelFractionFvPatchScalarField.H"
#include "pyrolysisArrhenius.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"
#include "fluidThermophysicalTransportModel.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::pyrolysisFuelFractionFvPatchScalarField::
pyrolysisFuelFractionFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(p, iF),
    curTimeIndex_(-1)
{
    this->refValue() = 0;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::pyrolysisFuelFractionFvPatchScalarField::
pyrolysisFuelFractionFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    mixedFvPatchScalarField(p, iF),
    curTimeIndex_(-1)
{
    if (dict.found("value"))
    {
        fvPatchScalarField::operator=
        (
            scalarField("value", iF.dimensions(), dict, p.size())
        );
    }
    else
    {
        fvPatchScalarField::operator=(this->patchInternalField());
    }

    // Baslangicta Neumann
    this->refValue() = *this;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::pyrolysisFuelFractionFvPatchScalarField::
pyrolysisFuelFractionFvPatchScalarField
(
    const pyrolysisFuelFractionFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    mixedFvPatchScalarField(ptf, p, iF, mapper),
    curTimeIndex_(ptf.curTimeIndex_)
{}


Foam::pyrolysisFuelFractionFvPatchScalarField::
pyrolysisFuelFractionFvPatchScalarField
(
    const pyrolysisFuelFractionFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(ptf, iF),
    curTimeIndex_(ptf.curTimeIndex_)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::pyrolysisFuelFractionFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = internalField().mesh();
    const label patchi = patch().index();

    const flameInFreefall::pyrolysisParams p =
        flameInFreefall::readPyrolysisDict(flameInFreefall::pyrolysisDict(mesh));

    // Yuzey sicakligi (T alanindan) ve rho_s (bu BC guncelleyecek)
    const scalarField& Tp =
        mesh.lookupObject<volScalarField>("T").boundaryField()[patchi];

    volScalarField& rho_sVol = flameInFreefall::rhoSField(mesh);
    scalarField& rho_s = rho_sVol.boundaryFieldRef()[patchi];

    // Arrhenius m_dot [kg/m^2/s] (guncelleme ONCESI rho_s ile)
    scalarField mDot(patch().size());
    forAll(mDot, i)
    {
        mDot[i] = flameInFreefall::arrheniusRate(Tp[i], rho_s[i], p);
    }

    // rho_s Euler guncellemesi: adim basina YALNIZCA BIR kez
    // (updateCoeffs bir zaman adiminda birden cok cagrilabilir)
    if (curTimeIndex_ != mesh.time().timeIndex())
    {
        flameInFreefall::updateRhoS
        (
            rho_s,
            mDot,
            mesh.time().deltaTValue()
        );
        curTimeIndex_ = mesh.time().timeIndex();
    }

    // Tur kutle yayinirligi rho*D [kg/m/s]: cozucunun gercek etkin DEff'i
    // (OF14 fluidThermophysicalTransportModel). Boylece Le=1 varsayimina
    // gerek kalmaz; yakit turunun kendi yayinirligi kullanilir.
    const fluidThermophysicalTransportModel& ttm =
        patch().mesh().lookupType<fluidThermophysicalTransportModel>();
    const volScalarField& Yi =
        patch().mesh().lookupObject<volScalarField>(internalField().name());
    const scalarField rhoD(ttm.DEff(Yi, patchi));

    // Robin -> mixed katsayilari
    // gaza giden yakit akisi: bu yuzun payi (rho_s yukarida toplam mDot ile azaldi)
    const scalarField alpha(p.yuzeyPayi*mDot/max(rhoD, small));          // [1/m]
    this->refValue() = 1;                                    // saf yakit
    this->refGrad()  = 0;
    this->valueFraction() = alpha/(alpha + patch().deltaCoeffs());

    mixedFvPatchScalarField::updateCoeffs();
}


void Foam::pyrolysisFuelFractionFvPatchScalarField::write(Ostream& os) const
{
    mixedFvPatchScalarField::write(os);
}


// * * * * * * * * * * * * * * * * Kayit  * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        pyrolysisFuelFractionFvPatchScalarField
    );
}

// ************************************************************************* //
