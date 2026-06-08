"""
html_exporter.py
~~~~~~~~~~~~~~~~
Xuất toàn bộ lời giải đơn hình thành file HTML độc lập với KaTeX render.
Không cần thư viện ngoài (chỉ dùng stdlib).

Cách dùng:
    from html_exporter import export_report_html
    path = export_report_html(report, engine, data_mode)
    webbrowser.open(f"file:///{path}")
"""

from __future__ import annotations

import os
import tempfile
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

from models import PivotStep, Snapshot, SolveReport, SolveTrace
from utils import fmt_num
import locales

import html


# ---------------------------------------------------------------------------
# Helpers: chuyển Fraction → LaTeX
# ---------------------------------------------------------------------------

def _frac(x: Fraction, mode: str = "Phân số") -> str:
    """Chuyển Fraction thành chuỗi LaTeX: phân số → \\frac{a}{b}, số nguyên → a."""
    if not isinstance(x, Fraction):
        x = Fraction(x)
    if x == 0:
        return "0"
    if mode == "Số thập phân":
        return fmt_num(x, mode)
    if x.denominator == 1:
        return str(x.numerator)
    sign = "-" if x < 0 else ""
    return f"{sign}\\dfrac{{{abs(x.numerator)}}}{{{x.denominator}}}"


def _term(coeff: Fraction, var_name: str, mode: str) -> str:
    """Tạo hạng tử LaTeX: hệ số × tên biến (bỏ qua hệ số = 0)."""
    if coeff == 0:
        return ""
    abs_c = abs(coeff)
    sign = "+" if coeff > 0 else "-"
    if abs_c == 1:
        body = f"\\,{_tex_var(var_name)}"
    else:
        body = f"\\,{_frac(abs_c, mode)}{_tex_var(var_name)}"
    return f"{sign}{body}"


def _tex_var(name: str) -> str:
    """Biến x3 → x_{3},  w2 → w_{2},  z → z, v.v."""
    for prefix in ("x", "w", "y", "a", "b", "s", "δ"):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return f"{prefix}_{{{name[len(prefix):]}}}"
    if name in ("z", "δ", "w"):
        return name
    return name


def _expr(coeffs_or_dict, names: List[str], mode: str,
          is_dict: bool = False) -> str:
    """
    Tạo biểu thức tuyến tính LaTeX.
    coeffs_or_dict: List[Fraction] | Dict[int,Fraction]
    """
    parts: List[str] = []
    if is_dict:
        items = [(j, coeffs_or_dict.get(j, Fraction(0))) for j in range(len(names))]
    else:
        items = list(enumerate(coeffs_or_dict))
    for j, c in items:
        if c == 0:
            continue
        t = _term(c, names[j], mode)
        parts.append(t)
    if not parts:
        return "0"
    s = " ".join(parts)
    # Xóa dấu "+" thừa đầu chuỗi
    return s.lstrip("+").strip()


def _rhs(val: Fraction, mode: str) -> str:
    return _frac(val, mode)


# ---------------------------------------------------------------------------
# Render bảng từ vựng (dictionary) → HTML table
# ---------------------------------------------------------------------------

def _snapshot_table(
    snapshot: Snapshot,
    mode: str,
    entering_name: Optional[str] = None,
    pivot_row: Optional[int] = None,
) -> str:
    """Tạo <table> HTML cho một snapshot (bảng từ vựng đơn hình).
    Chỉ hiển thị cột của biến phi cơ sở (biến cơ sở đã nằm ở cột nhãn, không cần cột riêng).
    """
    names = snapshot.all_names
    basis_set = set(snapshot.basis)

    # Chỉ lấy cột phi cơ sở (nonbasic columns)
    nonbasic_cols = [j for j in range(len(names)) if j not in basis_set]

    # Header
    header_cells = ["<th class='row-label'></th>", f"<th class='rhs-col'>{locales.t('html_constant_col')}</th>"]
    for j in nonbasic_cols:
        nm = names[j]
        css = "pivot-col-head" if nm == entering_name else ""
        header_cells.append(f"<th class='{css}'>${_tex_var(nm)}$</th>")
    thead = f"<thead><tr>{''.join(header_cells)}</tr></thead>"

    rows_html: List[str] = []

    # Hàng mục tiêu
    obj_label_tex = f"\\mathbf{{{_tex_var(snapshot.objective_label)}}}"
    obj_cells = [f"<td class='row-label'>${obj_label_tex}$</td>"]
    # Hằng số: ẩn nếu = 0 và có hạng tử khác (từ vựng xuất phát)
    obj_const_str = _frac(snapshot.obj_const, mode)
    has_obj_terms = any(snapshot.obj.get(j, Fraction(0)) != 0 for j in nonbasic_cols)
    if snapshot.obj_const == 0 and has_obj_terms:
        obj_cells.append(f"<td class='rhs-cell' style='color:#94A3B8'>$= 0$</td>")
    else:
        obj_cells.append(f"<td class='rhs-cell'>$= {obj_const_str}$</td>")
    for j in nonbasic_cols:
        nm = names[j]
        c = snapshot.obj.get(j, Fraction(0))
        css = "pivot-col" if nm == entering_name else ""
        cell_val = f"$+\\,{_frac(c, mode)}$" if c > 0 else (f"$-\\,{_frac(-c, mode)}$" if c < 0 else "$0$")
        obj_cells.append(f"<td class='{css}'>{cell_val}</td>")
    rows_html.append(f"<tr class='obj-row'>{''.join(obj_cells)}</tr>")

    # Hàng cơ sở
    for i, b in enumerate(snapshot.basis):
        b_name = names[b]
        is_pivot_row = (pivot_row is not None and i == pivot_row)
        row_css = "pivot-row" if is_pivot_row else ""
        cells = [f"<td class='row-label'>$\\mathbf{{{_tex_var(b_name)}}}$</td>"]
        cells.append(f"<td class='rhs-cell'>$= {_frac(snapshot.rhs[i], mode)}$</td>")
        for j in nonbasic_cols:
            nm = names[j]
            c = snapshot.rows[i].get(j, Fraction(0))
            cell_css = ""
            if nm == entering_name and is_pivot_row:
                cell_css = "pivot-cell"
            elif nm == entering_name:
                cell_css = "pivot-col"
            elif is_pivot_row:
                cell_css = "pivot-row"
            cell_val = f"$+\\,{_frac(c, mode)}$" if c > 0 else (f"$-\\,{_frac(-c, mode)}$" if c < 0 else "$0$")
            cells.append(f"<td class='{cell_css}'>{cell_val}</td>")
        rows_html.append(f"<tr class='{row_css}'>{''.join(cells)}</tr>")

    return f"""<div class="dict-table-wrap">
<table class="dict-table">
{thead}
<tbody>{''.join(rows_html)}</tbody>
</table>
</div>"""


# ---------------------------------------------------------------------------
# Render note cho từng bước xoay
# ---------------------------------------------------------------------------

def _step_note_html(step: PivotStep, snapshot: Snapshot, mode: str) -> str:
    names = snapshot.all_names
    enter = _tex_var(names[step.entering]) if step.entering is not None else "?"
    leave = _tex_var(names[step.leaving_var]) if step.leaving_var is not None else "?"
    rule = "Dantzig" if step.method == "dantzig" else "Bland"
    lines: List[str] = []

    if step.status == "phase1_aux_pivot":
        lines.append(f"<p class='note-rule'>⚙️ <b>{locales.t('html_rule_dantzig_p1')}</b></p>")
        lines.append(f"<p>{locales.t('html_aux_enter')}</p>")
        if step.ratios:
            lines.append("<ul>")
            for ri, bval, bi in step.ratios:
                lines.append(f"<li>${_tex_var(names[bi])}$: $b = {_frac(bval, mode)}$</li>")
            lines.append("</ul>")
        lines.append(f"<p>$\\Rightarrow$ {locales.t('html_entering', var=enter)} &nbsp;|&nbsp; {locales.t('html_leaving', var=leave)}</p>")
        if step.pivot_value is not None:
            lines.append(f"<p>{locales.t('html_pivot')} $a_{{{leave},{enter}}} = {_frac(step.pivot_value, mode)}$</p>")
        if step.degenerate:
            lines.append(f"<p class='warn'>{locales.t('html_degenerate')}</p>")
        return "".join(lines)

    lines.append(f"<p class='note-rule'>⚙️ <b>{locales.t('html_rule_label', rule=rule)}</b></p>")
    if step.entering is not None:
        coeff = snapshot.obj.get(step.entering, Fraction(0))
        if step.method == "dantzig":
            lines.append(f"<p>{locales.t('html_choose_dantzig', var=enter, coeff=_frac(coeff, mode))}</p>")
        else:
            lines.append(f"<p>{locales.t('html_choose_bland', var=enter)}</p>")
        lines.append(f"<p>$\\Rightarrow$ {locales.t('html_entering', var=enter)}</p>")

    if step.ratios:
        lines.append(f"<p>{locales.t('html_ratio_table', var=enter)}</p>")
        lines.append(f"<table class='ratio-table'><tr><th>{locales.t('html_row')}</th><th>$b_i$</th>"
                     "<th>$a_{{i,enter}}$</th><th>$\\theta = b_i / (-a_{{i,enter}})$</th></tr>")
        for ri, theta, bi in step.ratios:
            a_val = snapshot.rows[ri].get(step.entering, Fraction(0)) if step.entering is not None else Fraction(0)
            lines.append(f"<tr><td>${_tex_var(names[bi])}$</td>"
                         f"<td>${_frac(snapshot.rhs[ri], mode)}$</td>"
                         f"<td>${_frac(a_val, mode)}$</td>"
                         f"<td>${_frac(theta, mode)}$</td></tr>")
        lines.append("</table>")
        lines.append(f"<p>$\\Rightarrow$ {locales.t('html_leaving', var=leave)}</p>")

    if step.pivot_value is not None:
        lines.append(f"<p>{locales.t('html_pivot')} "
                     f"$a_{{{leave},{enter}}} = {_frac(step.pivot_value, mode)}$</p>")
    if step.degenerate:
        lines.append(f"<p class='warn'>{locales.t('html_degenerate')}</p>")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Render một trace (pha) hoàn chỉnh
# ---------------------------------------------------------------------------

def _render_trace_html(trace: SolveTrace, mode: str) -> str:
    parts: List[str] = []
    if not trace.steps:
        if trace.final_snapshot:
            parts.append(f"<p class='note'>{locales.t('html_init_dict_no_pivot')}</p>")
            parts.append(_snapshot_table(trace.final_snapshot, mode))
        return "".join(parts)

    for step in trace.steps:
        title = locales.t("html_init_dict") if step.iteration == 1 else locales.t("html_step_before", n=step.iteration)
        parts.append(f"<h4>{title}</h4>")

        # Bảng trước xoay (có highlight)
        entering_name = step.before.all_names[step.entering] if step.entering is not None else None
        parts.append(_snapshot_table(step.before, mode,
                                     entering_name=entering_name,
                                     pivot_row=step.leaving_row))

        # Giải thích bước
        parts.append(f"<div class='step-note'>")
        parts.append(_step_note_html(step, step.before, mode))
        parts.append("</div>")

        # Bảng sau xoay
        if step.after is not None:
            parts.append(f"<h4>{locales.t('html_step_after', n=step.iteration)}</h4>")
            parts.append(_snapshot_table(step.after, mode))

    # Trạng thái kết thúc
    if trace.status == "optimal":
        parts.append(f"<p class='success'>{locales.t('html_all_opt')}</p>")
    elif trace.status == "unbounded":
        last_entering = None
        if trace.steps:
            last_step = trace.steps[-1]
            if last_step.status == "unbounded" and last_step.entering is not None:
                last_entering = trace.steps[-1].before.all_names[last_step.entering]
        reason = locales.t("html_enter_no_leave", var=_tex_var(last_entering)) if last_entering else ""
        parts.append(f"<p class='warn'>{locales.t('html_unbounded', reason=reason)}</p>")
    elif trace.status == "cycle":
        rule = "Dantzig" if trace.steps and trace.steps[0].method == "dantzig" else "Bland"
        if rule == "Dantzig":
            parts.append(f"<p class='warn'>{locales.t('html_dantzig_cycle')}</p>")
        else:
            parts.append(f"<p class='warn'>{locales.t('html_bland_cycle')}</p>")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Phần bài toán gốc + chuẩn hóa
# ---------------------------------------------------------------------------

def _problem_html(engine, mode: str) -> str:
    prob = engine.problem
    n = len(prob.obj_coeffs)

    def expr_orig(coeffs):
        parts = []
        for j, c in enumerate(coeffs):
            if c == 0:
                continue
            abs_c = abs(c)
            vname = f"x_{{{j+1}}}"
            sign = "+" if c > 0 else "-"
            if abs_c == 1:
                body = f"\\,{vname}"
            else:
                body = f"\\,{_frac(abs_c, mode)}{vname}"
            parts.append(f"{sign}{body}")
        if not parts:
            return "0"
        return " ".join(parts).lstrip("+").strip()

    sense_label = "\\max" if prob.objective_sense == "max" else "\\min"
    obj_expr = expr_orig(prob.obj_coeffs)

    con_lines = []
    for cons in prob.constraints:
        lhs = expr_orig(cons["coeffs"])
        s_tex = {"≤": "\\leq", "≥": "\\geq", "=": "="}.get(cons["sense"], cons["sense"])
        rhs = _frac(Fraction(cons["rhs"]), mode)
        con_lines.append(f"\\quad {lhs} {s_tex} {rhs}")

    for i, sg in enumerate(prob.var_signs):
        nm = f"x_{{{i+1}}}"
        if sg == "≥0":
            con_lines.append(f"\\quad {nm} \\geq 0")
        elif sg == "≤0":
            con_lines.append(f"\\quad {nm} \\leq 0")

    con_body = " \\\\\n".join(con_lines)

    return (
        f"$${sense_label}\\; Z = {obj_expr}$$\n"
        f"$$\\begin{{cases}}\n{con_body}\n\\end{{cases}}$$"
    )


def _standardization_html(engine, mode: str) -> str:
    """Render các bước chuẩn hóa dưới dạng LaTeX đẹp theo thứ tự: Biến -> Ràng buộc -> Mục tiêu."""
    prob = engine.problem
    n = len(prob.obj_coeffs)
    parts = []

    # ── Bước 1: Thay thế biến không chuẩn ────────────────────────────────
    sub_notes = []
    for i, sg in enumerate(prob.var_signs):
        idx = f"{{{i+1}}}"
        nm  = f"x_{idx}"
        if sg == "≤0":
            y_nm = f"y_{idx}"
            sub_notes.append(f"$\\quad {nm} \\leq 0$: " + locales.t("html_var_neg", y_nm=y_nm, nm=nm))
        elif sg == "tự do":
            a_nm = f"a_{idx}"
            b_nm = f"b_{idx}"
            sub_notes.append(
                f"$\\quad {nm}$ " + locales.t("html_var_free", nm=nm, a_nm=a_nm, b_nm=b_nm)
            )
            
    if sub_notes:
        parts.append(f"<p>{locales.t('html_std_step1_sub')}</p>")
        for note in sub_notes:
            parts.append(f"<p>{note}</p>")
    else:
        parts.append(f"<p>{locales.t('html_std_step1_ok')}</p>")

    # ── Bước 2: Chuẩn hóa ràng buộc ──────────────────────────────────────
    parts.append(f"<p>{locales.t('html_std_step2')}</p>")

    std_names_list = getattr(engine, "std_names", None)
    all_names_list = getattr(engine, "all_names", None)

    def lhs_tex(row_coeffs_std):
        ps = []
        for j, c in enumerate(row_coeffs_std):
            if c == 0:
                continue
            abs_c = abs(c)
            sign = "+" if c > 0 else "-"
            nm_tex = _tex_var(std_names_list[j]) if std_names_list and j < len(std_names_list) else f"x_{{{j+1}}}"
            body = f"\\,{nm_tex}" if abs_c == 1 else f"\\,{_frac(abs_c, mode)}{nm_tex}"
            ps.append(f"{sign}{body}")
        return " ".join(ps).lstrip("+").strip() or "0"

    # Xây dựng bảng từ ràng buộc GỐC (prob.constraints), map sang std_constraints.
    # Ràng buộc "=" đã được tách thành 2 dòng ≤ trong engine, mỗi dòng có 1 biến bù.
    table_rows = []
    w_count = 0          # đếm biến bù (w1, w2, ...) theo thứ tự trong std_constraints
    std_row_idx = 0      # con trỏ vào engine.std_constraints

    for orig_i, cons in enumerate(prob.constraints):
        orig_sense = cons["sense"]
        # Tính lhs gốc (sau khi thay thế biến nếu có) từ std_constraints
        if orig_sense == "=":
            # Ràng buộc = → 2 dòng std liên tiếp: row_a (≤ b) và row_b (≤ -b)
            row_a  = engine.std_constraints[std_row_idx]
            rhs_a  = engine.std_rhs[std_row_idx]
            std_row_idx += 1
            row_b  = engine.std_constraints[std_row_idx]
            rhs_b  = engine.std_rhs[std_row_idx]
            std_row_idx += 1

            w_count += 1; slack_a = f"w_{{{w_count}}}"
            w_count += 1; slack_b = f"w_{{{w_count}}}"

            lhs_a = lhs_tex(row_a)
            lhs_b = lhs_tex(row_b)
            rhs_a_tex = _frac(rhs_a, mode)
            rhs_b_tex = _frac(rhs_b, mode)

            # Biểu diễn dạng gốc trước khi thay thế biến
            orig_lhs = lhs_tex([Fraction(c) for c in cons["coeffs"]] + [Fraction(0)] * (len(row_a) - len(cons["coeffs"])))
            orig_rhs = _frac(Fraction(cons["rhs"]), mode)

            sub_rows = (
                f"<tr>"
                f"<td style='white-space:nowrap' rowspan='2'><b>RB {orig_i+1}</b></td>"
                f"<td style='white-space:nowrap' rowspan='2'>${orig_lhs} = {orig_rhs}$</td>"
                f"<td style='white-space:nowrap;color:#0F766E'>$\\Rightarrow\\;{lhs_a} + {slack_a} = {rhs_a_tex}$</td>"
                f"<td style='color:#475569;font-size:0.88rem'>{locales.t('html_eq_split_a', i=orig_i+1, w=slack_a)}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='white-space:nowrap;color:#0F766E'>$\\Rightarrow\\;{lhs_b} + {slack_b} = {rhs_b_tex}$</td>"
                f"<td style='color:#475569;font-size:0.88rem'>{locales.t('html_eq_split_b', i=orig_i+1, w=slack_b)}</td>"
                f"</tr>"
            )
            table_rows.append(sub_rows)
        else:
            std_row = engine.std_constraints[std_row_idx]
            rhs_val = engine.std_rhs[std_row_idx]
            std_row_idx += 1

            lhs_str = lhs_tex(std_row)
            rhs_tex = _frac(rhs_val, mode)
            orig_lhs = lhs_tex([Fraction(c) for c in cons["coeffs"]] + [Fraction(0)] * (len(std_row) - len(cons["coeffs"])))
            orig_rhs = _frac(Fraction(cons["rhs"]), mode)

            w_count += 1
            slack_nm = f"w_{{{w_count}}}"
            if orig_sense == "≤":
                orig_rb = f"${orig_lhs} \\leq {orig_rhs}$"
                std_rb  = f"${lhs_str} + {slack_nm} = {rhs_tex}$"
                note    = locales.t("html_add_slack") + f" $+{slack_nm}$"
            else:  # ≥
                orig_rb = f"${orig_lhs} \\geq {orig_rhs}$"
                std_rb  = f"${lhs_str} + {slack_nm} = {rhs_tex}$"
                note    = locales.t("html_neg_to_leq") + f" $+{slack_nm}$"

            table_rows.append(
                f"<tr>"
                f"<td style='white-space:nowrap'><b>RB {orig_i+1}</b></td>"
                f"<td style='white-space:nowrap'>{orig_rb}</td>"
                f"<td style='white-space:nowrap;color:#0F766E'>$\\Rightarrow$&nbsp;{std_rb}</td>"
                f"<td style='color:#475569;font-size:0.88rem'>{note}</td>"
                f"</tr>"
            )

    parts.append(
        "<table style='border-collapse:collapse;width:100%;margin:8px 0 16px'>"
        "<thead><tr style='background:#EFF6FF'>"
        "<th style='padding:6px 12px;border:1px solid #CBD5E1;text-align:left'>RB</th>"
        f"<th style='padding:6px 12px;border:1px solid #CBD5E1'>{locales.t('html_orig_form')}</th>"
        f"<th style='padding:6px 12px;border:1px solid #CBD5E1'>{locales.t('html_std_form')}</th>"
        f"<th style='padding:6px 12px;border:1px solid #CBD5E1'>{locales.t('html_note')}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody>"
        "</table>"
    )

    # ── Bước 3: Hàm mục tiêu ─────────────────────────────────────────────
    parts.append(f"<p>{locales.t('html_std_step3')}</p>")

    def get_replaced_terms(coeffs, multiplier=1):
        """Tạo danh sách (hệ số, tên biến) sau khi tính toán cả phép thay thế a_i, b_i, y_i"""
        terms = []
        for i, c in enumerate(coeffs):
            if c == 0: continue
            c_mult = c * multiplier
            sg = prob.var_signs[i]
            idx = i + 1
            if sg == "≤0":
                terms.append((-c_mult, f"y_{{{idx}}}"))
            elif sg == "tự do":
                terms.append((c_mult, f"a_{{{idx}}}"))
                terms.append((-c_mult, f"b_{{{idx}}}"))
            else:
                terms.append((c_mult, f"x_{{{idx}}}"))
        return terms

    def format_terms(terms):
        """Chuyển đổi danh sách tuples (hệ số, tên biến) thành biểu thức LaTeX"""
        ps = []
        for c, nm in terms:
            if c == 0: continue
            abs_c = abs(c)
            sign = "+" if c > 0 else "-"
            tex_nm = _tex_var(nm)
            body = f"\\,{tex_nm}" if abs_c == 1 else f"\\,{_frac(abs_c, mode)}{tex_nm}"
            ps.append(f"{sign}{body}")
        return " ".join(ps).lstrip("+").strip() or "0"

    # Lấy biểu thức gốc ban đầu (tất cả là x)
    orig_terms = [(c, f"x_{{{i+1}}}") for i, c in enumerate(prob.obj_coeffs) if c != 0]
    orig_expr = format_terms(orig_terms)

    if prob.objective_sense == "max":
        parts.append(f"<p>{locales.t('html_obj_orig')} $$\\max Z = {orig_expr}$$</p>")
        
        # Nếu có thay thế biến ở Bước 1, in ra hàm mục tiêu sau khi thế
        if sub_notes:
            replaced_expr = format_terms(get_replaced_terms(prob.obj_coeffs, 1))
            parts.append(f"<p>{locales.t('html_obj_sub')} $$\\max Z = {replaced_expr}$$</p>")
            
        # Biểu thức dạng chuẩn (min) - nhân hệ số với -1
        min_expr = format_terms(get_replaced_terms(prob.obj_coeffs, -1))
        parts.append(f"<p>{locales.t('html_max_to_min')}</p>")
        parts.append(f"<p>$$\\min Z' = -\\max Z = {min_expr}$$</p>")
    else:
        parts.append(f"<p>{locales.t('html_obj_orig')} $$\\min Z = {orig_expr}$$</p>")
        
        # Nếu có thay thế biến ở Bước 1, in ra hàm mục tiêu sau khi thế
        if sub_notes:
            replaced_expr = format_terms(get_replaced_terms(prob.obj_coeffs, 1))
            parts.append(f"<p>{locales.t('html_obj_sub')} $$\\min Z = {replaced_expr}$$</p>")

    # ── Bảng biến chuẩn hóa cuối ──────────────────────────────────────────
    if std_names_list:
        std_tex = ",\\;".join(_tex_var(nm) for nm in std_names_list)
        parts.append(f"<p style='margin-top:20px'>{locales.t('html_std_vars')} $\\quad {std_tex}$</p>")

    raw_lines = getattr(engine, "standardization_lines", [])
    if raw_lines:
        parts.append("<details style='margin-top:8px'>"
                     f"<summary style='color:#64748B;font-size:0.87rem'>{locales.t('html_log_detail')}</summary>")
        for ln in raw_lines:
            if not ln.strip():
                parts.append("<br>")
            else:
                safe = ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(f"<p class='std-line'>{safe}</p>")
        parts.append("</details>")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Kết luận cuối
# ---------------------------------------------------------------------------

def _conclusion_html(report: SolveReport, engine, mode: str) -> str:
    parts: List[str] = []
    status = report.status
    is_max = engine.problem.objective_sense == "max"

    if status == "infeasible":
        has_aux = bool(getattr(engine, "need_aux_phase1", False))
        z_val = "$z_{\\max} = -\\infty$" if is_max else "$z_{\\min} = +\\infty$"
        if has_aux:
            reason = locales.t("html_infeasible_aux", z_val=z_val)
        else:
            art_names = [engine.all_names[a] for a in engine.artificial_vars] if engine.artificial_vars else []
            art_str = ", ".join(f"${nm}$" for nm in art_names) if art_names else locales.t("std_add_slack")
            reason = locales.t("html_infeasible_art", arts=art_str, z_val=z_val)
        parts.append(f"<div class='conclusion warn-box'><h3>{locales.t('html_concl_infeasible')}</h3>"
                     f"<p>{reason}</p></div>")
        return "".join(parts)
    if status == "unbounded":
        z_val = "$z_{\\max} = +\\infty$" if is_max else "$z_{\\min} = -\\infty$"
        parts.append(f"<div class='conclusion warn-box'><h3>{locales.t('html_concl_unbounded')}</h3>"
                     f"<p>{locales.t('html_unbounded_concl', z_val=z_val)}</p></div>")
        return "".join(parts)
    if status == "cycle":
        rule = "Dantzig" if report.dantzig.steps and report.dantzig.steps[0].method == "dantzig" else "Bland"
        if rule == "Dantzig" and report.bland is not None and report.bland.status == "cycle":
            parts.append(f"<div class='conclusion warn-box'><h3>{locales.t('html_concl_cycle')}</h3>"
                         f"<p>{locales.t('html_cycle_both')}</p></div>")
        elif rule == "Dantzig":
            parts.append(f"<div class='conclusion warn-box'><h3>{locales.t('html_concl_cycle')}</h3>"
                         f"<p>{locales.t('html_cycle_dantzig')}</p></div>")
        else:
            parts.append(f"<div class='conclusion warn-box'><h3>{locales.t('html_concl_cycle')}</h3>"
                         f"<p>{locales.t('html_cycle_bland')}</p></div>")
        return "".join(parts)

    # Optimal
    obj_std  = report.objective_std  or Fraction(0)
    obj_orig = report.objective_orig or Fraction(0)
    method_label = "Dantzig" if report.used_method == "dantzig" else "Bland"

    parts.append(f"<div class='conclusion success-box'>")
    parts.append(f"<h3>{locales.t('html_concl_optimal', method=method_label)}</h3>")

    # Giá trị mục tiêu
    if is_max:
        parts.append(
            f"<p>$z^* = \\max Z = -(\\min Z') = -({_frac(obj_std, mode)}) = {_frac(obj_orig, mode)}$</p>"
        )
    else:
        parts.append(f"<p>$z^* = \\min Z = {_frac(obj_orig, mode)}$</p>")

    # Nghiệm
    if report.multiple_optimal and report.multiple_optimal_vars:
        parts.append(f"<p class='warn'>{locales.t('html_multiple_opt')}</p>")
        free_idx = report.multiple_optimal_vars[0]
        snap = (report.phase2_trace.final_snapshot
                if report.phase2_trace and report.phase2_trace.final_snapshot
                else report.dantzig.final_snapshot)
        if snap:
            param = _tex_var(snap.all_names[free_idx])
            parts.append(f"<p>{locales.t('html_free_param')} ${param} \\geq 0$</p>")
            parts.append(f"<p>{locales.t('html_general_sol')}</p><ul>")
            bp = {b: i for i, b in enumerate(snap.basis)}
            for orig_idx, mapping in enumerate(engine.variable_mapping):
                const = Fraction(0)
                terms = []
                for si, mc in mapping:
                    if si in bp:
                        r = bp[si]
                        const += mc * snap.rhs[r]
                        coef_fv = snap.rows[r].get(free_idx, Fraction(0))
                        if coef_fv != 0:
                            terms.append((mc * coef_fv, snap.all_names[free_idx]))
                    elif si == free_idx:
                        terms.append((mc, snap.all_names[free_idx]))
                rhs_parts = [_frac(const, mode)] if const != 0 or not terms else []
                for cf, nm in terms:
                    t = _term(cf, nm, mode)
                    rhs_parts.append(t)
                rhs_str = " ".join(rhs_parts).lstrip("+").strip() or "0"
                parts.append(f"<li>$x_{{{orig_idx+1}}} = {rhs_str}$</li>")
            parts.append("</ul>")
    else:
        parts.append(f"<p>{locales.t('html_optimal_sol')}</p><ul>")
        for i in range(len(engine.problem.var_signs)):
            val = report.solution_orig.get(i, Fraction(0))
            parts.append(f"<li>$x_{{{i+1}}} = {_frac(val, mode)}$</li>")
        parts.append("</ul>")

    # Suy biến
    d = (report.dantzig.degenerate_steps or 0) + \
        ((report.bland.degenerate_steps if report.bland else 0) or 0)
    if d:
        parts.append(f"<p class='warn'>{locales.t('html_degenerate_count', d=d)}</p>")

    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# CSS + HTML template
# ---------------------------------------------------------------------------

_CSS = """
body {
    font-family: 'Segoe UI', 'Arial', sans-serif;
    background: #F8FAFC;
    color: #1E293B;
    margin: 0;
    padding: 0;
}
.page-header {
    background: #1E3A5F;
    color: #fff;
    padding: 24px 40px 18px;
}
.page-header h1 { margin: 0 0 4px; font-size: 1.45rem; }
.page-header p  { margin: 0; color: #B5D4F4; font-size: 0.9rem; }

.container { max-width: 1100px; margin: 0 auto; padding: 28px 32px 60px; }

h2 { color: #1E3A5F; border-bottom: 2px solid #BFDBFE; padding-bottom: 6px; margin-top: 36px; }
h3 { color: #185FA5; margin-top: 24px; }
h4 { color: #334155; margin: 20px 0 6px; font-size: 1rem; }

/* Bảng từ vựng */
.dict-table-wrap { overflow-x: auto; margin: 8px 0 16px; }
.dict-table {
    border-collapse: collapse;
    font-size: 0.95rem;
    min-width: 360px;
}
.dict-table th, .dict-table td {
    border: 1px solid #CBD5E1;
    padding: 7px 14px;
    text-align: center;
    white-space: nowrap;
}
.dict-table th { background: #EFF6FF; font-weight: 600; color: #1E3A5F; }
.dict-table .row-label { background: #F1F5F9; font-weight: 600; text-align: left; }
.dict-table .rhs-cell  { background: #F8FAFC; border-right: 2px solid #94A3B8; }
.dict-table .rhs-col   { background: #EFF6FF; border-right: 2px solid #94A3B8; }
.dict-table .obj-row td { background: #EEF2FF; }

/* Highlight xoay */
.dict-table .pivot-col      { background: #FEF9C3 !important; }
.dict-table .pivot-col-head { background: #FDE68A !important; }
.dict-table .pivot-row      { background: #E0F2FE !important; }
.dict-table .pivot-cell     { background: #BFDBFE !important; font-weight: 700; }

/* Step note */
.step-note {
    background: #F0FDF4;
    border-left: 4px solid #22C55E;
    padding: 10px 18px;
    margin: 8px 0 18px;
    border-radius: 0 6px 6px 0;
    font-size: 0.93rem;
}
.step-note p  { margin: 4px 0; }
.step-note ul { margin: 4px 0 4px 18px; }
.note-rule    { font-size: 1rem; margin-bottom: 6px !important; color: #185FA5; }

/* Ratio table */
.ratio-table {
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 0.88rem;
}
.ratio-table th, .ratio-table td {
    border: 1px solid #CBD5E1;
    padding: 5px 12px;
    text-align: center;
}
.ratio-table th { background: #F1F5F9; }

/* Status */
.note    { color: #0F766E; }
.warn    { color: #B45309; font-weight: 600; }
.success { color: #15803D; font-weight: 600; }

/* Conclusion boxes */
.conclusion { border-radius: 8px; padding: 20px 28px; margin-top: 32px; }
.success-box { background: #F0FDF4; border: 1.5px solid #86EFAC; }
.warn-box    { background: #FFFBEB; border: 1.5px solid #FCD34D; }
.conclusion h3 { margin-top: 0; }
.conclusion ul { margin: 8px 0 8px 20px; line-height: 1.9; }

/* Std lines */
.std-line { margin: 2px 0; font-family: 'Consolas', monospace; font-size: 0.88rem; color: #334155; }

/* Section divider */
.phase-section {
    border: 1.5px solid #BFDBFE;
    border-radius: 8px;
    padding: 18px 24px;
    margin: 24px 0;
    background: #fff;
}
.phase-section h2 { margin-top: 0; }

/* Collapsible */
details { margin: 12px 0; }
summary {
    cursor: pointer;
    font-weight: 600;
    color: #185FA5;
    padding: 8px 0;
    user-select: none;
}
summary:hover { color: #1E3A5F; }

/* Print */
@media print {
    .page-header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    details { display: block; }
    details[open] summary ~ * { display: block !important; }
}
"""

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {{
          delimiters: [
            {{left:'$$', right:'$$', display:true}},
            {{left:'$',  right:'$',  display:false}}
          ]
        }});"></script>
<style>
{css}
</style>
</head>
<body>
<div class="page-header">
  <h1>{page_h1}</h1>
  <p>{page_sub}</p>
</div>
<div class="container">
{body}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Hàm chính
# ---------------------------------------------------------------------------

def export_report_html(report: SolveReport, mode: str = "Phân số") -> str:
    """
    Tạo file HTML đầy đủ cho lời giải và trả về đường dẫn file tạm.
    Gọi webbrowser.open(f"file:///{path}") để mở trong trình duyệt.
    """
    engine = report.engine
    body_parts: List[str] = []

    # 1. Bài toán gốc
    body_parts.append(f"<h2>{locales.t('html_orig_problem')}</h2>")
    body_parts.append(_problem_html(engine, mode))

    # 2. Chuẩn hóa (collapsible)
    body_parts.append(f"<details><summary>{locales.t('html_std_detail')}</summary>")
    body_parts.append(_standardization_html(engine, mode))
    body_parts.append("</details>")

    # 3. Pha 1 (nếu có)
    has_aux = bool(getattr(engine, "need_aux_phase1", False))
    has_art = bool(engine.artificial_vars)

    if has_aux or has_art:
        body_parts.append("<div class='phase-section'>")
        body_parts.append(f"<h2>{locales.t('html_phase1')}</h2>")
        if has_aux:
            body_parts.append(
                f"<p class='note'>{locales.t('html_phase1_aux_note')}</p>"
            )
        elif has_art:
            art_names = [engine.all_names[a] for a in engine.artificial_vars]
            art_str = ", ".join(f"${nm}$" for nm in art_names)
            body_parts.append(
                f"<p class='note'>{locales.t('html_phase1_art_note', arts=art_str, arts_sum='+'.join(art_names))}</p>"
            )
        body_parts.append(_render_trace_html(report.dantzig, mode))
        if report.phase1_bland is not None and report.phase1_bland is not report.dantzig:
            body_parts.append(f"<h3>{locales.t('html_bland_after_p1')}</h3>")
            body_parts.append(_render_trace_html(report.phase1_bland, mode))
        body_parts.append("</div>")

        if report.status == "infeasible":
            body_parts.append(_conclusion_html(report, engine, mode))
            return _write_html(body_parts)

        if report.phase2_trace:
            body_parts.append("<div class='phase-section'>")
            body_parts.append(f"<h2>{locales.t('html_phase2')}</h2>")
            if has_aux:
                body_parts.append(
                    f"<p class='note'>{locales.t('html_phase2_aux_note')}</p>"
                )
            elif has_art:
                body_parts.append(
                    f"<p class='note'>{locales.t('html_phase2_art_note')}</p>"
                )
            body_parts.append(_render_trace_html(report.phase2_trace, mode))
            body_parts.append("</div>")
    else:
        body_parts.append("<div class='phase-section'>")
        body_parts.append(f"<h2>{locales.t('html_solve')}</h2>")
        body_parts.append(
            f"<p class='note'>{locales.t('html_no_phase1_note')}</p>"
        )
        body_parts.append(_render_trace_html(report.dantzig, mode))
        if report.bland is not None and report.bland is not report.dantzig:
            body_parts.append(f"<h3>{locales.t('html_bland_after')}</h3>")
            body_parts.append(_render_trace_html(report.bland, mode))
        body_parts.append("</div>")

    # 4. Kết luận
    body_parts.append(_conclusion_html(report, engine, mode))

    return _write_html(body_parts)


def _write_html(body_parts: List[str]) -> str:
    """Ghép body, điền vào template, ghi ra file tạm, trả về path."""
    body = "\n".join(body_parts)
    html = _HTML_TEMPLATE.format(
        css=_CSS, body=body,
        lang="en" if locales.current_lang == "en" else "vi",
        page_title=locales.t("html_page_title"),
        page_h1=locales.t("html_page_h1"),
        page_sub=locales.t("html_page_sub"),
    )
    fd, path = tempfile.mkstemp(suffix=".html", prefix="simplex_solution_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    return path