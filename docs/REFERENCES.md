# References

Compiled from the citations in `presentation/equations.md`, the parameter files (`*_parameters.json`, `ofm_material_params.json`) and the code comments.
Entries are only as complete as the repository's own notes: a field that is missing here was not recorded in the repository.
**Complete the missing details (title, volume, pages, DOI) from the original paper before final submission.**

Status flags:
- **verified**: the source file was found and the equation or value was read at the stated page (`presentation/equations.md`, section 6).
- **from memory**: cited in code or documents, but the paper was not opened; the value was entered from memory.
- **unverified**: the source is not in our local folders.

## A. Equations and parameters, page-verified

| Ref | Used for | Status |
|---|---|---|
| Spalding, D. B. (1953). The combustion of liquid fuels. *Proc. 4th Symp. (Int.) Combust.*, 847–864. | Transfer number B, `ln(1+B)`, evaporation constant K (droplet engine) | verified (§3.3 p. 853, §4 p. 854) |
| Godsave, G. A. E. (1953). Studies of the combustion of drops in a fuel spray — the burning of single drops of fuel. *Proc. 4th Symp. (Int.) Combust.*, 818–830. | d²-law, measured burning constants | verified (Eq. 15 p. 823, Table 1 p. 825) |
| Irace, et al. (2021). *Combust. Flame* 229, 111373. | Radiative extinction temperature 1140 K (sphere flames) | verified (p. 6, p. 8) |
| Snegirev, A. "On radiative extinction of microgravity diffusion flames" (pre-peer-review manuscript, cited in code as Snegirev 2022). | Extinction temperatures T_kr for ethylene, propane, methane | verified (pp. 1, 9); **journal and year not confirmed from the file** |
| Lecoustre, V. R., Sunderland, P. B., Chao, B. H., Axelbaum, R. L. Modeled quenching limits of spherical hydrogen diffusion flames. *Proc. Combust. Inst.* 34 (2013), 887–894. | H₂ extinction temperature 1070 K | verified (p. 893) |
| Cao, Ma, Bennett, et al. A computational and experimental study of coflow laminar methane/air diffusion flames: effects of fuel dilution, inlet velocity, and gravity. *Proc. Combust. Inst.* 35 (preprint). | Microgravity jet flame elongation (+28 %) | verified (PDF p. 4) |
| Dehghani, P., Sunderland, P. B., Quintiere, J. G., de Ris, J. L. (2021). Burning in microgravity: experimental results and analysis. *Combust. Flame* 228, 315–330. | Heat flux to a flat burner, gasification heat Eq. (21); BRE data | verified (Eq. 21 p. 326, Table 2 p. 321) |

## B. Cited in code and documents, not page-verified

**Combustion and heat transfer**
- Westbrook, C. K., Dryer, F. L. (1981). *Combust. Sci. Technol.* 27, 31 (Table 2). One-step kinetics, T_a = 15098 K (30 kcal/mol). *From memory; not checked against the paper's table.*
- Roper, F. G. (1977). *Combust. Flame* 29, 219–226. Laminar jet diffusion flame length; buoyancy velocity. (File exists locally; OCR unreadable, equation number not checked.)
- Ranz, W. E., Marshall, W. R. (1952). Droplet heat/mass transfer, `Nu/2 = 1 + 0.3 Pr^(1/3) Re^(1/2)`.
- Faeth, G. M. (1977). *Prog. Energy Combust. Sci.* 3, 191. Droplet combustion with natural convection.
- Puri, I. K., Seshadri, K. (1986). *Combust. Flame* 65, 137. Methane–air counterflow extinction strain a_q = 380 1/s.
- Kent, J. H. (1986). *Combust. Flame* 63, 349 (Table 1). Soot tendency from smoke-point mass flow.
- Nayagam, V., et al. (2012). *Combust. Flame* 159, 3583. Cold flame / radiative extinction of droplets.
- Farouk, T., Dryer, F. L. (2011, 2014). Droplet cold flame and extinction (details to be added).
- Marchese, A. J., Dryer, F. L. (1996); Dryer, F. L., et al. (2014). Water absorption by alcohol droplets (FLEX). *Unverified.*
- Law, C. K., Law, H. K. (1977). Variable-property droplet inner region. *Unverified.*
- Law, C. K., Faeth, G. M. (1994). *Prog. Energy Combust. Sci.* 20, 65–113. Droplet burning, 1 g vs µg review.
- Okajima, S., Kumagai, S. (1975). n-heptane droplet burning (1 g literature comparison).
- Choi, M. Y., Dryer, F. L. (2001). Droplet burning, flame/droplet ratio.
- Fernandez-Pello, A. C., Ray, S. R., Glassman, I. (1981). Blow-off (Damköhler) criterion. T'ien, J. S. (1986); Fernandez-Pello, A. C. (1984). Buoyancy-velocity scale. de Ris, J. N. (1969). Flame spread rate.
- Dzik, Nayagam, Williams (2010). *Int. Commun. Heat Mass Transfer* (doi 10.1016/j.icheatmasstransfer.2009.10.006). n-heptane droplet data.
- Dotson, K. T., Sunderland, P. B. (2010). AIAA 2010-1105. SPICE smoke point on the ISS (methane: no smoke point found).
- Linteris, G. T., Rafferty, J. (2008). Smoke-point flame lengths, Table 1 (SFPE column).
- Lamb, Roper (1940); Zeldovich (flame speed temperature dependence).
- Leckner (1972), WSGG: listed as a *candidate* for the radiation model, not used.

**Textbooks (not available locally, unverified)**
- Law, C. K. (2006). *Combustion Physics*. Cambridge University Press. (S_L,ref, flame speed, Ch. 7.)
- Turns, S. R. (2012). *An Introduction to Combustion*, 3rd ed. (Ch. 2, 10.)
- Modest, M. F. (2013). *Radiative Heat Transfer*, 3rd ed. (§11: κ_P = 3.83 f_v C₀ T / C₂.)
- Siegel, R., Howell, J. R. *Thermal Radiation Heat Transfer*.
- Hurley, M. J. (ed.) (2016). *SFPE Handbook of Fire Protection Engineering*, 5th ed. Springer, ISBN 978-1-4939-2565-0. Tables used: 36.5 (LOI), 4.11 (soot constant), A.24, A.31, A.32, A.36, A.37, A.38, A.39.

**Transport, thermodynamics and property data**
- Wilke, C. R. (1950). Viscosity of gas mixtures (mixing rule).
- Mathur, S., Tondon, P. K., Saxena, S. C. (1967). Thermal conductivity of gas mixtures (mixing rule).
- Watson, K. M. (1943). Heat of vaporisation correlation.
- Tee, L. S., Gotoh, S., Stewart, W. E. (1966). Lennard-Jones parameter correlation.
- Smith, G. P., et al. GRI-Mech 3.0 (JANAF thermo, transport `tran.dat`). Transport values entered from memory.
- Goodwin, D. G., et al. Cantera 3.2.0 (chemistry and property pre-computation). Alzueta (2023) mechanism for NH₃–CO–H₂.
- Bell, C. *chemicals* 1.5.2 (https://github.com/CalebBell/chemicals); DIPPR 801 (2017, via Serat).
- NIST Chemistry WebBook; Yaws, C. L. (2003). *Yaws' Handbook of Thermodynamic and Physical Properties of Chemical Compounds*; *Perry's Chemical Engineers' Handbook*, 8th ed.
- Stephenson and Malanowski (1987), Chase (1998), Majer and Svoboda (1985), Pittam and Pilcher (1972) and similar: sub-sources inside the NIST-derived property tables (`experiments/material_nist_fetch*.log`).
- Li, Liao (2018). *Combust. Sci. Technol.* 190, 2082–2096, Table 2. SIBAL (cotton–fibreglass) thermal properties (κ 0.0690 W/mK, ρ 573 kg/m³).
- Stoliarov, S. I., et al. (2009). *Combust. Flame* 156. PMMA pyrolysis A₁, E₁ (**from memory; paper could not be opened**).

## C. NASA experiment data and reports

- NASA Physical Sciences Informatics (PSI): Saffire I–III, BASS / BASS-II, FLEX / FLEX-2, BRE, SFLAME.
- NASA/TM-2021-0011385 — BASS-II summary report (PMMA λ = 2.09e-3 W/cm/K, α = 1.2e-3 cm²/s, L_v = 1700 J/g, pp. 64–65).
- NASA/TP-2015-216046 — FLEX per-test observations (cold-flame column).
- NTRS 20180005168 · NTRS 20170002628 (Saffire thermocouple bead placement) · NASA-CR 19970003276 (related to Marchese & Dryer).
- OpenFOAM Foundation, OpenFOAM 14 (`counterFlowFlame2D_GRI`, `smallPoolFire3D` tutorials).

## D. Not from a source (our own assumptions)

Marked in `presentation/equations.md` as **ASSUMPTION**: ethane T_kr (uses propane's 1200 K), jet aspect ratio 3, blow-off constant K = 5, soft temperature ceiling `2000 + a/(1 + a/700)`.
These must not be cited as literature values.
