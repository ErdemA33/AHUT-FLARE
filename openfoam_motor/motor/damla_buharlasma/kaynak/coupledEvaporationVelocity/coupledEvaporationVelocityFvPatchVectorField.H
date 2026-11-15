/*---------------------------------------------------------------------------*\
    coupledEvaporationVelocityFvPatchVectorField — damla yüzeyi Stefan hızı U = -(m''/rho_g) nf (kalıp: coupledPyrolysisVelocity)
\*---------------------------------------------------------------------------*/

#ifndef coupledEvaporationVelocityFvPatchVectorField_H
#define coupledEvaporationVelocityFvPatchVectorField_H

#include "fixedValueFvPatchFields.H"

namespace Foam
{

class coupledEvaporationVelocityFvPatchVectorField
:
    public fixedValueFvPatchVectorField
{
public:

    TypeName("coupledEvaporationVelocity");

    coupledEvaporationVelocityFvPatchVectorField(const fvPatch&, const DimensionedField<vector, fvMesh>&);

    coupledEvaporationVelocityFvPatchVectorField
    (
        const fvPatch&,
        const DimensionedField<vector, fvMesh>&,
        const dictionary&
    );

    coupledEvaporationVelocityFvPatchVectorField
    (
        const coupledEvaporationVelocityFvPatchVectorField&,
        const fvPatch&,
        const DimensionedField<vector, fvMesh>&,
        const fieldMapper&
    );

    coupledEvaporationVelocityFvPatchVectorField(const coupledEvaporationVelocityFvPatchVectorField&) = delete;

    coupledEvaporationVelocityFvPatchVectorField
    (
        const coupledEvaporationVelocityFvPatchVectorField&,
        const DimensionedField<vector, fvMesh>&
    );

    virtual tmp<fvPatchVectorField> clone
    (
        const DimensionedField<vector, fvMesh>& iF
    ) const
    {
        return tmp<fvPatchVectorField>(new coupledEvaporationVelocityFvPatchVectorField(*this, iF));
    }

    virtual void updateCoeffs();
};

} // End namespace Foam

#endif
