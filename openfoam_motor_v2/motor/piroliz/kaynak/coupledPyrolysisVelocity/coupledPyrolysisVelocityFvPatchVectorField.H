/*---------------------------------------------------------------------------*\
Class
    Foam::coupledPyrolysisVelocityFvPatchVectorField

Description
    Pirolize eden yuzeyde Stefan ufleme hizi sinir kosulu.

    Katidan cikan kutle, momentum denklemine yuzey normali boyunca bir hiz
    bileseni olarak girer:

        U_n = m_dot / rho_gaz          [m/s]

    - m_dot [kg/m^2/s]: komsu kati bolgenin mDotPyro patch degeri
      (sibalPyrolysis fvModel), mappedFvPatchBaseBase ile eslenir
    - rho_gaz [kg/m^3]: yuzeydeki gaz yogunlugu (cozucuden okunur)
    - Yon: yuzeyden gaz hacmine dogru (domain ici = -nf). Teget bilesen 0
      (kaymasiz).

    Taban sinif: fixedValueFvPatchVectorField
    Ornek alinan OF14 kaynak dosyalari icin README'ye bakin.

SourceFiles
    coupledPyrolysisVelocityFvPatchVectorField.C

\*---------------------------------------------------------------------------*/

#ifndef coupledPyrolysisVelocityFvPatchVectorField_H
#define coupledPyrolysisVelocityFvPatchVectorField_H

#include "fixedValueFvPatchFields.H"

namespace Foam
{

/*---------------------------------------------------------------------------*\
            Class coupledPyrolysisVelocityFvPatchVectorField Declaration
\*---------------------------------------------------------------------------*/

class coupledPyrolysisVelocityFvPatchVectorField
:
    public fixedValueFvPatchVectorField
{
public:

    //- Runtime tip bilgisi
    TypeName("coupledPyrolysisVelocity");


    // Constructors  (OF14 fixedValue ctor setiyle ayni sira)

        coupledPyrolysisVelocityFvPatchVectorField
        (
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&
        );

        coupledPyrolysisVelocityFvPatchVectorField
        (
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&,
            const dictionary&
        );

        coupledPyrolysisVelocityFvPatchVectorField
        (
            const coupledPyrolysisVelocityFvPatchVectorField&,
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&,
            const fieldMapper&
        );

        //- ic alan referansi olmadan kopya: OF14'te silinmis
        coupledPyrolysisVelocityFvPatchVectorField
        (
            const coupledPyrolysisVelocityFvPatchVectorField&
        ) = delete;

        coupledPyrolysisVelocityFvPatchVectorField
        (
            const coupledPyrolysisVelocityFvPatchVectorField&,
            const DimensionedField<vector, fvMesh>&
        );

        //- Clone
        virtual tmp<fvPatchVectorField> clone
        (
            const DimensionedField<vector, fvMesh>& iF
        ) const
        {
            return tmp<fvPatchVectorField>
            (
                new coupledPyrolysisVelocityFvPatchVectorField(*this, iF)
            );
        }


    // Member Functions

        //- U_n = m_dot/rho_gaz (domain ici), teget 0
        virtual void updateCoeffs();

        //- Alan dosyasina yaz
        virtual void write(Ostream&) const;
};


} // End namespace Foam

#endif

// ************************************************************************* //
