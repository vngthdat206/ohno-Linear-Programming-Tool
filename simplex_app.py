from __future__ import annotations

import math
import os
import tkinter as tk
import webbrowser
from fractions import Fraction
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional, Tuple

from models import ProblemData, SolveReport
from simplex_engine import SimplexEngine
from html_exporter import export_report_html
from utils import (VAR_SIGNS, SENSES, clean_number_text, fmt_num,
                   fr, parse_cell, row_expr, sense_to_standard, term_str)
from viz3d import Viz3DMixin


class SimplexApp(Viz3DMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ứng dụng Giải bài toán Quy hoạch tuyến tính (tổng quát)")
        self.geometry("1380x920")
        self.minsize(1100, 760)

        # Thiết lập các biến trạng thái mặc định
        self.objective_sense = tk.StringVar(value="min") # kiểu bài toán mặc định là min
        self.n_vars = tk.IntVar(value=2)
        self.n_constraints = tk.IntVar(value=3)
        self.data_mode = tk.StringVar(value="Phân số")
        self.method_preference = tk.StringVar(value="Dantzig Simplex")
        self.demo_preset_var = tk.StringVar(value="Ví dụ giải bằng 2 pha")
        self.need_aux_phase1 = False # cờ cho biết có cần biến phụ để giải pha 1 hay không
        self.phase1_aux_var_index: Optional[int] = None # chỉ số của biến phụ nếu cần thiết

        # Danh sách các widget nhập liệu sẽ được tạo động theo số biến và ràng buộc, lưu lại để dễ truy cập khi thu thập dữ liệu
        self.obj_entries: List[tk.Entry] = [] # hệ số x(j+1) của hàm mục tiêu
        self.var_signs: List[ttk.Combobox] = [] # dấu của x(j+1): ≥0 / ≤0 / tự do
        self.constraint_entries: List[List[tk.Entry]] = [] # hệ số x(j+1) của từng ràng buộc i
        self.constraint_senses: List[ttk.Combobox] = [] # dấu của ràng buộc i: ≤ / ≥ / =
        self.constraint_rhs: List[tk.Entry] = [] # vế phải của ràng buộc i

        # Biến lưu kết quả giải thuật gần nhất để có thể xuất file hoặc trực quan hóa nếu phù hợp
        self.last_report: Optional[SolveReport] = None
        self.last_problem: Optional[ProblemData] = None
        self.export_btn: Optional[tk.Button] = None
        self.html_btn: Optional[tk.Button] = None
        self.viz_btn: Optional[tk.Button] = None
        self.viz3d_btn: Optional[tk.Button] = None

        # Khởi động giao diện
        self._setup_style()
        self._build_ui()
        self._build_inputs()
        # Phím tắt đề chạy giải thuật: Ctrl + Alt + R (không phân biệt hoa thường)
        self.bind_all("<Control-Alt-r>", lambda e: self.run_solver())
        self.bind_all("<Control-Alt-R>", lambda e: self.run_solver())


    def _setup_style(self):
        # Palette màu cố định: "Nordic Frost"
        ME = {
            # Nền tổng thể: trắng tuyết nhạt, sạch và thoáng
            "bg":           "#FAFBFC",
            # Nền header (thanh tiêu đề trên cùng): xanh đêm Bắc Âu
            "header_bg":    "#1E3A5F",
            # Chữ tiêu đề trên header: trắng tinh
            "header_fg":    "#FFFFFF",
            # Chữ phụ trên header: xanh băng nhạt
            "subheader_fg": "#B5D4F4",
            # Chữ nội dung chính: xanh đen trung tính
            "fg":           "#334155",
            # Viền và tiêu đề labelframe: xanh dương đậm vừa
            "frame_fg":     "#185FA5",
            # Nút hành động chính (Chạy giải thuật): xanh dương Nordic
            "accent":       "#3B82F6",
            # Nút hành động chính khi hover / active: xanh dương đậm hơn
            "accent_hover": "#2563EB",
            # Nút hành động chính khi bị vô hiệu hóa: xám lạnh
            "accent_dis":   "#CBD5E1",
            # Chữ trên nút bị vô hiệu hóa: xám xanh
            "dis_fg":       "#94A3B8",
            # Nút cảnh báo (Điền ví dụ): hổ phách vàng ấm
            "warn":         "#F59E0B",
            # Nút cảnh báo khi hover: hổ phách đậm hơn
            "warn_hover":   "#D97706",
            # Nền vùng lời giải (output): trắng tinh
            "output_bg":    "#FFFFFF",
            # Chữ trong vùng lời giải: xanh đen đậm
            "output_fg":    "#1E293B",
            # Màu tag h1 (tên bài toán): xanh dương Nordic đậm
            "h1":           "#185FA5",
            # Màu tag h2 (tiêu đề bước): xanh đêm Bắc Âu
            "h2":           "#1E3A5F",
            # Màu tag note (ghi chú, kết luận): teal sage
            "note":         "#0F766E",
            # Màu tag warn (cảnh báo suy biến, không giới nội): hổ phách đậm
            "warn_tag":     "#B45309",
            # Nền ô cột xoay (pivotcol): vàng băng nhạt
            "pivot_col":    "#FEF9C3",
            # Nền hàng xoay (pivotrow): xanh băng nhạt
            "pivot_row":    "#E8F4FD",
            # Nền ô xoay giao nhau (pivotcell): xanh dương nhạt rõ
            "pivot_cell":   "#BFDBFE",
            # Nền kết luận cuối: xanh lá sage nhạt
            "conclusion":   "#F0FDF4",
        }
        self._me = ME  # lưu lại để các hàm khác có thể tham chiếu nếu cần

        # Áp dụng theme nền "clam" của ttk (nếu không có thì dùng theme mặc định)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Nền mặc định cho tất cả TFrame: trắng tuyết "Nordic Frost"
        style.configure("TFrame", background=ME["bg"])

        # Header: nền xanh đêm Bắc Âu, chữ trắng nổi bật
        style.configure("Header.TFrame", background=ME["header_bg"])
        style.configure("Header.TLabel", background=ME["header_bg"],
                        foreground=ME["header_fg"], font=("Segoe UI", 16, "bold"))

        # Dòng phụ dưới tiêu đề: chữ xanh băng nhạt trên nền đêm
        style.configure("SubHeader.TLabel", background=ME["header_bg"],
                        foreground=ME["subheader_fg"], font=("Segoe UI", 10))

        # Nhãn nội dung thông thường: xanh đen trên nền trắng tuyết
        style.configure("TLabel", background=ME["bg"],
                        foreground=ME["fg"], font=("Segoe UI", 10))

        # Khung nhóm (LabelFrame): nền trắng tuyết, viền 1px
        style.configure("TLabelframe", background=ME["bg"], borderwidth=1)
        style.configure("TLabelframe.Label", background=ME["bg"],
                        foreground=ME["frame_fg"], font=("Segoe UI", 10, "bold"))

        # Nút chung: font đậm, padding thoáng
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)

        # Nút hành động chính (Accent): xanh dương "Nordic Frost"
        style.configure("Accent.TButton", background=ME["accent"], foreground=ME["header_fg"])
        style.map(
            "Accent.TButton",
            background=[("disabled", ME["accent_dis"]),
                        ("active",   ME["accent_hover"]),
                        ("!disabled", ME["accent"])],
            foreground=[("disabled", ME["dis_fg"]),
                        ("!disabled", ME["header_fg"])],
        )

        # Nút cảnh báo (Warn): hổ phách vàng, hover sang hổ phách đậm
        style.configure("Warn.TButton", background=ME["warn"], foreground=ME["header_fg"])
        style.map("Warn.TButton", background=[("active", ME["warn_hover"])])

        # Combobox và Treeview: padding/chiều cao hàng tiêu chuẩn
        style.configure("TCombobox", padding=4)
        style.configure("Treeview", rowheight=28)


    def _build_ui(self):
        # Dựng bố cục tổng thể của cửa sổ chính:
        #   row 0 → header (tiêu đề cố định, không co giãn)
        #   row 1 → vùng làm việc chính (co giãn theo cửa sổ)
        #   row 2 → thanh trạng thái (status bar, cố định)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Thanh tiêu đề trên cùng: tên ứng dụng (h1) + hướng dẫn tóm tắt (h2)
        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 12))
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header,
                  text="Ứng dụng Giải bài toán Quy hoạch tuyến tính (tổng quát)",
                  style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Tab để chuyển ô - Tổ hợp phím Ctrl + Alt + R để giải - Hỗ trợ max/min, ràng buộc ≤ ≥ =, biến tự do - Giải bằng Dantzig / Bland / 2 pha - Trực quan hóa 2D / 3D",
            style="SubHeader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Khung chính: 2 cột
        # Cột 0 (left, cố định): bảng thiết lập + nhập liệu
        # Cột 1 (right, co giãn): vùng hiển thị lời giải
        main = ttk.Frame(self, padding=14)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # Cột trái: row 0 → Thiết lập (config), row 1 → Mẫu demo, row 3 → Nhập bài toán
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(3, weight=1)  # row nhập liệu co giãn theo chiều dọc

        # Nhóm "Thiết lập": kiểu dữ liệu, số biến, số ràng buộc, nút tạo lại
        config = ttk.Labelframe(left, text="Thiết lập", padding=12)
        config.grid(row=0, column=0, sticky="ew")
        config.columnconfigure(1, weight=1)

        ttk.Label(config, text="Kiểu dữ liệu:").grid(
            row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(config, textvariable=self.data_mode,
                     values=["Phân số", "Số thập phân"],
                     state="readonly", width=12).grid(
            row=0, column=1, sticky="w", pady=3)

        ttk.Label(config, text="Số biến (1–5):").grid(
            row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(config, from_=1, to=5, textvariable=self.n_vars,
                    width=10, command=self._build_inputs).grid(
            row=1, column=1, sticky="w", pady=3)

        ttk.Label(config, text="Số ràng buộc (1–10):").grid(
            row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(config, from_=1, to=10, textvariable=self.n_constraints,
                    width=10, command=self._build_inputs).grid(
            row=2, column=1, sticky="w", pady=3)

        ttk.Button(config, text="Tạo lại bảng nhập",
                   command=self._build_inputs).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        # Hàng nút xuất file + HTML + trực quan hóa
        action_row = ttk.Frame(config)
        action_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        action_row.columnconfigure(2, weight=1)

        # Nút "Xuất file .txt": ban đầu bị vô hiệu hóa (xám); chỉ sáng lên sau khi giải xong
        self.export_btn = tk.Button(
            action_row,
            text="📄  Xuất .txt",
            font=("Segoe UI", 9, "bold"),
            bg="#CBD5E1", fg="white",
            activebackground="#94A3B8", activeforeground="white",
            relief="flat", bd=0, padx=6, pady=7,
            cursor="arrow", state=tk.DISABLED,
            command=self.export_solution_txt,
        )
        self.export_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.export_btn.bind("<Enter>",
                             lambda e: self._on_button_enter(e, "#2563EB"))
        self.export_btn.bind("<Leave>",
                             lambda e: self._on_button_leave(e, "#CBD5E1"))

        # Nút "Xem HTML (KaTeX)": xuất lời giải đẹp ra trình duyệt
        self.html_btn = tk.Button(
            action_row,
            text="🌐  Xem HTML",
            font=("Segoe UI", 9, "bold"),
            bg="#CBD5E1", fg="white",
            activebackground="#94A3B8", activeforeground="white",
            relief="flat", bd=0, padx=6, pady=7,
            cursor="arrow", state=tk.DISABLED,
            command=self.open_solution_html,
        )
        self.html_btn.grid(row=0, column=1, sticky="ew", padx=(0, 3))
        self.html_btn.bind("<Enter>",
                           lambda e: self._on_button_enter(e, "#0F766E"))
        self.html_btn.bind("<Leave>",
                           lambda e: self._on_button_leave(e, "#CBD5E1"))

        # Nút "Trực quan hóa (2D/3D)": luôn hiển thị, nhưng đổi nhãn/màu theo số biến
        self.viz_btn = tk.Button(
            action_row,
            text="📊  Trực quan",
            font=("Segoe UI", 9, "bold"),
            bg="#6EBF8B", fg="white",
            activebackground="#4DAA72", activeforeground="white",
            relief="flat", bd=0, padx=6, pady=7,
            cursor="hand2",
            command=self._viz_dispatch,
        )
        self.viz_btn.grid(row=0, column=2, sticky="ew")
        self.viz_btn.bind("<Enter>",
                          lambda e: self._on_button_enter(e, None))
        self.viz_btn.bind("<Leave>",
                          lambda e: self._on_button_leave(e, None))

        self.viz3d_btn = None

        method_box = ttk.Labelframe(config, text="Phương pháp giải", padding=10)
        method_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        method_box.columnconfigure(1, weight=1)
        ttk.Label(method_box, text="Chọn phương pháp:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        method_combo = ttk.Combobox(
            method_box,
            textvariable=self.method_preference,
            values=["Dantzig Simplex", "Bland's Rule"],
            state="readonly",
            width=18,
        )
        method_combo.grid(row=0, column=1, sticky="ew")
        ttk.Label(
            method_box,
            text="Dantzig dừng khi phát hiện xoay vòng; Bland dùng để tránh lặp.",
            foreground="#64748B",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Button(config, text="Chạy giải thuật  (Ctrl+Alt+R)",
                   style="Accent.TButton",
                   command=self.run_solver).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        btns = ttk.Frame(left)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        btns.columnconfigure(1, weight=1)
        ttk.Label(btns, text="Mẫu:").grid(row=0, column=0, sticky="w",
                                           padx=(0, 6))
        demo_combo = ttk.Combobox(
            btns,
            textvariable=self.demo_preset_var,
            values=["Ví dụ giải bằng 2 pha",
                    "Ví dụ giải bài toán xoay vòng",
                    "Ví dụ giải bài toán vô số nghiệm",
                    "Ví dụ 3 biến (trực quan 3D)"],
            state="readonly", width=28,
        )
        demo_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(btns, text="Điền ví dụ",
                   style="Warn.TButton",
                   command=self.fill_demo).grid(row=0, column=2, sticky="ew")

        input_box = ttk.Labelframe(left, text="Nhập bài toán", padding=14)
        input_box.grid(row=3, column=0, sticky="nsew")
        input_box.columnconfigure(0, weight=1)
        input_box.rowconfigure(0, weight=1)
        self.input_canvas = tk.Canvas(input_box, background="#FAFBFC",
                                      highlightthickness=0, width=580, height=650)
        self.input_canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(input_box, orient="vertical",
                             command=self.input_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.input_canvas.configure(yscrollcommand=vsb.set)
        self.input_inner = ttk.Frame(self.input_canvas)
        self.input_window = self.input_canvas.create_window(
            (0, 0), window=self.input_inner, anchor="nw")
        self.input_inner.bind(
            "<Configure>",
            lambda e: self.input_canvas.configure(
                scrollregion=self.input_canvas.bbox("all")))
        self.input_canvas.bind(
            "<Configure>",
            lambda e: self.input_canvas.itemconfigure(
                self.input_window, width=e.width))

        # Cột phải (hiển thị lời giải): Dùng ScrolledText để cuộn cả dọc lẫn ngang; font monospace để canh cột bảng từ vựng
        right = ttk.Labelframe(main, text="Lời giải", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.output = scrolledtext.ScrolledText(
            right, wrap="none", font=("Consolas", 12),
            bg="#FFFFFF", fg="#1E293B",
            insertbackground="#1E293B", relief="flat", padx=14, pady=10,
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        # Định nghĩa các "tag" màu sắc dùng trong vùng lời giải:
        #   h1        → tên bài toán (to, đậm, màu nâu đỏ)
        #   h2        → tiêu đề pha / bước (đậm, màu xanh than)
        #   note      → ghi chú, kết quả từng bước (xanh indigo đất)
        #   warn      → cảnh báo suy biến, vô nghiệm (vàng đất)
        #   mono      → dạng bảng từ vựng (Consolas, không trang trí thêm)
        #   pivotcol  → highlight cột biến vào (nền vàng nhạt)
        #   pivotrow  → highlight hàng biến ra (nền xanh lam nhạt)
        #   pivotcell → highlight ô phần tử xoay = giao pivotcol ∩ pivotrow (nền đỏ hồng nhạt)
        #   conclusion→ highlight khối kết luận cuối (nền cam kem)
        self.output.tag_configure("h1", font=("Segoe UI", 15, "bold"),
                                   foreground="#185FA5", spacing1=8, spacing3=10)
        self.output.tag_configure("h2", font=("Segoe UI", 12, "bold"),
                                   foreground="#1E3A5F", spacing1=8, spacing3=4)
        self.output.tag_configure("note", foreground="#0F766E")
        self.output.tag_configure("warn", foreground="#B45309")
        self.output.tag_configure("mono", font=("Consolas", 12))
        self.output.tag_configure("pivotcol", background="#FEF9C3")
        self.output.tag_configure("pivotrow", background="#E8F4FD")
        self.output.tag_configure("pivotcell", background="#BFDBFE")
        self.output.tag_configure("conclusion", background="#F0FDF4")

        self.status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(self, textvariable=self.status_var,
                  anchor="w", padding=(14, 6)).grid(row=2, column=0, sticky="ew")

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        # Khi cửa sổ thay đổi kích thước, đảm bảo vùng lời giải không tự xuống dòng
        # (wrap="none" giữ mỗi dòng bảng từ vựng thẳng hàng, cuộn ngang nếu cần)
        try:
            self.output.configure(wrap="none")
        except Exception:
            pass

    def _build_inputs(self):
        # Xây dựng lại toàn bộ bảng nhập liệu mỗi khi số biến / số ràng buộc thay đổi.
        # Bước 1: xóa sạch tất cả widget cũ bên trong input_inner
        # Bước 2: xóa các danh sách tham chiếu (entry, combobox) để tránh trỏ đến widget đã hủy
        for child in self.input_inner.winfo_children():
            child.destroy()
        self.obj_entries.clear()
        self.var_signs.clear()
        self.constraint_entries.clear()
        self.constraint_senses.clear()
        self.constraint_rhs.clear()

        n = int(self.n_vars.get())        # số biến quyết định x1..xn
        m = int(self.n_constraints.get()) # số ràng buộc

        # Hàm mục tiêu: combobox chọn max/min, hàng nhập hệ số cj, hàng chọn dấu xj
        obj_frame = ttk.Labelframe(self.input_inner,
                                    text="Hàm mục tiêu", padding=10)
        obj_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        obj_frame.columnconfigure(1, weight=1)

        ttk.Label(obj_frame, text="Kiểu bài toán:").grid(
            row=0, column=0, sticky="w")
        ttk.Combobox(obj_frame, textvariable=self.objective_sense,
                     values=["max", "min"], state="readonly", width=8).grid(
            row=0, column=1, sticky="w", pady=2)

        ttk.Label(obj_frame, text="Hệ số:").grid(
            row=1, column=0, sticky="w", pady=(8, 2))
        # Tạo n ô entry cho hệ số c1..cn của hàm mục tiêu; sắp xếp ngang theo cột
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
        sign_frame.grid(row=2, column=0, columnspan=2,
                         sticky="ew", pady=(10, 0))
        for j in range(n):
            sc = ttk.Frame(sign_frame)
            sc.grid(row=0, column=j, padx=4, sticky="ew")
            ttk.Label(sc, text=f"x{j+1}").grid(row=0, column=0, sticky="w")
            cb = ttk.Combobox(sc, values=VAR_SIGNS, state="readonly", width=10)
            cb.set("≥0")
            cb.grid(row=1, column=0, sticky="ew")
            self.var_signs.append(cb)

        # Các ràng buộc: n ô hệ số, 1 combobox dấu (≤/≥/=), 1 ô vế phải
        cons_frame = ttk.Labelframe(self.input_inner,
                                     text="Ràng buộc", padding=10)
        cons_frame.grid(row=1, column=0, sticky="nsew")
        cons_frame.columnconfigure(0, weight=1)

        ttk.Label(cons_frame,
                  text="Nhập hệ số từng ràng buộc, chọn dấu rồi nhập vế phải."
                  ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        table = ttk.Frame(cons_frame)
        table.grid(row=1, column=0, sticky="ew")

        hdr = ttk.Frame(table)
        hdr.grid(row=0, column=0, columnspan=n+3, sticky="ew")
        ttk.Label(hdr, text="").grid(row=0, column=0, padx=2)
        for j in range(n):
            ttk.Label(hdr, text=f"x{j+1}", width=8,
                      anchor="center").grid(row=0, column=j+1, padx=2)
        ttk.Label(hdr, text="Dấu", width=8,
                  anchor="center").grid(row=0, column=n+1, padx=2)
        ttk.Label(hdr, text="Hệ số tự do", width=10,
                  anchor="center").grid(row=0, column=n+2, padx=2)

        for i in range(m):
            rf = ttk.Frame(table)
            rf.grid(row=i+1, column=0, columnspan=n+3, sticky="ew", pady=2)
            ttk.Label(rf, text=f"(RB{i+1})", width=5).grid(
                row=0, column=0, padx=2)
            row_entries = []
            for j in range(n):
                e = ttk.Entry(rf, width=10)
                e.grid(row=0, column=j+1, padx=2)
                row_entries.append(e)
            cb = ttk.Combobox(rf, values=SENSES, state="readonly", width=6)
            cb.set("≤")
            cb.grid(row=0, column=n+1, padx=2)
            rhs = ttk.Entry(rf, width=10)
            rhs.grid(row=0, column=n+2, padx=2)
            self.constraint_entries.append(row_entries)
            self.constraint_senses.append(cb)
            self.constraint_rhs.append(rhs)

        ttk.Label(
            self.input_inner,
            text="Bấm Tab để chuyển ô. Ctrl+Alt+R để giải.",
            foreground="#185FA5",
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

        self.input_inner.update_idletasks()
        self.input_canvas.configure(
            scrollregion=self.input_canvas.bbox("all"))
        self.last_problem = None
        self.last_report = None
        self._set_solution_available(False)
        self._update_viz_btn_state()

    def fill_demo(self):
        preset = self.demo_preset_var.get().strip()
        if preset == "Ví dụ giải bài toán xoay vòng":
            self._fill_demo_cycle()
        elif preset == "Ví dụ giải bài toán vô số nghiệm":
            self._fill_demo_multiple_optimal()
        elif preset == "Ví dụ 3 biến (trực quan 3D)":
            self._fill_demo_3var()
        else:
            self._fill_demo_two_phase()

    def _fill_demo_two_phase(self):
        self.n_vars.set(2); self.n_constraints.set(3)
        self.objective_sense.set("min"); self._build_inputs()
        for i, v in enumerate(["5", "-7"]):
            self.obj_entries[i].delete(0, tk.END)
            self.obj_entries[i].insert(0, v)
        for cb in self.var_signs:
            cb.set("≥0")
        data = [(["-4","1"],"≤","-2"),(["1","1"],"≤","5"),(["−1","−1"],"≤","-1")]
        for i,(c,s,r) in enumerate(data):
            for j,e in enumerate(self.constraint_entries[i]):
                e.delete(0,tk.END); e.insert(0,c[j])
            self.constraint_senses[i].set(s)
            self.constraint_rhs[i].delete(0,tk.END)
            self.constraint_rhs[i].insert(0,r)

    def _fill_demo_cycle(self):
        self.n_vars.set(4); self.n_constraints.set(3)
        self.objective_sense.set("min"); self._build_inputs()
        for i,v in enumerate(["-10","57","9","24"]):
            self.obj_entries[i].delete(0,tk.END); self.obj_entries[i].insert(0,v)
        for cb in self.var_signs: cb.set("≥0")
        data=[
            (["0.5","-5.5","-2.5","9"],"≤","0"),
            (["0.5","-1.5","-0.5","1"],"≤","0"),
            (["1","0","0","0"],"≤","1"),
        ]
        for i,(c,s,r) in enumerate(data):
            for j,e in enumerate(self.constraint_entries[i]):
                e.delete(0,tk.END); e.insert(0,c[j])
            self.constraint_senses[i].set(s)
            self.constraint_rhs[i].delete(0,tk.END)
            self.constraint_rhs[i].insert(0,r)

    def _fill_demo_multiple_optimal(self):
        self.n_vars.set(3); self.n_constraints.set(4)
        self.objective_sense.set("max"); self._build_inputs()
        for i,v in enumerate(["-3","1","1"]):
            self.obj_entries[i].delete(0,tk.END); self.obj_entries[i].insert(0,v)
        for cb in self.var_signs: cb.set("≥0")
        data=[
            (["1","-1","0"],"≤","0"),
            (["-2","0","1"],"≤","1"),
            (["0","-2","1"],"≤","2"),
            (["1","1","-1"],"≤","6"),
        ]
        for i,(c,s,r) in enumerate(data):
            for j,e in enumerate(self.constraint_entries[i]):
                e.delete(0,tk.END); e.insert(0,c[j])
            self.constraint_senses[i].set(s)
            self.constraint_rhs[i].delete(0,tk.END)
            self.constraint_rhs[i].insert(0,r)

    def _fill_demo_3var(self):
        self.n_vars.set(3); self.n_constraints.set(3)
        self.objective_sense.set("max"); self._build_inputs()
        for i,v in enumerate(["5","4","3"]):
            self.obj_entries[i].delete(0,tk.END); self.obj_entries[i].insert(0,v)
        for cb in self.var_signs: cb.set("≥0")
        data=[
            (["6","4","2"],"≤","240"),
            (["3","5","5"],"≤","270"),
            (["5","3","6"],"≤","420"),
        ]
        for i,(c,s,r) in enumerate(data):
            for j,e in enumerate(self.constraint_entries[i]):
                e.delete(0,tk.END); e.insert(0,c[j])
            self.constraint_senses[i].set(s)
            self.constraint_rhs[i].delete(0,tk.END)
            self.constraint_rhs[i].insert(0,r)

    def _collect_problem(self) -> ProblemData:
        # Thu thập toàn bộ dữ liệu từ giao diện nhập liệu và đóng gói thành ProblemData.
        n = int(self.n_vars.get())
        m = int(self.n_constraints.get())
        obj_coeffs = [parse_cell(e.get(), self.data_mode.get())
                      for e in self.obj_entries[:n]]
        var_signs = [cb.get() or "≥0" for cb in self.var_signs[:n]]
        constraints = []
        for i in range(m):
            coeffs = [parse_cell(e.get(), self.data_mode.get())
                      for e in self.constraint_entries[i][:n]]
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
        # Bật/tắt nút "Xuất file .txt" và "Xem HTML" tùy theo có kết quả giải hay chưa.
        for btn, hover_color, base_color in [
            (self.export_btn, "#2563EB", "#3B82F6"),
            (self.html_btn,   "#0F766E", "#0D9488"),
        ]:
            if btn is None:
                continue
            if available:
                btn._base_bg = base_color
                btn._hover_bg = hover_color
                btn.config(state=tk.NORMAL,
                           bg=base_color,
                           activebackground=hover_color,
                           cursor="hand2")
            else:
                btn._base_bg = "#CBD5E1"
                btn._hover_bg = "#94A3B8"
                btn.config(state=tk.DISABLED,
                           bg="#CBD5E1",
                           activebackground="#94A3B8",
                           cursor="arrow")

    # Bảng màu và nhãn nút trực quan hóa theo số biến:
    #   2 biến → nút xanh sage "Nordic Frost" "Trực quan hóa (2D)"
    #   3 biến → nút tím indigo "Trực quan hóa (3D)"
    #   >3 biến→ nút xám bị vô hiệu hóa (không hỗ trợ)
    _VIZ_STYLES = {
        2: dict(bg="#6EBF8B", hover="#4DAA72", icon="📊",
                label="Trực quan hóa (2D)"),
        3: dict(bg="#7C3AED", hover="#6D28D9", icon="🧊",
                label="Trực quan hóa (3D)"),
    }
    _VIZ_DISABLED = dict(bg="#CBD5E1", hover="#94A3B8",
                         icon="🔒", label="Trực quan hóa (>3 biến)")

    def _update_viz_btn_state(self) -> None:
        # Cập nhật màu sắc, nhãn và trạng thái nút viz_btn theo số biến hiện tại.
        if self.viz_btn is None:
            return
        n = int(self.n_vars.get())
        if n > 3:
            # Hơn 3 biến: không hỗ trợ trực quan, khóa nút lại
            s = self._VIZ_DISABLED
            self.viz_btn.config(
                text=f"{s['icon']}  {s['label']}",
                state=tk.DISABLED,
                bg=s["bg"], activebackground=s["hover"],
                cursor="arrow",
            )
            self.viz_btn._base_bg = s["bg"]
            self.viz_btn._hover_bg = s["hover"]
        else:
            # 2 hoặc 3 biến: kích hoạt nút với màu phù hợp
            s = self._VIZ_STYLES.get(n, self._VIZ_STYLES[2])
            self.viz_btn.config(
                text=f"{s['icon']}  {s['label']}",
                state=tk.NORMAL,
                bg=s["bg"], activebackground=s["hover"],
                cursor="hand2",
            )
            self.viz_btn._base_bg = s["bg"]
            self.viz_btn._hover_bg = s["hover"]

    def _viz_dispatch(self) -> None:
        # Điều phối yêu cầu trực quan hóa theo số biến:
        #   2 biến → vẽ đồ thị 2D miền chấp nhận + đường đồng mức
        #   3 biến → vẽ mô hình 3D (Viz3DMixin)
        #   khác  → thông báo không hỗ trợ
        n = int(self.n_vars.get())
        if n == 2:
            self.visualize_two_variable_problem()
        elif n == 3:
            self.visualize_three_variable_problem()
        else:
            messagebox.showinfo(
                "Trực quan hóa",
                "Tính năng trực quan chỉ hỗ trợ bài toán 2 hoặc 3 biến.\n"
                "Vui lòng giảm số biến xuống còn 2 hoặc 3.",
            )

    def _on_button_enter(self, event, darker_color: Optional[str] = None) -> None:
        # Xử lý sự kiện hover vào nút: đổi sang màu hover (tối hơn).
        btn = event.widget
        if str(btn.cget("state")) == "disabled":
            return
        if darker_color is None:
            darker_color = getattr(btn, "_hover_bg", btn.cget("bg"))
        elif btn is self.export_btn:
            darker_color = getattr(btn, "_hover_bg", darker_color)
        btn.config(bg=darker_color)

    def _on_button_leave(self, event, original_color: Optional[str] = None) -> None:
        # Xử lý sự kiện hover rời nút: khôi phục màu nền gốc.
        btn = event.widget
        if str(btn.cget("state")) == "disabled":
            return
        if original_color is None or btn is self.export_btn:
            original_color = getattr(btn, "_base_bg", btn.cget("bg"))
        btn.config(bg=original_color)


    def _normalize_method_choice(self, choice: Optional[str]) -> str:
        # Chuẩn hóa lựa chọn từ dropdown thành khóa nội bộ của solver.
        value = (choice or "").strip().lower()
        if value in {"dantzig simplex", "dantzig", "d"}:
            return "dantzig"
        if value in {"bland's rule", "bland", "blands rule", "bland rule"}:
            return "bland"
        raise ValueError("Phương pháp giải không hợp lệ. Hãy chọn Dantzig Simplex hoặc Bland's Rule.")

    def export_solution_txt(self) -> None:
        # Xuất nội dung vùng lời giải ra file .txt.
        content = self.output.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showinfo("Xuất file .txt", "Chưa có lời giải để xuất.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu nội dung lời giải",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile="loi_giai.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            self.status_var.set(f"Đã xuất file: {path}")
        except Exception as exc:
            messagebox.showerror("Lỗi xuất file", str(exc))

    def open_solution_html(self) -> None:
        """Xuất lời giải đầy đủ ra HTML+KaTeX và mở trong trình duyệt mặc định."""
        if self.last_report is None:
            messagebox.showinfo("Xem HTML", "Chưa có lời giải. Vui lòng chạy giải thuật trước.")
            return
        try:
            self.status_var.set("Đang tạo file HTML…")
            self.update_idletasks()
            path = export_report_html(self.last_report, self.data_mode.get())
            url = f"file:///{path.replace(os.sep, '/')}"
            webbrowser.open(url)
            self.status_var.set(f"Đã mở trình duyệt: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Lỗi xuất HTML", str(exc))
            self.status_var.set("Lỗi khi tạo file HTML.")


    def _boundary_text(self, coeffs, sense: str, rhs: Fraction) -> str:
        # Tạo chuỗi biểu diễn một ràng buộc dạng "a·x₁ + b·x₂ sense rhs" để hiển thị chú thích trên biểu đồ 2D.
        a, b = coeffs
        parts = []
        mode = self.data_mode.get()
        if a != 0:
            parts.append(f"{fmt_num(a, mode)}x₁")
        if b != 0:
            sign = "+" if b > 0 and parts else ""
            parts.append(f"{sign}{fmt_num(b, mode)}x₂")
        lhs = " ".join(parts).replace("+ -", "- ") or "0"
        return f"{lhs} {sense} {fmt_num(rhs, mode)}"

    def _build_halfplanes(self, prob: ProblemData):
        # Chuyển danh sách ràng buộc + điều kiện dấu biến thành danh sách nửa mặt phẳng (a, b, rhs, sense, nhãn). Dùng để vẽ vùng chấp nhận được trên đồ thị 2D. Điều kiện dấu biến (≥0 / ≤0 / tự do) được thêm vào như các ràng buộc trục tọa độ.
        halfplanes = []
        for i, cons in enumerate(prob.constraints, start=1):
            a = fr(cons["coeffs"][0])
            b = fr(cons["coeffs"][1])
            rhs = fr(cons["rhs"])
            sense = sense_to_standard(cons["sense"])
            halfplanes.append((a, b, rhs, sense, f"RB{i}"))
        s0, s1 = prob.var_signs[0], prob.var_signs[1]
        if s0 == "≥0":
            halfplanes.append((Fraction(1), Fraction(0), Fraction(0), "≥", "x₁ ≥ 0"))
        elif s0 == "≤0":
            halfplanes.append((Fraction(1), Fraction(0), Fraction(0), "≤", "x₁ ≤ 0"))
        if s1 == "≥0":
            halfplanes.append((Fraction(0), Fraction(1), Fraction(0), "≥", "x₂ ≥ 0"))
        elif s1 == "≤0":
            halfplanes.append((Fraction(0), Fraction(1), Fraction(0), "≤", "x₂ ≤ 0"))
        return halfplanes

    def _is_feasible_point(self, x, y, halfplanes, tol=1e-8):
        # Kiểm tra điểm (x, y) có thỏa tất cả nửa mặt phẳng không.
        for a, b, c, sense, _ in halfplanes:
            lhs = float(a)*x + float(b)*y
            cc = float(c)
            if sense == "≤" and lhs > cc+tol: return False
            if sense == "≥" and lhs < cc-tol: return False
            if sense == "=" and abs(lhs-cc) > tol: return False
        return True

    def _compute_feasible_vertices(self, halfplanes):
        # Tính tất cả đỉnh của miền chấp nhận được bằng cách giao từng cặp đường thẳng, sau đó lọc lại chỉ giữ các giao điểm thỏa toàn bộ ràng buộc còn lại.
        lines = [(a, b, c, lbl) for a, b, c, _, lbl in halfplanes]
        vertices = []
        for i in range(len(lines)):
            a1, b1, c1, _ = lines[i]
            for j in range(i+1, len(lines)):
                a2, b2, c2, _ = lines[j]
                det = float(a1*b2 - a2*b1)
                if abs(det) < 1e-12: continue
                x = float((c1*b2 - c2*b1)/det)
                y = float((a1*c2 - a2*c1)/det)
                if math.isfinite(x) and math.isfinite(y) and \
                   self._is_feasible_point(x, y, halfplanes):
                    vertices.append((x, y))
        return vertices

    def _deduplicate_points(self, points, eps=1e-7):
        # Loại bỏ các điểm trùng lặp (trong phạm vi eps) để tránh vẽ đỉnh hai lần.
        unique = []
        for p in points:
            if not any(abs(p[0]-q[0]) <= eps and abs(p[1]-q[1]) <= eps
                       for q in unique):
                unique.append(p)
        return unique

    def _compute_plot_bounds(self, vertices, halfplanes):
        # Tính khung nhìn (xmin, xmax, ymin, ymax) để đồ thị bao phủ toàn bộ miền khả thi.
        # Luôn đảm bảo gốc tọa độ (0, 0) nằm trong khung nhìn.
        if vertices:
            xs = [p[0] for p in vertices]; ys = [p[1] for p in vertices]
            sx = max(xs)-min(xs); sy = max(ys)-min(ys)
            px = max(0.9, sx*0.18) if len(xs) > 1 else max(1.4, abs(xs[0])*0.35+1)
            py = max(0.9, sy*0.18) if len(ys) > 1 else max(1.4, abs(ys[0])*0.35+1)
            xmin, xmax = min(xs)-px, max(xs)+px
            ymin, ymax = min(ys)-py, max(ys)+py
            xmin, ymin = min(xmin, 0.), min(ymin, 0.)
            xmax, ymax = max(xmax, 0.), max(ymax, 0.)
        else:
            xmin, xmax, ymin, ymax = -5., 5., -5., 5.
        xr, yr = xmax-xmin, ymax-ymin
        return xmin-0.22*xr, xmax+0.22*xr, ymin-0.22*yr, ymax+0.22*yr

    def _create_meshgrid(self, xmin, xmax, ymin, ymax):
        # Tạo lưới 220×220 điểm bao phủ khung nhìn để tô màu miền chấp nhận bằng contourf.
        import numpy as np
        x = np.linspace(xmin, xmax, 220)
        y = np.linspace(ymin, ymax, 220)
        X, Y = np.meshgrid(x, y)
        return x, y, X, Y

    def _compute_feasible_region(self, halfplanes, X, Y):
        # Tính mảng boolean mask: True tại điểm (X[i,j], Y[i,j]) nếu thuộc miền khả thi.
        import numpy as np
        mask = np.ones_like(X, dtype=bool)
        for a, b, c, sense, _ in halfplanes:
            lhs = float(a)*X + float(b)*Y; cc = float(c)
            if sense == "≤": mask &= lhs <= cc+1e-9
            elif sense == "≥": mask &= lhs >= cc-1e-9
            else: mask &= np.abs(lhs-cc) <= 1e-2
        return mask

    def _find_optimal_vertex(self, vertex_values, maximize):
        # Tìm đỉnh tối ưu trong danh sách (x, y, z): max z nếu maximize, min z nếu minimize.
        if not vertex_values: return None
        return max(vertex_values, key=lambda t: t[2]) if maximize \
               else min(vertex_values, key=lambda t: t[2])

    def _request_canvas_redraw(self, canvas, delay_ms=14):
        # Đặt lịch vẽ lại canvas sau delay_ms mili-giây bằng widget.after().
        widget = canvas.get_tk_widget()
        if getattr(widget, "_redraw_job", None) is not None:
            return
        def _do():
            widget._redraw_job = None
            try: canvas.draw_idle()
            except Exception: pass
        widget._redraw_job = widget.after(delay_ms, _do)

    def _line_box_intersections(self, a, b, c, xmin, xmax, ymin, ymax):
        # Tính giao điểm của đường thẳng a·x + b·y = c với các cạnh của hộp giới hạn [xmin, xmax] × [ymin, ymax]. Trả về danh sách điểm nằm trong hộp.
        # Dùng để xác định đoạn thẳng cần vẽ cho từng ràng buộc / đường đồng mức.
        eps = 1e-12; pts = []
        def add(pt):
            x, y = pt
            if math.isfinite(x) and math.isfinite(y) \
               and xmin-1e-9 <= x <= xmax+1e-9 \
               and ymin-1e-9 <= y <= ymax+1e-9:
                for qx, qy in pts:
                    if abs(qx-x) <= 1e-7 and abs(qy-y) <= 1e-7: return
                pts.append((x, y))
        fa, fb, fc = float(a), float(b), float(c)
        if abs(fb) > eps:
            add((xmin, (fc-fa*xmin)/fb)); add((xmax, (fc-fa*xmax)/fb))
        if abs(fa) > eps:
            add(((fc-fb*ymin)/fa, ymin)); add(((fc-fb*ymax)/fa, ymax))
        return pts


    def visualize_two_variable_problem(self) -> None:
        # Mở cửa sổ trực quan hóa 2 biến với giao diện đồng bộ phong cách 3D:
        #   - nền tối, khung nội dung lớn
        #   - bảng thông tin nổi ở góc phải
        #   - thanh điều khiển ở dưới
        #   - giữ nguyên đầy đủ chức năng pan / zoom / reset
        try:
            prob = self._collect_problem()
        except Exception as exc:
            messagebox.showerror("Trực quan hóa", str(exc))
            return
        if len(prob.obj_coeffs) != 2:
            messagebox.showinfo(
                "Trực quan hóa",
                "Tính năng này chỉ hỗ trợ đúng 2 biến x₁ và x₂."
            )
            return

        try:
            import numpy as np
            import matplotlib
            matplotlib.use("TkAgg", force=True)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except Exception as exc:
            messagebox.showerror(
                "Trực quan hóa",
                f"Không khởi tạo được thư viện: {exc}"
            )
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

        win = self._create_visualization_window()
        outer = tk.Frame(win, bg="#0f172a")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        canvas_host = tk.Frame(outer, bg="#0f172a")
        canvas_host.grid(row=0, column=0, sticky="nsew")
        canvas_host.rowconfigure(0, weight=1)
        canvas_host.columnconfigure(0, weight=1)

        fig, ax = self._create_figure()
        self._plot_feasible_region(ax, X, Y, feasible_mask)
        self._plot_constraints(ax, halfplanes, xmin, xmax, ymin, ymax)
        self._plot_objective_contours(ax, c1, c2, vertex_values,
                                      xmin, xmax, ymin, ymax, maximize)
        self._plot_vertices(ax, vertex_values, maximize)
        self._plot_optimal_point(ax, optimal_point, maximize)
        self._configure_axes(ax, xmin, xmax, ymin, ymax)

        canvas = FigureCanvasTkAgg(fig, master=canvas_host)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.configure(bg="#0f172a", highlightthickness=0, bd=0)
        canvas_widget.grid(row=0, column=0, sticky="nsew")

        self._create_info_panel(canvas_host, prob, vertices, vertex_values,
                                 optimal_point, maximize)
        self._create_zoom_controls(outer, ax, canvas, (xmin, xmax), (ymin, ymax))
        self._enable_canvas_interactions(ax, canvas)
        win.focus_force()


    def _create_visualization_window(self):
        # Tạo cửa sổ Toplevel riêng biệt cho trực quan hóa với giao diện tối, đồng bộ 2D/3D.
        top = tk.Toplevel(self)
        top.title("Trực quan hóa bài toán 2 biến — 2D")
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
        top.configure(bg="#0f172a")
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        top.protocol("WM_DELETE_WINDOW", top.destroy)
        return top


    def _create_figure(self):
        # Khởi tạo Figure và Axes matplotlib theo phong cách tối, mượt hơn.
        from matplotlib.figure import Figure
        fig = Figure(figsize=(15.6, 9.2), dpi=110)
        fig.patch.set_facecolor("#0f172a")
        fig.subplots_adjust(left=0.055, right=0.985, top=0.94, bottom=0.09)
        ax = fig.add_subplot(111)
        ax.set_facecolor("#111827")
        ax.set_axisbelow(True)
        ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.18, color="#64748b")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#475569")
        ax.spines["bottom"].set_color("#475569")
        ax.tick_params(colors="#cbd5e1", labelsize=9)
        return fig, ax


    def _plot_feasible_region(self, ax, X, Y, mask):
        # Tô vùng chấp nhận được với lớp màu dịu và viền mềm để nhìn “mượt” hơn.
        z = mask.astype(float)
        ax.contourf(
            X, Y, z,
            levels=[0.5, 1.5],
            colors=["#0ea5e9"],
            alpha=0.14,
            antialiased=True,
            zorder=0,
        )
        ax.contour(
            X, Y, z,
            levels=[0.5],
            colors=["#38bdf8"],
            linewidths=1.2,
            alpha=0.38,
            zorder=0.2,
        )


    def _plot_constraints(self, ax, halfplanes, xmin, xmax, ymin, ymax):
        # Vẽ ràng buộc theo kiểu có “glow” nhẹ để đồng bộ với giao diện 3D.
        palette = ["#60a5fa", "#a78bfa", "#14b8a6", "#f59e0b", "#fb7185", "#22d3ee"]
        seen = set()
        for idx, (a, b, c, sense, label) in enumerate(halfplanes):
            color = palette[idx % len(palette)]
            pts = self._line_box_intersections(a, b, c, xmin, xmax, ymin, ymax)
            if len(pts) < 2:
                continue
            pts = sorted(pts, key=lambda p: (p[0], p[1]))
            (x1, y1), (x2, y2) = pts[0], pts[-1]

            # Lớp nền mờ giúp đường trông dày và mượt hơn.
            ax.plot([x1, x2], [y1, y2],
                    color=color, linewidth=5.2, alpha=0.10,
                    solid_capstyle="round", zorder=1.8)
            ax.plot([x1, x2], [y1, y2],
                    color=color, linewidth=2.8, alpha=0.96,
                    solid_capstyle="round", zorder=2.4)

            if label not in seen:
                seen.add(label)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                dx, dy = 0.014 * (xmax - xmin), 0.014 * (ymax - ymin)
                ax.text(
                    mx + dx, my + dy, label,
                    fontsize=9, color=color, weight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        fc="#0f172a",
                        ec=color,
                        lw=1.0,
                        alpha=0.9,
                    ),
                    zorder=3,
                )


    def _plot_objective_contours(self, ax, c1, c2, vv, xmin, xmax, ymin, ymax, maximize):
        # Vẽ các đường đồng mức hàm mục tiêu với độ tương phản vừa phải,
        # đường tối ưu nổi bật hơn nhưng không quá gắt.
        if not vv or abs(c1) + abs(c2) < 1e-12:
            return

        zvals = sorted(v[2] for v in vv)
        z_best = max(zvals) if maximize else min(zvals)
        spread = max(1.0, abs(zvals[-1] - zvals[0]) if len(zvals) > 1 else abs(z_best) or 1.0)
        levels = [z_best - 1.2 * spread, z_best - 0.65 * spread, z_best - 0.22 * spread,
                  z_best, z_best + 0.22 * spread, z_best + 0.65 * spread, z_best + 1.2 * spread]

        for lv in levels:
            pts = self._line_box_intersections(
                Fraction(str(c1)), Fraction(str(c2)), Fraction(str(lv)),
                xmin, xmax, ymin, ymax
            )
            if len(pts) < 2:
                continue
            pts = sorted(pts, key=lambda p: (p[0], p[1]))
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            is_best = abs(lv - z_best) < 1e-9

            ax.plot(
                [x1, x2], [y1, y2],
                color="#f59e0b" if is_best else "#93c5fd",
                linewidth=3.0 if is_best else 1.4,
                linestyle="-" if is_best else "--",
                alpha=0.92 if is_best else 0.22,
                zorder=1.5,
            )
            if is_best:
                tx, ty = (x1 + x2) / 2, (y1 + y2) / 2
                ax.text(
                    tx, ty,
                    f"  z = {fmt_num(Fraction(str(lv)), self.data_mode.get())}",
                    color="#e2e8f0",
                    fontsize=9,
                    weight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.28",
                        fc="#1e293b",
                        ec="#f59e0b",
                        alpha=0.95,
                    ),
                    zorder=4,
                )


    def _plot_vertices(self, ax, vv, maximize):
        # Tô đa giác các đỉnh khả thi và gắn số thứ tự với nhãn rõ hơn.
        if not vv:
            return
        pts = list(vv)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda t: math.atan2(t[1] - cy, t[0] - cx))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        ax.fill(xs, ys, color="#38bdf8", alpha=0.10, zorder=1.0)
        ax.plot(xs + [xs[0]], ys + [ys[0]],
                color="#93c5fd", linewidth=1.2,
                linestyle=":", alpha=0.50, zorder=2.2)

        for idx, (vx, vy, val) in enumerate(pts, start=1):
            ax.scatter([vx], [vy], s=58, color="#e2e8f0",
                       edgecolors="#0f172a", linewidths=1.0, zorder=5)
            ax.scatter([vx], [vy], s=24, color="#60a5fa",
                       edgecolors="none", zorder=5.1)
            ax.annotate(
                f"{idx}",
                xy=(vx, vy),
                xytext=(7, 7),
                textcoords="offset points",
                fontsize=9,
                color="#e2e8f0",
                bbox=dict(boxstyle="circle,pad=0.20", fc="#1e293b", ec="#60a5fa", alpha=0.96),
                zorder=6,
            )


    def _plot_optimal_point(self, ax, optimal, maximize):
        # Đánh dấu điểm tối ưu nổi bật hơn, đồng thời giữ tông màu hài hòa.
        if optimal is None:
            return
        bx, by, bz = optimal
        ax.scatter([bx], [by], s=340, marker="*", color="#f59e0b",
                   edgecolors="#0f172a", linewidths=1.2, zorder=7)
        ax.scatter([bx], [by], s=120, marker="o", facecolors="none",
                   edgecolors="#fde68a", linewidths=1.8, zorder=6.9)
        ax.annotate(
            f"Điểm tối ưu\n({bx:.3g}, {by:.3g})\nz = {bz:.3g}",
            xy=(bx, by),
            xytext=(14, 18),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
            color="#e2e8f0",
            bbox=dict(boxstyle="round,pad=0.38", fc="#1e293b", ec="#f59e0b", alpha=0.97),
            arrowprops=dict(arrowstyle="->", color="#f59e0b", lw=1.5),
            zorder=8,
        )


    def _configure_axes(self, ax, xmin, xmax, ymin, ymax):
        # Thiết lập trục theo phong cách tối, đồng bộ với 3D.
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("auto", adjustable="box")
        ax.set_xlabel("x₁", fontsize=12, fontweight="bold", color="#e2e8f0")
        ax.set_ylabel("x₂", fontsize=12, fontweight="bold", color="#e2e8f0")
        ax.set_title(
            "Miền chấp nhận được và đường đồng mức hàm mục tiêu",
            fontsize=14,
            fontweight="bold",
            pad=12,
            color="#e2e8f0",
        )

        ax.axhline(0, color="#64748b", linewidth=1.0, alpha=0.55, zorder=0.5)
        ax.axvline(0, color="#64748b", linewidth=1.0, alpha=0.55, zorder=0.5)

        ax.tick_params(colors="#cbd5e1", labelsize=9)

        hs, ls = ax.get_legend_handles_labels()
        if hs:
            ax.legend(
                hs, ls,
                loc="upper left",
                frameon=True,
                fontsize=9,
                title="Ràng buộc",
                title_fontsize=10,
                fancybox=True,
                shadow=False,
                facecolor="#0f172a",
                edgecolor="#334155",
                labelcolor="#e2e8f0",
            )


    def _create_control_button(self, parent, text, color, hover_color, command):
        # Tạo nút tkinter với hiệu ứng hover gọn và sắc nét hơn.
        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9, "bold"),
            bg=color,
            fg="white",
            activebackground=hover_color,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=command,
        )
        btn.pack(side="left", padx=4, pady=4)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        return btn


    def _enable_canvas_interactions(self, ax, canvas):
        # Gắn các sự kiện chuột vào canvas matplotlib:
        #   - Kéo nút trái: pan (di chuyển khung nhìn)
        #   - Lăn chuột: zoom vào/ra quanh vị trí con trỏ
        state = {"press": None}

        def clamp():
            xm, xx = ax.get_xlim()
            ym, yx = ax.get_ylim()
            if xx - xm < 1e-6:
                ax.set_xlim(xm - 1, xx + 1)
            if yx - ym < 1e-6:
                ax.set_ylim(ym - 1, yx + 1)

        def on_press(ev):
            if ev.inaxes != ax or ev.button != 1 or ev.xdata is None:
                return
            state["press"] = (ev.xdata, ev.ydata, ax.get_xlim(), ax.get_ylim())

        def on_release(ev):
            state["press"] = None

        def on_move(ev):
            if not state["press"] or ev.inaxes != ax or ev.xdata is None:
                return
            x0, y0, xl, yl = state["press"]
            ax.set_xlim(xl[0] + x0 - ev.xdata, xl[1] + x0 - ev.xdata)
            ax.set_ylim(yl[0] + y0 - ev.ydata, yl[1] + y0 - ev.ydata)
            clamp()
            self._request_canvas_redraw(canvas)

        def on_scroll(ev):
            if ev.inaxes != ax or ev.xdata is None:
                return
            base = 1.08 if getattr(ev, "button", None) == "down" else 1 / 1.08
            xl = ax.get_xlim()
            yl = ax.get_ylim()
            xd, yd = ev.xdata, ev.ydata
            nw = (xl[1] - xl[0]) * base
            nh = (yl[1] - yl[0]) * base
            rx = (xl[1] - xd) / (xl[1] - xl[0])
            ry = (yl[1] - yd) / (yl[1] - yl[0])
            ax.set_xlim(xd - (1 - rx) * nw, xd + rx * nw)
            ax.set_ylim(yd - (1 - ry) * nh, yd + ry * nh)
            clamp()
            self._request_canvas_redraw(canvas)

        canvas.mpl_connect("button_press_event", on_press)
        canvas.mpl_connect("button_release_event", on_release)
        canvas.mpl_connect("motion_notify_event", on_move)
        canvas.mpl_connect("scroll_event", on_scroll)


    def _create_zoom_controls(self, parent, ax, canvas, initial_xlim, initial_ylim):
        # Thanh điều khiển phía dưới với cùng tông màu tối như phần trực quan hóa 3D.
        ctrl = tk.Frame(parent, bg="#1e293b")
        ctrl.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ctrl.columnconfigure(0, weight=1)

        btn_frame = tk.Frame(ctrl, bg="#1e293b")
        btn_frame.pack(side="left", padx=12, pady=6)

        def reset_view():
            ax.set_xlim(initial_xlim)
            ax.set_ylim(initial_ylim)
            self._request_canvas_redraw(canvas)

        def fit_view():
            x1, x2 = ax.get_xlim()
            y1, y2 = ax.get_ylim()
            dx = (x2 - x1) * 0.14
            dy = (y2 - y1) * 0.14
            ax.set_xlim(x1 + dx, x2 - dx)
            ax.set_ylim(y1 + dy, y2 - dy)
            self._request_canvas_redraw(canvas)

        def toggle_grid():
            ax.grid(not ax.get_xgridlines()[0].get_visible())
            self._request_canvas_redraw(canvas)

        self._create_control_button(btn_frame, "Mặc định", "#334155", "#475569", reset_view)
        self._create_control_button(btn_frame, "Fit", "#1d4ed8", "#1e40af", fit_view)
        self._create_control_button(btn_frame, "Lưới", "#64748b", "#475569", toggle_grid)

        tk.Label(
            ctrl,
            text="Kéo chuột trái để pan -- Lăn chuột để zoom -- Nút Fit để thu khung nhìn",
            bg="#1e293b",
            fg="#94a3b8",
            font=("Segoe UI", 9),
        ).pack(side="right", padx=16)


    def _create_info_panel(self, parent, prob, vertices, vv, optimal, maximize):
        # Bảng tóm tắt kiểu 3D: tối, gọn, và có đủ thông tin quan trọng để người dùng đọc nhanh.
        info_frame = tk.Frame(
            parent,
            bg="#111827",
            bd=0,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        info_frame.place(relx=0.985, rely=0.02, anchor="ne", width=340, height=214)

        title = tk.Label(
            info_frame,
            text="Tóm tắt",
            bg="#111827",
            fg="#e2e8f0",
            font=("Segoe UI", 11, "bold"),
        )
        title.pack(anchor="w", padx=10, pady=(8, 2))

        text = tk.Text(
            info_frame,
            wrap="word",
            bg="#111827",
            fg="#cbd5e1",
            insertbackground="#cbd5e1",
            bd=0,
            font=("Segoe UI", 9),
            height=10,
            padx=10,
            pady=6,
            highlightthickness=0,
        )
        text.pack(fill="both", expand=True)

        lines = [
            f"Kiểu: {'Bài toán Max' if prob.objective_sense == 'max' else 'Bài toán Min'}",
            f"Số ràng buộc: {len(prob.constraints)}",
            f"Số đỉnh khả thi: {len(vertices)}",
        ]
        if optimal:
            lines += [
                f"Điểm tối ưu: ({optimal[0]:.3g}, {optimal[1]:.3g})",
                f"Giá trị mục tiêu: {optimal[2]:.3g}",
            ]
        else:
            lines.append("Chưa tìm được miền khả thi.")
        lines += [
            "Kéo chuột trái để pan.",
            "Lăn chuột để zoom.",
            "Dùng nút dưới để Fit / Mặc định / Lưới.",
        ]
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

    def _format_problem(self, engine):
        # Tạo chuỗi hiển thị bài toán gốc (trước chuẩn hóa):
        # Căn thẳng cột: cụm (hệ số·biến) của từng biến thẳng nhau, dấu ≤/≥/= thẳng, RHS thẳng.
        mode = self.data_mode.get()
        prob = engine.problem
        n = len(prob.obj_coeffs)
        var_names = [f"x{i+1}" for i in range(n)]

        def fmt_coeff(c):
            """Định dạng hệ số tuyệt đối (không có dấu)."""
            return fmt_num(abs(c), mode)

        def build_terms(coeffs):
            """Trả về list (sign_str, body_str) cho từng hạng tử khác 0."""
            terms = []
            for c, nm in zip(coeffs, var_names):
                if c == 0:
                    continue
                sign = "+" if c > 0 else "-"
                if abs(c) == 1:
                    body = nm
                else:
                    body = f"{fmt_coeff(c)}{nm}"
                terms.append((sign, body))
            return terms

        # ── Thu thập tất cả hàng để tính độ rộng cột ────────────────────
        # Mỗi hàng là list các (sign, body) theo thứ tự biến
        def row_cells(coeffs):
            """Với mỗi biến xj, trả về chuỗi hiển thị cho ô đó (có thể rỗng)."""
            cells = []
            for c, nm in zip(coeffs, var_names):
                if c == 0:
                    cells.append(("", ""))
                else:
                    sign = "+" if c > 0 else "-"
                    body = nm if abs(c) == 1 else f"{fmt_coeff(c)}{nm}"
                    cells.append((sign, body))
            return cells

        obj_cells   = row_cells(prob.obj_coeffs)
        cons_cells  = [row_cells(cons["coeffs"]) for cons in prob.constraints]
        all_cells   = [obj_cells] + cons_cells

        # Độ rộng mỗi cột (sign + body gộp lại, ví dụ "- 3/2x2")
        col_w = []
        for j in range(n):
            w = 0
            for row in all_cells:
                sign, body = row[j]
                cell_str = f"{sign} {body}" if sign else ""
                w = max(w, len(cell_str))
            col_w.append(max(w, len(var_names[j]) + 2))  # tối thiểu đủ chứa tên biến

        # Độ rộng RHS
        rhs_strs = [fmt_num(cons["rhs"], mode) for cons in prob.constraints]
        rhs_w = max((len(s) for s in rhs_strs), default=1)

        def render_row(cells):
            """Ghép một hàng đã căn phải theo col_w."""
            parts = []
            first_nonzero = True
            for j, (sign, body) in enumerate(cells):
                if not sign:  # hệ số = 0, điền khoảng trắng
                    parts.append(" " * col_w[j])
                else:
                    if first_nonzero and sign == "+":
                        cell_str = body          # hạng tử đầu bỏ dấu +
                    else:
                        cell_str = f"{sign} {body}"
                    parts.append(cell_str.rjust(col_w[j]))
                    first_nonzero = False
            return "  ".join(parts).rstrip()

        sense_label = "max" if prob.objective_sense == "max" else "min"
        obj_line = f"    {sense_label} Z = {render_row(obj_cells)}"

        # Căn dấu ràng buộc và RHS
        sense_w = 1  # "≤" / "≥" / "=" đều 1 ký tự
        con_lines = []
        for i, cons in enumerate(prob.constraints):
            lhs  = render_row(cons_cells[i])
            s    = cons["sense"]
            rhs  = rhs_strs[i].rjust(rhs_w)
            con_lines.append(f"      {lhs}  {s}  {rhs}")

        # Điều kiện dấu biến
        sign_parts = []
        for i, sg in enumerate(prob.var_signs):
            nm = f"x{i+1}"
            if sg == "≥0":     sign_parts.append(f"{nm} ≥ 0")
            elif sg == "≤0":   sign_parts.append(f"{nm} ≤ 0")
            else:              sign_parts.append(f"{nm} tự do")

        lines = [
            "Bài tập Quy Hoạch Tuyến Tính — Phương pháp Đơn hình",
            "  Bài toán gốc:",
            obj_line,
            "    s.t. {",
        ]
        lines += con_lines
        lines.append(f"      {',  '.join(sign_parts)}")
        lines.append("    }")
        return "\n".join(lines)

    def _format_standardization(self, engine):
        # Tạo chuỗi giải thích từng bước chuẩn hóa:
        #   - Biến tự do / âm được thay thế bằng biến phụ
        #   - Ràng buộc ≥ nhân (-1), ràng buộc = thêm biến bù
        #   - Hàm max nhân (-1) để đưa về dạng min
        mode = self.data_mode.get()
        def expr(coeffs, names):
            parts=[]
            for c,nm in zip(coeffs,names):
                if c==0: continue
                if c==1: parts.append(f"+ {nm}")
                elif c==-1: parts.append(f"- {nm}")
                elif c>0: parts.append(f"+ {fmt_num(c,mode)}{nm}")
                else: parts.append(f"- {fmt_num(-c,mode)}{nm}")
            if not parts: return "0"
            s=" ".join(parts)
            return s[2:] if s.startswith("+ ") else s
        n_orig=len(engine.problem.var_signs)
        extra_x=[nm for nm in engine.std_names if nm.startswith("x") and nm not in {f"x{i+1}" for i in range(n_orig)}]
        lines=["========================","*Chuẩn hóa bài toán gốc:","========================","","_Chuẩn hóa ràng buộc dấu:"]
        for idx,sign in enumerate(engine.problem.var_signs):
            nm=f"x{idx+1}"
            if sign=="≥0": lines.append(f"        {nm} ≥ 0: giữ nguyên {nm} ≥ 0")
            elif sign=="≤0": lines.append(f"        {nm} tự do âm: đặt {nm} = -y{idx+1}, với y{idx+1} ≥ 0")
            else: lines.append(f"        {nm} tự do: đặt {nm} = a{idx+1} - b{idx+1}, với a{idx+1}, b{idx+1} ≥ 0")
        lines+=["","_Chuẩn hóa ràng buộc đẳng thức, bất đẳng thức:"]
        sc=n_orig+1
        for i,cons in enumerate(engine.problem.constraints):
            s=cons["sense"]
            if s=="≤": lines.append(f"    RB{i+1}: giữ nguyên")
            elif s=="≥": lines.append(f"    RB{i+1}: nhân (-1) để đưa về ≤")
            else:
                snm=f"x{sc}"; sc+=1
                lines.append(f"    RB{i+1}: trừ thêm biến bù {snm} ≥ 0")
                row=engine.std_constraints[i]; names=engine.std_names[:len(row)]
                lines.append(f"    ---> RB{i+1}:  {expr(row,names)} ≤ {fmt_num(engine.std_rhs[i],mode)}")
        lines+=["","_Các biến sau chuẩn hóa:"]
        for idx,sign in enumerate(engine.problem.var_signs):
            if sign=="≥0": lines.append(f"        x{idx+1} = x{idx+1}")
            elif sign=="≤0": lines.append(f"        x{idx+1} = -y{idx+1}")
            else: lines.append(f"        x{idx+1} = a{idx+1} - b{idx+1}")
        for nm in extra_x: lines.append(f"        {nm} = {nm}")
        lines+=["","_Chuẩn hóa hàm mục tiêu:"]
        if engine.problem.objective_sense=="min": lines.append("    Hàm min, giữ nguyên:")
        else: lines.append("    Hàm max → nhân (-1):")
        obj_expr=expr(engine.std_obj_coeffs, engine.std_names)
        lines.append(f"        min Z = {obj_expr}")
        lines+=["","=========================","*Dạng chuẩn của bài toán:","=========================",f"    min Z = {obj_expr}","    {"]
        for i,row in enumerate(engine.std_constraints):
            lines.append(f"      {expr(row,engine.std_names[:len(row)])} ≤ {fmt_num(engine.std_rhs[i],mode)}")
        slack_names=[nm for nm in engine.std_names if nm.startswith("x") and nm not in {f"x{i+1}" for i in range(n_orig)}]
        aux_names=[nm for nm in engine.std_names if not nm.startswith("x")]
        var_list=[f"x{i+1}" for i in range(n_orig)]+slack_names+aux_names
        lines.append(f"    {', '.join(var_list)} ≥ 0")
        lines.append("    }")
        return "\n".join(lines)

    def _dict_lines(self, snapshot):
        # Tạo danh sách dòng cho bảng từ vựng.
        # Mỗi cột biến có độ rộng = max độ rộng hạng tử thực tế trên tất cả hàng.
        # Khoảng cách giữa các cột = GAP cố định (không phụ thuộc nội dung).
        # Bỏ separator │ để gọn hơn.
        GAP = 2          # số khoảng trắng giữa hai cột liền kề
        mode = self.data_mode.get()
        names = snapshot.all_names

        all_rows = [(snapshot.objective_label, snapshot.obj_const, snapshot.obj)]
        for i, b in enumerate(snapshot.basis):
            all_rows.append((names[b], snapshot.rhs[i], snapshot.rows[i]))

        # Độ rộng cột nhãn và cột hằng số
        label_w = max(len(row[0]) for row in all_rows)
        const_strs = [fmt_num(row[1], mode) for row in all_rows]
        const_w = max(len(s) for s in const_strs)

        # Độ rộng mỗi cột biến: max độ rộng hạng tử (kể cả "0" nếu hệ số = 0 được bỏ → ô trống)
        # Hạng tử rỗng ("") vẫn cần giữ chỗ bằng đúng độ rộng cột → không dùng ljust mà dùng rjust
        col_w = []
        col_cells = []   # col_cells[row_idx][col_idx] = chuỗi hạng tử (có thể rỗng)
        for _ in all_rows:
            col_cells.append([])

        for j, name in enumerate(names):
            w = 0
            for ri, (_, _, coeffs) in enumerate(all_rows):
                s = term_str(coeffs.get(j, Fraction(0)), name, mode)
                col_cells[ri].append(s)
                w = max(w, len(s))
            col_w.append(w)   # độ rộng thực tế tối thiểu; có thể bằng 0 nếu cột toàn rỗng

        def line_for(ri, label, const_s):
            label_part = label.ljust(label_w)
            const_part = const_s.rjust(const_w)
            # Mỗi ô: ljust theo col_w[j] (giữ chỗ cho ô rỗng)
            term_parts = [col_cells[ri][j].ljust(col_w[j]) for j in range(len(names))]
            # Ghép bằng GAP khoảng trắng, sau đó rstrip để bỏ trailing spaces
            term_part = (" " * GAP).join(term_parts).rstrip()
            return f"{label_part} = {const_part}    {term_part}"

        lines = []
        for ri, ((label, const, coeffs), const_s) in enumerate(zip(all_rows, const_strs)):
            lines.append(line_for(ri, label, const_s))
        return lines

    def _insert_snapshot(self, snapshot, title, tags=None):
        # Chèn tiêu đề và bảng từ vựng vào output ScrolledText.
        # Nếu có tags (entering / pivot_row), áp dụng highlight màu:
        #   pivotcol  → tất cả ô cột biến vào
        #   pivotrow  → toàn bộ hàng biến ra
        #   pivotcell → ô giao (phần tử xoay)
        self.output.insert(tk.END, title+"\n","h2")
        start=self.output.index(tk.END)
        for line in self._dict_lines(snapshot):
            self.output.insert(tk.END, line+"\n","mono")
        if tags and snapshot.all_names:
            var_name=tags.get("entering"); pivot_row=tags.get("pivot_row")
            if var_name:
                end=self.output.index(tk.END); idx=start
                while True:
                    pos=self.output.search(var_name,idx,stopindex=end)
                    if not pos: break
                    self.output.tag_add("pivotcol",pos,f"{pos}+{len(var_name)}c")
                    idx=f"{pos}+{len(var_name)}c"
            if pivot_row is not None:
                rn=int(start.split(".")[0])+int(pivot_row)
                self.output.tag_add("pivotrow",f"{rn}.0",f"{rn}.end")
                if var_name:
                    lt=self.output.get(f"{rn}.0",f"{rn}.end"); p=lt.find(var_name)
                    if p!=-1: self.output.tag_add("pivotcell",f"{rn}.{p}",f"{rn}.{p+len(var_name)}")

    def _insert_step_note(self, step, snapshot):
        # In giải thích chi tiết một bước xoay: quy tắc chọn biến vào (Dantzig/Bland), bảng tỉ số θ để chọn biến ra, phần tử xoay, và cờ suy biến nếu θ = 0.
        mode=self.data_mode.get(); names=snapshot.all_names
        enter=names[step.entering] if step.entering is not None else "?"
        leave=names[step.leaving_var] if step.leaving_var is not None else "?"
        rule="Dantzig" if step.method=="dantzig" else "Bland"
        if step.status=="phase1_aux_pivot":
            self.output.insert(tk.END,"Theo quy tắc Dantzig:\n","h2")
            self.output.insert(tk.END,"— Pha 1: x0 là biến vào, biến ra là hàng có b_i âm.\n","note")
            if step.ratios:
                self.output.insert(tk.END,"— Xét các b_i âm:\n","note")
                for ri,bval,bi in step.ratios:
                    self.output.insert(tk.END,f"  • {names[bi]}: {fmt_num(bval,mode)}\n","note")
            self.output.insert(tk.END,f"  ⟹ biến vào: {enter}\n  ⟹ biến ra: {leave}\n","note")
            if step.pivot_value is not None:
                self.output.insert(tk.END,f"— Phần tử xoay: a_{{{leave},{enter}}} = {fmt_num(step.pivot_value,mode)}.\n","note")
            if step.degenerate: self.output.insert(tk.END,"— Bước suy biến (θ=0).\n","warn")
            return
        self.output.insert(tk.END,f"Theo quy tắc {rule}:\n","h2")
        if step.entering is not None:
            coeff=snapshot.obj.get(step.entering,Fraction(0))
            if step.method=="dantzig":
                self.output.insert(tk.END,f"— Chọn {enter} vì hệ số nhỏ nhất {fmt_num(coeff,mode)}.\n","note")
            else:
                self.output.insert(tk.END,f"— Bland: chọn {enter}.\n","note")
            self.output.insert(tk.END,f"  ⟹ biến vào: {enter}\n","note")
        if step.ratios:
            self.output.insert(tk.END,f"— Tỉ số tại cột {enter}:\n","note")
            for ri,theta,bi in step.ratios:
                coeff=snapshot.rows[ri][step.entering] if step.entering is not None else Fraction(1)
                self.output.insert(tk.END,f"  • {names[bi]}: {fmt_num(snapshot.rhs[ri],mode)} / {fmt_num(-coeff,mode)} = {fmt_num(theta,mode)}\n","note")
            self.output.insert(tk.END,f"  ⟹ biến ra: {leave}\n","note")
        if step.pivot_value is not None:
            self.output.insert(tk.END,f"— Phần tử xoay: a_{{{leave},{enter}}} = {fmt_num(step.pivot_value,mode)}.\n","note")
        if step.degenerate: self.output.insert(tk.END,"— Bước suy biến (θ=0).\n","warn")

    def _linear_text(self, const, terms, mode):
        # Tạo chuỗi biểu diễn biểu thức tuyến tính: hằng số + tổng các hạng tử.
        # Bỏ qua hệ số = 0; xử lý dấu + / - giữa các hạng tử cho đúng ký pháp.
        parts=[]
        if const!=0 or not terms: parts.append(fmt_num(const,mode))
        for coef,name in terms:
            if coef==0: continue
            body=name if abs(coef)==1 else f"{fmt_num(abs(coef),mode)}{name}"
            if parts: parts.append(f"+ {body}" if coef>0 else f"- {body}")
            else: parts.append(body if coef>0 else f"- {body}")
        return " ".join(parts).strip() if parts else "0"

    def _format_multiple_optimal_family(self, engine, snapshot, report):
        # Tạo chuỗi mô tả họ vô số nghiệm tối ưu: biến nào có hệ số 0 trong hàm mục tiêu được dùng làm tham số tự do. Hiển thị z*, biến cơ sở theo tham số đó.
        mode=self.data_mode.get(); free_vars=report.multiple_optimal_vars or []
        if not free_vars: return []
        param_name=snapshot.all_names[free_vars[0]]
        lines=[f"  Do hệ số trước {param_name} bằng 0. Bài toán có vô số nghiệm.\n  Cho các biến mục tiêu bằng 0:","",f"    z = {fmt_num(snapshot.obj_const,mode)}"]
        def row_expr(ri):
            terms=[(snapshot.rows[ri].get(fv,Fraction(0)),snapshot.all_names[fv]) for fv in free_vars if snapshot.rows[ri].get(fv,Fraction(0))!=0]
            return self._linear_text(snapshot.rhs[ri],terms,mode)
        for ri,b in enumerate(snapshot.basis): lines.append(f"    {snapshot.all_names[b]} = {row_expr(ri)}")
        return lines

    def _format_multiple_optimal_conclusion(self, engine, snapshot, report):
        # Tạo phần KẾT LUẬN cho trường hợp vô số nghiệm:
        # Biểu diễn x1..xn theo tham số tự do (biến free_vars) dùng variable_mapping để quy đổi từ biến chuẩn hóa về biến gốc của người dùng.
        mode=self.data_mode.get(); free_vars=report.multiple_optimal_vars or []
        if not free_vars: return []
        lines=["  Nghiệm tối ưu:","  {"]
        bp={b:i for i,b in enumerate(snapshot.basis)}
        def std_expr(idx):
            if idx in bp:
                r=bp[idx]; terms=[(snapshot.rows[r].get(fv,Fraction(0)),snapshot.all_names[fv]) for fv in free_vars if snapshot.rows[r].get(fv,Fraction(0))!=0]
                return snapshot.rhs[r],terms
            if idx in free_vars: return Fraction(0),[(Fraction(1),snapshot.all_names[idx])]
            return Fraction(0),[]
        for orig_idx,mapping in enumerate(engine.variable_mapping):
            if len(mapping)==1 and mapping[0][0] in free_vars and mapping[0][1]==Fraction(1):
                lines.append(f"    x{orig_idx+1} ≥ 0"); continue
            const=Fraction(0); terms=[]
            for si,mc in mapping:
                sc,st=std_expr(si); const+=mc*sc
                for coef,name in st: terms.append((mc*coef,name))
            lines.append(f"    x{orig_idx+1} = {self._linear_text(const,terms,mode)}")
        lines.append("  }"); return lines

    def _render_trace(self, title, trace):
        # In toàn bộ quá trình lặp của một pha (Dantzig hoặc Bland):
        #   - Với mỗi bước: in bảng từ vựng trước xoay (có highlight) → ghi chú bước → bảng sau xoay
        #   - In trạng thái kết thúc: tối ưu / không giới nội / xoay vòng
        if not trace.steps:
            self.output.insert(tk.END,"Từ vựng ban đầu:\n","h2")
            if trace.final_snapshot: self._insert_snapshot(trace.final_snapshot,"")
            return
        for step in trace.steps:
            t="Từ vựng ban đầu:" if step.iteration==1 else f"Bước {step.iteration} trước xoay:"
            self._insert_snapshot(step.before,t,
                tags={"entering":step.before.all_names[step.entering] if step.entering is not None else None,"pivot_row":step.leaving_row} if step.entering is not None else None)
            self.output.insert(tk.END,"\n")
            self._insert_step_note(step,step.before)
            self.output.insert(tk.END,"\n")
            if step.after is not None:
                self._insert_snapshot(step.after,f"Sau xoay bước {step.iteration}:")
                self.output.insert(tk.END,"\n")
        if trace.status=="optimal": self.output.insert(tk.END,"  Các hệ số cải thiện không còn âm → tối ưu.\n","note")
        elif trace.status=="unbounded": self.output.insert(tk.END,"  Bài toán không giới nội.\n","warn")
        elif trace.status=="cycle":
            rule = "Dantzig" if trace.steps and trace.steps[0].method == "dantzig" else "Bland"
            if rule == "Dantzig":
                self.output.insert(tk.END,"  Dantzig phát hiện xoay vòng → dừng và gợi ý dùng Bland.\n","warn")
            else:
                self.output.insert(tk.END,"  Bland phát hiện xoay vòng.\n","warn")

    def _render_result(self, report):
        # Xóa output cũ và in toàn bộ lời giải theo cấu trúc:
        #   1. Bài toán gốc + chuẩn hóa
        #   2. Pha 1 (nếu cần biến phụ x0): trace theo phương pháp đã chọn
        #   3. Pha 2: trace theo phương pháp đã chọn
        #   4. KẾT LUẬN: trạng thái, z*, nghiệm tối ưu (hoặc họ vô số nghiệm)
        self.output.delete("1.0",tk.END)
        engine=report.engine; mode=self.data_mode.get()
        self.output.insert(tk.END,self._format_problem(engine)+"\n\n","h1")
        self.output.insert(tk.END,self._format_standardization(engine)+"\n","mono")
        if self._has_aux_phase1(engine):
            self.output.insert(tk.END,"\n=============================\n*Pha 1: Giải bài toán bổ trợ\n=============================\n","h2")
            self.output.insert(tk.END,"_ Tồn tại b_i âm → giải pha 1 bằng biến phụ x0\n","note")
            self._render_trace("Pha 1",report.dantzig)
            if report.phase1_bland is not None and report.phase1_bland is not report.dantzig:
                self.output.insert(tk.END,"\n*Bland sau Dantzig lặp ở pha 1\n","h2")
                self._render_trace("Pha 1 - Bland",report.phase1_bland)
            self.output.insert(tk.END,"\n")
            if report.status=="infeasible":
                self.output.insert(tk.END,"\nKẾT LUẬN\n","h2")
                self.output.insert(tk.END,"  Vô nghiệm: x0 vẫn trong cơ sở.\n","warn"); return
            if report.phase2_trace is not None:
                self.output.insert(tk.END,"\n============================\n*Pha 2: Giải bài toán gốc\n============================\n","h2")
                self._render_trace("Pha 2",report.phase2_trace)
            else:
                self.output.insert(tk.END,"\nKẾT LUẬN\n  Vô nghiệm.\n","warn"); return
        else:
            self.output.insert(tk.END,"\n============================\n Không cần Pha 1\n============================\n_ b_i ≥ 0, cơ sở ban đầu khả thi, giải trực tiếp.\n\n============================\n Giải bài toán\n============================\n","h2")
            self._render_trace("Giải bài toán",report.dantzig)
            if report.bland is not None and report.bland is not report.dantzig:
                self.output.insert(tk.END,"\n Bland (sau Dantzig xoay vòng)\n","h2")
                self._render_trace("Bland",report.bland)
        final=report.phase2_trace.final_snapshot if report.phase2_trace and report.phase2_trace.final_snapshot else (report.bland.final_snapshot if report.bland and report.bland.final_snapshot else report.dantzig.final_snapshot)
        if report.status in ("unbounded",) or (report.bland and report.bland.status=="unbounded"):
            self.output.insert(tk.END,"\nKẾT LUẬN\n  Không giới nội.\n","warn"); return
        if report.status=="cycle":
            rule = "Dantzig" if report.dantzig.steps and report.dantzig.steps[0].method == "dantzig" else "Bland"
            if rule == "Dantzig":
                self.output.insert(tk.END,"\nKẾT LUẬN\n  Dantzig phát hiện xoay vòng. Hãy thử Bland.\n","warn")
            else:
                self.output.insert(tk.END,"\nKẾT LUẬN\n  Bland phát hiện xoay vòng.\n","warn")
            return
        obj_std=report.objective_std or Fraction(0)
        obj_orig=report.objective_orig or Fraction(0)
        if report.multiple_optimal and final and report.multiple_optimal_vars:
            for line in self._format_multiple_optimal_family(engine,final,report):
                self.output.insert(tk.END,line+"\n","warn" if "vô số" in line else "note")
            self.output.insert(tk.END,"\nKẾT LUẬN\n","h2")
            self.output.insert(tk.END,f"  Tối ưu ({report.used_method.upper()}), z* = {fmt_num(obj_std,mode)}, gốc: {fmt_num(obj_orig,mode)}\n","note")
            for line in self._format_multiple_optimal_conclusion(engine,final,report):
                self.output.insert(tk.END,line+"\n","note")
        else:
            self.output.insert(tk.END,"\nKẾT LUẬN\n","h2")
            method_lbl = "Dantzig Simplex" if report.used_method == "dantzig" else "Bland's Rule"
            self.output.insert(tk.END,
                f"  Tối ưu ({method_lbl}).\n"
                f"  z* (bảng min) = {fmt_num(obj_std,mode)}\n"
                f"  Giá trị gốc   = {fmt_num(obj_orig,mode)}\n",
                "note")
            # Nghiệm: mỗi xi một dòng, căn phải theo cụm "xi = val"
            n_orig = len(engine.problem.var_signs)
            sol_strs = [fmt_num(report.solution_orig.get(i, Fraction(0)), mode)
                        for i in range(n_orig)]
            val_w = max(len(s) for s in sol_strs)
            var_w = max(len(f"x{i+1}") for i in range(n_orig))
            self.output.insert(tk.END,"  Nghiệm tối ưu:\n","note")
            for i, val_s in enumerate(sol_strs):
                nm = f"x{i+1}".ljust(var_w)
                val = val_s.rjust(val_w)
                self.output.insert(tk.END, f"    {nm} = {val}\n", "note")
        d=(report.dantzig.degenerate_steps or 0)+((report.bland.degenerate_steps if report.bland else 0) or 0)
        if d: self.output.insert(tk.END,f"  Có {d} bước suy biến.\n","warn")

    def _has_aux_phase1(self, engine):
        # Trả về True nếu engine đã thực hiện pha 1 với biến phụ x0
        # (xảy ra khi có ít nhất một b_i âm sau khi đưa về dạng chuẩn).
        return bool(getattr(engine,"need_aux_phase1",False))

    def run_solver(self):
        # Điểm vào chính khi người dùng bấm "Chạy giải thuật" hoặc nhấn Ctrl+Alt+R:
        #   1. Thu thập dữ liệu từ giao diện (_collect_problem)
        #   2. Tạo SimplexEngine và gọi solve_full() theo phương pháp người dùng đã chọn
        #   3. Lưu kết quả vào last_report / last_problem để xuất file / trực quan
        #   4. Hiển thị lời giải và cập nhật thanh trạng thái
        #   5. Bắt ngoại lệ (nhập liệu sai / lỗi giải thuật) và thông báo lỗi
        try:
            prob=self._collect_problem()
            engine=SimplexEngine(prob)
            report=engine.solve_full(self.method_preference.get())
            self.last_problem=prob; self.last_report=report
            self._render_result(report)
            self._set_solution_available(report.status=="optimal")
            self.status_var.set(f"Đã giải xong: {report.status}.")
        except Exception as exc:
            self.last_report=None; self._set_solution_available(False)
            messagebox.showerror("Lỗi nhập liệu / giải thuật",str(exc))
            self.status_var.set("Có lỗi xảy ra.")

def main():
    app = SimplexApp()
    app.mainloop()


if __name__ == "__main__":
    main()
