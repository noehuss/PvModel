import pandas as pd
import yaml
from abc import ABC, abstractmethod

# Idée
# Classe PVplant: par polygone, classe PVtype (ou autre): par type d'installation (Ombrière, Sol, Toiture, Toiture Plane) pour différencier les calculs de CAPEX

# Load param
with open("param_ap.yaml", encoding="utf-8") as file:
    param_ap = yaml.load(file, Loader=yaml.FullLoader)
pertes_installation = pd.DataFrame(param_ap['pertes_installation']['orientation'], index=param_ap['pertes_installation']['inclinaison'])
ratio_puissance = param_ap['ratio_puissance']

class PVplant(ABC):
    ratioPuissance = float

    def __init__(self, id, surface, orientation, inclinaison, productible, power=0) -> None:
        self.id = id
        self.surface = surface
        self.orientation = orientation
        self.inclinaison = inclinaison
        self.power = power
        self.productible = productible #kWh/kWc
        self._power()
        self._energy()

    def _power(self):
        self.powerMax = self.surface*self.ratioPuissance
        self.power = min(self.power, self.powerMax) # clip
        self.utilisation = self.power/self.powerMax #0 à 1

    def _energy(self):
        self.production =  self.power*self.productible*pertes_installation.at[self.inclinaison, self.orientation] #kWh
    
class Ombriere(PVplant):
    type = 'ombriere'
    ratioPuissance = ratio_puissance[type]

class ToiturePlane(PVplant):
    type = 'toiture_plane'
    ratioPuissance = ratio_puissance[type]


class ToitureInclinee(PVplant):
    type = 'toiture_inclinee'
    ratioPuissance = ratio_puissance[type]

class Sol(PVplant):
    type = 'sol'
    ratioPuissance = ratio_puissance[type]

omb = Ombriere(id=1, surface=10, orientation='est', inclinaison=10, productible=1000)
print(omb.powerMax)
print(omb.production)