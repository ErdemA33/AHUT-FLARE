/*---------------------------------------------------------------------------*\
    coupledPyrolysisSpeciesFvPatchScalarField — bkz. .H
\*---------------------------------------------------------------------------*/

#include "coupledPyrolysisSpeciesFvPatchScalarField.H"
#include "neighbourMDot.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "fluidThermophysicalTransportModel.H"

Foam::coupledPyrolysisSpeciesFvPatchScalarField::
coupledPyrolysisSpeciesFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(p, iF),
    fuel_(false)
{
    this->refValue() = 0;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::coupledPyrolysisSpeciesFvPatchScalarField::
coupledPyrolysisSpeciesFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    mixedFvPatchScalarField(p, iF),
    fuel_(dict.lookup<Switch>("fuel"))
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


Foam::coupledPyrolysisSpeciesFvPatchScalarField::
coupledPyrolysisSpeciesFvPatchScalarField
(
    const coupledPyrolysisSpeciesFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    mixedFvPatchScalarField(ptf, p, iF, mapper),
    fuel_(ptf.fuel_)
{}


Foam::coupledPyrolysisSpeciesFvPatchScalarField::
coupledPyrolysisSpeciesFvPatchScalarField
(
    const coupledPyrolysisSpeciesFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(ptf, iF),
    fuel_(ptf.fuel_)
{}


void Foam::coupledPyrolysisSpeciesFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const label patchi = patch().index();

    const scalarField mDot(flameInFreefall::neighbourMDot(patch(), "mDotPyro"));

    const fluidThermophysicalTransportModel& ttm =
        patch().mesh().lookupType<fluidThermophysicalTransportModel>();
    const volScalarField& Yi =
        patch().mesh().lookupObject<volScalarField>(internalField().name());
    const scalarField rhoD(ttm.DEff(Yi, patchi));

    const scalarField alpha(mDot/max(rhoD, small));     // [1/m]
    this->refValue() = fuel_ ? 1.0 : 0.0;
    this->refGrad() = 0;
    this->valueFraction() = alpha/(alpha + patch().deltaCoeffs());

    mixedFvPatchScalarField::updateCoeffs();
}


void Foam::coupledPyrolysisSpeciesFvPatchScalarField::write(Ostream& os) const
{
    mixedFvPatchScalarField::write(os);
    writeEntry(os, "fuel", fuel_);
}


namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        coupledPyrolysisSpeciesFvPatchScalarField
    );
}
