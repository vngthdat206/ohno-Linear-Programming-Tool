from __future__ import annotations

import math
import re
import tkinter as tk
from dataclasses import dataclass
from fractions import Fraction
from tkinter import ttk, scrolledtext, messagebox, filedialog
from copy import deepcopy
from typing import Dict, List, Optional, Tuple, Any


# =========================
# Utilities
# =========================

def fr(x: Any) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(str(x))
    s = str(x).strip()
    if s == "":
        return Fraction(0)
    s = s.replace("−", "-")
    return Fraction(s)


def fmt_num(x: Fraction, mode: str = "Phân số", prec: int = 8) -> str:
    if not isinstance(x, Fraction):
        x = fr(x)
    if x == 0:
        return "0"
    if mode == "Số thập phân":
        val = float(x)
        if abs(val - round(val)) < 10 ** -(prec - 2):
            s = f"{round(val):.0f}"
        else:
            s = f"{val:.{prec}f}".rstrip("0").rstrip(".")
        return s.replace("-0", "0")
    if x.denominator == 1:
        return str(x.numerator)
    return f"{x.numerator}/{x.denominator}"


def clean_number_text(s: str) -> str:
    return s.strip().replace("−", "-")


SENSES = ["≤", "≥", "="]
VAR_SIGNS = ["≥0", "≤0", "tự do"]


# =========================
# Data models
# =========================

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


# =========================
# Simplex engine
# =========================

class SimplexEngine:
    def __init__(self, problem: ProblemData):
        self.problem = problem
        self.std_names: List[str] = []
        self.std_obj_coeffs: List[Fraction] = []
        self.std_constraints: List[List[Fraction]] = []
        self.std_senses: List[str] = []
        self.std_rhs: List[Fraction] = []
        self.variable_mapping: List[List[Tuple[int, Fraction]]] = []
        self.standardization_lines: List[str] = []
        self.strict_notes: List[str] = []
        self.all_names: List[str] = []
        self.artificial_vars: List[int] = []
        self.initial_basis: List[int] = []
        self.initial_rows: List[Dict[int, Fraction]] = []
        self.initial_rhs: List[Fraction] = []
        self.need_aux_phase1 = False
        self.phase1_aux_var_index: Optional[int] = None
        self._prepare()

    # ---------- transformation ----------
    def _prepare(self) -> None:
        self._transform_variables()
        self._transform_constraints()
        self._build_dictionary()

    def _transform_variables(self) -> None:
        raw_obj = [fr(c) for c in self.problem.obj_coeffs]
        if self.problem.objective_sense == "max":
            std_obj = [-c for c in raw_obj]
            self.standardization_lines.append(
                "Chuyển bài toán max về min tương đương bằng cách nhân (-1) vào hàm mục tiêu."
            )
        else:
            std_obj = raw_obj[:]
            self.standardization_lines.append("Vì hàm mục tiêu là hàm min, đã ở dạng chuẩn nên giữ nguyên:")

        self.variable_mapping = []
        self.std_names = []

        for idx, sign in enumerate(self.problem.var_signs):
            name = f"x{idx + 1}"
            if sign == "≥0":
                j = len(self.std_names)
                self.std_names.append(name)
                self.variable_mapping.append([(j, Fraction(1))])
                self.standardization_lines.append(f"  {name} ≥ 0: giữ nguyên {name} ≥ 0")
            elif sign == "≤0":
                j = len(self.std_names)
                y_name = f"y{idx + 1}"
                self.std_names.append(y_name)
                self.variable_mapping.append([(j, Fraction(-1))])
                self.standardization_lines.append(f"  {name} ≤ 0: đặt {name} = -{y_name}, với {y_name} ≥ 0")
            elif sign == "tự do":
                j1 = len(self.std_names)
                a_name = f"a{idx + 1}"
                self.std_names.append(a_name)
                j2 = len(self.std_names)
                b_name = f"b{idx + 1}"
                self.std_names.append(b_name)
                self.variable_mapping.append([(j1, Fraction(1)), (j2, Fraction(-1))])
                self.standardization_lines.append(
                    f"  {name} tự do: đặt {name} = {a_name} - {b_name}, với {a_name}, {b_name} ≥ 0"
                )
            else:
                raise ValueError(f"Kiểu dấu biến không hợp lệ: {sign}")

        nstd = len(self.std_names)
        self.std_obj_coeffs = [Fraction(0) for _ in range(nstd)]
        for orig_idx, mapping in enumerate(self.variable_mapping):
            for k, coef in mapping:
                self.std_obj_coeffs[k] += std_obj[orig_idx] * coef

        self.standardization_lines.append("")
    def _transform_constraints(self) -> None:
        n_orig = len(self.problem.var_signs)
        next_slack = n_orig + 1

        def fmt_expr(coeffs: list[Fraction], names: list[str]) -> str:
            parts: list[str] = []
            for c, nm in zip(coeffs, names):
                if c == 0:
                    continue
                sign = "+" if c > 0 else "-"
                abs_c = abs(c)
                if abs_c == 1:
                    parts.append(f"{sign} {nm}")
                else:
                    parts.append(f"{sign} {fmt_num(abs_c, 'Phân số')}{nm}")
            if not parts:
                return "0"
            text = " ".join(parts)
            return text[2:] if text.startswith("+ ") else text

        self.std_constraints = []
        self.std_senses = []
        self.std_rhs = []

        for i, cons in enumerate(self.problem.constraints):
            coeffs = [fr(x) for x in cons["coeffs"]]
            row = [Fraction(0) for _ in range(len(self.std_names))]
            for orig_idx, mapping in enumerate(self.variable_mapping):
                for k, coef in mapping:
                    row[k] += coeffs[orig_idx] * coef

            sense = cons["sense"]
            rhs = fr(cons["rhs"])

            if sense == "≥":
                row = [-a for a in row]
                rhs = -rhs
                sense = "≤"
                self.standardization_lines.append(
                    f'  RB{i + 1}: do dấu của ràng buộc đã là "≥", nên nhân cả hai vế với (-1) để đưa về "≤".'
                )
            elif sense == "=":
                slack_name = f"x{next_slack}"
                next_slack += 1
                self.std_names.append(slack_name)
                self.std_obj_coeffs.append(Fraction(1))
                row.append(Fraction(-1))
                self.standardization_lines.append(
                    f'  RB{i + 1}: do ràng buộc ở dạng đẳng thức "=", nên ta trừ thêm biến bù {slack_name} ≥ 0 vào vế trái.'
                )
                self.standardization_lines.append(f"  ---> RB{i + 1}:  {fmt_expr(row, self.std_names)} ≤ {fmt_num(rhs, 'Phân số')}")
                self.std_constraints.append(row)
                self.std_senses.append("≤")
                self.std_rhs.append(rhs)
                continue
            elif sense == "≤":
                self.standardization_lines.append(
                    f'  RB{i + 1}: giữ nguyên, do dấu của ràng buộc đã là "≤"'
                )
            else:
                raise ValueError(f"Dấu ràng buộc không hợp lệ: {sense}")

            self.standardization_lines.append(f"  ---> RB{i + 1}:  {fmt_expr(row, self.std_names)} ≤ {fmt_num(rhs, 'Phân số')}")
            self.std_constraints.append(row)
            self.std_senses.append(sense)
            self.std_rhs.append(rhs)

        self.standardization_lines.append("")
    def _build_dictionary(self) -> None:
        self.all_names = self.std_names[:]
        next_slack = 1
        basis: List[int] = []
        rows: List[Dict[int, Fraction]] = []
        rhs: List[Fraction] = []

        for coeffs, sense, b in zip(self.std_constraints, self.std_senses, self.std_rhs):
            if sense != "≤":
                raise ValueError(f"Chỉ nhận ràng buộc dạng ≤ sau chuẩn hóa, nhận được: {sense}")
            row = {j: -a for j, a in enumerate(coeffs) if a != 0}
            sidx = len(self.all_names)
            self.all_names.append(f"w{next_slack}")
            next_slack += 1
            basis.append(sidx)
            rows.append(row)
            rhs.append(b)

        self.initial_basis = basis
        self.initial_rows = rows
        self.initial_rhs = rhs
        self.artificial_vars = []
        self.need_aux_phase1 = any(b < 0 for b in self.initial_rhs)
    # ---------- dictionary operations ----------
    @staticmethod
    def _canonicalize(
        basis: List[int],
        rows: List[Dict[int, Fraction]],
        rhs: List[Fraction],
        raw_obj: Dict[int, Fraction],
        raw_const: Fraction = Fraction(0),
    ) -> Tuple[Fraction, Dict[int, Fraction]]:
        obj = deepcopy(raw_obj)
        const = raw_const
        for i, b in enumerate(basis):
            p = obj.get(b, Fraction(0))
            if p != 0:
                const += p * rhs[i]
                for j, a in rows[i].items():
                    obj[j] = obj.get(j, Fraction(0)) + p * a
                obj[b] = Fraction(0)
        obj = {j: c for j, c in obj.items() if c != 0}
        return const, obj

    @staticmethod
    def _pivot(
        basis: List[int],
        rows: List[Dict[int, Fraction]],
        rhs: List[Fraction],
        obj_const: Fraction,
        obj: Dict[int, Fraction],
        entering: int,
        leaving_row: int,
    ) -> Tuple[List[int], List[Dict[int, Fraction]], List[Fraction], Fraction, Dict[int, Fraction]]:
        d = rows[leaving_row].get(entering, Fraction(0))
        if d == 0:
            raise ZeroDivisionError("Pivot bằng 0")

        old_basic = basis[leaving_row]
        new_basis = basis[:]
        new_basis[leaving_row] = entering

        # Solve leaving row for entering variable.
        new_rows = [deepcopy(r) for r in rows]
        new_rhs = rhs[:]
        new_row: Dict[int, Fraction] = {old_basic: Fraction(1, 1) / d}
        for j, a in rows[leaving_row].items():
            if j == entering:
                continue
            new_row[j] = -a / d
        new_rows[leaving_row] = {k: v for k, v in new_row.items() if v != 0}
        new_rhs[leaving_row] = -rhs[leaving_row] / d

        # Substitute entering variable into all other rows.
        for i in range(len(rows)):
            if i == leaving_row:
                continue
            a_ie = rows[i].get(entering, Fraction(0))
            if a_ie == 0:
                continue

            updated: Dict[int, Fraction] = {}
            new_rhs[i] = rhs[i] + a_ie * new_rhs[leaving_row]
            updated[old_basic] = a_ie / d

            # coefficients from pivot row
            for j, a_rj in rows[leaving_row].items():
                if j == entering:
                    continue
                coeff = rows[i].get(j, Fraction(0)) - a_ie * a_rj / d
                if coeff != 0:
                    updated[j] = coeff

            for j, a_ij in rows[i].items():
                if j == entering or j in rows[leaving_row]:
                    continue
                if a_ij != 0:
                    updated[j] = a_ij

            new_rows[i] = {k: v for k, v in updated.items() if v != 0}

        # Objective update.
        c_e = obj.get(entering, Fraction(0))
        new_obj_const = obj_const + c_e * new_rhs[leaving_row]
        new_obj: Dict[int, Fraction] = {}
        if c_e != 0:
            new_obj[old_basic] = c_e / d
        for j, a_rj in rows[leaving_row].items():
            if j == entering:
                continue
            coeff = obj.get(j, Fraction(0)) - c_e * (a_rj / d)
            if coeff != 0:
                new_obj[j] = coeff
        for j, c in obj.items():
            if j == entering or j in rows[leaving_row]:
                continue
            if c != 0:
                new_obj[j] = new_obj.get(j, Fraction(0)) + c
        new_obj = {k: v for k, v in new_obj.items() if v != 0}
        return new_basis, new_rows, new_rhs, new_obj_const, new_obj

    def _state(
        self,
        basis: List[int],
        rows: List[Dict[int, Fraction]],
        rhs: List[Fraction],
        obj_const: Fraction,
        obj: Dict[int, Fraction],
        phase: int,
        objective_label: str,
        art_vars: Optional[List[int]] = None,
    ) -> Snapshot:
        return Snapshot(
            basis=basis[:],
            rows=[deepcopy(r) for r in rows],
            rhs=rhs[:],
            obj_const=obj_const,
            obj=deepcopy(obj),
            phase=phase,
            objective_label=objective_label,
            all_names=self.all_names[:],
            art_vars=(art_vars[:] if art_vars is not None else self.artificial_vars[:]),
        )

    # ---------- solving ----------
    def _choose_entering(self, obj: Dict[int, Fraction], basis: List[int], method: str) -> Optional[int]:
        basis_set = set(basis)
        neg_vars = [j for j, c in obj.items() if c < 0 and j not in basis_set]
        if not neg_vars:
            return None
        if method == "dantzig":
            # most negative coefficient among nonbasic variables
            return min(neg_vars, key=lambda j: (obj[j], j))
        return min(neg_vars)

    def _choose_leaving(self, snapshot: Snapshot, entering: int, method: str) -> Tuple[Optional[int], List[Tuple[int, Fraction, int]]]:
        candidates: List[Tuple[Fraction, int, int]] = []
        ratios: List[Tuple[int, Fraction, int]] = []
        for i, row in enumerate(snapshot.rows):
            a = row.get(entering, Fraction(0))
            if a < 0:
                theta = snapshot.rhs[i] / (-a)
                ratios.append((i, theta, snapshot.basis[i]))
                candidates.append((theta, snapshot.basis[i], i))
        if not candidates:
            return None, ratios
        if method == "dantzig":
            # smallest ratio, first occurrence in tie
            candidates.sort(key=lambda t: (t[0], t[2]))
            return candidates[0][2], ratios
        # Bland: smallest ratio, then smallest basis index
        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        return candidates[0][2], ratios

    def _solve_once(self, method: str, phase: int, basis: List[int], rows: List[Dict[int, Fraction]], rhs: List[Fraction], obj_const: Fraction, obj: Dict[int, Fraction], objective_label: str, art_vars: List[int]) -> SolveTrace:
        steps: List[PivotStep] = []
        seen = set()
        degenerate_steps = 0
        max_iter = 500

        def signature() -> Tuple:
            return (
                tuple(basis),
                tuple(sorted((i, tuple(sorted(r.items())), rhs[i]) for i, r in enumerate(rows))),
                obj_const,
                tuple(sorted(obj.items())),
                phase,
            )

        for iteration in range(1, max_iter + 1):
            sig = signature()
            if sig in seen:
                return SolveTrace(
                    status="cycle",
                    steps=steps,
                    final_snapshot=self._state(basis, rows, rhs, obj_const, obj, phase, objective_label, art_vars),
                    degenerate_steps=degenerate_steps,
                    cycle_detected=True,
                )
            seen.add(sig)

            snapshot = self._state(basis, rows, rhs, obj_const, obj, phase, objective_label, art_vars)
            entering = self._choose_entering(obj, basis, method)
            if entering is None:
                # optimal
                multiple = any(c == 0 for j, c in obj.items() if j not in basis)
                return SolveTrace(
                    status="optimal",
                    steps=steps,
                    final_snapshot=snapshot,
                    degenerate_steps=degenerate_steps,
                    multiple_optimal=multiple,
                )

            leaving_row, ratios = self._choose_leaving(snapshot, entering, method)
            if leaving_row is None:
                steps.append(
                    PivotStep(
                        phase=phase,
                        method=method,
                        iteration=iteration,
                        before=snapshot,
                        after=None,
                        entering=entering,
                        leaving_row=None,
                        leaving_var=None,
                        pivot_value=None,
                        ratios=ratios,
                        status="unbounded",
                    )
                )
                return SolveTrace(
                    status="unbounded",
                    steps=steps,
                    final_snapshot=snapshot,
                    degenerate_steps=degenerate_steps,
                    unbounded=True,
                )

            pivot_value = rows[leaving_row][entering]
            theta = rhs[leaving_row] / (-pivot_value)
            deg = theta == 0
            if deg:
                degenerate_steps += 1

            new_basis, new_rows, new_rhs, new_obj_const, new_obj = self._pivot(
                basis, rows, rhs, obj_const, obj, entering, leaving_row
            )

            after = self._state(new_basis, new_rows, new_rhs, new_obj_const, new_obj, phase, objective_label, art_vars)
            steps.append(
                PivotStep(
                    phase=phase,
                    method=method,
                    iteration=iteration,
                    before=snapshot,
                    after=after,
                    entering=entering,
                    leaving_row=leaving_row,
                    leaving_var=basis[leaving_row],
                    pivot_value=pivot_value,
                    ratios=ratios,
                    degenerate=deg,
                    status="pivot",
                )
            )
            basis, rows, rhs, obj_const, obj = new_basis, new_rows, new_rhs, new_obj_const, new_obj

        return SolveTrace(
            status="cycle",
            steps=steps,
            final_snapshot=self._state(basis, rows, rhs, obj_const, obj, phase, objective_label, art_vars),
            degenerate_steps=degenerate_steps,
            cycle_detected=True,
        )

    def _phase1_aux_start(self) -> Tuple[List[int], List[Dict[int, Fraction]], List[Fraction], Fraction, Dict[int, Fraction], int]:
        basis = self.initial_basis[:]
        rows = [dict(r) for r in self.initial_rows]
        rhs = self.initial_rhs[:]

        if self.phase1_aux_var_index is None:
            self.phase1_aux_var_index = len(self.all_names)
            self.all_names.append("x0")

        aux_idx = self.phase1_aux_var_index
        for row in rows:
            # FIX: Thêm x0 với hệ số +1 để từ vựng pha 1 đúng cách:
            # δ = x0 - a*var - ...
            row[aux_idx] = Fraction(1)

        # FIX: Hàm mục tiêu bổ trợ phải là δ = x0
        raw_obj = {aux_idx: Fraction(1)}
        const, obj = self._canonicalize(basis, rows, rhs, raw_obj, Fraction(0))
        return basis, rows, rhs, const, obj, aux_idx

    def _choose_leaving_phase1(
        self,
        snapshot: Snapshot,
        entering: int,
        method: str,
        iteration: int,
        aux_idx: int,
    ) -> Tuple[Optional[int], List[Tuple[int, Fraction, int]]]:
        candidates: List[Tuple[Fraction, int, int]] = []
        ratios: List[Tuple[int, Fraction, int]] = []

        for i, row in enumerate(snapshot.rows):
            a = row.get(entering, Fraction(0))
            if a == 0:
                continue
            if iteration == 1 and entering == aux_idx:
                # Iteration 1: Chọn hàng có RHS âm nhất (lấy giá trị tuyệt đối)
                theta = abs(snapshot.rhs[i])
                ratios.append((i, theta, snapshot.basis[i]))
                candidates.append((theta, snapshot.basis[i], i))
            else:
                # Sau iteration 1: chỉ xét các hàng có RHS và hệ số pivot trái dấu
                if snapshot.rhs[i] * a < 0:
                    theta = abs(snapshot.rhs[i] / a)
                    ratios.append((i, theta, snapshot.basis[i]))
                    candidates.append((theta, snapshot.basis[i], i))

        if not candidates:
            return None, ratios
        if method == "dantzig":
            candidates.sort(key=lambda t: (t[0], t[2]))
            return candidates[0][2], ratios
        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        return candidates[0][2], ratios


    def _solve_phase1_aux_once(
        self,
        method: str,
        basis: List[int],
        rows: List[Dict[int, Fraction]],
        rhs: List[Fraction],
        obj_const: Fraction,
        obj: Dict[int, Fraction],
        objective_label: str,
        aux_idx: int,
    ) -> SolveTrace:
        steps: List[PivotStep] = []
        degenerate_steps = 0

        # --- Bước đặc biệt 1: đưa x0 vào cơ sở bằng hàng có b_i âm nhất ---
        neg_rows = [(rhs[i], basis[i], i) for i in range(len(rhs)) if rhs[i] < 0]
        if not neg_rows:
            snapshot = self._state(basis, rows, rhs, obj_const, obj, 1, objective_label, self.artificial_vars)
            return SolveTrace(
                status="optimal",
                steps=[],
                final_snapshot=snapshot,
                degenerate_steps=0,
                multiple_optimal=all(c >= 0 for c in obj.values()),
            )

        neg_rows.sort(key=lambda t: (t[0], t[1], t[2]))
        leaving_row = neg_rows[0][2]
        snapshot_before = self._state(basis, rows, rhs, obj_const, obj, 1, objective_label, self.artificial_vars)
        pivot_value = rows[leaving_row].get(aux_idx, Fraction(0))
        if pivot_value == 0:
            raise ZeroDivisionError("Phần tử xoay ở bước pha 1 bằng 0")

        theta = abs(rhs[leaving_row] / pivot_value)
        deg = theta == 0
        if deg:
            degenerate_steps += 1

        new_basis, new_rows, new_rhs, new_obj_const, new_obj = self._pivot(
            basis, rows, rhs, obj_const, obj, aux_idx, leaving_row
        )
        after = self._state(new_basis, new_rows, new_rhs, new_obj_const, new_obj, 1, objective_label, self.artificial_vars)
        steps.append(
            PivotStep(
                phase=1,
                method=method,
                iteration=1,
                before=snapshot_before,
                after=after,
                entering=aux_idx,
                leaving_row=leaving_row,
                leaving_var=basis[leaving_row],
                pivot_value=pivot_value,
                ratios=[(i, rhs[i], basis[i]) for i in range(len(rhs)) if rhs[i] < 0],
                degenerate=deg,
                status="phase1_aux_pivot",
            )
        )

        # --- Sau bước đặc biệt, giải tiếp bằng đơn hình Dantzig/Bland như bình thường ---
        later = self._solve_once(
            method,
            1,
            new_basis,
            new_rows,
            new_rhs,
            new_obj_const,
            new_obj,
            objective_label,
            self.artificial_vars,
        )

        for st in later.steps:
            st.iteration += 1

        steps.extend(later.steps)
        return SolveTrace(
            status=later.status,
            steps=steps,
            final_snapshot=later.final_snapshot,
            degenerate_steps=degenerate_steps + later.degenerate_steps,
            cycle_detected=later.cycle_detected,
            infeasible=later.infeasible,
            unbounded=later.unbounded,
            multiple_optimal=later.multiple_optimal,
            phase1_infeasible=later.phase1_infeasible,
            phase1_value=later.phase1_value,
        )


    def _phase2_start(self, snapshot: Snapshot, strip_vars: Optional[List[int]] = None) -> Tuple[List[int], List[Dict[int, Fraction]], List[Fraction], Fraction, Dict[int, Fraction]]:
        # Rebuild the phase-2 objective from the current basis.
        basis = snapshot.basis[:]
        rows = [deepcopy(r) for r in snapshot.rows]
        rhs = snapshot.rhs[:]

        if strip_vars:
            strip_set = set(strip_vars)
            for row in rows:
                for v in strip_set:
                    row.pop(v, None)

        raw_obj = {j: c for j, c in enumerate(self.std_obj_coeffs) if c != 0}
        raw_const = Fraction(0)
        const, obj = self._canonicalize(basis, rows, rhs, raw_obj, raw_const)
        return basis, rows, rhs, const, obj

    def _phase1_start(self) -> Tuple[List[int], List[Dict[int, Fraction]], List[Fraction], Fraction, Dict[int, Fraction]]:
        basis = self.initial_basis[:]
        rows = [deepcopy(r) for r in self.initial_rows]
        rhs = self.initial_rhs[:]
        raw_obj = {a: Fraction(1) for a in self.artificial_vars}
        const, obj = self._canonicalize(basis, rows, rhs, raw_obj, Fraction(0))
        return basis, rows, rhs, const, obj


    def solve_full(self) -> SolveReport:
        notes = self.standardization_lines[:] + self.strict_notes[:]

        if self.need_aux_phase1:
            basis, rows, rhs, obj_const, obj, aux_idx = self._phase1_aux_start()
            phase1 = self._solve_phase1_aux_once("dantzig", basis, rows, rhs, obj_const, obj, "δ", aux_idx)
            phase1_bland = None
            if phase1.status == "cycle":
                phase1_bland = self._solve_phase1_aux_once("bland", basis, rows, rhs, obj_const, obj, "δ", aux_idx)
                if phase1_bland.status == "cycle":
                    return self._assemble_report(
                        "bland", phase1, phase1_bland, notes, phase1_infeasible=False,
                        phase1_bland=phase1_bland, phase2_trace=None
                    )
                phase1 = phase1_bland
                used = "bland"
            else:
                used = "dantzig"

            if phase1.final_snapshot is None:
                return self._assemble_report(
                    used, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=phase1_bland, phase2_trace=None
                )

            # x0 không còn nằm trong cơ sở và giá trị mục tiêu pha 1 bằng 0 => sang pha 2
            aux_idx_in_basis = aux_idx in phase1.final_snapshot.basis
            if phase1.final_snapshot.obj_const != 0 or aux_idx_in_basis:
                phase1.infeasible = True
                phase1.status = "infeasible"
                return self._assemble_report(
                    used, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=phase1_bland, phase2_trace=None
                )

            basis2, rows2, rhs2, obj_const2, obj2 = self._phase2_start(phase1.final_snapshot, strip_vars=[aux_idx])
            phase2 = self._solve_once(used, 2, basis2, rows2, rhs2, obj_const2, obj2, "z", self.artificial_vars)
            return self._assemble_report(
                used, phase1, phase2, notes, phase1_infeasible=False,
                phase1_bland=phase1_bland, phase2_trace=phase2
            )

        if self.artificial_vars:
            # Phase 1 first.
            basis, rows, rhs, obj_const, obj = self._phase1_start()
            phase1 = self._solve_once("dantzig", 1, basis, rows, rhs, obj_const, obj, "w", self.artificial_vars)
            phase1_bland = None
            if phase1.status == "cycle":
                phase1_bland = self._solve_once("bland", 1, basis, rows, rhs, obj_const, obj, "w", self.artificial_vars)
                if phase1_bland.status == "cycle":
                    return self._assemble_report(
                        "bland", phase1, phase1_bland, notes, phase1_infeasible=False,
                        phase1_bland=phase1_bland, phase2_trace=None
                    )
                phase1 = phase1_bland
                used = "bland"
            else:
                used = "dantzig"

            if phase1.final_snapshot is None:
                return self._assemble_report(
                    used, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=phase1_bland, phase2_trace=None
                )

            if phase1.final_snapshot.obj_const != 0:
                phase1.infeasible = True
                phase1.status = "infeasible"
                return self._assemble_report(
                    used, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=phase1_bland, phase2_trace=None
                )

            basis2, rows2, rhs2, obj_const2, obj2 = self._phase2_start(phase1.final_snapshot)
            phase2 = self._solve_once(used, 2, basis2, rows2, rhs2, obj_const2, obj2, "z", self.artificial_vars)
            return self._assemble_report(
                used, phase1, phase2, notes, phase1_infeasible=False,
                phase1_bland=phase1_bland, phase2_trace=phase2
            )

        # No artificials => phase 2 only.
        basis, rows, rhs, obj_const, obj = self._phase2_start(self._state(self.initial_basis, self.initial_rows, self.initial_rhs, Fraction(0), {}, 2, "z", self.artificial_vars))
        dantzig = self._solve_once("dantzig", 2, basis, rows, rhs, obj_const, obj, "z", self.artificial_vars)
        if dantzig.status == "cycle":
            bland = self._solve_once("bland", 2, basis, rows, rhs, obj_const, obj, "z", self.artificial_vars)
            return self._assemble_report(
                "bland", dantzig, bland, notes, phase1_infeasible=False,
                phase1_bland=None, phase2_trace=bland
            )
        return self._assemble_report(
            "dantzig", dantzig, None, notes, phase1_infeasible=False,
            phase1_bland=None, phase2_trace=dantzig
        )

    def _assemble_report(
        self,
        used_method: str,
        dantzig: SolveTrace,
        bland: Optional[SolveTrace],
        notes: List[str],
        phase1_infeasible: bool,
        phase1_bland: Optional[SolveTrace] = None,
        phase2_trace: Optional[SolveTrace] = None,
    ) -> SolveReport:
        trace = bland if (bland is not None and bland.status != "cycle") else dantzig
        final_snapshot = trace.final_snapshot
        solution_std, solution_orig, objective_std, objective_orig, multiple, multiple_vars = self.extract_solution(final_snapshot) if final_snapshot else ({}, {}, None, None, False, [])
        status = trace.status
        if dantzig.status == "cycle" and bland is not None and bland.status == "optimal":
            status = "optimal"
        return SolveReport(
            status=status,
            used_method=used_method,
            dantzig=dantzig,
            bland=bland,
            engine=self,
            solution_std=solution_std,
            solution_orig=solution_orig,
            objective_std=objective_std,
            objective_orig=objective_orig,
            multiple_optimal=multiple,
            multiple_optimal_vars=multiple_vars,
            notes=notes,
            phase1_bland=phase1_bland,
            phase2_trace=phase2_trace,
        )


    def extract_solution(self, snapshot: Snapshot) -> Tuple[Dict[int, Fraction], Dict[int, Fraction], Optional[Fraction], Optional[Fraction], bool, List[int]]:
        # Standard variables are the first len(std_names) indices.
        std_values = {i: Fraction(0) for i in range(len(self.std_names))}
        for i, b in enumerate(snapshot.basis):
            if b < len(self.std_names):
                std_values[b] = snapshot.rhs[i]
        # Original variables
        orig_values: Dict[int, Fraction] = {}
        for orig_idx, mapping in enumerate(self.variable_mapping):
            val = Fraction(0)
            for k, coef in mapping:
                val += coef * std_values.get(k, Fraction(0))
            orig_values[orig_idx] = val

        obj_std = snapshot.obj_const
        if self.problem.objective_sense == "max":
            obj_orig = -obj_std
        else:
            obj_orig = obj_std

        # Phát hiện vô số nghiệm:
        # Một biến không cơ sở có hệ số 0 trên hàng mục tiêu và còn có thể thay đổi một chút
        # mà không phá tính khả thi thì sẽ sinh ra vô số nghiệm tối ưu.
        basis_set = set(snapshot.basis)
        multiple = False
        free_vars: List[int] = []
        for j in range(len(self.std_names)):
            if j in basis_set:
                continue
            if snapshot.obj.get(j, Fraction(0)) != 0:
                continue

            col = [row.get(j, Fraction(0)) for row in snapshot.rows]
            neg_ratios = [
                snapshot.rhs[i] / (-a)
                for i, a in enumerate(col)
                if a < 0
            ]
            if not neg_ratios or min(neg_ratios) > 0:
                multiple = True
                free_vars.append(j)

        return std_values, orig_values, obj_std, obj_orig, multiple, free_vars

# =========================
# Helpers
# =========================

def sense_to_standard(s: str) -> str:
    s = s.strip()
    if s in {"≤", "≥", "="}:
        return s
    if s == "<":
        return "≤"
    if s == ">":
        return "≥"
    raise ValueError(f"Dấu ràng buộc không hợp lệ: {s}")


def parse_cell(value: str, mode: str) -> Fraction:
    value = clean_number_text(value)
    if value == "":
        return Fraction(0)
    try:
        return fr(value)
    except Exception as exc:
        raise ValueError(f"Không đọc được số: {value}") from exc


# =========================
# Rendering
# =========================

def term_str(coeff: Fraction, var: str, mode: str) -> str:
    coeff = fr(coeff)
    if coeff == 0:
        return ""
    sign = "+" if coeff > 0 else "-"
    abs_c = abs(coeff)
    if abs_c == 1:
        body = var
    else:
        body = f"{fmt_num(abs_c, mode)}{var}"
    return f"{sign} {body}"


def row_expr(label: str, const: Fraction, coeffs: Dict[int, Fraction], names: List[str], mode: str) -> str:
    # build aligned cells with fixed widths
    cells = []
    widths: Dict[int, int] = {}
    for j, name in enumerate(names):
        pieces = [term_str(coeffs.get(j, Fraction(0)), name, mode)]
        widths[j] = max(8, len(pieces[0]) + 2)
    parts = [f"{label} = {fmt_num(const, mode)}"]
    for j, name in enumerate(names):
        cell = term_str(coeffs.get(j, Fraction(0)), name, mode)
        parts.append(cell.ljust(widths[j]))
    return " ".join(parts).rstrip()


# =========================
# GUI App
# =========================

class SimplexApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ứng dụng Quy hoạch tuyến tính — Đơn hình")
        self.geometry("1380x920")
        self.minsize(1100, 760)

        self.objective_sense = tk.StringVar(value="max")
        self.n_vars = tk.IntVar(value=3)
        self.n_constraints = tk.IntVar(value=3)
        self.data_mode = tk.StringVar(value="Phân số")
        self.method_preference = tk.StringVar(value="auto")
        self.demo_preset_var = tk.StringVar(value="Ví dụ giải bằng 2 pha")
        self.need_aux_phase1 = False
        self.phase1_aux_var_index: Optional[int] = None

        self.obj_entries: List[tk.Entry] = []
        self.var_signs: List[ttk.Combobox] = []
        self.constraint_entries: List[List[tk.Entry]] = []
        self.constraint_senses: List[ttk.Combobox] = []
        self.constraint_rhs: List[tk.Entry] = []

        self.need_aux_phase1 = False
        self.phase1_aux_var_index: Optional[int] = None
        self.last_report: Optional[SolveReport] = None
        self.last_problem: Optional[ProblemData] = None
        self.export_btn: Optional[tk.Button] = None
        self.viz_btn: Optional[tk.Button] = None
        self._setup_style()
        self._build_ui()
        self._build_inputs()
        self.bind_all("<Control-Alt-r>", lambda e: self.run_solver())
        self.bind_all("<Control-Alt-R>", lambda e: self.run_solver())

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#f4f1eb")
        style.configure("Header.TFrame", background="#1f2937")
        style.configure("Header.TLabel", background="#1f2937", foreground="#ffffff", font=("Segoe UI", 16, "bold"))
        style.configure("SubHeader.TLabel", background="#1f2937", foreground="#dbeafe", font=("Segoe UI", 10))
        style.configure("TLabel", background="#f4f1eb", foreground="#172033", font=("Segoe UI", 10))
        style.configure("TLabelframe", background="#f4f1eb", borderwidth=1)
        style.configure("TLabelframe.Label", background="#f4f1eb", foreground="#111827", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map(
            "Accent.TButton",
            background=[("disabled", "#d1d5db"), ("active", "#1d4ed8"), ("!disabled", "#2563eb")],
            foreground=[("disabled", "#6b7280"), ("!disabled", "white")],
        )
        style.configure("Warn.TButton", background="#b45309", foreground="white")
        style.map("Warn.TButton", background=[("active", "#92400e")])
        style.configure("TCombobox", padding=4)
        style.configure("Treeview", rowheight=28)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 12))
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Ứng dụng Quy hoạch tuyến tính — Phương pháp Đơn hình", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Tab để chuyển ô • Ctrl+Alt+R để giải • Hỗ trợ max/min, ràng buộc ≤ ≥ =, biến tự do và biến dấu âm",
            style="SubHeader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        main = ttk.Frame(self, padding=14)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(2, weight=0)
        left.rowconfigure(3, weight=1)

        config = ttk.Labelframe(left, text="Thiết lập", padding=12)
        config.grid(row=0, column=0, sticky="ew")
        config.columnconfigure(1, weight=1)

        ttk.Label(config, text="Kiểu dữ liệu:").grid(row=0, column=0, sticky="w", pady=3)
        mode = ttk.Combobox(config, textvariable=self.data_mode, values=["Phân số", "Số thập phân"], state="readonly", width=12)
        mode.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(config, text="Số biến (1–5):").grid(row=1, column=0, sticky="w", pady=3)
        nvars = ttk.Spinbox(config, from_=1, to=5, textvariable=self.n_vars, width=10, command=self._build_inputs)
        nvars.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(config, text="Số ràng buộc (1–10):").grid(row=2, column=0, sticky="w", pady=3)
        ncons = ttk.Spinbox(config, from_=1, to=10, textvariable=self.n_constraints, width=10, command=self._build_inputs)
        ncons.grid(row=2, column=1, sticky="w", pady=3)

        ttk.Button(config, text="Tạo lại bảng nhập", command=self._build_inputs).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

        # ---- Nút xuất .txt + nút trực quan hoá ----
        action_row = ttk.Frame(config)
        action_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)

        self.export_btn = tk.Button(
            action_row,
            text="📄  Xuất file .txt",
            font=("Segoe UI", 9, "bold"),
            bg="#9ca3af", fg="white",
            activebackground="#6b7280", activeforeground="white",
            relief="flat", bd=0, padx=6, pady=7,
            cursor="arrow",
            state=tk.DISABLED,
            command=self.export_solution_txt,
        )
        self.export_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.export_btn.bind("<Enter>", lambda e: self._on_button_enter(e, "#0f766e"))
        self.export_btn.bind("<Leave>", lambda e: self._on_button_leave(e, "#9ca3af"))

        self.viz_btn = tk.Button(
            action_row,
            text="📊  Trực quan hóa BT 2 biến",
            font=("Segoe UI", 9, "bold"),
            bg="#0d9488", fg="white",
            activebackground="#0f766e", activeforeground="white",
            relief="flat", bd=0, padx=6, pady=7,
            cursor="hand2",
            command=self.visualize_two_variable_problem,
        )
        self.viz_btn.grid(row=0, column=1, sticky="ew")
        self.viz_btn.bind("<Enter>", lambda e: self._on_button_enter(e, "#0f766e"))
        self.viz_btn.bind("<Leave>", lambda e: self._on_button_leave(e, "#0d9488"))

        ttk.Button(config, text="Chạy giải thuật  (Ctrl+Alt+R)", style="Accent.TButton", command=self.run_solver).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

        btns = ttk.Frame(left)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        btns.columnconfigure(1, weight=1)
        ttk.Label(btns, text="Mẫu:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        demo_combo = ttk.Combobox(
            btns,
            textvariable=self.demo_preset_var,
            values=["Ví dụ giải bằng 2 pha", "Ví dụ giải bài toán xoay vòng", "Ví dụ giải bài toán vô số nghiệm"],
            state="readonly",
            width=26,
        )
        demo_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(btns, text="Điền ví dụ", style="Warn.TButton", command=self.fill_demo).grid(row=0, column=2, sticky="ew")

        input_box = ttk.Labelframe(left, text="Nhập bài toán", padding=14)
        input_box.grid(row=3, column=0, sticky="nsew")
        input_box.columnconfigure(0, weight=1)
        input_box.rowconfigure(0, weight=1)
        self.input_canvas = tk.Canvas(input_box, background="#f4f1eb", highlightthickness=0, width=580, height=650)
        self.input_canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(input_box, orient="vertical", command=self.input_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.input_canvas.configure(yscrollcommand=vsb.set)
        self.input_inner = ttk.Frame(self.input_canvas)
        self.input_window = self.input_canvas.create_window((0, 0), window=self.input_inner, anchor="nw")
        self.input_inner.bind("<Configure>", lambda e: self.input_canvas.configure(scrollregion=self.input_canvas.bbox("all")))
        self.input_canvas.bind("<Configure>", lambda e: self.input_canvas.itemconfigure(self.input_window, width=e.width))

        right = ttk.Labelframe(main, text="Lời giải", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.output = scrolledtext.ScrolledText(
            right,
            wrap="none",
            font=("Consolas", 12),
            bg="#fbfaf6",
            fg="#1e1b1b",
            insertbackground="#1e1b1b",
            relief="flat",
            padx=14,
            pady=10,
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.tag_configure("h1", font=("Segoe UI", 15, "bold"), foreground="#b45309", spacing1=8, spacing3=10)
        self.output.tag_configure("h2", font=("Segoe UI", 12, "bold"), foreground="#1f2937", spacing1=8, spacing3=4)
        self.output.tag_configure("note", foreground="#0f4c81")
        self.output.tag_configure("warn", foreground="#a16207")
        self.output.tag_configure("mono", font=("Consolas", 12))
        self.output.tag_configure("pivotcol", background="#fde68a")
        self.output.tag_configure("pivotrow", background="#dbeafe")
        self.output.tag_configure("pivotcell", background="#fca5a5")
        self.output.tag_configure("conclusion", background="#fff7ed")

        self.status_var = tk.StringVar(value="Sẵn sàng.")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(14, 6))
        status.grid(row=2, column=0, sticky="ew")

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        try:
            self.output.configure(wrap="none")
        except Exception:
            pass

    def _build_inputs(self):
        for child in self.input_inner.winfo_children():
            child.destroy()
        self.obj_entries.clear()
        self.var_signs.clear()
        self.constraint_entries.clear()
        self.constraint_senses.clear()
        self.constraint_rhs.clear()

        n = int(self.n_vars.get())
        m = int(self.n_constraints.get())

        # Objective block
        obj_frame = ttk.Labelframe(self.input_inner, text="Hàm mục tiêu", padding=10)
        obj_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        obj_frame.columnconfigure(1, weight=1)

        ttk.Label(obj_frame, text="Kiểu bài toán:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(obj_frame, textvariable=self.objective_sense, values=["max", "min"], state="readonly", width=8).grid(
            row=0, column=1, sticky="w", pady=2
        )
        ttk.Label(obj_frame, text="Hệ số:").grid(row=1, column=0, sticky="w", pady=(8, 2))
        coef_row = ttk.Frame(obj_frame)
        coef_row.grid(row=1, column=1, sticky="ew", pady=(8, 2))
        for j in range(n):
            coef_row.columnconfigure(j, weight=1)
            cell = ttk.Frame(coef_row)
            cell.grid(row=0, column=j, padx=4, sticky="ew")
            ttk.Label(cell, text=f"x{j+1}").grid(row=0, column=0, sticky="w")
            e = ttk.Entry(cell, width=10)
            e.grid(row=1, column=0, sticky="ew")
            self.obj_entries.append(e)

        sign_frame = ttk.Frame(obj_frame)
        sign_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for j in range(n):
            sign_cell = ttk.Frame(sign_frame)
            sign_cell.grid(row=0, column=j, padx=4, sticky="ew")
            ttk.Label(sign_cell, text=f"x{j+1}").grid(row=0, column=0, sticky="w")
            cb = ttk.Combobox(sign_cell, values=VAR_SIGNS, state="readonly", width=10)
            cb.set("≥0")
            cb.grid(row=1, column=0, sticky="ew")
            self.var_signs.append(cb)

        # Constraints block
        cons_frame = ttk.Labelframe(self.input_inner, text="Ràng buộc", padding=10)
        cons_frame.grid(row=1, column=0, sticky="nsew")
        cons_frame.columnconfigure(0, weight=1)

        ttk.Label(cons_frame, text="Nhập hệ số từng ràng buộc, chọn dấu rồi nhập vế phải.").grid(row=0, column=0, sticky="w", pady=(0, 6))
        table = ttk.Frame(cons_frame)
        table.grid(row=1, column=0, sticky="ew")
        for j in range(n):
            table.columnconfigure(j, weight=1)
        table.columnconfigure(n, weight=0)
        table.columnconfigure(n+1, weight=0)
        table.columnconfigure(n+2, weight=0)

        header = ttk.Frame(table)
        header.grid(row=0, column=0, columnspan=n+3, sticky="ew")
        ttk.Label(header, text="").grid(row=0, column=0, padx=2)
        for j in range(n):
            ttk.Label(header, text=f"x{j+1}", width=8, anchor="center").grid(row=0, column=j+1, padx=2)
        ttk.Label(header, text="Dấu", width=8, anchor="center").grid(row=0, column=n+1, padx=2)
        ttk.Label(header, text="Hệ số tự do", width=10, anchor="center").grid(row=0, column=n+2, padx=2)

        for i in range(m):
            row_frame = ttk.Frame(table)
            row_frame.grid(row=i+1, column=0, columnspan=n+3, sticky="ew", pady=2)
            ttk.Label(row_frame, text=f"(RB{i+1})", width=5).grid(row=0, column=0, padx=2)
            row_entries = []
            for j in range(n):
                e = ttk.Entry(row_frame, width=10)
                e.grid(row=0, column=j+1, padx=2)
                row_entries.append(e)
            cb = ttk.Combobox(row_frame, values=SENSES, state="readonly", width=6)
            cb.set("≤")
            cb.grid(row=0, column=n+1, padx=2)
            rhs = ttk.Entry(row_frame, width=10)
            rhs.grid(row=0, column=n+2, padx=2)
            self.constraint_entries.append(row_entries)
            self.constraint_senses.append(cb)
            self.constraint_rhs.append(rhs)

        hint = ttk.Label(
            self.input_inner,
            text="Muốn chuyển con trỏ nhập liệu sang ô khác bấm phím Tab. Dùng Ctrl+Alt+R để chạy quá trình giải thuật.",
            foreground="#92400e",
        )
        hint.grid(row=2, column=0, sticky="w", pady=(10, 0))

        self.input_inner.update_idletasks()
        self.input_canvas.configure(scrollregion=self.input_canvas.bbox("all"))
        self.last_problem = None
        self.last_report = None
        self._set_solution_available(False)

    def fill_demo(self):
        preset = self.demo_preset_var.get().strip()
        if preset == "Ví dụ giải bài toán xoay vòng":
            self._fill_demo_cycle()
        elif preset == "Ví dụ giải bài toán vô số nghiệm":
            self._fill_demo_multiple_optimal()
        else:
            self._fill_demo_two_phase()

    def _fill_demo_two_phase(self):
        # Demo theo bài mẫu pha 1 người dùng cung cấp
        self.n_vars.set(2)
        self.n_constraints.set(3)
        self.objective_sense.set("min")
        self._build_inputs()

        demo_obj = ["5", "-7"]
        for i, e in enumerate(self.obj_entries):
            e.delete(0, tk.END)
            if i < len(demo_obj):
                e.insert(0, demo_obj[i])

        for cb in self.var_signs:
            cb.set("≥0")

        data = [
            (["-4", "1"], "≤", "-2"),
            (["1", "1"], "≤", "5"),
            (["−1", "−1"], "≤", "-1"),
        ]
        for i in range(3):
            coeffs, sense, rhs = data[i]
            for j, e in enumerate(self.constraint_entries[i]):
                e.delete(0, tk.END)
                if j < len(coeffs):
                    e.insert(0, coeffs[j])
            self.constraint_senses[i].set(sense)
            self.constraint_rhs[i].delete(0, tk.END)
            self.constraint_rhs[i].insert(0, rhs)

    def _fill_demo_cycle(self):
        # Demo bài toán xoay vòng: Dantzig lặp cơ sở, sau đó Bland tiếp tục giải.
        self.n_vars.set(4)
        self.n_constraints.set(3)
        self.objective_sense.set("min")
        self._build_inputs()

        demo_obj = ["-10", "57", "9", "24"]
        for i, e in enumerate(self.obj_entries):
            e.delete(0, tk.END)
            if i < len(demo_obj):
                e.insert(0, demo_obj[i])

        for cb in self.var_signs:
            cb.set("≥0")

        data = [
            (["0.5", "-5.5", "-2.5", "9"], "≤", "0"),
            (["0.5", "-1.5", "-0.5", "1"], "≤", "0"),
            (["1", "0", "0", "0"], "≤", "1"),
        ]
        for i in range(3):
            coeffs, sense, rhs = data[i]
            for j, e in enumerate(self.constraint_entries[i]):
                e.delete(0, tk.END)
                if j < len(coeffs):
                    e.insert(0, coeffs[j])
            self.constraint_senses[i].set(sense)
            self.constraint_rhs[i].delete(0, tk.END)
            self.constraint_rhs[i].insert(0, rhs)

    def _fill_demo_multiple_optimal(self):
        # Demo bài toán vô số nghiệm: có một biến không cơ sở với hệ số 0 ở hàng mục tiêu.
        self.n_vars.set(3)
        self.n_constraints.set(4)
        self.objective_sense.set("max")
        self._build_inputs()

        demo_obj = ["-3", "1", "1"]
        for i, e in enumerate(self.obj_entries):
            e.delete(0, tk.END)
            if i < len(demo_obj):
                e.insert(0, demo_obj[i])

        for cb in self.var_signs:
            cb.set("≥0")

        data = [
            (["1", "-1", "0"], "≤", "0"),
            (["-2", "0", "1"], "≤", "1"),
            (["0", "-2", "1"], "≤", "2"),
            (["1", "1", "-1"], "≤", "6"),
        ]
        for i in range(4):
            coeffs, sense, rhs = data[i]
            for j, e in enumerate(self.constraint_entries[i]):
                e.delete(0, tk.END)
                if j < len(coeffs):
                    e.insert(0, coeffs[j])
            self.constraint_senses[i].set(sense)
            self.constraint_rhs[i].delete(0, tk.END)
            self.constraint_rhs[i].insert(0, rhs)

    def _collect_problem(self) -> ProblemData:
        n = int(self.n_vars.get())
        m = int(self.n_constraints.get())
        obj_coeffs = [parse_cell(e.get(), self.data_mode.get()) for e in self.obj_entries[:n]]
        var_signs = [cb.get() or "≥0" for cb in self.var_signs[:n]]
        constraints = []
        for i in range(m):
            coeffs = [parse_cell(e.get(), self.data_mode.get()) for e in self.constraint_entries[i][:n]]
            sense = self.constraint_senses[i].get() or "≤"
            rhs = parse_cell(self.constraint_rhs[i].get(), self.data_mode.get())
            constraints.append({"coeffs": coeffs, "sense": sense, "rhs": rhs})
        return ProblemData(
            objective_sense=self.objective_sense.get(),
            obj_coeffs=obj_coeffs,
            constraints=constraints,
            var_signs=var_signs,
        )


    def _set_solution_available(self, available: bool) -> None:
        if self.export_btn is not None:
            self.export_btn.config(state=tk.NORMAL if available else tk.DISABLED)

    def _on_button_enter(self, event, darker_color: str) -> None:
        """Handle mouse enter on button - change to darker color"""
        if event.widget.cget("state") != "disabled":
            event.widget.config(bg=darker_color)

    def _on_button_leave(self, event, original_color: str) -> None:
        """Handle mouse leave on button - revert to original color"""
        if event.widget.cget("state") != "disabled":
            event.widget.config(bg=original_color)

    def export_solution_txt(self) -> None:
        content = self.output.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showinfo("Xuất file .txt", "Chưa có lời giải để xuất.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Lưu nội dung lời giải",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile="loi_giai.txt",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            self.status_var.set(f"Đã xuất file: {file_path}")
        except Exception as exc:
            messagebox.showerror("Lỗi xuất file", str(exc))

    def _boundary_text(self, coeffs: Tuple[Fraction, Fraction], sense: str, rhs: Fraction) -> str:
        a, b = coeffs
        parts = []
        if a != 0:
            parts.append(f"{fmt_num(a, self.data_mode.get())}x₁")
        if b != 0:
            sign = "+" if b > 0 and parts else ""
            parts.append(f"{sign}{fmt_num(b, self.data_mode.get())}x₂")
        lhs = " ".join(parts).replace("+ -", "- ")
        if not lhs:
            lhs = "0"
        return f"{lhs} {sense} {fmt_num(rhs, self.data_mode.get())}"

    def visualize_two_variable_problem(self) -> None:
        """
        Visualize 2-variable linear programming problem geometrically.
        Displays feasible region, constraints, and objective function contours.
        """
        # ========== STEP 1: DATA VALIDATION & COLLECTION ==========
        try:
            prob = self._collect_problem()
        except Exception as exc:
            messagebox.showerror("Trực quan hóa", str(exc))
            return

        if len(prob.obj_coeffs) != 2:
            messagebox.showinfo("Trực quan hóa", "Tính năng này chỉ hỗ trợ đúng 2 biến x₁ và x₂.")
            return

        # ========== STEP 2: IMPORT LIBRARIES ==========
        try:
            import numpy as np
            import matplotlib
            matplotlib.use("TkAgg", force=True)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except Exception as exc:
            messagebox.showerror("Trực quan hóa", f"Không khởi tạo được thư viện: {exc}")
            return

        # ========== STEP 3: PREPARE GEOMETRIC DATA ==========
        halfplanes = self._build_halfplanes(prob)
        vertices = self._compute_feasible_vertices(halfplanes)
        vertices = self._deduplicate_points(vertices)
        
        xmin, xmax, ymin, ymax = self._compute_plot_bounds(vertices, halfplanes)
        x_mesh, y_mesh, X, Y = self._create_meshgrid(xmin, xmax, ymin, ymax)
        feasible_mask = self._compute_feasible_region(halfplanes, X, Y)

        c1, c2 = float(prob.obj_coeffs[0]), float(prob.obj_coeffs[1])
        vertex_values = [(p[0], p[1], c1 * p[0] + c2 * p[1]) for p in vertices]
        maximize = prob.objective_sense == "max"
        optimal_point = self._find_optimal_vertex(vertex_values, maximize)

        # ========== STEP 4: CREATE WINDOW & UI ==========
        window = self._create_visualization_window()
        title_frame = self._create_window_titlebar(window)
        plot_frame = self._create_plot_container(window)

        # ========== STEP 5: CREATE FIGURE & PLOT ==========
        fig, ax = self._create_figure()
        self._plot_feasible_region(ax, X, Y, feasible_mask)
        self._plot_constraints(ax, halfplanes, xmin, xmax, ymin, ymax)
        self._plot_objective_contours(ax, c1, c2, vertex_values, xmin, xmax, ymin, ymax, maximize)
        self._plot_vertices(ax, vertex_values, maximize)
        self._plot_optimal_point(ax, optimal_point, maximize)
        self._configure_axes(ax, xmin, xmax, ymin, ymax)

        # ========== STEP 6: DRAW CANVAS & OVERLAY ==========
        canvas = FigureCanvasTkAgg(fig, master=plot_frame)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=0, column=0, sticky="nsew")

        # ========== STEP 7: ADD INTERACTIVE CONTROLS ==========
        zoom_state = {'xlim': (xmin, xmax), 'ylim': (ymin, ymax)}
        self._create_zoom_controls(plot_frame, ax, canvas, zoom_state)
        self._create_info_panel(plot_frame, prob, vertices, vertex_values, optimal_point, maximize)

        # ========== STEP 8: FINALIZE WINDOW ==========
        window.transient(self)
        window.grab_set()

    # ===== HELPER METHODS FOR VISUALIZATION =====

    def _build_halfplanes(self, prob: ProblemData) -> List[Tuple[Fraction, Fraction, Fraction, str, str]]:
        """Build list of halfplanes from constraints and sign restrictions."""
        halfplanes: List[Tuple[Fraction, Fraction, Fraction, str, str]] = []
        
        # Add constraint halfplanes
        for i, cons in enumerate(prob.constraints, start=1):
            a = fr(cons["coeffs"][0])
            b = fr(cons["coeffs"][1])
            rhs = fr(cons["rhs"])
            sense = sense_to_standard(cons["sense"])
            halfplanes.append((a, b, rhs, sense, f"RB{i}"))
        
        # Add sign restriction halfplanes
        sign0, sign1 = prob.var_signs[0], prob.var_signs[1]
        if sign0 == "≥0":
            halfplanes.append((Fraction(1), Fraction(0), Fraction(0), "≥", "x₁ ≥ 0"))
        elif sign0 == "≤0":
            halfplanes.append((Fraction(1), Fraction(0), Fraction(0), "≤", "x₁ ≤ 0"))
        if sign1 == "≥0":
            halfplanes.append((Fraction(0), Fraction(1), Fraction(0), "≥", "x₂ ≥ 0"))
        elif sign1 == "≤0":
            halfplanes.append((Fraction(0), Fraction(1), Fraction(0), "≤", "x₂ ≤ 0"))
        
        return halfplanes

    def _is_feasible_point(self, x: float, y: float, halfplanes: List, tol: float = 1e-8) -> bool:
        """Check if point (x,y) satisfies all halfplane constraints."""
        for a, b, c, sense, _ in halfplanes:
            lhs = float(a) * x + float(b) * y
            cc = float(c)
            if sense == "≤" and lhs > cc + tol:
                return False
            if sense == "≥" and lhs < cc - tol:
                return False
            if sense == "=" and abs(lhs - cc) > tol:
                return False
        return True

    def _compute_feasible_vertices(self, halfplanes: List) -> List[Tuple[float, float]]:
        """Find all feasible vertex points from halfplane intersections."""
        lines = [(a, b, c, lbl) for a, b, c, _, lbl in halfplanes]
        vertices: List[Tuple[float, float]] = []
        
        for i in range(len(lines)):
            a1, b1, c1, _ = lines[i]
            for j in range(i + 1, len(lines)):
                a2, b2, c2, _ = lines[j]
                det = float(a1 * b2 - a2 * b1)
                if abs(det) < 1e-12:
                    continue
                x = float((c1 * b2 - c2 * b1) / det)
                y = float((a1 * c2 - a2 * c1) / det)
                if math.isfinite(x) and math.isfinite(y) and self._is_feasible_point(x, y, halfplanes):
                    vertices.append((x, y))
        
        return vertices

    def _deduplicate_points(self, points: List[Tuple[float, float]], eps: float = 1e-7) -> List[Tuple[float, float]]:
        """Remove duplicate points from list."""
        unique: List[Tuple[float, float]] = []
        for p in points:
            if not any(abs(p[0] - q[0]) <= eps and abs(p[1] - q[1]) <= eps for q in unique):
                unique.append(p)
        return unique

    def _compute_plot_bounds(self, vertices: List, halfplanes: List) -> Tuple[float, float, float, float]:
        """Compute plot bounds with a lighter margin so the plane feels wider."""
        if vertices:
            xs = [p[0] for p in vertices]
            ys = [p[1] for p in vertices]
            span_x = max(xs) - min(xs)
            span_y = max(ys) - min(ys)
            pad_x = max(0.9, span_x * 0.18) if len(xs) > 1 else max(1.4, abs(xs[0]) * 0.35 + 1.0)
            pad_y = max(0.9, span_y * 0.18) if len(ys) > 1 else max(1.4, abs(ys[0]) * 0.35 + 1.0)
            xmin, xmax = min(xs) - pad_x, max(xs) + pad_x
            ymin, ymax = min(ys) - pad_y, max(ys) + pad_y
            xmin, ymin = min(xmin, 0.0), min(ymin, 0.0)
            xmax, ymax = max(xmax, 0.0), max(ymax, 0.0)
        else:
            # Default bounds for empty region
            s = 5.0
            xmin, xmax, ymin, ymax = -s, s, -s, s

        # Keep the scene broad, but not overly zoomed out.
        xr, yr = xmax - xmin, ymax - ymin
        xmin, xmax = xmin - 0.22 * xr, xmax + 0.22 * xr
        ymin, ymax = ymin - 0.22 * yr, ymax + 0.22 * yr
        return xmin, xmax, ymin, ymax

    def _create_meshgrid(self, xmin: float, xmax: float, ymin: float, ymax: float):
        """Create mesh grid for plotting feasible region.
        Reduced resolution keeps pan/zoom noticeably smoother."""
        import numpy as np
        x = np.linspace(xmin, xmax, 220)
        y = np.linspace(ymin, ymax, 220)
        X, Y = np.meshgrid(x, y)
        return x, y, X, Y

    def _compute_feasible_region(self, halfplanes: List, X, Y) -> Any:
        """Compute boolean mask for feasible region."""
        import numpy as np
        mask = np.ones_like(X, dtype=bool)
        for a, b, c, sense, _ in halfplanes:
            lhs = float(a) * X + float(b) * Y
            cc = float(c)
            if sense == "≤":
                mask &= lhs <= cc + 1e-9
            elif sense == "≥":
                mask &= lhs >= cc - 1e-9
            else:
                mask &= np.abs(lhs - cc) <= 1e-2
        return mask

    def _find_optimal_vertex(self, vertex_values: List, maximize: bool) -> Optional[Tuple[float, float, float]]:
        """Find optimal vertex from all feasible vertices."""
        if not vertex_values:
            return None
        return max(vertex_values, key=lambda t: t[2]) if maximize else min(vertex_values, key=lambda t: t[2])

    def _create_visualization_window(self) -> tk.Toplevel:
        """Create main visualization window."""
        top = tk.Toplevel(self)
        top.title("")
        top.geometry("1400x900")
        top.minsize(900, 600)
        top.rowconfigure(1, weight=1)
        top.columnconfigure(0, weight=1)
        return top

    def _create_window_titlebar(self, window: tk.Toplevel) -> tk.Frame:
        """Create custom title bar with minimize/close buttons."""
        title_frame = tk.Frame(window, bg="#1a202c", height=35)
        title_frame.grid(row=0, column=0, sticky="ew")
        title_frame.pack_propagate(False)

        title_label = tk.Label(
            title_frame, text="Trực quan hóa bài toán 2 biến",
            font=("Segoe UI", 11, "bold"), bg="#1a202c", fg="#e2e8f0"
        )
        title_label.pack(side="left", padx=12, pady=8)

        btn_frame = tk.Frame(title_frame, bg="#1a202c")
        btn_frame.pack(side="right", padx=8, pady=4)

        min_btn = tk.Button(
            btn_frame, text="−", font=("Segoe UI", 12, "bold"),
            bg="#2d3748", fg="#cbd5e1", activebackground="#4a5568",
            relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
            command=window.iconify
        )
        min_btn.pack(side="left", padx=2)

        close_btn = tk.Button(
            btn_frame, text="✕", font=("Segoe UI", 12, "bold"),
            bg="#2d3748", fg="#cbd5e1", activebackground="#e53e3e",
            relief="flat", bd=0, padx=9, pady=2, cursor="hand2",
            command=window.destroy
        )
        close_btn.pack(side="left", padx=2)

        return title_frame

    def _create_plot_container(self, window: tk.Toplevel) -> ttk.Frame:
        """Create frame to hold the plot."""
        plot_frame = ttk.Frame(window, padding=8)
        plot_frame.grid(row=1, column=0, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        return plot_frame

    def _create_figure(self):
        """Create matplotlib figure and axes."""
        from matplotlib.figure import Figure
        fig = Figure(figsize=(11, 8), dpi=100)
        fig.patch.set_facecolor("#f8fafc")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#ffffff")
        ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.28)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return fig, ax

    def _plot_feasible_region(self, ax, X, Y, mask):
        """Shade the feasible region."""
        ax.contourf(X, Y, mask.astype(float), levels=[0.5, 1.5], alpha=0.25, colors=["#93c5fd"])

    def _plot_constraints(self, ax, halfplanes: List, xmin: float, xmax: float, ymin: float, ymax: float):
        """Plot constraint boundary lines."""
        import numpy as np
        palette = ["#2563eb", "#7c3aed", "#0f766e", "#d97706", "#be123c", "#0891b2"]
        label_added = set()

        for idx, (a, b, c, sense, label) in enumerate(halfplanes):
            color = palette[idx % len(palette)]
            skip_label = label in label_added
            label_added.add(label)

            if abs(float(b)) > 1e-12:
                x_ext = np.linspace(xmin - (xmax - xmin) * 0.5, xmax + (xmax - xmin) * 0.5, 1000)
                y_ext = (float(c) - float(a) * x_ext) / float(b)
                ax.plot(x_ext, y_ext, color=color, linewidth=2.2, alpha=0.92, 
                       label="" if skip_label else label, clip_on=False)
            elif abs(float(a)) > 1e-12:
                xv = float(c) / float(a)
                ax.axvline(xv, color=color, linewidth=2.2, alpha=0.92, 
                          label="" if skip_label else label, clip_on=False)

    def _plot_objective_contours(self, ax, c1: float, c2: float, vertex_values: List, 
                                 xmin: float, xmax: float, ymin: float, ymax: float, maximize: bool):
        """Plot objective function contour lines."""
        import numpy as np
        if len(vertex_values) < 1 or abs(c1) + abs(c2) < 1e-12:
            return

        zvals = sorted(v[2] for v in vertex_values)
        if len(zvals) >= 2:
            levels = np.linspace(zvals[0], zvals[-1], num=min(6, max(3, len(zvals))))
        else:
            levels = np.array([zvals[0]])

        x_ext = np.linspace(xmin - (xmax - xmin) * 0.5, xmax + (xmax - xmin) * 0.5, 1000)
        for lv in levels:
            if abs(c2) > 1e-12:
                y_ext = (lv - c1 * x_ext) / c2
                ax.plot(x_ext, y_ext, color="#ef4444", linewidth=1.5, linestyle="--", alpha=0.42, clip_on=False)
            elif abs(c1) > 1e-12:
                xv = lv / c1
                ax.axvline(xv, color="#ef4444", linewidth=1.5, linestyle="--", alpha=0.42, clip_on=False)

    def _plot_vertices(self, ax, vertex_values: List, maximize: bool):
        """Plot feasible vertices in order."""
        if not vertex_values:
            return

        ordered = sorted(vertex_values, key=lambda t: t[2], reverse=maximize)
        px = [p[0] for p in ordered]
        py = [p[1] for p in ordered]
        
        # Connect vertices path
        ax.plot(px, py, color="#111827", linewidth=1.2, linestyle=":", alpha=0.55, zorder=4)
        
        # Plot individual vertices
        for idx, (vx, vy, val) in enumerate(ordered, start=1):
            ax.scatter([vx], [vy], s=36, color="#1d4ed8", edgecolors="white", linewidths=0.8, zorder=5)
            ax.annotate(
                f"{idx}",
                xy=(vx, vy), xytext=(5, 5), textcoords="offset points",
                fontsize=9, color="#111827",
                bbox=dict(boxstyle="circle,pad=0.15", fc="#dbeafe", ec="#93c5fd", alpha=0.95),
            )

    def _plot_optimal_point(self, ax, optimal: Optional[Tuple[float, float, float]], maximize: bool):
        """Plot the optimal vertex with annotation."""
        if optimal is None:
            return

        bx, by, bz = optimal
        ax.scatter([bx], [by], s=160, marker="*", color="#f59e0b", 
                  edgecolors="#111827", linewidths=1.2, zorder=6)
        ax.annotate(
            f"Điểm tối ưu\n({bx:.3g}, {by:.3g})\nz = {bz:.3g}",
            xy=(bx, by), xytext=(12, 16), textcoords="offset points",
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc="#fff7ed", ec="#fb923c", alpha=0.98),
            arrowprops=dict(arrowstyle="->", color="#fb923c", lw=1.5),
        )

    def _configure_axes(self, ax, xmin: float, xmax: float, ymin: float, ymax: float):
        """Configure axes labels, limits, and styling."""
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_xlabel("x₁", fontsize=12, fontweight="bold")
        ax.set_ylabel("x₂", fontsize=12, fontweight="bold")
        ax.set_title("Miền chấp nhận được, ràng buộc và đường đồng mức hàm mục tiêu",
                    fontsize=14, fontweight="bold", pad=14)
        
        # Axis crossings at origin
        ax.axhline(0, color="#334155", linewidth=1.1, alpha=0.7)
        ax.axvline(0, color="#334155", linewidth=1.1, alpha=0.7)
        
        # Legend
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, loc="upper left", frameon=True, fontsize=9,
                     title="Ràng buộc", title_fontsize=10, fancybox=True, shadow=True)

    def _create_zoom_controls(self, plot_frame: ttk.Frame, ax, canvas, zoom_state: Dict):
        """Create zoom/reset control buttons."""
        ctrl_frame = tk.Frame(plot_frame, bg="#2d3748", relief="solid", bd=2)
        ctrl_frame.place(relx=0.01, rely=0.95, anchor="sw")

        def zoom_in():
            xc1, xc2 = ax.get_xlim()
            yc1, yc2 = ax.get_ylim()
            dx, dy = (xc2 - xc1) * 0.125, (yc2 - yc1) * 0.125
            ax.set_xlim(xc1 + dx, xc2 - dx)
            ax.set_ylim(yc1 + dy, yc2 - dy)
            zoom_state['xlim'], zoom_state['ylim'] = ax.get_xlim(), ax.get_ylim()
            canvas.draw_idle()

        def zoom_out():
            xc1, xc2 = ax.get_xlim()
            yc1, yc2 = ax.get_ylim()
            dx, dy = (xc2 - xc1) * 0.125, (yc2 - yc1) * 0.125
            ax.set_xlim(xc1 - dx, xc2 + dx)
            ax.set_ylim(yc1 - dy, yc2 + dy)
            zoom_state['xlim'], zoom_state['ylim'] = ax.get_xlim(), ax.get_ylim()
            canvas.draw_idle()

        def reset():
            ax.set_xlim(zoom_state['xlim'])
            ax.set_ylim(zoom_state['ylim'])
            canvas.draw_idle()

        # Zoom In button
        self._create_control_button(ctrl_frame, "🔍+", "#4299e1", "#3182ce", zoom_in)
        # Zoom Out button
        self._create_control_button(ctrl_frame, "🔍−", "#ed8936", "#dd6b20", zoom_out)
        # Reset button
        self._create_control_button(ctrl_frame, "↺", "#48bb78", "#38a169", reset)

    def _create_control_button(self, parent: tk.Frame, text: str, color: str, hover_color: str, command):
        """Create a styled control button with hover effect."""
        btn = tk.Button(
            parent, text=text, font=("Segoe UI", 10, "bold"),
            bg=color, fg="white", activebackground=hover_color,
            relief="flat", bd=0, padx=8, pady=6, cursor="hand2",
            command=command
        )
        btn.pack(side="left", padx=4, pady=6)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))

    def _create_info_panel(self, plot_frame: ttk.Frame, prob: ProblemData, vertices: List,
                          vertex_values: List, optimal: Optional[Tuple], maximize: bool):
        """Create information panel in top-right corner."""
        info_frame = tk.Frame(plot_frame, bg="#ffffff", relief="solid", bd=1,
                             highlightthickness=1, highlightbackground="#cbd5e1")
        info_frame.place(relx=0.98, rely=0.01, anchor="ne", x=-12, y=12)

        info = scrolledtext.ScrolledText(
            info_frame, wrap="word", font=("Consolas", 9), bg="#ffffff", relief="flat",
            padx=10, pady=10, width=28, height=16, cursor="arrow"
        )
        info.pack(fill="both", expand=True)

        # Fill with information
        info.insert(tk.END, "📋 BÌNH THUYẾT MINH\n\n")
        info.insert(tk.END, "Hàm mục tiêu:\n")
        info.insert(tk.END, f"{prob.objective_sense.upper()} Z = {fmt_num(prob.obj_coeffs[0], self.data_mode.get())}x₁")
        if prob.obj_coeffs[1] >= 0:
            info.insert(tk.END, f" + {fmt_num(prob.obj_coeffs[1], self.data_mode.get())}x₂\n\n")
        else:
            info.insert(tk.END, f" − {fmt_num(-prob.obj_coeffs[1], self.data_mode.get())}x₂\n\n")

        info.insert(tk.END, "Các ràng buộc:\n")
        for i, cons in enumerate(prob.constraints, start=1):
            info.insert(tk.END, f"RB{i}: {self._boundary_text((cons['coeffs'][0], cons['coeffs'][1]), sense_to_standard(cons['sense']), cons['rhs'])}\n")

        info.insert(tk.END, "\nĐỉnh khả thi:\n")
        if vertex_values:
            ordered = sorted(vertex_values, key=lambda t: t[2], reverse=maximize)
            for idx, (vx, vy, val) in enumerate(ordered, start=1):
                info.insert(tk.END, f"{idx}. ({vx:.3g}, {vy:.3g})\n   Z = {val:.3g}\n")
        else:
            info.insert(tk.END, "(Không tìm thấy)\n")

        if optimal is not None:
            info.insert(tk.END, f"\n✓ TỐI ƯU:\n({optimal[0]:.3g}, {optimal[1]:.3g})\nZ = {optimal[2]:.3g}")

        info.configure(state="disabled")

    # ---------- formatting ----------
    def _format_problem(self, engine: SimplexEngine) -> str:
        mode = self.data_mode.get()

        def expr(coeffs, names):
            parts = []
            for c, nm in zip(coeffs, names):
                if c == 0:
                    continue
                if c == 1:
                    parts.append(f"+ {nm}")
                elif c == -1:
                    parts.append(f"- {nm}")
                elif c > 0:
                    parts.append(f"+ {fmt_num(c, mode)}{nm}")
                else:
                    parts.append(f"- {fmt_num(-c, mode)}{nm}")
            if not parts:
                return "0"
            s = " ".join(parts)
            return s[2:] if s.startswith("+ ") else s

        lines = []
        lines.append("Bài tập Quy Hoạch Tuyến Tính — Phương pháp Đơn hình")
        lines.append("  Bài toán gốc:")
        lines.append(f"    {engine.problem.objective_sense} Z = {expr(engine.problem.obj_coeffs, [f'x{i+1}' for i in range(len(engine.problem.obj_coeffs))])}")
        lines.append("    {")
        for cons in engine.problem.constraints:
            lines.append(f"      {expr(cons['coeffs'], [f'x{i+1}' for i in range(len(cons['coeffs']))])} {cons['sense']} {fmt_num(cons['rhs'], mode)}")
        vars_line = ", ".join([f"x{i+1}" for i in range(len(engine.problem.var_signs))])
        lines.append(f"    {vars_line} thuộc các điều kiện dấu đã chọn")
        lines.append("    }")
        return "\n".join(lines)
    def _format_standardization(self, engine: SimplexEngine) -> str:
        mode = self.data_mode.get()

        def expr(coeffs, names):
            parts = []
            for c, nm in zip(coeffs, names):
                if c == 0:
                    continue
                if c == 1:
                    parts.append(f"+ {nm}")
                elif c == -1:
                    parts.append(f"- {nm}")
                elif c > 0:
                    parts.append(f"+ {fmt_num(c, mode)}{nm}")
                else:
                    parts.append(f"- {fmt_num(-c, mode)}{nm}")
            if not parts:
                return "0"
            s = " ".join(parts)
            return s[2:] if s.startswith("+ ") else s

        n_orig = len(engine.problem.var_signs)
        extra_x = [name for name in engine.std_names if name.startswith("x") and not name in {f"x{i+1}" for i in range(n_orig)}]
        aux_names = [name for name in engine.std_names if not name.startswith("x")]
        displayed_names = [f"x{i+1}" for i in range(n_orig)] + extra_x + aux_names

        lines = []
        lines.append("========================")
        lines.append("*Chuẩn hóa bài toán gốc:")
        lines.append("========================")
        lines.append("")
        lines.append("_Chuẩn hóa ràng buộc dấu:")
        for idx, sign in enumerate(engine.problem.var_signs):
            name = f"x{idx+1}"
            if sign == "≥0":
                lines.append(f"        {name} ≥ 0: giữ nguyên {name} ≥ 0")
            elif sign == "≤0":
                lines.append(f"        {name} tự do âm: đặt {name} = -y{idx+1}, với y{idx+1} ≥ 0")
            else:
                lines.append(f"        {name} tự do: đặt {name} = a{idx+1} - b{idx+1}, với a{idx+1}, b{idx+1} ≥ 0")
        lines.append("")
        lines.append("_Chuẩn hóa ràng buộc đẳng thức, bất đẳng thức:")

        slack_counter = n_orig + 1
        for i, cons in enumerate(engine.problem.constraints):
            sense = cons["sense"]
            if sense == "≤":
                lines.append(f"    RB{i+1}: giữ nguyên, do dấu của ràng buộc đã là \"≤\"")
            elif sense == "≥":
                lines.append(f"    RB{i+1}: do ràng buộc ở dạng \"≥\", nhân cả hai vế với (-1) để đưa về \"≤\"")
            else:
                slack_name = f"x{slack_counter}"
                slack_counter += 1
                lines.append(f"    RB{i+1}: do ràng buộc ở dạng đẳng thức \"=\", nên ta trừ thêm biến bù {slack_name} ≥ 0 vào vế trái.")
                row = engine.std_constraints[i]
                names = engine.std_names[:len(row)]
                lines.append(f"    ---> RB{i+1}:  {expr(row, names)} ≤ {fmt_num(engine.std_rhs[i], mode)}")

        lines.append("")
        lines.append("_Các biến trong bài toán sau chuẩn hóa:")
        for idx, sign in enumerate(engine.problem.var_signs):
            if sign == "≥0":
                lines.append(f"        x{idx+1} = x{idx+1}")
            elif sign == "≤0":
                lines.append(f"        x{idx+1} = -y{idx+1}")
            else:
                lines.append(f"        x{idx+1} = a{idx+1} - b{idx+1}")
        for name in extra_x:
            lines.append(f"        {name} = {name}")
        lines.append("")
        lines.append("_Chuẩn hóa hàm mục tiêu:")
        if engine.problem.objective_sense == "min":
            lines.append("    Vì hàm mục tiêu là hàm min, đã ở dạng chuẩn nên giữ nguyên:")
        else:
            lines.append("    Vì hàm mục tiêu là hàm max nên nhân (-1) để đưa về bài toán min tương ứng:")
        lines.append(f"        {engine.problem.objective_sense} Z = {expr(engine.problem.obj_coeffs, [f'x{i+1}' for i in range(len(engine.problem.obj_coeffs))])}")
        lines.append("    Thay các biến sau chuẩn hóa vào hàm min.")

        obj_line_names = []
        obj_line_coeffs = []
        for idx, sign in enumerate(engine.problem.var_signs):
            if sign == "≥0":
                obj_line_names.append(f"x{idx+1}")
                obj_line_coeffs.append(engine.problem.obj_coeffs[idx] if engine.problem.objective_sense == "min" else -engine.problem.obj_coeffs[idx])
            elif sign == "≤0":
                obj_line_names.append(f"y{idx+1}")
                obj_line_coeffs.append(-(engine.problem.obj_coeffs[idx] if engine.problem.objective_sense == "min" else -engine.problem.obj_coeffs[idx]))
            else:
                obj_line_names.extend([f"a{idx+1}", f"b{idx+1}"])
                coeff = engine.problem.obj_coeffs[idx] if engine.problem.objective_sense == "min" else -engine.problem.obj_coeffs[idx]
                obj_line_coeffs.extend([coeff, -coeff])
        for name in extra_x:
            obj_line_names.append(name)
            obj_line_coeffs.append(Fraction(0))
        # display like the sample: keep the transformed expression only
        obj_expr = expr(engine.std_obj_coeffs, engine.std_names)
        lines.append(f"        {'min' if engine.problem.objective_sense == 'min' else 'min'} Z = {obj_expr}")
        lines.append("")
        lines.append("=========================")
        lines.append("*Dạng chuẩn của bài toán:")
        lines.append("=========================")
        lines.append(f"    min Z = {obj_expr}")
        lines.append("    {")
        for i, row in enumerate(engine.std_constraints):
            lines.append(f"      {expr(row, engine.std_names[:len(row)])} ≤ {fmt_num(engine.std_rhs[i], mode)}")
        # variable list: original x's first, then slack x's, then other auxiliaries
        slack_names = [name for name in engine.std_names if name.startswith("x") and name not in {f"x{i+1}" for i in range(n_orig)}]
        aux_names2 = [name for name in engine.std_names if not name.startswith("x")]
        var_list = [f"x{i+1}" for i in range(n_orig)] + slack_names + aux_names2
        lines.append(f"    {', '.join(var_list)} ≥ 0")
        lines.append("    }")
        return "\n".join(lines)
    def _dict_lines(self, snapshot: Snapshot) -> List[str]:
        mode = self.data_mode.get()
        names = snapshot.all_names
        # Width per variable column.
        widths = []
        for j, name in enumerate(names):
            max_len = len(name)
            # objective + rows
            candidates = [snapshot.obj.get(j, Fraction(0))]
            for r in snapshot.rows:
                candidates.append(r.get(j, Fraction(0)))
            for c in candidates:
                s = term_str(c, name, mode)
                max_len = max(max_len, len(s))
            widths.append(max(8, min(14, max_len + 2)))

        def line_for(label: str, const: Fraction, coeffs: Dict[int, Fraction]) -> str:
            out = [f"{label} = {fmt_num(const, mode)}"]
            for j, name in enumerate(names):
                cell = term_str(coeffs.get(j, Fraction(0)), name, mode)
                out.append(cell.ljust(widths[j]))
            return " ".join(out).rstrip()

        lines = [line_for(snapshot.objective_label, snapshot.obj_const, snapshot.obj)]
        for i, b in enumerate(snapshot.basis):
            lines.append(line_for(names[b], snapshot.rhs[i], snapshot.rows[i]))
        return lines

    def _insert_snapshot(self, snapshot: Snapshot, title: str, tags: Optional[Dict[str, str]] = None):
        self.output.insert(tk.END, title + "\n", "h2")
        start = self.output.index(tk.END)
        lines = self._dict_lines(snapshot)
        for line in lines:
            self.output.insert(tk.END, line + "\n", "mono")
        # tags
        if tags and snapshot.all_names:
            var_name = tags.get("entering")
            pivot_row = tags.get("pivot_row")
            if var_name:
                block_end = self.output.index(tk.END)
                idx = start
                while True:
                    pos = self.output.search(var_name, idx, stopindex=block_end)
                    if not pos:
                        break
                    self.output.tag_add("pivotcol", pos, f"{pos}+{len(var_name)}c")
                    idx = f"{pos}+{len(var_name)}c"
            if pivot_row is not None:
                row_no = int(start.split(".")[0]) + int(pivot_row)
                row_start = f"{row_no}.0"
                row_end = f"{row_no}.end"
                self.output.tag_add("pivotrow", row_start, row_end)
                if var_name:
                    line_text = self.output.get(row_start, row_end)
                    pos = line_text.find(var_name)
                    if pos != -1:
                        self.output.tag_add("pivotcell", f"{row_no}.{pos}", f"{row_no}.{pos+len(var_name)}")



    def _insert_step_note(self, step: PivotStep, snapshot: Snapshot):
        mode = self.data_mode.get()
        names = snapshot.all_names
        enter = names[step.entering] if step.entering is not None else "?"
        leave = names[step.leaving_var] if step.leaving_var is not None else "?"
        rule = "Dantzig" if step.method == "dantzig" else "Bland"

        if step.status == "phase1_aux_pivot":
            self.output.insert(tk.END, "Theo quy tắc Dantzig:\n", "h2")
            self.output.insert(tk.END, "— Pha 1: Ở lần xoay đầu, x0 là biến vào, biến ra là biến ở hàng có b_i âm.\n", "note")
            if step.ratios:
                self.output.insert(tk.END, "— Xét các b_i âm:\n", "note")
                for row_idx, bval, basis_idx in step.ratios:
                    row_name = names[basis_idx]
                    self.output.insert(tk.END, f"  • {row_name}: {fmt_num(bval, mode)}\n", "note")
            self.output.insert(tk.END, f"  ⟹ biến vào: {enter}\n", "note")
            self.output.insert(tk.END, f"  ⟹ biến ra: {leave}\n", "note")
            if step.pivot_value is not None:
                self.output.insert(tk.END, f"— Phần tử xoay: a_{{{leave},{enter}}} = {fmt_num(step.pivot_value, mode)}.\n", "note")
            if step.degenerate:
                self.output.insert(tk.END, "— Bước này là suy biến vì θ = 0.\n", "warn")
            return

        self.output.insert(tk.END, f"Theo quy tắc {rule}:\n", "h2")
        if step.entering is not None:
            coeff = snapshot.obj.get(step.entering, Fraction(0))
            if step.method == "dantzig":
                self.output.insert(tk.END, f"— Trong các biến có hệ số âm trên hàm mục tiêu, chọn {enter} vì có hệ số nhỏ nhất {fmt_num(coeff, mode)}.\n", "note")
            else:
                self.output.insert(tk.END, f"— Bland: ưu tiên nhóm biến x trước rồi mới tới nhóm w; trong nhóm có hệ số âm, chọn {enter}.\n", "note")
            self.output.insert(tk.END, f"  ⟹ biến vào: {enter}\n", "note")
        if step.ratios:
            self.output.insert(tk.END, f"— Xét tỉ số tại cột {enter} (chỉ lấy hàng có hệ số âm):\n", "note")
            for row_idx, theta, basis_idx in step.ratios:
                row_name = names[basis_idx]
                coeff = snapshot.rows[row_idx][step.entering] if step.entering is not None else Fraction(1)
                self.output.insert(tk.END, f"  • {row_name}: {fmt_num(snapshot.rhs[row_idx], mode)} / {fmt_num(-coeff, mode)} = {fmt_num(theta, mode)}\n", "note")
            self.output.insert(tk.END, f"  ⟹ biến ra: {leave}\n", "note")
        if step.pivot_value is not None:
            self.output.insert(tk.END, f"— Phần tử xoay: a_{{{leave},{enter}}} = {fmt_num(step.pivot_value, mode)}.\n", "note")
        if step.degenerate:
            self.output.insert(tk.END, "— Bước này là suy biến vì θ = 0.\n", "warn")



    def _affine_text(self, const: Fraction, coef: Fraction, var_name: str, mode: str) -> str:
        parts: List[str] = []
        if const != 0 or coef == 0:
            parts.append(fmt_num(const, mode))
        if coef != 0:
            body = var_name if abs(coef) == 1 else f"{fmt_num(abs(coef), mode)}{var_name}"
            if parts:
                parts.append(f"+ {body}" if coef > 0 else f"- {body}")
            else:
                parts.append(body if coef > 0 else f"- {body}")
        return " ".join(parts).strip()

    def _linear_text(self, const: Fraction, terms: List[Tuple[Fraction, str]], mode: str) -> str:
        parts: List[str] = []
        if const != 0 or not terms:
            parts.append(fmt_num(const, mode))
        for coef, name in terms:
            if coef == 0:
                continue
            body = name if abs(coef) == 1 else f"{fmt_num(abs(coef), mode)}{name}"
            if parts:
                parts.append(f"+ {body}" if coef > 0 else f"- {body}")
            else:
                parts.append(body if coef > 0 else f"- {body}")
        return " ".join(parts).strip() if parts else "0"

    def _format_multiple_optimal_family(self, engine: SimplexEngine, snapshot: Snapshot, report: SolveReport) -> List[str]:
        mode = self.data_mode.get()
        free_vars = report.multiple_optimal_vars or []
        if not free_vars:
            return []

        param_name = snapshot.all_names[free_vars[0]]
        lines: List[str] = []
        lines.append(
            f"  Do hệ số trước {param_name} bằng 0. Vậy khi {param_name} thay đổi, các giá trị nghiệm khác vẫn có thể khả thi nên bài toán có vô số nghiệm."
            f" \n "
            f"  Cho các biến có mặt trên hàm mục tiêu bằng 0, ta được:"
        )
        lines.append("")
        lines.append(f"    z = {fmt_num(snapshot.obj_const, mode)}")

        def row_expr(row_idx: int) -> str:
            terms: List[Tuple[Fraction, str]] = []
            for fv in free_vars:
                coef = snapshot.rows[row_idx].get(fv, Fraction(0))
                if coef != 0:
                    terms.append((coef, snapshot.all_names[fv]))
            return self._linear_text(snapshot.rhs[row_idx], terms, mode)

        for row_idx, b in enumerate(snapshot.basis):
            lines.append(f"    {snapshot.all_names[b]} = {row_expr(row_idx)}")
        return lines

    def _format_multiple_optimal_conclusion(self, engine: SimplexEngine, snapshot: Snapshot, report: SolveReport) -> List[str]:
        mode = self.data_mode.get()
        free_vars = report.multiple_optimal_vars or []
        if not free_vars:
            return []

        lines: List[str] = []
        lines.append("  Nghiệm tối ưu là bộ nghiệm thỏa:")
        lines.append("  {")
        basis_pos = {b: i for i, b in enumerate(snapshot.basis)}

        def std_expr(idx: int) -> Tuple[Fraction, List[Tuple[Fraction, str]]]:
            if idx in basis_pos:
                r = basis_pos[idx]
                terms: List[Tuple[Fraction, str]] = []
                for fv in free_vars:
                    coef = snapshot.rows[r].get(fv, Fraction(0))
                    if coef != 0:
                        terms.append((coef, snapshot.all_names[fv]))
                return snapshot.rhs[r], terms
            if idx in free_vars:
                return Fraction(0), [(Fraction(1), snapshot.all_names[idx])]
            return Fraction(0), []

        for orig_idx, mapping in enumerate(engine.variable_mapping):
            if len(mapping) == 1 and mapping[0][0] in free_vars and mapping[0][1] == Fraction(1):
                lines.append(f"    x{orig_idx + 1} ≥ 0")
                continue

            const = Fraction(0)
            terms: List[Tuple[Fraction, str]] = []
            for std_idx, map_coef in mapping:
                s_const, s_terms = std_expr(std_idx)
                const += map_coef * s_const
                for coef, name in s_terms:
                    terms.append((map_coef * coef, name))

            expr_text = self._linear_text(const, terms, mode)
            lines.append(f"    x{orig_idx + 1} = {expr_text}")

        lines.append("  }")
        return lines

    def _render_trace(self, title: str, trace: SolveTrace):
        if not trace.steps:
            self.output.insert(tk.END, "Từ vựng ban đầu:\n", "h2")
            if trace.final_snapshot:
                self._insert_snapshot(trace.final_snapshot, "")
            return

        current_phase = None
        for step in trace.steps:
            if current_phase != step.phase:
                current_phase = step.phase
            title_text = "Từ vựng ban đầu:" if step.iteration == 1 else f"Bước {step.iteration} trước xoay:"
            self._insert_snapshot(
                step.before,
                title_text,
                tags={"entering": step.before.all_names[step.entering] if step.entering is not None else None, "pivot_row": step.leaving_row} if step.entering is not None else None,
            )
            self.output.insert(tk.END, "\n")
            self._insert_step_note(step, step.before)
            self.output.insert(tk.END, "\n")
            if step.after is not None:
                self._insert_snapshot(step.after, f"Sau xoay bước {step.iteration}:")
                self.output.insert(tk.END, "\n")

        if trace.status == "optimal":
            self.output.insert(tk.END, "  Các hệ số cải thiện trên hàm mục tiêu đã không còn âm nên đạt tối ưu.\n", "note")
        elif trace.status == "unbounded":
            self.output.insert(tk.END, "  Bài toán không giới nội: đã chọn được biến vào nhưng không chọn được biến ra vì không còn hàng nào có hệ số âm.\n", "warn")
        elif trace.status == "cycle":
            self.output.insert(tk.END, "  Dantzig đã lặp cơ sở sau hữu hạn bước nên sẽ giải lại từ đầu bằng Bland.\n", "warn")

    def _render_result(self, report: SolveReport):
        self.output.delete("1.0", tk.END)
        engine = report.engine
        mode = self.data_mode.get()

        self.output.insert(tk.END, self._format_problem(engine) + "\n\n", "h1")
        self.output.insert(tk.END, self._format_standardization(engine) + "\n", "mono")

        if self._has_aux_phase1(engine):
            self.output.insert(tk.END, "\n=============================\n", "h2")
            self.output.insert(tk.END, "*Pha 1: Giải bài toán bổ trợ\n", "h2")
            self.output.insert(tk.END, "=============================\n", "h2")
            self.output.insert(tk.END, "_ Vì tồn tại b_i âm nên cần giải pha 1 bằng biến phụ x0\n", "note")
            self._render_trace("Pha 1", report.dantzig)
            if report.phase1_bland is not None and report.phase1_bland is not report.dantzig:
                self.output.insert(tk.END, "\n-----------------------------\n", "h2")
                self.output.insert(tk.END, "*Bland sau khi Dantzig lặp ở pha 1\n", "h2")
                self.output.insert(tk.END, "-----------------------------\n", "h2")
                self._render_trace("Pha 1 - Bland", report.phase1_bland)
            self.output.insert(tk.END, "\n")

            if report.status == "infeasible":
                self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
                self.output.insert(tk.END, "  Trạng thái: vô nghiệm. Pha 1 tối ưu nhưng x0 vẫn nằm trong cơ sở nên miền chấp nhận được là rỗng.\n", "warn")
                return

            if report.phase2_trace is not None:
                self.output.insert(tk.END, "\n============================\n", "h2")
                self.output.insert(tk.END, "*Pha 2: Giải bài toán gốc\n", "h2")
                self.output.insert(tk.END, "============================\n", "h2")
                self._render_trace("Pha 2", report.phase2_trace)
            else:
                self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
                self.output.insert(tk.END, "  Trạng thái: vô nghiệm.\n", "warn")
                return
        else:
            self.output.insert(tk.END, "\n============================\n", "h2")
            self.output.insert(tk.END, "*Pha 1: Giải bài toán bổ trợ\n", "h2")
            self.output.insert(tk.END, "============================\n", "h2")
            self.output.insert(tk.END, "_ Vì tất cả các b_i đều ≥ 0 nên không giải pha 1\n", "note")
            self.output.insert(tk.END, "\n============================\n", "h2")
            self.output.insert(tk.END, "*Pha 2: Giải bài toán gốc\n", "h2")
            self.output.insert(tk.END, "============================\n", "h2")
            self._render_trace("Pha 2", report.dantzig)
            if report.bland is not None and report.bland is not report.dantzig:
                self.output.insert(tk.END, "\n-----------------------------\n", "h2")
                self.output.insert(tk.END, "*Bland sau khi Dantzig lặp ở pha 2\n", "h2")
                self.output.insert(tk.END, "-----------------------------\n", "h2")
                self._render_trace("Pha 2 - Bland", report.bland)

        final_snap = report.phase2_trace.final_snapshot if report.phase2_trace and report.phase2_trace.final_snapshot else (
            report.bland.final_snapshot if report.bland and report.bland.final_snapshot else report.dantzig.final_snapshot
        )

        if report.status == "unbounded" or (report.bland is not None and report.bland.status == "unbounded"):
            self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
            self.output.insert(tk.END, "  Trạng thái: bài toán không giới nội.\n", "warn")
            return
        if report.status == "cycle":
            self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
            self.output.insert(tk.END, "  Trạng thái: Dantzig lặp và Bland cũng chưa kết thúc trong giới hạn lặp.\n", "warn")
            return

        obj_std = report.objective_std if report.objective_std is not None else Fraction(0)
        obj_orig = report.objective_orig if report.objective_orig is not None else Fraction(0)

        if report.multiple_optimal and final_snap and report.multiple_optimal_vars:
            for line in self._format_multiple_optimal_family(engine, final_snap, report):
                self.output.insert(tk.END, line + "\n", "warn" if "vô số nghiệm" in line else "note")

            self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
            self.output.insert(tk.END, f"  Trạng thái: tối ưu đạt được bằng {report.used_method.upper()}.\n", "note")
            self.output.insert(tk.END, f"  Trong bảng min: z* = {fmt_num(obj_std, mode)}\n", "note")
            self.output.insert(tk.END, f"  Giá trị tối ưu của bài toán gốc: {fmt_num(obj_orig, mode)}\n", "note")
            for line in self._format_multiple_optimal_conclusion(engine, final_snap, report):
                self.output.insert(tk.END, line + "\n", "note")
            if report.dantzig.degenerate_steps or (report.bland and report.bland.degenerate_steps):
                d = report.dantzig.degenerate_steps + (report.bland.degenerate_steps if report.bland else 0)
                self.output.insert(tk.END, f"  Có {d} bước suy biến trong quá trình xoay.\n", "warn")
            return

        self.output.insert(tk.END, "\nKẾT LUẬN\n", "h2")
        self.output.insert(tk.END, f"  Trạng thái: tối ưu đạt được bằng {report.used_method.upper()}.\n", "note")
        self.output.insert(tk.END, f"  Trong bảng min: z* = {fmt_num(obj_std, mode)}\n", "note")
        self.output.insert(tk.END, f"  Giá trị tối ưu của bài toán gốc: {fmt_num(obj_orig, mode)}\n", "note")
        self.output.insert(tk.END, "  Nghiệm tối ưu: ", "note")
        orig_parts = []
        for i in range(len(engine.problem.var_signs)):
            orig_parts.append(f"x{i+1} = {fmt_num(report.solution_orig.get(i, Fraction(0)), mode)}")
        self.output.insert(tk.END, "; ".join(orig_parts) + "\n", "note")
        if report.dantzig.degenerate_steps or (report.bland and report.bland.degenerate_steps):
            d = report.dantzig.degenerate_steps + (report.bland.degenerate_steps if report.bland else 0)
            self.output.insert(tk.END, f"  Có {d} bước suy biến trong quá trình xoay.\n", "warn")
    def _has_aux_phase1(self, engine: SimplexEngine) -> bool:
        return bool(getattr(engine, "need_aux_phase1", False))

    def run_solver(self):
        try:
            prob = self._collect_problem()
            engine = SimplexEngine(prob)
            report = engine.solve_full()
            self.last_problem = prob
            self.last_report = report
            self._render_result(report)
            self._set_solution_available(True)
            self.status_var.set(f"Đã giải xong: {report.status}.")
        except Exception as exc:
            self.last_report = None
            self._set_solution_available(False)
            messagebox.showerror("Lỗi nhập liệu / giải thuật", str(exc))
            self.status_var.set("Có lỗi xảy ra. Kiểm tra lại dữ liệu nhập.")


        # ==========================================================
    # Overridden visualization / export behavior
    # ==========================================================

    def _set_solution_available(self, available: bool) -> None:
        if self.export_btn is None:
            return
        if available:
            self.export_btn._base_bg = "#16a34a"
            self.export_btn._hover_bg = "#15803d"
            self.export_btn._disabled_bg = "#9ca3af"
            self.export_btn.config(state=tk.NORMAL, bg=self.export_btn._base_bg,
                                   activebackground=self.export_btn._hover_bg, cursor="hand2")
        else:
            self.export_btn._base_bg = "#9ca3af"
            self.export_btn._hover_bg = "#6b7280"
            self.export_btn._disabled_bg = "#9ca3af"
            self.export_btn.config(state=tk.DISABLED, bg=self.export_btn._base_bg,
                                   activebackground=self.export_btn._hover_bg, cursor="arrow")

    def _on_button_enter(self, event, darker_color: Optional[str] = None) -> None:
        btn = event.widget
        if str(btn.cget("state")) == "disabled":
            return
        if btn is self.export_btn:
            darker_color = getattr(btn, "_hover_bg", darker_color if darker_color is not None else btn.cget("bg"))
        elif darker_color is None:
            darker_color = getattr(btn, "_hover_bg", btn.cget("bg"))
        btn.config(bg=darker_color)

    def _on_button_leave(self, event, original_color: Optional[str] = None) -> None:
        btn = event.widget
        if str(btn.cget("state")) == "disabled":
            return
        if original_color is None or btn is self.export_btn:
            original_color = getattr(btn, "_base_bg", btn.cget("bg"))
        btn.config(bg=original_color)

    def _request_canvas_redraw(self, canvas, delay_ms: int = 14) -> None:
        widget = canvas.get_tk_widget()
        job = getattr(widget, "_redraw_job", None)
        if job is not None:
            return

        def _do_redraw():
            widget._redraw_job = None
            try:
                canvas.draw_idle()
            except Exception:
                pass

        widget._redraw_job = widget.after(delay_ms, _do_redraw)

    def run_solver(self):
        try:
            prob = self._collect_problem()
            engine = SimplexEngine(prob)
            report = engine.solve_full()
            self.last_problem = prob
            self.last_report = report
            self._render_result(report)
            self._set_solution_available(report.status == "optimal")
            self.status_var.set(f"Đã giải xong: {report.status}.")
        except Exception as exc:
            self.last_report = None
            self._set_solution_available(False)
            messagebox.showerror("Lỗi nhập liệu / giải thuật", str(exc))
            self.status_var.set("Có lỗi xảy ra. Kiểm tra lại dữ liệu nhập.")

    def _create_visualization_window(self) -> tk.Toplevel:
        top = tk.Toplevel(self)
        top.title("Trực quan hóa bài toán 2 biến")
        top.geometry("1540x980")
        top.minsize(1100, 760)
        top.resizable(True, True)
        try:
            top.state("zoomed")
        except Exception:
            try:
                top.attributes("-zoomed", True)
            except Exception:
                pass
        top.configure(bg="#f8fafc")
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        top.protocol("WM_DELETE_WINDOW", top.destroy)
        return top

    def _create_figure(self):
        from matplotlib.figure import Figure
        fig = Figure(figsize=(16, 9.6), dpi=105)
        fig.patch.set_facecolor("#f8fafc")
        fig.subplots_adjust(left=0.045, right=0.992, top=0.94, bottom=0.085)
        ax = fig.add_subplot(111)
        ax.set_facecolor("#ffffff")
        ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.16)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        return fig, ax

    def _line_box_intersections(self, a: Fraction, b: Fraction, c: Fraction,
                                xmin: float, xmax: float, ymin: float, ymax: float):
        eps = 1e-12
        pts = []

        def add(pt):
            x, y = pt
            if math.isfinite(x) and math.isfinite(y) and xmin - 1e-9 <= x <= xmax + 1e-9 and ymin - 1e-9 <= y <= ymax + 1e-9:
                for qx, qy in pts:
                    if abs(qx - x) <= 1e-7 and abs(qy - y) <= 1e-7:
                        return
                pts.append((x, y))

        fa, fb, fc = float(a), float(b), float(c)
        if abs(fb) > eps:
            add((xmin, (fc - fa * xmin) / fb))
            add((xmax, (fc - fa * xmax) / fb))
        if abs(fa) > eps:
            add(((fc - fb * ymin) / fa, ymin))
            add(((fc - fb * ymax) / fa, ymax))
        return pts

    def _plot_feasible_region(self, ax, X, Y, mask):
        ax.contourf(X, Y, mask.astype(float), levels=[0.5, 1.5], alpha=0.16,
                    colors=["#93c5fd"], zorder=0)

    def _plot_constraints(self, ax, halfplanes, xmin, xmax, ymin, ymax):
        palette = ["#1d4ed8", "#7c3aed", "#0f766e", "#d97706", "#be123c", "#0891b2"]
        labels_seen = set()
        for idx, (a, b, c, sense, label) in enumerate(halfplanes):
            color = palette[idx % len(palette)]
            pts = self._line_box_intersections(a, b, c, xmin, xmax, ymin, ymax)
            if len(pts) < 2:
                continue
            pts = sorted(pts, key=lambda p: (p[0], p[1]))
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=2.4, alpha=0.95,
                    solid_capstyle="round", zorder=2)
            if label not in labels_seen:
                labels_seen.add(label)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                dx = 0.012 * (xmax - xmin)
                dy = 0.012 * (ymax - ymin)
                ax.text(mx + dx, my + dy, label, fontsize=9, color=color, weight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="#ffffff", ec=color, alpha=0.88),
                        zorder=3)

    def _plot_objective_contours(self, ax, c1: float, c2: float, vertex_values, xmin, xmax, ymin, ymax, maximize: bool):
        if not vertex_values or abs(c1) + abs(c2) < 1e-12:
            return
        zvals = sorted(v[2] for v in vertex_values)
        z_best = max(zvals) if maximize else min(zvals)
        span = max(1.0, float(abs(zvals[-1] - zvals[0])) if len(zvals) > 1 else max(1.0, abs(z_best)))
        levels = [z_best - span, z_best - 0.5 * span, z_best, z_best + 0.5 * span, z_best + span]
        for lv in levels:
            pts = self._line_box_intersections(Fraction(str(c1)), Fraction(str(c2)), Fraction(str(lv)),
                                               xmin, xmax, ymin, ymax)
            if len(pts) < 2:
                continue
            pts = sorted(pts, key=lambda p: (p[0], p[1]))
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            is_best = abs(lv - z_best) < 1e-9
            ax.plot([x1, x2], [y1, y2], color="#ef4444",
                    linewidth=2.8 if is_best else 1.6,
                    linestyle="-" if is_best else "--",
                    alpha=0.72 if is_best else 0.28,
                    zorder=1.5)
            if is_best:
                tx, ty = (x1 + x2) / 2, (y1 + y2) / 2
                ax.text(tx, ty, f"  z = {fmt_num(Fraction(str(lv)), self.data_mode.get())}",
                        color="#b91c1c", fontsize=9, weight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="#fff1f2", ec="#fca5a5", alpha=0.95),
                        zorder=4)

    def _plot_vertices(self, ax, vertex_values, maximize: bool):
        if not vertex_values:
            return
        pts = [(p[0], p[1], p[2]) for p in vertex_values]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda t: math.atan2(t[1] - cy, t[0] - cx))
        ax.fill([p[0] for p in pts], [p[1] for p in pts], color="#dbeafe", alpha=0.10, zorder=1)
        ax.plot([p[0] for p in pts] + [pts[0][0]],
                [p[1] for p in pts] + [pts[0][1]],
                color="#0f172a", linewidth=1.2, linestyle=":", alpha=0.52, zorder=2.5)
        for idx, (vx, vy, val) in enumerate(pts, start=1):
            ax.scatter([vx], [vy], s=42, color="#2563eb", edgecolors="white",
                       linewidths=1.0, zorder=5)
            ax.annotate(
                f"{idx}", xy=(vx, vy), xytext=(6, 6), textcoords="offset points",
                fontsize=9, color="#0f172a",
                bbox=dict(boxstyle="circle,pad=0.18", fc="#eff6ff", ec="#93c5fd", alpha=0.95),
                zorder=6
            )

    def _plot_optimal_point(self, ax, optimal, maximize: bool):
        if optimal is None:
            return
        bx, by, bz = optimal
        ax.scatter([bx], [by], s=220, marker="*", color="#f59e0b",
                   edgecolors="#111827", linewidths=1.2, zorder=7)
        ax.annotate(
            f"Điểm tối ưu\n({bx:.3g}, {by:.3g})\nz = {bz:.3g}",
            xy=(bx, by), xytext=(14, 18), textcoords="offset points",
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", fc="#fff7ed", ec="#fb923c", alpha=0.98),
            arrowprops=dict(arrowstyle="->", color="#fb923c", lw=1.5),
            zorder=8
        )

    def _configure_axes(self, ax, xmin: float, xmax: float, ymin: float, ymax: float):
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("auto", adjustable="box")
        ax.set_xlabel("x₁", fontsize=12, fontweight="bold")
        ax.set_ylabel("x₂", fontsize=12, fontweight="bold")
        ax.set_title("Miền chấp nhận được và đường đồng mức hàm mục tiêu",
                     fontsize=14, fontweight="bold", pad=10, color="#0f172a")
        ax.axhline(0, color="#334155", linewidth=1.1, alpha=0.7, zorder=0.5)
        ax.axvline(0, color="#334155", linewidth=1.1, alpha=0.7, zorder=0.5)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(
                handles, labels, loc="upper left", frameon=True, fontsize=9,
                title="Ràng buộc", title_fontsize=10, fancybox=True, shadow=False,
                facecolor="#ffffff", edgecolor="#cbd5e1"
            )

    def _create_control_button(self, parent, text: str, color: str, hover_color: str, command):
        btn = tk.Button(
            parent, text=text, font=("Segoe UI", 10, "bold"),
            bg=color, fg="white", activebackground=hover_color,
            activeforeground="white", relief="flat", bd=0, padx=10, pady=6,
            cursor="hand2", command=command
        )
        btn.pack(side="left", padx=4, pady=4)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        return btn

    def _enable_canvas_interactions(self, ax, canvas):
        state = {"press": None}

        def clamp_limits():
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            if xmax - xmin < 1e-6:
                ax.set_xlim(xmin - 1, xmax + 1)
            if ymax - ymin < 1e-6:
                ax.set_ylim(ymin - 1, ymax + 1)

        def on_press(event):
            if event.inaxes != ax or event.button != 1 or event.xdata is None or event.ydata is None:
                return
            state["press"] = (event.xdata, event.ydata, ax.get_xlim(), ax.get_ylim())

        def on_release(event):
            state["press"] = None

        def on_move(event):
            if not state["press"] or event.inaxes != ax or event.xdata is None or event.ydata is None:
                return
            x0, y0, xlim0, ylim0 = state["press"]
            dx = x0 - event.xdata
            dy = y0 - event.ydata
            ax.set_xlim(xlim0[0] + dx, xlim0[1] + dx)
            ax.set_ylim(ylim0[0] + dy, ylim0[1] + dy)
            clamp_limits()
            self._request_canvas_redraw(canvas)

        def on_scroll(event):
            if event.inaxes != ax or event.xdata is None or event.ydata is None:
                return
            base = 1.10 if getattr(event, "button", None) == "down" else 1 / 1.10
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()
            xdata, ydata = event.xdata, event.ydata
            new_w = (cur_xlim[1] - cur_xlim[0]) * base
            new_h = (cur_ylim[1] - cur_ylim[0]) * base
            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            ax.set_xlim(xdata - (1 - relx) * new_w, xdata + relx * new_w)
            ax.set_ylim(ydata - (1 - rely) * new_h, ydata + rely * new_h)
            clamp_limits()
            self._request_canvas_redraw(canvas)

        canvas.mpl_connect("button_press_event", on_press)
        canvas.mpl_connect("button_release_event", on_release)
        canvas.mpl_connect("motion_notify_event", on_move)
        canvas.mpl_connect("scroll_event", on_scroll)

    def _create_zoom_controls(self, parent, ax, canvas, initial_xlim, initial_ylim):
        ctrl_frame = tk.Frame(parent, bg="#0f172a", highlightthickness=1, highlightbackground="#334155")
        ctrl_frame.place(relx=0.015, rely=0.965, anchor="sw")

        def zoom_in():
            x1, x2 = ax.get_xlim()
            y1, y2 = ax.get_ylim()
            dx = (x2 - x1) * 0.14
            dy = (y2 - y1) * 0.14
            ax.set_xlim(x1 + dx, x2 - dx)
            ax.set_ylim(y1 + dy, y2 - dy)
            self._request_canvas_redraw(canvas)

        def zoom_out():
            x1, x2 = ax.get_xlim()
            y1, y2 = ax.get_ylim()
            dx = (x2 - x1) * 0.14
            dy = (y2 - y1) * 0.14
            ax.set_xlim(x1 - dx, x2 + dx)
            ax.set_ylim(y1 - dy, y2 + dy)
            self._request_canvas_redraw(canvas)

        def reset():
            ax.set_xlim(initial_xlim)
            ax.set_ylim(initial_ylim)
            self._request_canvas_redraw(canvas)

        self._create_control_button(ctrl_frame, "🔍+", "#2563eb", "#1d4ed8", zoom_in)
        self._create_control_button(ctrl_frame, "🔍−", "#f59e0b", "#d97706", zoom_out)
        self._create_control_button(ctrl_frame, "↺", "#10b981", "#059669", reset)

        hint = tk.Label(
            ctrl_frame,
            text="Kéo chuột trái để di chuyển • Lăn chuột để zoom",
            bg="#0f172a", fg="#e2e8f0", font=("Segoe UI", 9)
        )
        hint.pack(side="left", padx=10, pady=6)

    def _create_info_panel(self, parent, prob: ProblemData, vertices, vertex_values, optimal, maximize: bool):
        info_frame = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#cbd5e1")
        info_frame.place(relx=0.987, rely=0.02, anchor="ne", width=320, height=182)

        title = tk.Label(info_frame, text="Tóm tắt", bg="#ffffff", fg="#0f172a",
                         font=("Segoe UI", 11, "bold"))
        title.pack(anchor="w", padx=10, pady=(8, 2))

        text = tk.Text(info_frame, wrap="word", bg="#ffffff", fg="#0f172a", bd=0,
                       font=("Segoe UI", 9), height=8, padx=10, pady=6)
        text.pack(fill="both", expand=True)

        lines = [
            f"Kiểu: {'Bài toán Max' if prob.objective_sense == 'max' else 'Bài toán Min'}",
            f"Số ràng buộc: {len(prob.constraints)}",
            f"Số đỉnh khả thi: {len(vertices)}",
        ]
        if optimal is not None:
            lines.append(f"Điểm tối ưu: ({optimal[0]:.3g}, {optimal[1]:.3g})")
            lines.append(f"Giá trị mục tiêu: {optimal[2]:.3g}")
        else:
            lines.append("Chưa tìm được miền khả thi.")
        lines.append("Kéo chuột trái để pan.")
        lines.append("Dùng nút hoặc lăn chuột để zoom.")
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

    def visualize_two_variable_problem(self) -> None:
        try:
            prob = self._collect_problem()
        except Exception as exc:
            messagebox.showerror("Trực quan hóa", str(exc))
            return

        if len(prob.obj_coeffs) != 2:
            messagebox.showinfo("Trực quan hóa", "Tính năng này chỉ hỗ trợ đúng 2 biến x₁ và x₂.")
            return

        try:
            import numpy as np
            import matplotlib
            matplotlib.use("TkAgg", force=True)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except Exception as exc:
            messagebox.showerror("Trực quan hóa", f"Không khởi tạo được thư viện: {exc}")
            return

        halfplanes = self._build_halfplanes(prob)
        vertices = self._deduplicate_points(self._compute_feasible_vertices(halfplanes))
        xmin, xmax, ymin, ymax = self._compute_plot_bounds(vertices, halfplanes)
        _, _, X, Y = self._create_meshgrid(xmin, xmax, ymin, ymax)
        feasible_mask = self._compute_feasible_region(halfplanes, X, Y)

        c1, c2 = float(prob.obj_coeffs[0]), float(prob.obj_coeffs[1])
        vertex_values = [(p[0], p[1], c1 * p[0] + c2 * p[1]) for p in vertices]
        maximize = prob.objective_sense == "max"
        optimal_point = self._find_optimal_vertex(vertex_values, maximize)

        window = self._create_visualization_window()
        plot_frame = tk.Frame(window, bg="#f8fafc", bd=0, highlightthickness=0)
        plot_frame.grid(row=0, column=0, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)

        fig, ax = self._create_figure()
        self._plot_feasible_region(ax, X, Y, feasible_mask)
        self._plot_constraints(ax, halfplanes, xmin, xmax, ymin, ymax)
        self._plot_objective_contours(ax, c1, c2, vertex_values, xmin, xmax, ymin, ymax, maximize)
        self._plot_vertices(ax, vertex_values, maximize)
        self._plot_optimal_point(ax, optimal_point, maximize)
        self._configure_axes(ax, xmin, xmax, ymin, ymax)

        canvas = FigureCanvasTkAgg(fig, master=plot_frame)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.configure(bd=0, highlightthickness=0, relief="flat")
        canvas_widget.pack(fill="both", expand=True)

        self._create_info_panel(plot_frame, prob, vertices, vertex_values, optimal_point, maximize)
        self._create_zoom_controls(plot_frame, ax, canvas, (xmin, xmax), (ymin, ymax))
        self._enable_canvas_interactions(ax, canvas)
        window.focus_force()

# =========================
# Main
# =========================

def main():
    app = SimplexApp()
    app.mainloop()


if __name__ == "__main__":
    main()
