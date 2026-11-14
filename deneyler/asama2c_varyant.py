"""Bir varyantın dürüst testinin bir parçası: 'n2' (N2 ile kalibre -> CO2/He) ya da 'NC7H16'/'CH3OH' (yakıt dışarıda) ya da 'tum'."""
import sys, json; sys.path.insert(0,'/path/to/ahut-flare')
import numpy as np, damla_motoru as dm
parca=sys.argv[1]
t=dm.flex_oku(); X=dm.flex_bilesim(t)
if parca=='n2':
    mk=(t.seyreltici=='n2').to_numpy()
elif parca=='tum':
    mk=np.ones(len(t),bool)
else:
    mk=(t.yakit!=parca).to_numpy()
r=dm.kalibre_hizli(t[mk].reset_index(drop=True),X[:,mk],baslangic_sayisi=6)
p=dm.param_sozluk(r.x)
if parca in ('NC7H16','CH3OH'):
    diger=[z for z in dm.KALIBRE_YAKITLAR if z!=parca][0]; p[f'lnA_{parca}']=p[f'lnA_{diger}']
o=dm.hizli_tahmin(p,t,X)
out={'parca':parca,'kayip':float(r.fun),'p':p}
alt={'n2':{'eğitim N2':mk,'test CO2':(t.seyreltici=='co2').to_numpy(),'test He':(t.seyreltici=='he').to_numpy(),'test CO2+He':~mk},
     'tum':{'hepsi':mk}}.get(parca,{f'test {parca}':~mk})
for ad,m in alt.items():
    out[ad]=dm.olcutler(t[m].reset_index(drop=True),{k:v[m] for k,v in o.items()})
print(json.dumps(out,ensure_ascii=False))
