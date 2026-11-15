/*---------------------------------------------------------------------------*\
    coupledEvaporationVelocityFvPatchVectorField — bkz. .H
\*---------------------------------------------------------------------------*/

#include "coupledEvaporationVelocityFvPatchVectorField.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"
#include "uniformDimensionedFields.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::coupledEvaporationVelocityFvPatchVectorField::coupledEvaporationVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(p, iF)
{}


Foam::coupledEvaporationVelocityFvPatchVectorField::coupledEvaporationVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const dictionary& dict
)
:
    fixedValueFvPatchVectorField(p, iF, dict)
{}


Foam::coupledEvaporationVelocityFvPatchVectorField::coupledEvaporationVelocityFvPatchVectorField
(
    const coupledEvaporationVelocityFvPatchVectorField& ptf,
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    fixedValueFvPatchVectorField(ptf, p, iF, mapper)
{}


Foam::coupledEvaporationVelocityFvPatchVectorField::coupledEvaporationVelocityFvPatchVectorField
(
    const coupledEvaporationVelocityFvPatchVectorField& ptf,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(ptf, iF)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::coupledEvaporationVelocityFvPatchVectorField::updateCoeffs()
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

    const scalarField& rhoGas =
        mesh.lookupObject<volScalarField>("rho").boundaryField()[patchi];

    // nf(): akışkan bölgesinden dışarı (sıvıya doğru); üfleme -nf yönünde.
    // Hareketli ağ: yüzeye göre bağıl akı rho (U.n - w) = -m'',
    // w = meshPhi/|Sf| (yüzeyin nf yönündeki hızı; movingWallVelocity kalıbı)
    const vectorField nHat(patch().nf());
    scalarField w(patch().size(), 0);
    if (mesh.moving())
    {
        w = scalarField(mesh.phi().boundaryField()[patchi])/patch().magSf();
    }
    this->operator==((w - mDot/max(rhoGas, small))*nHat);

    fixedValueFvPatchVectorField::updateCoeffs();
}


namespace Foam
{
    makePatchTypeField(fvPatchVectorField, coupledEvaporationVelocityFvPatchVectorField);
}
