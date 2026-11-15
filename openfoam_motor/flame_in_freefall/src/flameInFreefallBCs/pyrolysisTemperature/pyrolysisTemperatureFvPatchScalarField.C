/*---------------------------------------------------------------------------*\
    pyrolysisTemperatureFvPatchScalarField (adim 2)

    Yuzey enerji dengesi (isil ince, kati icine akis ihmal):
        q_net = m_dot * L_pyrolysis   (yuzeyden ayrilir)
        dT/dn = -q_net / k_gaz
    valueFraction = 0 (saf gradyan/Neumann formu); m_dot dusuk T'de
    Arrhenius sayesinde ~0 oldugundan yuzey once gazdan isinir, pirolize
    baslayinca gradyan negatiflesir. rho_s YALNIZCA okunur.
\*---------------------------------------------------------------------------*/

#include "pyrolysisTemperatureFvPatchScalarField.H"
#include "pyrolysisArrhenius.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"
#include "thermophysicalTransportModel.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::pyrolysisTemperatureFvPatchScalarField::
pyrolysisTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(p, iF)
{
    this->refValue() = 0;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::pyrolysisTemperatureFvPatchScalarField::
pyrolysisTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    mixedFvPatchScalarField(p, iF)
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

    this->refValue() = *this;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::pyrolysisTemperatureFvPatchScalarField::
pyrolysisTemperatureFvPatchScalarField
(
    const pyrolysisTemperatureFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    mixedFvPatchScalarField(ptf, p, iF, mapper)
{}


Foam::pyrolysisTemperatureFvPatchScalarField::
pyrolysisTemperatureFvPatchScalarField
(
    const pyrolysisTemperatureFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(ptf, iF)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::pyrolysisTemperatureFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = internalField().mesh();
    const label patchi = patch().index();

    const flameInFreefall::pyrolysisParams p =
        flameInFreefall::readPyrolysisDict(flameInFreefall::pyrolysisDict(mesh));

    // Bu BC'nin uzerinde oldugu alan T'dir; patch sicakliklari:
    const scalarField& Tp = *this;

    // rho_s: YALNIZCA oku (guncelleyen pyrolysisFuelFraction)
    const scalarField& rho_s =
        flameInFreefall::rhoSField(mesh).boundaryField()[patchi];

    // Yuzeydeki gazin etkin isi iletim katsayisi k_gaz [W/m/K].
    // OF14: termo nesnesinde degil, thermophysicalTransportModel'de
    // (externalTemperature BC ile ayni erisim kalibi).
    const thermophysicalTransportModel& ttm =
        patch().mesh().lookupType<thermophysicalTransportModel>();
    const scalarField kappap(ttm.kappaEff(patchi));

    // Arrhenius m_dot [kg/m^2/s]
    scalarField mDot(patch().size());
    forAll(mDot, i)
    {
        mDot[i] = flameInFreefall::arrheniusRate(Tp[i], rho_s[i], p);
    }

    // q_net = m_dot*L  ->  dT/dn = -q_net/k_gaz
    this->refValue() = Tp;                 // valueFraction 0 iken kullanilmaz
    this->refGrad()  = -(p.yuzeyPayi*mDot*p.L_pyrolysis)/max(kappap, small);
    this->valueFraction() = 0;

    mixedFvPatchScalarField::updateCoeffs();
}


void Foam::pyrolysisTemperatureFvPatchScalarField::write(Ostream& os) const
{
    mixedFvPatchScalarField::write(os);
}


// * * * * * * * * * * * * * * * * Kayit  * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        pyrolysisTemperatureFvPatchScalarField
    );
}

// ************************************************************************* //
