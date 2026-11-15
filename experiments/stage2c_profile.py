"""Profil: bir parametre sabit (ızgara değeri), diğerleri tüm FLEX verisiyle ayarlanır -> kayıp + parçalar."""
import sys, json; sys.path.insert(0,'/path/to/ahut-flare')
import numpy as np, droplet_engine as dm
from scipy.optimize import minimize
ad, deger = sys.argv[1], float(sys.argv[2]); genis = len(sys.argv) > 3
t=dm.flex_oku(); X=dm.flex_bilesim(t)
i=dm.PARAM_ADLARI.index(ad)
sin=list(dm.SINIRLAR)
if genis:   # genişletilmiş sınırlar (profil dışındaki parametreler için)
    sin[dm.PARAM_ADLARI.index('beta')]=(0.0,1.6); sin[dm.PARAM_ADLARI.index('s')]=(0.3,12.0); sin[dm.PARAM_ADLARI.index('Ta')]=(4000.0,30000.0)
sin[i]=(deger,deger)
p0,_=dm.varsayilan_parametreler()
rng=np.random.default_rng(0); lo=np.array([b[0] for b in sin]); hi=np.array([b[1] for b in sin])
en=None
for k in range(5):
    x0=np.clip(np.array([p0[a] for a in dm.PARAM_ADLARI]),lo,hi) if k==0 else lo+rng.random(len(lo))*(hi-lo)
    r=minimize(dm.kayip_hizli,x0,args=(t,X),method='L-BFGS-B',bounds=sin,options={'maxiter':400})
    if en is None or r.fun<en.fun: en=r
_,parca=dm.kayip_hizli(en.x,t,X,ayrinti=True)
o=dm.hizli_tahmin(dm.param_sozluk(en.x),t,X); m=dm.olcutler(t,o)
print(json.dumps({'ad':ad,'deger':deger,'kayip':float(en.fun),'parca':parca,'p':dm.param_sozluk(en.x),'olcut':m}))
