from __future__ import annotations

import os
import tempfile
import webbrowser
from fractions import Fraction
from typing import List, Optional

from models import Snapshot, PivotStep, SolveTrace, SolveReport
from utils import fmt_num


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

def _snapshot_table(
    snapshot: Snapshot,
    mode: str,
    entering_name: Optional[str] = None,
    pivot_row: Optional[int] = None,
) -> str:
    """Tạo <table> HTML cho một snapshot (bảng từ vựng đơn hình)."""
    names = snapshot.all_names
    n = len(names)

    # Header: tên biến phi cơ sở (hiển thị tên biến thay vì chỉ số)
    header_cells = ["<th class='row-label'></th>", "<th class='rhs-col'>Hằng số</th>"]
    for j, nm in enumerate(names):
        css = "pivot-col-head" if nm == entering_name else ""
        header_cells.append(f"<th class='{css}'>${_tex_var(nm)}$</th>")
    thead = f"<thead><tr>{''.join(header_cells)}</tr></thead>"

    rows_html: List[str] = []

    # Hàng mục tiêu
    obj_cells = [f"<td class='row-label'>$\\mathbf{{{_tex_var(snapshot.objective_label)}}}$</td>"]
    obj_cells.append(f"<td class='rhs-cell'>$= {_frac(snapshot.obj_const, mode)}$</td>")
    for j, nm in enumerate(names):
        c = snapshot.obj.get(j, Fraction(0))
        css = "pivot-col" if nm == entering_name else ""
        obj_cells.append(f"<td class='{css}'>${_frac(c, mode)}$</td>" if c != 0
                         else f"<td class='{css}'>$0$</td>")
    rows_html.append(f"<tr class='obj-row'>{''.join(obj_cells)}</tr>")

    # Hàng cơ sở
    for i, b in enumerate(snapshot.basis):
        b_name = names[b]
        is_pivot_row = (pivot_row is not None and i == pivot_row)
        row_css = "pivot-row" if is_pivot_row else ""
        cells = [f"<td class='row-label'>$\\mathbf{{{_tex_var(b_name)}}}$</td>"]
        cells.append(f"<td class='rhs-cell'>$= {_frac(snapshot.rhs[i], mode)}$</td>")
        for j, nm in enumerate(names):
            c = snapshot.rows[i].get(j, Fraction(0))
            cell_css = ""
            if nm == entering_name and is_pivot_row:
                cell_css = "pivot-cell"
            elif nm == entering_name:
                cell_css = "pivot-col"
            elif is_pivot_row:
                cell_css = "pivot-row"
            cells.append(f"<td class='{cell_css}'>${_frac(c, mode)}$</td>" if c != 0
                         else f"<td class='{cell_css}'>$0$</td>")
        rows_html.append(f"<tr class='{row_css}'>{''.join(cells)}</tr>")

    return f"""<div class="dict-table-wrap">
<table class="dict-table">
{thead}
<tbody>{''.join(rows_html)}</tbody>
</table>
</div>"""

def _step_note_html(step: PivotStep, snapshot: Snapshot, mode: str) -> str:
    names = snapshot.all_names
    enter = _tex_var(names[step.entering]) if step.entering is not None else "?"
    leave = _tex_var(names[step.leaving_var]) if step.leaving_var is not None else "?"
    rule = "Dantzig" if step.method == "dantzig" else "Bland"
    lines: List[str] = []

    if step.status == "phase1_aux_pivot":
        lines.append(f"<p class='note-rule'>⚙️ <b>Quy tắc Dantzig — Pha 1 (biến phụ)</b></p>")
        lines.append(f"<p>Biến phụ $x_0$ đóng vai trò biến vào. "
                     f"Biến ra là hàng có $b_i$ âm nhỏ nhất.</p>")
        if step.ratios:
            lines.append("<ul>")
            for ri, bval, bi in step.ratios:
                lines.append(f"<li>${_tex_var(names[bi])}$: $b = {_frac(bval, mode)}$</li>")
            lines.append("</ul>")
        lines.append(f"<p>$\\Rightarrow$ Biến vào: ${enter}$ &nbsp;|&nbsp; Biến ra: ${leave}$</p>")
        if step.pivot_value is not None:
            lines.append(f"<p>Phần tử xoay: $a_{{{leave},{enter}}} = {_frac(step.pivot_value, mode)}$</p>")
        if step.degenerate:
            lines.append("<p class='warn'>⚠️ Bước suy biến ($\\theta = 0$).</p>")
        return "".join(lines)

    lines.append(f"<p class='note-rule'>⚙️ <b>Quy tắc {rule}</b></p>")
    if step.entering is not None:
        coeff = snapshot.obj.get(step.entering, Fraction(0))
        if step.method == "dantzig":
            lines.append(f"<p>Chọn <b>${enter}$</b> vì có hệ số nhỏ nhất "
                         f"$= {_frac(coeff, mode)}$ trong hàng mục tiêu.</p>")
        else:
            lines.append(f"<p>Bland: chọn <b>${enter}$</b> (chỉ số nhỏ nhất trong các biến cải thiện).</p>")
        lines.append(f"<p>$\\Rightarrow$ Biến vào: ${enter}$</p>")

    if step.ratios:
        lines.append(f"<p>Bảng tỉ số $\\theta$ tại cột ${enter}$:</p>")
        lines.append("<table class='ratio-table'><tr><th>Hàng</th><th>$b_i$</th>"
                     "<th>$a_{{i,enter}}$</th><th>$\\theta = b_i / (-a_{{i,enter}})$</th></tr>")
        for ri, theta, bi in step.ratios:
            a_val = snapshot.rows[ri].get(step.entering, Fraction(0)) if step.entering is not None else Fraction(0)
            lines.append(f"<tr><td>${_tex_var(names[bi])}$</td>"
                         f"<td>${_frac(snapshot.rhs[ri], mode)}$</td>"
                         f"<td>${_frac(a_val, mode)}$</td>"
                         f"<td>${_frac(theta, mode)}$</td></tr>")
        lines.append("</table>")
        lines.append(f"<p>$\\Rightarrow$ Biến ra: ${leave}$</p>")

    if step.pivot_value is not None:
        lines.append(f"<p>Phần tử xoay: "
                     f"$a_{{{leave},{enter}}} = {_frac(step.pivot_value, mode)}$</p>")
    if step.degenerate:
        lines.append("<p class='warn'>⚠️ Bước suy biến ($\\theta = 0$).</p>")
    return "".join(lines)

def _render_trace_html(trace: SolveTrace, mode: str) -> str:
    parts: List[str] = []
    if not trace.steps:
        if trace.final_snapshot:
            parts.append("<p class='note'>Từ vựng ban đầu (không cần xoay):</p>")
            parts.append(_snapshot_table(trace.final_snapshot, mode))
        return "".join(parts)

    for step in trace.steps:
        title = "Từ vựng ban đầu" if step.iteration == 1 else f"Bước {step.iteration} — trước xoay"
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
            parts.append(f"<h4>Sau xoay — Bước {step.iteration}</h4>")
            parts.append(_snapshot_table(step.after, mode))

    # Trạng thái kết thúc
    if trace.status == "optimal":
        parts.append("<p class='success'>✅ Tất cả hệ số cải thiện ≥ 0 → Tối ưu.</p>")
    elif trace.status == "unbounded":
        parts.append("<p class='warn'>⚠️ Bài toán không giới nội (unbounded).</p>")
    elif trace.status == "cycle":
        rule = "Dantzig" if trace.steps and trace.steps[0].method == "dantzig" else "Bland"
        if rule == "Dantzig":
            parts.append("<p class='warn'>🔄 Dantzig phát hiện xoay vòng — hãy thử Bland.</p>")
        else:
            parts.append("<p class='warn'>🔄 Bland phát hiện xoay vòng.</p>")

    return "".join(parts)

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
    """Render các bước chuẩn hóa dưới dạng LaTeX đẹp."""
    prob = engine.problem
    n = len(prob.obj_coeffs)
    names_orig = [f"x_{{{i+1}}}" for i in range(n)]

    def expr_std(coeffs):
        """Build LaTeX expression từ list/dict hệ số."""
        parts = []
        items = list(enumerate(coeffs)) if not isinstance(coeffs, dict) else coeffs.items()
        for j, c in items:
            if c == 0:
                continue
            abs_c = abs(c)
            sign = "+" if c > 0 else "-"
            nm = engine.all_names[j] if hasattr(engine, "all_names") and j < len(engine.all_names) else f"x_{{{j+1}}}"
            tex_nm = _tex_var(nm)
            if abs_c == 1:
                body = f"\\,{tex_nm}"
            else:
                body = f"\\,{_frac(abs_c, mode)}{tex_nm}"
            parts.append(f"{sign}{body}")
        if not parts:
            return "0"
        return " ".join(parts).lstrip("+").strip()

    parts = []

    # ── Bước 1: Chuyển max → min nếu cần ──────────────────────────────────
    if prob.objective_sense == "max":
        obj_orig_expr = expr_std(prob.obj_coeffs)
        neg_coeffs = [-c for c in prob.obj_coeffs]
        obj_min_expr = expr_std(neg_coeffs)
        parts.append("<p>📌 <b>Bước 1: Chuyển bài toán max → min</b></p>")
        parts.append(f"<p>$$\\max Z = {obj_orig_expr} \\;\\equiv\\; \\min(-Z) = {obj_min_expr}$$</p>")
    else:
        parts.append("<p>📌 <b>Bước 1: Dạng mục tiêu</b></p>")
        obj_expr = expr_std(prob.obj_coeffs)
        parts.append(f"<p>$$\\min Z = {obj_expr}$$</p>")

    # ── Bước 2: Xử lý biến dấu âm / tự do ────────────────────────────────
    sub_notes = []
    for i, sg in enumerate(prob.var_signs):
        nm = f"x_{{{i+1}}}"
        if sg == "≤0":
            sub_notes.append(f"$\\quad {nm} \\leq 0$: đặt ${nm}' = -{nm} \\geq 0$")
        elif sg == "tự do":
            sub_notes.append(f"$\\quad {nm}$ tự do: đặt ${nm} = {nm}^+ - {nm}^-$, "
                             f"$\\;{nm}^+,\\, {nm}^- \\geq 0$")
    if sub_notes:
        parts.append("<p>📌 <b>Bước 2: Thay thế biến không chuẩn</b></p>")
        for note in sub_notes:
            parts.append(f"<p>{note}</p>")
    else:
        parts.append("<p>📌 <b>Bước 2: Biến số</b> — tất cả $x_i \\geq 0$, không cần thay thế.</p>")

    # ── Bước 3: Chuẩn hóa ràng buộc (thêm biến bù / nhân tạo) ────────────
    parts.append("<p>📌 <b>Bước 3: Chuẩn hóa ràng buộc</b></p>")
    con_items = []
    # Lấy tên biến chuẩn từ engine nếu có
    std_names = getattr(engine, "all_names", None)

    for i, cons in enumerate(prob.constraints):
        s = cons["sense"]
        lhs_coeffs = cons["coeffs"]
        rhs_val = Fraction(cons["rhs"])

        # Build LHS từ biến gốc
        lhs_parts = []
        for j, c in enumerate(lhs_coeffs):
            if c == 0:
                continue
            abs_c = abs(c)
            sign = "+" if c > 0 else "-"
            nm = names_orig[j]
            body = f"\\,{nm}" if abs_c == 1 else f"\\,{_frac(abs_c, mode)}{nm}"
            lhs_parts.append(f"{sign}{body}")
        lhs_str = " ".join(lhs_parts).lstrip("+").strip() or "0"
        rhs_str = _frac(rhs_val, mode)
        s_tex = {"≤": "\\leq", "≥": "\\geq", "=": "="}.get(s, s)

        if s == "≤":
            # Thêm biến bù s_i
            slack_nm = f"s_{{{i+1}}}"
            std_lhs = f"{lhs_str} + {slack_nm}"
            note = f"(thêm biến bù $+{slack_nm}$)"
        elif s == "≥":
            # Trừ biến bù, thêm biến nhân tạo nếu cần
            slack_nm = f"s_{{{i+1}}}"
            art_nm   = f"a_{{{i+1}}}"
            std_lhs = f"{lhs_str} - {slack_nm} + {art_nm}"
            note = f"(trừ biến bù $-{slack_nm}$, thêm biến nhân tạo $+{art_nm}$)"
        else:  # =
            art_nm = f"a_{{{i+1}}}"
            std_lhs = f"{lhs_str} + {art_nm}"
            note = f"(thêm biến nhân tạo $+{art_nm}$)"

        # Nếu RHS âm, nhân -1 cả hai vế trước khi thêm biến
        if rhs_val < 0:
            note = "(nhân $-1$ cả hai vế, " + note.lstrip("(")
            rhs_str = _frac(-rhs_val, mode)
            # flip dấu ràng buộc
            std_lhs_orig = std_lhs
            std_lhs = f"\\text{{...}}"  # placeholder, đủ để reader hiểu

        con_items.append(
            f"<li>Ràng buộc {i+1}: $\\quad {lhs_str} {s_tex} {_frac(Fraction(cons['rhs']), mode)}$"
            f"<br>$\\Rightarrow\\quad {std_lhs} = {rhs_str}$ &nbsp; {note}</li>"
        )

    parts.append(f"<ul>{''.join(con_items)}</ul>")

    # ── Bảng biến chuẩn hóa cuối ──────────────────────────────────────────
    if std_names:
        std_tex = ",\\;".join(_tex_var(nm) for nm in std_names)
        parts.append(f"<p>Các biến trong bài toán chuẩn hóa: $\\quad {std_tex}$</p>")

    # Fallback: nếu engine có standardization_lines, show thêm ở cuối
    raw_lines = getattr(engine, "standardization_lines", [])
    if raw_lines:
        parts.append("<details style='margin-top:8px'>"
                     "<summary style='color:#64748B;font-size:0.87rem'>Xem log chi tiết (text thuần)</summary>")
        for ln in raw_lines:
            if not ln.strip():
                parts.append("<br>")
            else:
                safe = ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(f"<p class='std-line'>{safe}</p>")
        parts.append("</details>")

    return "".join(parts)

def _conclusion_html(report: SolveReport, engine, mode: str) -> str:
    from utils import fmt_num
    parts: List[str] = []

    status = report.status
    if status == "infeasible":
        parts.append("<div class='conclusion warn-box'><h3>KẾT LUẬN: Vô nghiệm</h3>"
                     "<p>Biến phụ $x_0$ còn trong cơ sở sau Pha 1 → Bài toán vô nghiệm.</p></div>")
        return "".join(parts)

    if status in ("unbounded",):
        parts.append("<div class='conclusion warn-box'><h3>KẾT LUẬN: Không giới nội</h3>"
                     "<p>Không tìm được nghiệm hữu hạn tối ưu.</p></div>")
        return "".join(parts)

    if status == "cycle":
        rule = "Dantzig" if report.dantzig.steps and report.dantzig.steps[0].method == "dantzig" else "Bland"
        if rule == "Dantzig":
            parts.append("<div class='conclusion warn-box'><h3>KẾT LUẬN: Xoay vòng</h3>"
                         "<p>Dantzig phát hiện xoay vòng — hãy thử Bland.</p></div>")
        else:
            parts.append("<div class='conclusion warn-box'><h3>KẾT LUẬN: Xoay vòng</h3>"
                         "<p>Bland phát hiện xoay vòng.</p></div>")
        return "".join(parts)

    # Optimal
    obj_std = report.objective_std or Fraction(0)
    obj_orig = report.objective_orig or Fraction(0)
    method_label = "Dantzig Simplex" if report.used_method == "dantzig" else "Bland's Rule"

    parts.append(f"<div class='conclusion success-box'>")
    parts.append(f"<h3>KẾT LUẬN: Tối ưu ({method_label})</h3>")

    if report.multiple_optimal and report.multiple_optimal_vars:
        parts.append("<p class='warn'>⚠️ Bài toán có <b>vô số nghiệm tối ưu</b>.</p>")
        free_idx = report.multiple_optimal_vars[0]
        snap = (report.phase2_trace.final_snapshot if report.phase2_trace and report.phase2_trace.final_snapshot
                else report.dantzig.final_snapshot)
        if snap:
            param = _tex_var(snap.all_names[free_idx])
            parts.append(f"<p>Tham số tự do: ${param} \\geq 0$</p>")
            parts.append(f"<p>$z^* = {_frac(snap.obj_const, mode)}$</p>")
            parts.append("<p>Nghiệm tổng quát:</p><ul>")
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
        parts.append(f"<p>$z^*$ (dạng chuẩn min) $= {_frac(obj_std, mode)}$</p>")
        parts.append(f"<p>Giá trị mục tiêu gốc $= {_frac(obj_orig, mode)}$</p>")
        parts.append("<p><b>Nghiệm tối ưu:</b></p><ul>")
        for i in range(len(engine.problem.var_signs)):
            val = report.solution_orig.get(i, Fraction(0))
            parts.append(f"<li>$x_{{{i+1}}} = {_frac(val, mode)}$</li>")
        parts.append("</ul>")

    # Suy biến
    d = (report.dantzig.degenerate_steps or 0) + \
        ((report.bland.degenerate_steps if report.bland else 0) or 0)
    if d:
        parts.append(f"<p class='warn'>ℹ️ Có {d} bước suy biến ($\\theta = 0$).</p>")

    parts.append("</div>")
    return "".join(parts)

def export_report_html(report: SolveReport, mode: str = "Phân số") -> str:
    """
    Tạo file HTML đầy đủ cho lời giải và trả về đường dẫn file tạm.
    Gọi webbrowser.open(f"file:///{path}") để mở trong trình duyệt.
    """
    engine = report.engine
    body_parts: List[str] = []

    # 1. Bài toán gốc
    body_parts.append("<h2>📋 Bài toán gốc</h2>")
    body_parts.append(_problem_html(engine, mode))

    # 2. Chuẩn hóa (collapsible)
    body_parts.append("<details><summary>⚙️ Chi tiết chuẩn hóa bài toán</summary>")
    body_parts.append(_standardization_html(engine, mode))
    body_parts.append("</details>")

    # 3. Pha 1 (nếu có)
    has_aux = bool(getattr(engine, "need_aux_phase1", False))
    has_art = bool(engine.artificial_vars)

    if has_aux or has_art:
        body_parts.append("<div class='phase-section'>")
        body_parts.append("<h2>🔧 Pha 1</h2>")
        if has_aux:
            body_parts.append("<p class='note'>Tồn tại $b_i &lt; 0$ → Giải pha 1 bằng biến phụ $x_0$.</p>")
        body_parts.append(_render_trace_html(report.dantzig, mode))
        if report.phase1_bland is not None and report.phase1_bland is not report.dantzig:
            body_parts.append("<h3>🔄 Bland (sau Dantzig xoay vòng ở Pha 1)</h3>")
            body_parts.append(_render_trace_html(report.phase1_bland, mode))
        body_parts.append("</div>")

        if report.status == "infeasible":
            body_parts.append(_conclusion_html(report, engine, mode))
            return _write_html(body_parts)

        if report.phase2_trace:
            body_parts.append("<div class='phase-section'>")
            body_parts.append("<h2>🎯 Pha 2</h2>")
            body_parts.append(_render_trace_html(report.phase2_trace, mode))
            body_parts.append("</div>")
    else:
        body_parts.append("<div class='phase-section'>")
        body_parts.append("<h2>🎯 Giải bài toán</h2>")
        body_parts.append("<p class='note'>$b_i \\geq 0$ với mọi $i$ → không cần Pha 1, giải trực tiếp.</p>")
        body_parts.append(_render_trace_html(report.dantzig, mode))
        if report.bland is not None and report.bland is not report.dantzig:
            body_parts.append("<h3>🔄 Bland (sau Dantzig xoay vòng)</h3>")
            body_parts.append(_render_trace_html(report.bland, mode))
        body_parts.append("</div>")

    # 4. Kết luận
    body_parts.append(_conclusion_html(report, engine, mode))

    return _write_html(body_parts)

def _write_html(body_parts: List[str]) -> str:
    """Ghép body, điền vào template, ghi ra file tạm, trả về path."""
    body = "\n".join(body_parts)
    html = _HTML_TEMPLATE.format(css=_CSS, body=body)
    fd, path = tempfile.mkstemp(suffix=".html", prefix="simplex_solution_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    return path
