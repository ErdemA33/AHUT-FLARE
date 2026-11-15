/*---------------------------------------------------------------------------*\
    coupledEvaporationSpeciesFvPatchScalarField — bkz. .H
\*---------------------------------------------------------------------------*/

#include "coupledEvaporationSpeciesFvPatchScalarField.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "fluidThermophysicalTransportModel.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::coupledEvaporationSpeciesFvPatchScalarField::
coupledEvaporationSpeciesFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(p, iF),
    epsilon_(0)
{
    this->refValue() = 0;
    this->refGrad() = 0;
    this->valueFraction() = 0;
}


Foam::coupledEvaporationSpeciesFvPatchScalarField::
coupledEvaporationSpeciesFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    mixedFvPatchScalarField(p, iF),
    epsilon_(dict.lookup<scalar>("epsilon"))
{
    if (epsilon_ < 0 || epsilon_ > 1)
    {
        FatalIOErrorInFunction(dict)
            << "epsilon = " << epsilon_ << " [0, 1] araliginda olmali"
            << exit(FatalIOError);
    }

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


Foam::coupledEvaporationSpeciesFvPatchScalarField::
coupledEvaporationSpeciesFvPatchScalarField
(
    const coupledEvaporationSpeciesFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    mixedFvPatchScalarField(ptf, p, iF, mapper),
    epsilon_(ptf.epsilon_)
{}


Foam::coupledEvaporationSpeciesFvPatchScalarField::
coupledEvaporationSpeciesFvPatchScalarField
(
    const coupledEvaporationSpeciesFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(ptf, iF),
    epsilon_(ptf.epsilon_)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::coupledEvaporationSpeciesFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = patch().boundaryMesh().mesh();
    const label patchi = patch().index();

    // m'' [kg/m^2/s]: damlaBuharlasma'nın mDotEvap patch değeri
    scalarField mDot(patch().size(), 0);
    if (mesh.foundObject<volScalarField>("mDotEvap"))
    {
        mDot = mesh.lookupObject<volScalarField>("mDotEvap")
            .boundaryField()[patchi];
    }

    const fluidThermophysicalTransportModel& ttm =
        mesh.lookupType<fluidThermophysicalTransportModel>();

    const volScalarField& Yi =
        mesh.lookupObject<volScalarField>(internalField().name());

    const scalarField rhoD(ttm.DEff(Yi, patchi));
    const scalarField alpha(mDot/max(rhoD, small));     // [1/m]

    this->refValue() = epsilon_;
    this->refGrad() = 0;
    this->valueFraction() = alpha/(alpha + patch().deltaCoeffs());

    mixedFvPatchScalarField::updateCoeffs();
}


void Foam::coupledEvaporationSpeciesFvPatchScalarField::write
(
    Ostream& os
) const
{
    mixedFvPatchScalarField::write(os);
    writeEntry(os, "epsilon", epsilon_);
}


// * * * * * * * * * * * * * * * * Kayit  * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        coupledEvaporationSpeciesFvPatchScalarField
    );
}
