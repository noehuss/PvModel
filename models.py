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

class PVplant:
    ratioPuissance = float

    def __init__(self, id, surface, orientation, inclinaison, productible, correction_productible=True) -> None:
        self.id = id
        self.surface = surface
        self.orientation = orientation
        self.inclinaison = inclinaison
        self.productible = productible*pertes_installation.at[self.inclinaison, self.orientation] if correction_productible else productible #kWh/kWc
        self.powerMax = self.surface*self.ratioPuissance/1000

    def productionCalc(self, power):
        self._power(power)
        self._energy()
        self._production_type()

    def _power(self, power):
        self.power = min(power, self.powerMax) if power is not None else self.powerMax
        self.utilisation = self.power/self.powerMax #0 à 1

    def _energy(self):
        self.production =  self.power*self.productible #kWh

    def _production_type(self):
        self.prod_df = pd.read_csv(filepath_or_buffer='prod_ref.csv', sep=';', index_col='DateTime')
        self.prod_df.index = pd.to_datetime(self.prod_df.index, dayfirst=True) # besoin de garder DateTime ? pas certain
        self.prod_df['Prod'] = self.prod_df['Prod']*self.productible/self.prod_df['Prod'].sum() # production horaire par kWc
    
class OmbrierePeigne(PVplant):
    type = 'ombriere'
    ratioPuissance = ratio_puissance[type]

class ToiturePlanePeigne(PVplant):
    type = 'toiture_plane'
    ratioPuissance = ratio_puissance[type]


class ToitureInclineePeigne(PVplant):
    type = 'toiture_inclinee'
    ratioPuissance = ratio_puissance[type]

class SolPeigne(PVplant):
    type = 'sol'
    ratioPuissance = ratio_puissance[type]

class Centrale(ABC):
    def __init__(self, id, peignes:list[PVplant], power:float):
        self.id = id
        self.peignes = sorted(peignes, key=lambda x: x.productible, reverse=True) # tri par ordre décroissant de productible / potentiel
        self.powerMax = sum(peigne.powerMax for peigne in self.peignes)
        self.productible = sum(peigne.productible*peigne.powerMax for peigne in self.peignes)/self.powerMax # weighted average
        self._centrale_definition(power)

    def _centrale_definition(self, power):
        self.power = min(power, self.powerMax) if power else self.powerMax
        remaining_power = self.power
        
        # Problem de knapsack continue
        for p in self.peignes:
            alloc = min(p.powerMax, remaining_power)
            p.productionCalc(alloc)
            remaining_power -= alloc

        self.total_production = sum(p.production for p in self.peignes)

    def production_profile(self) -> pd.DataFrame:
        """
        Agrège les courbes horaires de production de chaque peigne.
        """
        prod_total = None

        for p in self.peignes:
            prod_df = p.prod_df.copy()
            prod_df['Prod'] = prod_df['Prod'] * p.power  # kWh par heure pour ce peigne

            if prod_total is None:
                prod_total = prod_df[['Prod']].copy()
            else:
                prod_total['Prod'] += prod_df['Prod']

        self.prod_df = prod_total

        self.total_production = self.prod_df['Prod'].sum() #type:ignore
        return self.prod_df #type: ignore
    
    @abstractmethod
    def _capex(self, **kwargs):
        pass
    
    @abstractmethod
    def _opex(self):
        pass

class CentraleOmbriere(Centrale):
    def _capex(self, **kwargs):
        for k, val in kwargs.items():
            pass

    def _opex(self):
        pass


omb = OmbrierePeigne(id=1, surface=1000, orientation='est', inclinaison=10, productible=1000)
toi = ToitureInclineePeigne(id=2, surface=20, orientation='sud', inclinaison=20, productible=1200)
sol = SolPeigne(id=3, surface=30, orientation='ouest', inclinaison=20, productible=900)

centrale = CentraleOmbriere(id="C1", peignes=[omb], power=250)
print([p.power for p in centrale.peignes])

df = centrale.production_profile()

print(df.head())  # courbe horaire totale
print(f"Production annuelle totale : {centrale.total_production:.0f} kWh")

