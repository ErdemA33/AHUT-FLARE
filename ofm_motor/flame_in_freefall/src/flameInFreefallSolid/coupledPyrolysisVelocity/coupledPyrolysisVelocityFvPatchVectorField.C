/*---------------------------------------------------------------------------*\
    coupledPyrolysisVelocityFvPatchVectorField (adim 2)

    U = (m_dot / rho_gaz) * (-nf), m_dot komsu kati bolgeden (mDotPyro).
\*---------------------------------------------------------------------------*/

#include "coupledPyrolysisVelocityFvPatchVectorField.H"
#include "neighbourMDot.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::coupledPyrolysisVelocityFvPatchVectorField::
coupledPyrolysisVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(p, iF)
{}


Foam::coupledPyrolysisVelocityFvPatchVectorField::
coupledPyrolysisVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const dictionary& dict
)
:
    fixedValueFvPatchVectorField(p, iF, dict)
{}


Foam::coupledPyrolysisVelocityFvPatchVectorField::
coupledPyrolysisVelocityFvPatchVectorField
(
    const coupledPyrolysisVelocityFvPatchVectorField& ptf,
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    fixedValueFvPatchVectorField(ptf, p, iF, mapper)
{}


Foam::coupledPyrolysisVelocityFvPatchVectorField::
coupledPyrolysisVelocityFvPatchVectorField
(
    const coupledPyrolysisVelocityFvPatchVectorField& ptf,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(ptf, iF)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::coupledPyrolysisVelocityFvPatchVectorField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = internalField().mesh();
    const label patchi = patch().index();

    // Komsu kati bolgeden kutle akisi [kg/m^2/s] (sibalPyrolysis)
    const scalarField mDot(flameInFreefall::neighbourMDot(patch(), "mDotPyro"));

    const scalarField& rhoGas =
        mesh.lookupObject<volScalarField>("rho").boundaryField()[patchi];

    // nf(): akiskan domaininden DISARI; ufleme -nf yonunde
    const vectorField nHat(patch().nf());
    this->operator==(-(mDot/max(rhoGas, small))*nHat);

    fixedValueFvPatchVectorField::updateCoeffs();
}


void Foam::coupledPyrolysisVelocityFvPatchVectorField::write(Ostream& os) const
{
    fixedValueFvPatchVectorField::write(os);
}


// * * * * * * * * * * * * * * * * Kayit  * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchVectorField,
        coupledPyrolysisVelocityFvPatchVectorField
    );
}

// ************************************************************************* //
