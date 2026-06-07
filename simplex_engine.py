from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

from models import ProblemData, Snapshot, PivotStep, SolveTrace, SolveReport
from utils import fr, fmt_num


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


    def solve_full(self, preferred_method: str = "dantzig") -> SolveReport:
        notes = self.standardization_lines[:] + self.strict_notes[:]

        method = (preferred_method or "dantzig").strip().lower()
        if method in {"dantzig simplex", "dantzig", "d"}:
            method_key = "dantzig"
        elif method in {"bland's rule", "bland", "blands rule", "bland rule"}:
            method_key = "bland"
        else:
            raise ValueError("Phương pháp giải không hợp lệ. Hãy chọn Dantzig Simplex hoặc Bland's Rule.")

        if self.need_aux_phase1:
            basis, rows, rhs, obj_const, obj, aux_idx = self._phase1_aux_start()
            phase1 = self._solve_phase1_aux_once(method_key, basis, rows, rhs, obj_const, obj, "δ", aux_idx)

            if phase1.status == "cycle":
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=False,
                    phase1_bland=None, phase2_trace=None
                )

            if phase1.final_snapshot is None:
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=None, phase2_trace=None
                )

            # x0 không còn nằm trong cơ sở và giá trị mục tiêu pha 1 bằng 0 => sang pha 2
            aux_idx_in_basis = aux_idx in phase1.final_snapshot.basis
            if phase1.final_snapshot.obj_const != 0 or aux_idx_in_basis:
                phase1.infeasible = True
                phase1.status = "infeasible"
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=None, phase2_trace=None
                )

            basis2, rows2, rhs2, obj_const2, obj2 = self._phase2_start(phase1.final_snapshot, strip_vars=[aux_idx])
            phase2 = self._solve_once(method_key, 2, basis2, rows2, rhs2, obj_const2, obj2, "z", self.artificial_vars)
            return self._assemble_report(
                method_key, phase1, None, notes, phase1_infeasible=False,
                phase1_bland=None, phase2_trace=phase2
            )

        if self.artificial_vars:
            # Phase 1 first.
            basis, rows, rhs, obj_const, obj = self._phase1_start()
            phase1 = self._solve_once(method_key, 1, basis, rows, rhs, obj_const, obj, "w", self.artificial_vars)

            if phase1.status == "cycle":
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=False,
                    phase1_bland=None, phase2_trace=None
                )

            if phase1.final_snapshot is None:
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=None, phase2_trace=None
                )

            if phase1.final_snapshot.obj_const != 0:
                phase1.infeasible = True
                phase1.status = "infeasible"
                return self._assemble_report(
                    method_key, phase1, None, notes, phase1_infeasible=True,
                    phase1_bland=None, phase2_trace=None
                )

            basis2, rows2, rhs2, obj_const2, obj2 = self._phase2_start(phase1.final_snapshot)
            phase2 = self._solve_once(method_key, 2, basis2, rows2, rhs2, obj_const2, obj2, "z", self.artificial_vars)
            return self._assemble_report(
                method_key, phase1, None, notes, phase1_infeasible=False,
                phase1_bland=None, phase2_trace=phase2
            )

        # No artificials => phase 2 only.
        basis, rows, rhs, obj_const, obj = self._phase2_start(
            self._state(self.initial_basis, self.initial_rows, self.initial_rhs, Fraction(0), {}, 2, "z", self.artificial_vars)
        )
        trace = self._solve_once(method_key, 2, basis, rows, rhs, obj_const, obj, "z", self.artificial_vars)
        return self._assemble_report(
            method_key, trace, None, notes, phase1_infeasible=False,
            phase1_bland=None, phase2_trace=trace
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
