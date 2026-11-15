/*---------------------------------------------------------------------------*\
    flameInFreefallBCs — ortak piroliz yardimcilari (serbest fonksiyonlar)

    Uc sinir kosulu (pyrolysisFuelFraction, pyrolysisTemperature,
    pyrolysisVelocity) ayni Arrhenius fizigini ve ayni parametre dosyasini
    (constant/pyrolysisProperties) paylasir. Ortak taban sinif YOK (coklu
    kalitim + makePatchTypeField sorunlarindan kacinmak icin); yalnizca
    paylasilan serbest fonksiyonlar.

    rho_s yazma hakki: YALNIZCA pyrolysisFuelFraction gunceller (updateRhoS).
    Digerleri rho_s'i salt-okur.

    Birimler: her yer SI. rho_s dict'te g/m^2 yazili, okuma aninda kg/m^2'ye
    cevrilir (readPyrolysisDict icinde tek nokta).
\*---------------------------------------------------------------------------*/

#ifndef pyrolysisArrhenius_H
#define pyrolysisArrhenius_H

#include "scalarField.H"
#include "dictionary.H"
#include "fvMesh.H"
#include "IOdictionary.H"
#include "volFieldsFwd.H"

namespace Foam
{
namespace flameInFreefall
{

//- constant/pyrolysisProperties parametreleri (hepsi dosyadan okunur)
struct pyrolysisParams
{
    scalar A;            // [1/s]
    scalar E;            // [J/mol]
    scalar n;            // [-]
    scalar rho_s_ref;    // [kg/m^2]  (okuma aninda g/m^2'den donusturulmus)
    scalar rho_s_init;   // [kg/m^2]
    scalar L_pyrolysis;  // [J/kg]
    word   fuelSpecies;  // ornegin CH4
    scalar m_dot_max;    // [kg/m^2/s]  piroliz hiz tavani (stabilite)
    scalar yuzeyPayi;    // [-] gaza giden akinin bu yuze dusen payi (0.5 simetrik, 1 tek yuz; ontanim 1)
};


//- pyrolysisProperties sozlugunu mesh registry'sine bir kez kaydeder ve
//  referansini dondurur. MUST_READ_IF_MODIFIED: dosya degisirse yeniden
//  derlemeden otomatik yeniden okunur (A, E, L vb. derlemeden degistirilebilir).
const IOdictionary& pyrolysisDict(const fvMesh& mesh);

//- Parametreleri sozlukten oku (rho_s_ref/init: g/m^2 -> kg/m^2)
pyrolysisParams readPyrolysisDict(const dictionary& dict);

//- Yuzey hucresi basina Arrhenius piroliz hizi [kg/m^2/s]
//
//    m_dot = A * rho_s * exp(-E/(R*T)) * (rho_s/rho_s_ref)^(n-1)
//
//  rho_s <= 0 (burnout) ya da T <= 0 ise m_dot = 0. Esik yok: Arrhenius
//  dusuk T'de kendiliginden ~0 (karar: eski T_threshold kaldirildi).
scalar arrheniusRate(scalar T, scalar rho_s, const pyrolysisParams& p);

//- rho_s Euler ileri adimi:  rho_s[i] = max(0, rho_s[i] - m_dot[i]*deltaT)
void updateRhoS(scalarField& rho_s, const scalarField& m_dot, scalar deltaT);

//- Paylasilan rho_s alanini (katinin alansal yogunlugu, [kg/m^2]) registry'e
//  kaydeder ve referansini dondurur. Cozucu bu alani tanimadigi icin burada
//  olusturulur: zaman dizininde varsa okunur (READ_IF_PRESENT), yoksa
//  constant/pyrolysisProperties'teki rho_s_init (kg/m^2) ile baslatilir;
//  AUTO_WRITE ile her yazma adiminda diske yazilir. Idempotent.
volScalarField& rhoSField(const fvMesh& mesh);


} // namespace flameInFreefall
} // namespace Foam

#endif

// ************************************************************************* //
