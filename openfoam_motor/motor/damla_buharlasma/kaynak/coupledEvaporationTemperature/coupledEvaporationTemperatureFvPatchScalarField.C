/*---------------------------------------------------------------------------*\
    coupledEvaporationTemperatureFvPatchScalarField — bkz. .H
\*---------------------------------------------------------------------------*/

#include "coupledEvaporationTemperatureFvPatchScalarField.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "uniformDimensionedFields.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::coupledEvaporationTemperatureFvPatchScalarField::coupledEvaporationTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    fixedValueFvPatchScalarField(p, iF)
{}


Foam::coupledEvaporationTemperatureFvPatchScalarField::coupledEvaporationTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    fixedValueFvPatchScalarField(p, iF, dict)
{}


Foam::coupledEvaporationTemperatureFvPatchScalarField::coupledEvaporationTemperatureFvPatchScalarField
(
    const coupledEvaporationTemperatureFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    fixedValueFvPatchScalarField(ptf, p, iF, mapper)
{}


Foam::coupledEvaporationTemperatureFvPatchScalarField::coupledEvaporationTemperatureFvPatchScalarField
(
    const coupledEvaporationTemperatureFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    fixedValueFvPatchScalarField(ptf, iF)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::coupledEvaporationTemperatureFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = patch().boundaryMesh().mesh();

    // T_w = T_l (damlaBuharlasma TlDamla); model yoksa değer korunur
    if (mesh.foundObject<uniformDimensionedScalarField>("TlDamla"))
    {
        const scalar Tl =
            mesh.lookupObject<uniformDimensionedScalarField>("TlDamla")
           .value();
        this->operator==(Tl);
    }

    fixedValueFvPatchScalarField::updateCoeffs();
}


namespace Foam
{
    makePatchTypeField(fvPatchScalarField, coupledEvaporationTemperatureFvPatchScalarField);
}
