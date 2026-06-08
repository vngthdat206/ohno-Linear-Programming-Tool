from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProblemData:
    objective_sense: str
    obj_coeffs: List[Fraction]
    constraints: List[Dict[str, Any]]
    var_signs: List[str]


@dataclass
class Snapshot:
    basis: List[int]
    rows: List[Dict[int, Fraction]]
    rhs: List[Fraction]
    obj_const: Fraction
    obj: Dict[int, Fraction]
    phase: int
    objective_label: str
    all_names: List[str]
    art_vars: List[int]


@dataclass
class PivotStep:
    phase: int
    method: str
    iteration: int
    before: Snapshot
    after: Optional[Snapshot]
    entering: Optional[int]
    leaving_row: Optional[int]
    leaving_var: Optional[int]
    pivot_value: Optional[Fraction]
    ratios: List[Tuple[int, Fraction, int]]
    degenerate: bool = False
    status: str = "pivot"


@dataclass
class SolveTrace:
    status: str
    steps: List[PivotStep]
    final_snapshot: Optional[Snapshot]
    degenerate_steps: int = 0
    cycle_detected: bool = False
    infeasible: bool = False
    unbounded: bool = False
    multiple_optimal: bool = False
    phase1_infeasible: bool = False
    phase1_value: Optional[Fraction] = None


@dataclass
class SolveReport:
    status: str
    used_method: str
    dantzig: SolveTrace
    bland: Optional[SolveTrace]
    engine: "SimplexEngine"
    solution_std: Dict[int, Fraction]
    solution_orig: Dict[int, Fraction]
    objective_std: Optional[Fraction]
    objective_orig: Optional[Fraction]
    multiple_optimal: bool
    multiple_optimal_vars: Optional[List[int]]
    notes: List[str]
    phase1_bland: Optional[SolveTrace] = None
    phase2_trace: Optional[SolveTrace] = None
