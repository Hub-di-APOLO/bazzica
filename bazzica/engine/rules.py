"""Configurazione delle regole (varianti come insiemi di flag)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace


@dataclass(frozen=True)
class RulesConfig:
    scambio: bool = False          # Heisenberg: fase di scambio carte con il compagno
    einstein: bool = False         # tris con il 7 bello = 5 Scope
    fermi: bool = False            # 2 di denari = -5 + punti di mazzo; Napoleone = 10
    pascal: bool = False           # assi di chi ha chiamato Bazzica valgono 1
    curie: bool = False            # Piccola e Grande
    federico: bool = False         # Napola
    avogadro: bool = False         # ogni asso preso è Scopa
    margherita_hack: bool = False  # 4 Mani esatte
    punti_vittoria: int = 21
    nome_variante: str = "Vanilla"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "RulesConfig":
        return RulesConfig(**d)

    def descrizione(self) -> str:
        s = self.nome_variante
        if self.margherita_hack:
            s += " + Margherita Hack"
        return s


_ORDINE = ["Vanilla", "Heisenberg", "Einstein", "Fermi", "Pascal", "Curie", "Federico II", "Avogadro"]
_FLAG = {
    "Heisenberg": "scambio",
    "Einstein": "einstein",
    "Fermi": "fermi",
    "Pascal": "pascal",
    "Curie": "curie",
    "Federico II": "federico",
    "Avogadro": "avogadro",
}

VARIANTI = tuple(_ORDINE)


def preset(nome: str, margherita_hack: bool = False) -> RulesConfig:
    """Restituisce la configurazione di una variante nominata (cumulativa)."""
    if nome not in _ORDINE:
        raise ValueError(f"Variante sconosciuta: {nome}")
    flags = {}
    for n in _ORDINE[1:_ORDINE.index(nome) + 1]:
        flags[_FLAG[n]] = True
    return RulesConfig(nome_variante=nome, margherita_hack=margherita_hack, **flags)


def with_flags(rules: RulesConfig, **kw) -> RulesConfig:
    return replace(rules, **kw)
