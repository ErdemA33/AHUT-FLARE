/*---------------------------------------------------------------------------*\
    coupledEvaporationTemperatureFvPatchScalarField — damla yüzeyi sıcaklığı T = T_l (Dirichlet)
\*---------------------------------------------------------------------------*/

#ifndef coupledEvaporationTemperatureFvPatchScalarField_H
#define coupledEvaporationTemperatureFvPatchScalarField_H

#include "fixedValueFvPatchFields.H"

namespace Foam
{

class coupledEvaporationTemperatureFvPatchScalarField
:
    public fixedValueFvPatchScalarField
{
public:

    TypeName("coupledEvaporationTemperature");

    coupledEvaporationTemperatureFvPatchScalarField(const fvPatch&, const DimensionedField<scalar, fvMesh>&);

    coupledEvaporationTemperatureFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const dictionary&
    );

    coupledEvaporationTemperatureFvPatchScalarField
    (
        const coupledEvaporationTemperatureFvPatchScalarField&,
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const fieldMapper&
    );

    coupledEvaporationTemperatureFvPatchScalarField(const coupledEvaporationTemperatureFvPatchScalarField&) = delete;

    coupledEvaporationTemperatureFvPatchScalarField
    (
        const coupledEvaporationTemperatureFvPatchScalarField&,
        const DimensionedField<scalar, fvMesh>&
    );

    virtual tmp<fvPatchScalarField> clone
    (
        const DimensionedField<scalar, fvMesh>& iF
    ) const
    {
        return tmp<fvPatchScalarField>(new coupledEvaporationTemperatureFvPatchScalarField(*this, iF));
    }

    virtual void updateCoeffs();
};

} // End namespace Foam

#endif
