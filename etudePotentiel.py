import pandas as pd
from production import *
from abc import ABC, abstractmethod

#sitePV  object: consommation, prix
class EtudePotentiel:
    def __init__(self, centrale:Centrale, site):
        self.centrale = centrale
        self.site = site

    @abstractmethod
    def _power_flow(self):
        pass

    @abstractmethod
    def bilan_eco(self):
        pass

    def payback_time(self):
        pass
    
class EtudeVenteTotale(EtudePotentiel):
    def _power_flow(self):
        self.power_flow = centrale.prod_df.copy()
        
    def bilan_eco(self):
        self.prix_vente = 1
        self.revenues  = self.prix_vente*self.power_flow['Prod'].sum()
