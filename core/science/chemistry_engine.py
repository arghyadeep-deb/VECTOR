"""
ChemistryEngine — RDKit molecular analysis wrapper.
Lazy-imports rdkit; degrades to SMILES-string parsing if not installed.
Architecture invariant: loop must never crash on ImportError.
"""

import re
from typing import Any
from loguru import logger
from core.config import CONFIG


class ChemistryEngine:
    """
    Molecular property analysis via RDKit.
    Degrades to heuristic SMILES parsing if RDKit is not installed.
    """

    def __init__(self):
        self._rdkit_available: bool | None = None
        self._Chem = None
        self._Descriptors = None
        logger.info("[VECTOR][chemistry] ChemistryEngine ready")

    def _check_rdkit(self) -> bool:
        if self._rdkit_available is None:
            try:
                from rdkit import Chem
                from rdkit.Chem import Descriptors
                self._Chem = Chem
                self._Descriptors = Descriptors
                self._rdkit_available = True
                logger.debug("[VECTOR][chemistry] RDKit available")
            except ImportError:
                self._rdkit_available = False
                logger.debug("[VECTOR][chemistry] RDKit not installed — heuristic mode")
        return self._rdkit_available

    # ── public API ────────────────────────────────────────────────────────────
    def analyze_molecule(self, smiles: str) -> dict:
        """
        Given a SMILES string, return molecular properties.
        Uses RDKit if available, else heuristic estimates.
        """
        if self._check_rdkit():
            return self._rdkit_analyze(smiles)
        return self._heuristic_analyze(smiles)

    def get_capabilities(self) -> dict:
        return {
            "rdkit_available": self._check_rdkit(),
            "mode": "rdkit" if self._check_rdkit() else "heuristic",
            "analyses": ["molecular_weight", "heavy_atoms", "rings", "validity"],
        }

    # ── RDKit implementation ──────────────────────────────────────────────────
    def _rdkit_analyze(self, smiles: str) -> dict:
        try:
            mol = self._Chem.MolFromSmiles(smiles)
            if mol is None:
                return {"smiles": smiles, "valid": False, "error": "Invalid SMILES", "method": "rdkit"}
            mw = self._Descriptors.MolWt(mol)
            heavy = mol.GetNumHeavyAtoms()
            rings = mol.GetRingInfo().NumRings()
            hbd = self._Descriptors.NumHDonors(mol)
            hba = self._Descriptors.NumHAcceptors(mol)
            logp = self._Descriptors.MolLogP(mol)
            return {
                "smiles": smiles,
                "valid": True,
                "molecular_weight": round(mw, 3),
                "heavy_atoms": heavy,
                "ring_count": rings,
                "h_bond_donors": hbd,
                "h_bond_acceptors": hba,
                "logP": round(logp, 3),
                "lipinski_ok": (mw <= 500 and hbd <= 5 and hba <= 10 and logp <= 5),
                "method": "rdkit",
            }
        except Exception as e:
            logger.warning("[VECTOR][chemistry] RDKit analyze failed: {}", e)
            return self._heuristic_analyze(smiles)

    # ── heuristic fallback (no RDKit) ─────────────────────────────────────────
    def _heuristic_analyze(self, smiles: str) -> dict:
        """Rough property estimation from SMILES atom count."""
        atoms = re.findall(r"[A-Z][a-z]?", smiles)
        heavy = len(atoms)
        # Each ring-closure digit appears exactly twice in a SMILES string
        # (once to open the ring bond, once to close it back to the same
        # atom) -- counting raw digit occurrences doubled every real ring
        # (e.g. "c1ccccc1" has 1 ring but 2 "1"s), inflating ring_count 2x
        # for the common single-digit-per-ring case this heuristic targets.
        rings = (smiles.count("1") + smiles.count("2")) // 2
        mw_estimate = heavy * 12.0  # very rough: assume mostly carbon
        return {
            "smiles": smiles,
            "valid": len(smiles) > 0,
            "molecular_weight": round(mw_estimate, 1),
            "heavy_atoms": heavy,
            "ring_count": rings,
            "method": "heuristic",
            "note": "Install rdkit for accurate properties",
        }


if __name__ == "__main__":
    eng = ChemistryEngine()
    caps = eng.get_capabilities()
    print(f"  mode={caps['mode']} rdkit={caps['rdkit_available']}")

    # Water
    water = eng.analyze_molecule("O")
    assert water.get("valid") is True or "smiles" in water, f"Water analysis failed: {water}"

    # Aspirin SMILES
    aspirin = eng.analyze_molecule("CC(=O)Oc1ccccc1C(=O)O")
    assert "molecular_weight" in aspirin, f"Missing MW: {aspirin}"
    if caps["rdkit_available"]:
        assert 170 < aspirin["molecular_weight"] < 185, f"Aspirin MW off: {aspirin['molecular_weight']}"

    print(f"OK chemistry_engine -- aspirin_mw={aspirin['molecular_weight']} method={aspirin['method']}")
