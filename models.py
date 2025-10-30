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
    """
    Représente un peigne photovoltaïque (unité élémentaire d'une centrale).
    """

    def __init__(self, id: int, surface: float, orientation: str, inclinaison: float,
                 productible: float, ratio_puissance: float, correction_productible: bool = True):
        self.id = id
        self.surface = surface
        self.orientation = orientation
        self.inclinaison = inclinaison
        self._productible = productible
        self.ratio_puissance = ratio_puissance
        self.correction_productible = correction_productible

        self.power = None
        self.production = None
        self.prod_df = None

    @property
    def productible(self) -> float:
        """Productible corrigé selon orientation/inclinaison."""
        if self.correction_productible:
            return self._productible * pertes_installation.at[self.inclinaison, self.orientation]
        return self._productible

    @property
    def powerMax(self) -> float:
        """Puissance max installable (kWc)."""
        return self.surface * self.ratio_puissance / 1000

    def productionCalc(self, power: float | None = None) -> None:
        """Calcule la production horaire et annuelle pour une puissance donnée."""
        self._power(power)
        self._energy()
        self._production_profile()

    def _power(self, power: float | None) -> None:
        self.power = min(power, self.powerMax) if power is not None else self.powerMax
        self.utilisation = self.power / self.powerMax

    def _energy(self) -> None:
        self.production = self.power * self.productible  # kWh/an

    def _production_profile(self) -> None:
        prod_ref = pd.read_csv("prod_ref.csv", sep=";", index_col="DateTime")
        prod_ref.index = pd.to_datetime(prod_ref.index, dayfirst=True)
        prod_ref["Prod"] = prod_ref["Prod"] * self.productible / prod_ref["Prod"].sum()
        self.prod_df = prod_ref
    

class OmbrierePeigne(PVplant):
    def __init__(self, **kwargs):
        super().__init__(ratio_puissance=ratio_puissance["ombriere"], **kwargs)

class ToiturePlanePeigne(PVplant):
    def __init__(self, **kwargs):
        super().__init__(ratio_puissance=ratio_puissance["toiture_plane"], **kwargs)

class ToitureInclineePeigne(PVplant):
    def __init__(self, **kwargs):
        super().__init__(ratio_puissance=ratio_puissance["toiture_inclinee"], **kwargs)

class SolPeigne(PVplant):
    def __init__(self, **kwargs):
        super().__init__(ratio_puissance=ratio_puissance["sol"], **kwargs)

class Centrale(ABC):
    def __init__(self, id, peignes:list[PVplant], power:float, **kwargs):
        """
        **kwargs: 
        Pour ombrière:
            - structure: Simple, Double, Mixte
            - config_sol: Complexe, Moyen, Facile
        """
        self.id = id
        self.peignes = sorted(peignes, key=lambda x: x.productible, reverse=True) # tri par ordre décroissant de productible / potentiel
        self.powerMax = sum(peigne.powerMax for peigne in self.peignes)
        self.productible = sum(peigne.productible*peigne.powerMax for peigne in self.peignes)/self.powerMax # weighted average
        self.kwargs = kwargs
        self.allocate_power(power)
        self.capex: float
        self.opex: float
        self.lcoe: float
        self.estimation_eco(**kwargs)

    def update(self, power):
        self.allocate_power(power)
        self.estimation_eco(**self.kwargs)

    def allocate_power(self, power):
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

    def _lcoe(self):
        print(self.total_production)
        self.lcoe = (self.capex*1000 + 18.25849635*self.opex)/(14.68895095*self.total_production/1000)

    def estimation_eco(self, **kwargs):
        self._capex(**kwargs)
        self._opex()
        self._lcoe()

class CentraleOmbriere(Centrale):
    def _capex(self, **kwargs):
        """
        **kwargs: 
            - structure: Simple, Double, Mixte
            - config_sol: Complexe, Moyen, Facile
        """
        for k, val in kwargs.items():
            print(k, "=", val)
        coeffs = param_ap['capex_centrale_ombriere'][kwargs['structure']][kwargs['config_sol']]
        if self.power <= 700:
            self.capex = coeffs['a'] + coeffs['b']/(1+(self.power/coeffs['c'])**(-coeffs['d']))
        else:
            self.capex = coeffs['k'] + 184.7

    def _opex(self):
        if self.power < 200:
            self.opex = 8.54*self.power + 6630
        elif self.power < 500:
            self.opex = 8.17*self.power + 7420
        else:
            self.opex = 15.6*self.power + 5960


class ProductionSite:
    def __init__(self, id, centrales: list[Centrale]):
        self.id = id
        self.centrales = centrales
        self.powerMax = sum(c.powerMax for c in self.centrales)

        # pondération de la productibilité moyenne
        self.productible = sum(c.productible * c.powerMax for c in self.centrales) / self.powerMax

    def allocate_power(self, power: float):
        """
        Distribue la puissance donnée entre les centrales pour maximiser la production,
        en fonction du ratio productible / CAPEX (continuous knapsack).
        """
        self.power = min(power, self.powerMax)
        remaining_power = self.power

        # Trier les centrales par lcoe croissant
        self.centrales.sort(key=lambda c: c.lcoe, reverse=False)

        # Allocation gloutonne
        for c in self.centrales:
            alloc = min(c.powerMax, remaining_power)
            c.update(alloc)
            remaining_power -= alloc

        self.allocations = pd.DataFrame([
            {"centrale": c.id, "power_alloc": c.power, "lcoe": c.lcoe, "productible": c.productible, "capex": getattr(c, "capex", None)}
            for c in self.centrales
        ])

        self.total_production = sum(c.total_production for c in self.centrales if hasattr(c, "total_production"))
        return self.allocations

    def production_profile(self):
        """
        Agrège les profils de production horaires de toutes les centrales.
        """
        prod_total = None
        for c in self.centrales:
            if not hasattr(c, 'prod_df'):
                c.production_profile()
            prod_df = c.prod_df.copy()
            if prod_total is None:
                prod_total = prod_df[['Prod']].copy()
            else:
                prod_total['Prod'] += prod_df['Prod']

        self.prod_df = prod_total
        self.total_production = self.prod_df['Prod'].sum()
        return self.prod_df



omb = OmbrierePeigne(id=1, surface=3000, orientation='est', inclinaison=10, productible=1000)
toi = ToitureInclineePeigne(id=2, surface=20, orientation='sud', inclinaison=20, productible=1200)
sol = SolPeigne(id=3, surface=30, orientation='ouest', inclinaison=20, productible=900)

centrale = CentraleOmbriere(id="C1", peignes=[omb], power=800, structure='Double', config_sol='Facile')
centrale2 = CentraleOmbriere(id="C2", peignes=[omb], power=600, structure='Simple', config_sol='Facile')

print([p.power for p in centrale.peignes])
print(centrale.capex)
print(centrale.opex)
print(centrale.lcoe)
df = centrale.production_profile()

print(df.head())  # courbe horaire totale
print(f"Production annuelle totale : {centrale.total_production:.0f} kWh")

# Création du site
site = ProductionSite(id="Site_A", centrales=[centrale, centrale2])

# Allocation de puissance (ex: 1 MW)
alloc_df = site.allocate_power(1000)
print(alloc_df)

# Profil horaire global
prod_df = site.production_profile()
print(f"Production annuelle totale : {site.total_production:.0f} kWh")