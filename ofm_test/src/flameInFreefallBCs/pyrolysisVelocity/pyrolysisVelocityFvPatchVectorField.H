/*---------------------------------------------------------------------------*\
Class
    Foam::pyrolysisVelocityFvPatchVectorField

Description
    Pirolize eden yuzeyde Stefan ufleme hizi sinir kosulu.

    Katidan cikan kutle, momentum denklemine yuzey normali boyunca bir hiz
    bileseni olarak girer:

        U_n = m_dot / rho_gaz          [m/s]

    - m_dot [kg/m^2/s]: ortak Arrhenius hesabi (pyrolysisArrhenius.H)
    - rho_gaz [kg/m^3]: yuzeydeki gaz yogunlugu (cozucuden okunur)
    - Yon: yuzeyden gaz hacmine dogru (domain ici = -nf). Teget bilesen 0
      (kaymasiz).

    rho_s alanini YALNIZCA okur (guncelleyen pyrolysisFuelFraction).

    Taban sinif: fixedValueFvPatchVectorField
    Ornek alinan OF14 kaynak dosyalari icin README'ye bakin.

SourceFiles
    pyrolysisVelocityFvPatchVectorField.C

\*---------------------------------------------------------------------------*/

#ifndef pyrolysisVelocityFvPatchVectorField_H
#define pyrolysisVelocityFvPatchVectorField_H

#include "fixedValueFvPatchFields.H"

namespace Foam
{

/*---------------------------------------------------------------------------*\
            Class pyrolysisVelocityFvPatchVectorField Declaration
\*---------------------------------------------------------------------------*/

class pyrolysisVelocityFvPatchVectorField
:
    public fixedValueFvPatchVectorField
{
public:

    //- Runtime tip bilgisi
    TypeName("pyrolysisVelocity");


    // Constructors  (OF14 fixedValue ctor setiyle ayni sira)

        pyrolysisVelocityFvPatchVectorField
        (
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&
        );

        pyrolysisVelocityFvPatchVectorField
        (
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&,
            const dictionary&
        );

        pyrolysisVelocityFvPatchVectorField
        (
            const pyrolysisVelocityFvPatchVectorField&,
            const fvPatch&,
            const DimensionedField<vector, fvMesh>&,
            const fieldMapper&
        );

        //- ic alan referansi olmadan kopya: OF14'te silinmis
        pyrolysisVelocityFvPatchVectorField
        (
            const pyrolysisVelocityFvPatchVectorField&
        ) = delete;

        pyrolysisVelocityFvPatchVectorField
        (
            const pyrolysisVelocityFvPatchVectorField&,
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
                new pyrolysisVelocityFvPatchVectorField(*this, iF)
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
