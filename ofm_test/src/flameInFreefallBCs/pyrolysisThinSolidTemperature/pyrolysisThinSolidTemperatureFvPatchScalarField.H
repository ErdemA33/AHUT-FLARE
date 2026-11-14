/*---------------------------------------------------------------------------*\
Class
    Foam::pyrolysisThinSolidTemperatureFvPatchScalarField

Description
    Isil ince kati (kumas) enerji denklemi ile yuzey sicakligi (Li 2020 yapisi):

        C dTs/dt = k_gaz (T_c - Ts) delta + q_igniter + qr - f m_dot L
        C        = f c_s (m_inert + rho_s)

    f      : yuzeyPayi (pyrolysisProperties; 0.5 simetrik yarim model, 1 tek yuz)
    q_ign  : W_m*f / (secilen yuzlerin toplam x-genisligi), t_on <= t < t_off,
             yuz merkezi x_min <= x <= x_max olan yuzlere
    qr     : radyasyon modelinin net duvar akisi (P1: duvara giren pozitif)
    Iletim terimi kapali (implicit); Ts0 zaman adimi basina bir kez saklanir.
    Gaza Dirichlet (valueFraction 1, refValue Ts) olarak verilir.
    rho_s YALNIZCA okunur (guncelleyen pyrolysisFuelFraction).

    Sozluk:
        c_s       1255;      // J/kg/K
        m_inert   0.0455;    // kg/m2 (toplam alan yogunlugu - yanabilir)
        qr        qr;        // alan adi; yoksa 0
        igniter { W_m 450.7; t_on 0; t_off 7.99; x_min 0.150; x_max 0.1657; }
\*---------------------------------------------------------------------------*/

#ifndef pyrolysisThinSolidTemperatureFvPatchScalarField_H
#define pyrolysisThinSolidTemperatureFvPatchScalarField_H

#include "mixedFvPatchFields.H"

namespace Foam
{

class pyrolysisThinSolidTemperatureFvPatchScalarField
:
    public mixedFvPatchScalarField
{
    // Private data

        scalar c_s_;
        scalar m_inert_;
        word qrName_;
        scalar W_m_;
        scalar t_on_;
        scalar t_off_;
        scalar x_min_;
        scalar x_max_;

        //- Onceki zaman adiminin yuzey sicakligi
        scalarField Ts0_;

        //- Ts0_'in ait oldugu zaman indeksi
        label timeIndex_;

    void readDict(const dictionary& dict);

public:

    TypeName("pyrolysisThinSolidTemperature");

    pyrolysisThinSolidTemperatureFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&
    );

    pyrolysisThinSolidTemperatureFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const dictionary&
    );

    pyrolysisThinSolidTemperatureFvPatchScalarField
    (
        const pyrolysisThinSolidTemperatureFvPatchScalarField&,
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const fieldMapper&
    );

    pyrolysisThinSolidTemperatureFvPatchScalarField
    (
        const pyrolysisThinSolidTemperatureFvPatchScalarField&
    ) = delete;

    pyrolysisThinSolidTemperatureFvPatchScalarField
    (
        const pyrolysisThinSolidTemperatureFvPatchScalarField&,
        const DimensionedField<scalar, fvMesh>&
    );

    virtual tmp<fvPatchScalarField> clone
    (
        const DimensionedField<scalar, fvMesh>& iF
    ) const
    {
        return tmp<fvPatchScalarField>
        (
            new pyrolysisThinSolidTemperatureFvPatchScalarField(*this, iF)
        );
    }

    virtual void updateCoeffs();

    virtual void write(Ostream&) const;
};

}

#endif
