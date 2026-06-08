from __future__ import annotations

import math
import itertools
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk

from utils import fmt_num, fr, sense_to_standard
from models import ProblemData
import locales

def _halfspace_feasible(x: float, y: float, z: float,
                        planes: List[Tuple[float, float, float, float, str]],
                        tol: float = 1e-7) -> bool:
    
    for a, b, c, d, sense in planes:
        lhs = a * x + b * y + c * z
        if sense == "≤" and lhs > d + tol:
            return False
        if sense == "≥" and lhs < d - tol:
            return False
        if sense == "=" and abs(lhs - d) > tol:
            return False
    return True


def _intersect_3planes(p1, p2, p3):
    (a1, b1, c1, d1, _) = p1
    (a2, b2, c2, d2, _) = p2
    (a3, b3, c3, d3, _) = p3
    det = (a1 * (b2 * c3 - b3 * c2)
           - b1 * (a2 * c3 - a3 * c2)
           + c1 * (a2 * b3 - a3 * b2))
    if abs(det) < 1e-12:
        return None
    x = ((d1 * (b2 * c3 - b3 * c2)
          - b1 * (d2 * c3 - d3 * c2)
          + c1 * (d2 * b3 - d3 * b2)) / det)
    y = ((a1 * (d2 * c3 - d3 * c2)
          - d1 * (a2 * c3 - a3 * c2)
          + c1 * (a2 * d3 - a3 * d2)) / det)
    z = ((a1 * (b2 * d3 - b3 * d2)
          - b1 * (a2 * d3 - a3 * d2)
          + d1 * (a2 * b3 - a3 * b2)) / det)
    return x, y, z


def _convex_hull_3d_simple(pts: List[Tuple[float, float, float]]):
    if len(pts) < 3:
        return []
    try:
        from scipy.spatial import ConvexHull
        import numpy as np
        arr = np.array(pts)
        hull = ConvexHull(arr)
        return [tuple(s) for s in hull.simplices]
    except Exception:
        pass

    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cz = sum(p[2] for p in pts) / len(pts)
    center = (cx, cy, cz)
    n = len(pts)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n))          
    pts_with_center = pts + [center]
    return faces, pts_with_center

class Viz3DMixin:

    def visualize_three_variable_problem(self) -> None:
        try:
            prob = self._collect_problem()
        except Exception as exc:
            messagebox.showerror(locales.t("viz_error"), str(exc))
            return

        if len(prob.obj_coeffs) != 3:
            messagebox.showinfo(
                locales.t("viz_error"),
                locales.t("viz_3d_err")
            )
            return

        try:
            import numpy as np
            import matplotlib
            matplotlib.use("TkAgg", force=True)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from mpl_toolkits.mplot3d import Axes3D          
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        except Exception as exc:
            messagebox.showerror(
                locales.t("viz_error"),
                f"{locales.t('viz_not_lib')}\n{exc}\n\n"
                "Hãy cài: pip install matplotlib numpy"
            )
            return

        planes = self._build_planes_3d(prob)
        vertices = self._feasible_vertices_3d(planes)
        vertices = self._dedup3(vertices)

        c1 = float(prob.obj_coeffs[0])
        c2 = float(prob.obj_coeffs[1])
        c3 = float(prob.obj_coeffs[2])
        maximize = prob.objective_sense == "max"
        vv = [(x, y, z, c1*x + c2*y + c3*z) for x, y, z in vertices]
        optimal = (max(vv, key=lambda t: t[3]) if maximize
                   else min(vv, key=lambda t: t[3])) if vv else None

        win = tk.Toplevel(self)
        win.title(locales.t("viz_3d_title"))
        win.geometry("1400x900")
        win.minsize(900, 600)
        try:
            win.state("zoomed")
        except Exception:
            try:
                win.attributes("-zoomed", True)
            except Exception:
                pass
        win.configure(bg=self._me["canvas_bg"])
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        outer = tk.Frame(win, bg=self._me["canvas_bg"])
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)

        from matplotlib.figure import Figure
        fig = Figure(figsize=(14, 9), dpi=100)
        fig.patch.set_facecolor(self._me["canvas_bg"])
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor(self._me["canvas_bg"])
        for pane in [ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane]:
            pane.fill = False
            pane.set_edgecolor("#334155")
        ax.tick_params(colors="#94a3b8", labelsize=8)
        ax.xaxis.label.set_color("#94a3b8")
        ax.yaxis.label.set_color("#94a3b8")
        ax.zaxis.label.set_color("#94a3b8")
        ax.set_xlabel("x₁", fontsize=11, labelpad=8)
        ax.set_ylabel("x₂", fontsize=11, labelpad=8)
        ax.set_zlabel("x₃", fontsize=11, labelpad=8)
        ax.set_title(
            "Miền chấp nhận được (3D) & điểm tối ưu",
            fontsize=13, fontweight="bold", color=self._me["fg"], pad=12
        )

        self._draw_3d_scene(ax, planes, vertices, vv, optimal, maximize, prob)

        canvas = FigureCanvasTkAgg(fig, master=outer)
        canvas.draw()
        w = canvas.get_tk_widget()
        w.configure(bg=self._me["canvas_bg"], highlightthickness=0)
        w.grid(row=0, column=0, sticky="nsew")

        self._build_info_panel_3d(outer, prob, vertices, vv, optimal, maximize)

        ctrl = tk.Frame(win, bg=self._me["header_bg"])
        ctrl.grid(row=1, column=0, sticky="ew")
        self._build_3d_controls(ctrl, ax, canvas, fig)

        win.focus_force()


    def _build_planes_3d(self, prob: ProblemData):
        planes = []
        for i, cons in enumerate(prob.constraints, start=1):
            a = float(fr(cons["coeffs"][0]))
            b = float(fr(cons["coeffs"][1]))
            c = float(fr(cons["coeffs"][2]))
            d = float(fr(cons["rhs"]))
            sense = sense_to_standard(cons["sense"])
            planes.append((a, b, c, d, sense, f"RB{i}"))

        signs = prob.var_signs
        # x1
        if signs[0] == "≥0":
            planes.append((1, 0, 0, 0, "≥", "x₁ ≥ 0"))
        elif signs[0] == "≤0":
            planes.append((1, 0, 0, 0, "≤", "x₁ ≤ 0"))
        # x2
        if signs[1] == "≥0":
            planes.append((0, 1, 0, 0, "≥", "x₂ ≥ 0"))
        elif signs[1] == "≤0":
            planes.append((0, 1, 0, 0, "≤", "x₂ ≤ 0"))
        # x3
        if len(signs) > 2:
            if signs[2] == "≥0":
                planes.append((0, 0, 1, 0, "≥", "x₃ ≥ 0"))
            elif signs[2] == "≤0":
                planes.append((0, 0, 1, 0, "≤", "x₃ ≤ 0"))
        return planes

    def _feasible_vertices_3d(self, planes):

        hp = [(p[0], p[1], p[2], p[3], p[4]) for p in planes]
        n = len(hp)
        vertices = []
        for i, j, k in itertools.combinations(range(n), 3):
            pt = _intersect_3planes(hp[i], hp[j], hp[k])
            if pt is None:
                continue
            x, y, z = pt
            if not all(math.isfinite(v) for v in (x, y, z)):
                continue
            if _halfspace_feasible(x, y, z, hp):
                vertices.append((x, y, z))
        return vertices

    def _dedup3(self, pts, eps=1e-6):
        unique = []
        for p in pts:
            if not any(
                abs(p[0]-q[0]) < eps and abs(p[1]-q[1]) < eps and abs(p[2]-q[2]) < eps
                for q in unique
            ):
                unique.append(p)
        return unique

    def _draw_3d_scene(self, ax, planes, vertices, vv, optimal, maximize, prob):
        import numpy as np
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        mode = self.data_mode.get()

        # ---- axis limits ----
        if vertices:
            xs = [p[0] for p in vertices]
            ys = [p[1] for p in vertices]
            zs = [p[2] for p in vertices]
        else:
            xs = ys = zs = [-3, 3]

        pad = max(1.0, (max(xs)-min(xs)+max(ys)-min(ys)+max(zs)-min(zs)) * 0.15)
        xlo, xhi = min(xs)-pad, max(xs)+pad
        ylo, yhi = min(ys)-pad, max(ys)+pad
        zlo, zhi = min(zs)-pad, max(zs)+pad

        ax.set_xlim(xlo, xhi)
        ax.set_ylim(ylo, yhi)
        ax.set_zlim(zlo, zhi)

        palette = [
            "#3b82f6", "#a855f7", "#10b981",
            "#f59e0b", "#ef4444", "#06b6d4",
            "#ec4899", "#84cc16",
        ]
        hp = [(p[0], p[1], p[2], p[3], p[4]) for p in planes]

        if vertices and len(vertices) >= 3:
            try:
                from scipy.spatial import ConvexHull
                arr = np.array(vertices)
                hull = ConvexHull(arr)
                faces = [arr[s] for s in hull.simplices]
                poly = Poly3DCollection(
                    faces, alpha=0.18, linewidth=0.6,
                    facecolor="#93c5fd", edgecolor="#3b82f6"
                )
                ax.add_collection3d(poly)
            except Exception:
                pass

        for idx, (a, b, c, d, sense, label) in enumerate(planes):
            color = palette[idx % len(palette)]
            self._draw_plane_patch(ax, a, b, c, d, color,
                                   xlo, xhi, ylo, yhi, zlo, zhi, label, idx)
        if vertices:
            xs_v = [p[0] for p in vertices]
            ys_v = [p[1] for p in vertices]
            zs_v = [p[2] for p in vertices]
            ax.scatter(xs_v, ys_v, zs_v,
                       s=48, c="#60a5fa", edgecolors="white",
                       linewidths=0.8, zorder=5, depthshade=True,
                       label="Đỉnh khả thi")

            for idx2, (x, y, z, val) in enumerate(vv, start=1):
                ax.text(x, y, z,
                        f" {idx2}", fontsize=8, color=self._me["fg"],
                        bbox=dict(boxstyle="round,pad=0.15",
                                  fc="#1e3a5f", ec="#3b82f6", alpha=0.85))

        if optimal is not None:
            bx, by, bz, bval = optimal
            ax.scatter([bx], [by], [bz],
                       s=260, marker="*", c="#f59e0b",
                       edgecolors="#fbbf24", linewidths=1.2,
                       zorder=10, depthshade=False, label="Điểm tối ưu")
            ax.text(bx, by, bz,
                    f"  ★ tối ưu\n  ({bx:.3g}, {by:.3g}, {bz:.3g})\n  z={bval:.3g}",
                    fontsize=9, fontweight="bold", color="#fbbf24",
                    bbox=dict(boxstyle="round,pad=0.3",
                              fc="#1c1917", ec="#f59e0b", alpha=0.96))

        c1 = float(prob.obj_coeffs[0])
        c2 = float(prob.obj_coeffs[1])
        c3 = float(prob.obj_coeffs[2])
        norm = math.sqrt(c1**2 + c2**2 + c3**2)
        if norm > 1e-10 and vertices:
            cx = sum(p[0] for p in vertices) / len(vertices)
            cy = sum(p[1] for p in vertices) / len(vertices)
            cz = sum(p[2] for p in vertices) / len(vertices)
            scale = pad * 0.7 / norm
            sign = 1 if maximize else -1
            dx, dy, dz = sign*c1*scale, sign*c2*scale, sign*c3*scale
            ax.quiver(cx, cy, cz, dx, dy, dz,
                      color="#f87171", linewidth=2.2, arrow_length_ratio=0.25,
                      label="Hướng tối ưu hóa")

        leg = ax.legend(loc="upper left", fontsize=8,
                        facecolor="#1e293b", edgecolor="#334155",
                        labelcolor=self._me["fg"], framealpha=0.85)

    def _draw_plane_patch(self, ax, a, b, c, d, color,
                          xlo, xhi, ylo, yhi, zlo, zhi,
                          label, idx):
        import numpy as np
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        norm = math.sqrt(a**2 + b**2 + c**2)
        if norm < 1e-12:
            return

        try:
            res = 8
            if abs(c) > max(abs(a), abs(b)) * 0.5:
                # z = (d - ax - by) / c
                xs = np.linspace(xlo, xhi, res)
                ys = np.linspace(ylo, yhi, res)
                X, Y = np.meshgrid(xs, ys)
                Z = (d - a * X - b * Y) / c
                # clip to zlo..zhi
                mask = (Z >= zlo - 0.01) & (Z <= zhi + 0.01)
                if not mask.any():
                    return
                Z = np.clip(Z, zlo, zhi)
            elif abs(b) > abs(a) * 0.5:
                xs = np.linspace(xlo, xhi, res)
                zs = np.linspace(zlo, zhi, res)
                X, Z = np.meshgrid(xs, zs)
                Y = (d - a * X - c * Z) / b
                mask = (Y >= ylo - 0.01) & (Y <= yhi + 0.01)
                if not mask.any():
                    return
                Y = np.clip(Y, ylo, yhi)
            else:
                zs = np.linspace(zlo, zhi, res)
                ys = np.linspace(ylo, yhi, res)
                Y, Z = np.meshgrid(ys, zs)
                X = (d - b * Y - c * Z) / a
                mask = (X >= xlo - 0.01) & (X <= xhi + 0.01)
                if not mask.any():
                    return
                X = np.clip(X, xlo, xhi)

            ax.plot_surface(X, Y, Z, alpha=0.08, color=color,
                            linewidth=0, antialiased=True, zorder=1)

            if abs(c) > max(abs(a), abs(b)) * 0.5:
                for xi in [xlo, xhi]:
                    ys2 = np.linspace(ylo, yhi, 30)
                    zs2 = np.clip((d - a * xi - b * ys2) / c, zlo, zhi)
                    ax.plot([xi]*30, ys2, zs2, color=color,
                            linewidth=1.4, alpha=0.75)
            xm = (xlo + xhi) / 2
            ym = (ylo + yhi) / 2
            if abs(c) > 1e-10:
                zm = (d - a * xm - b * ym) / c
                zm = max(zlo, min(zhi, zm))
            elif abs(b) > 1e-10:
                zm = (zlo + zhi) / 2
                ym = (d - a * xm - c * zm) / b
                ym = max(ylo, min(yhi, ym))
            else:
                zm = (zlo + zhi) / 2
                xm = (d - b * ym - c * zm) / a
                xm = max(xlo, min(xhi, xm))

            if idx < 6:  # only label first few to avoid clutter
                ax.text(xm, ym, zm, label, fontsize=8, color=color,
                        bbox=dict(boxstyle="round,pad=0.18",
                                  fc=self._me["header_bg"], ec=color, alpha=0.88))
        except Exception:
            pass

    def _build_info_panel_3d(self, parent, prob, vertices, vv, optimal, maximize):
        mode = self.data_mode.get()

        panel = tk.Frame(parent, bg=self._me["header_bg"], width=280,
                         highlightthickness=1, highlightbackground="#334155")
        panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        panel.grid_propagate(False)
        panel.columnconfigure(0, weight=1)

        def lbl(text, fg=self._me["fg"], font=("Segoe UI", 9), **kw):
            tk.Label(panel, text=text, bg=self._me["header_bg"], fg=fg,
                     font=font, anchor="w", wraplength=260, **kw).pack(
                fill="x", padx=10, pady=1)

        lbl("Tóm tắt bài toán 3D",
            fg="#f8fafc", font=("Segoe UI", 11, "bold"))

        tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)

        sense_txt = "MAX" if prob.objective_sense == "max" else "MIN"

        def coef_str(c):
            return fmt_num(fr(c), mode)

        c1, c2, c3 = prob.obj_coeffs
        obj_txt = (f"{sense_txt} Z = {coef_str(c1)}x₁"
                   f" {'+ ' if c2 >= 0 else '- '}{coef_str(abs(fr(c2)))}x₂"
                   f" {'+ ' if c3 >= 0 else '- '}{coef_str(abs(fr(c3)))}x₃")
        lbl("Hàm mục tiêu:", fg="#94a3b8", font=("Segoe UI", 8))
        lbl(obj_txt, fg="#7dd3fc", font=("Consolas", 9))

        tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)
        lbl(f"Số ràng buộc: {len(prob.constraints)}", fg="#94a3b8")
        lbl(f"Số đỉnh khả thi: {len(vertices)}", fg="#94a3b8")

        tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)
        lbl("Ràng buộc:", fg="#94a3b8", font=("Segoe UI", 8))
        for i, cons in enumerate(prob.constraints, start=1):
            a, b, c = cons["coeffs"]
            d = cons["rhs"]
            s = sense_to_standard(cons["sense"])
            txt = (f"RB{i}: {coef_str(a)}x₁ + {coef_str(b)}x₂"
                   f" + {coef_str(c)}x₃ {s} {coef_str(d)}")
            lbl(txt, fg=self._me["fg"], font=("Consolas", 8))

        if vv:
            tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)
            lbl("Đỉnh khả thi (Z):", fg="#94a3b8", font=("Segoe UI", 8))
            ordered = sorted(vv, key=lambda t: t[3], reverse=maximize)
            for idx, (x, y, z, val) in enumerate(ordered, start=1):
                lbl(f"  {idx}. ({x:.3g}, {y:.3g}, {z:.3g})  z={val:.3g}",
                    fg=self._me["fg"], font=("Consolas", 8))

        if optimal is not None:
            tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)
            bx, by, bz, bv = optimal
            lbl("Điểm tối ưu:", fg="#fbbf24", font=("Segoe UI", 9, "bold"))
            lbl(f"  ({bx:.4g}, {by:.4g}, {bz:.4g})",
                fg="#fbbf24", font=("Consolas", 9))
            lbl(f"  Z = {bv:.4g}", fg="#fbbf24", font=("Consolas", 9))
        else:
            lbl("Không tìm thấy đỉnh khả thi.",
                fg="#f87171", font=("Segoe UI", 9))

        tk.Frame(panel, bg="#334155", height=1).pack(fill="x", padx=8, pady=4)
        lbl("Xoay: kéo chuột trái\n   Zoom: lăn chuột\n   Pan: kéo chuột phải",
            fg="#64748b", font=("Segoe UI", 8))


    def _build_3d_controls(self, ctrl, ax, canvas, fig):
        ctrl.columnconfigure(0, weight=1)

        btn_frame = tk.Frame(ctrl, bg=self._me["header_bg"])
        btn_frame.pack(side="left", padx=12, pady=6)

        def mk_btn(text, color, hover, cmd):
            b = tk.Button(
                btn_frame, text=text,
                font=("Segoe UI", 9, "bold"),
                bg=color, fg="white",
                activebackground=hover, activeforeground="white",
                relief="flat", bd=0, padx=10, pady=5,
                cursor="hand2", command=cmd
            )
            b.pack(side="left", padx=4)
            b.bind("<Enter>", lambda e, hv=hover: b.config(bg=hv))
            b.bind("<Leave>", lambda e, cv=color: b.config(bg=cv))

        def reset_view():
            ax.view_init(elev=22, azim=-55)
            canvas.draw_idle()

        def view_xy():
            ax.view_init(elev=90, azim=-90)
            canvas.draw_idle()

        def view_xz():
            ax.view_init(elev=0, azim=-90)
            canvas.draw_idle()

        def view_yz():
            ax.view_init(elev=0, azim=0)
            canvas.draw_idle()

        def toggle_grid():
            ax.grid(not ax.get_xgridlines()[0].get_visible())
            canvas.draw_idle()

        mk_btn("Mặc định", "#334155", "#475569", reset_view)
        mk_btn("Mặt XY",  "#1d4ed8", "#1e40af", view_xy)
        mk_btn("Mặt XZ",  "#0f766e", "#0d9488", view_xz)
        mk_btn("Mặt YZ",  "#7c3aed", "#6d28d9", view_yz)
        mk_btn("Lưới",    "#64748b", "#475569", toggle_grid)

        hint = tk.Label(
            ctrl,
            text="Kéo chuột trái để xoay 3D -- Lăn chuột để zoom -- Kéo chuột phải để dịch chuyển",
            bg=self._me["header_bg"], fg="#64748b", font=("Segoe UI", 9)
        )
        hint.pack(side="right", padx=16)
