from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List

SENSES = ["≤", "≥", "="]
VAR_SIGNS = ["≥0", "≤0", "tự do"]


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
    widths: Dict[int, int] = {}
    for j, name in enumerate(names):
        pieces = [term_str(coeffs.get(j, Fraction(0)), name, mode)]
        widths[j] = max(8, len(pieces[0]) + 2)
    parts = [f"{label} = {fmt_num(const, mode)}"]
    for j, name in enumerate(names):
        cell = term_str(coeffs.get(j, Fraction(0)), name, mode)
        parts.append(cell.ljust(widths[j]))
    return " ".join(parts).rstrip()
