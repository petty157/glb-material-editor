#!/usr/bin/env python3
"""
GLB Material Editor
-------------------
Drop any .glb file on this script (or pass it as an argument) to edit its
PBR materials through a clean GUI.

Requirements: Python 3.7+ with tkinter (included in most Python installs).
No third-party packages needed.

Usage:
    python glb_material_editor.py                   # file picker opens
    python glb_material_editor.py path/to/model.glb # open directly
"""

import sys, os, json, struct, shutil, tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from copy import deepcopy

# ─────────────────────────── GLB read / write ────────────────────────────────

CHUNK_JSON = 0x4E4F534A
CHUNK_BIN  = 0x004E4942

def read_glb(path: str):
    with open(path, "rb") as f:
        raw = f.read()
    magic, version, _ = struct.unpack_from("<III", raw, 0)
    if magic != 0x46546C67:
        raise ValueError("Not a valid GLB file (bad magic bytes).")
    offset = 12
    json_bytes = bin_bytes = b""
    while offset < len(raw):
        chunk_len, chunk_type = struct.unpack_from("<II", raw, offset)
        chunk_data = raw[offset + 8 : offset + 8 + chunk_len]
        if chunk_type == CHUNK_JSON:
            json_bytes = chunk_data
        elif chunk_type == CHUNK_BIN:
            bin_bytes = chunk_data
        offset += 8 + chunk_len
    gltf = json.loads(json_bytes)
    return gltf, bin_bytes, raw


def write_glb(path: str, gltf: dict, bin_bytes: bytes):
    json_raw = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    pad_json = (4 - len(json_raw) % 4) % 4
    json_raw += b" " * pad_json
    pad_bin = (4 - len(bin_bytes) % 4) % 4 if bin_bytes else 0
    bin_padded = bin_bytes + b"\x00" * pad_bin
    json_chunk = struct.pack("<II", len(json_raw), CHUNK_JSON) + json_raw
    bin_chunk  = (struct.pack("<II", len(bin_padded), CHUNK_BIN) + bin_padded) if bin_bytes else b""
    total = 12 + len(json_chunk) + len(bin_chunk)
    header = struct.pack("<III", 0x46546C67, 2, total)
    with open(path, "wb") as f:
        f.write(header + json_chunk + bin_chunk)


def backup_file(path: str) -> str:
    bak = path + ".bak"
    shutil.copy2(path, bak)
    return bak


# ─────────────────────────── Material helpers ────────────────────────────────

def material_type_label(mat: dict) -> str:
    flags = []
    pbr = mat.get("pbrMetallicRoughness", {})
    if pbr:
        flags.append("PBR MetallicRoughness")
    if mat.get("extensions", {}).get("KHR_materials_unlit"):
        flags.append("Unlit")
    if mat.get("normalTexture"):
        flags.append("Normal Map")
    if mat.get("emissiveFactor", [0,0,0]) != [0,0,0]:
        flags.append("Emissive")
    if mat.get("occlusionTexture"):
        flags.append("Occlusion")
    alpha = mat.get("alphaMode", "OPAQUE")
    flags.append(f"Alpha:{alpha}")
    if mat.get("doubleSided", False):
        flags.append("DoubleSided")
    return "  |  ".join(flags) if flags else "Unknown"


def linear_to_srgb(c: float) -> int:
    c = max(0.0, min(1.0, c))
    if c <= 0.0031308:
        srgb = c * 12.92
    else:
        srgb = 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return round(srgb * 255)

def srgb_to_linear(v: int) -> float:
    c = v / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4

def factor_to_hex(factor) -> str:
    r, g, b = factor[0], factor[1], factor[2]
    return "#{:02x}{:02x}{:02x}".format(
        linear_to_srgb(r), linear_to_srgb(g), linear_to_srgb(b))

def hex_to_factor(hex_color: str, alpha: float = 1.0):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return [srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha]

def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


# ─────────────────────────── GUI ─────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self, glb_path: str | None = None):
        super().__init__()
        self.title("GLB Material Editor")
        self.resizable(True, True)
        self.minsize(720, 480)
        self.configure(bg="#1e1e2e")

        self.glb_path: str | None = None
        self.gltf: dict = {}
        self.bin_bytes: bytes = b""
        self.original_materials: list = []
        self._mat_widgets: list[dict] = []

        self._build_ui()

        if glb_path:
            self._load_file(glb_path)
        else:
            self.after(100, self._ask_open)

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4",
                         font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#1e1e2e", foreground="#89b4fa",
                         font=("Segoe UI", 11, "bold"))
        style.configure("Type.TLabel", background="#1e1e2e", foreground="#a6e3a1",
                         font=("Segoe UI", 9, "italic"))
        style.configure("TButton", font=("Segoe UI", 9), padding=4)
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4",
                         insertcolor="#cdd6f4")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        topbar = ttk.Frame(self)
        topbar.pack(fill="x", padx=10, pady=8)

        self.lbl_file = ttk.Label(topbar, text="No file loaded", style="TLabel")
        self.lbl_file.pack(side="left", padx=(0, 10))

        ttk.Button(topbar, text="📂 Open GLB", command=self._ask_open).pack(side="left", padx=3)
        ttk.Button(topbar, text="💾 Save (overwrite)", command=self._save,
                   style="Accent.TButton").pack(side="right", padx=3)
        ttk.Button(topbar, text="↩ Reset all", command=self._reset_all).pack(side="right", padx=3)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        canvas = tk.Canvas(outer, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.mat_frame = ttk.Frame(canvas)
        self.mat_frame_id = canvas.create_window((0, 0), window=self.mat_frame, anchor="nw")

        self.mat_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self.mat_frame_id, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.canvas = canvas

        self.status_var = tk.StringVar(value="Open a .glb file to begin.")
        ttk.Label(self, textvariable=self.status_var, style="TLabel").pack(
            side="bottom", anchor="w", padx=12, pady=4)

    # ── File I/O ─────────────────────────────────────────────────────────────

    def _ask_open(self):
        path = filedialog.askopenfilename(
            title="Open GLB file",
            filetypes=[("GLB files", "*.glb"), ("All files", "*.*")])
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            gltf, bin_bytes, _ = read_glb(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")
            return
        self.glb_path  = path
        self.gltf      = gltf
        self.bin_bytes = bin_bytes
        self.original_materials = deepcopy(gltf.get("materials", []))
        filename = os.path.basename(path)
        self.lbl_file.configure(text=f"📄 {filename}")
        self.title(f"GLB Material Editor — {filename}")
        self.status_var.set(f"Loaded: {path}")
        self._render_materials()

    def _save(self):
        if not self.glb_path:
            messagebox.showwarning("No file", "No GLB file is currently loaded.")
            return
        try:
            bak = backup_file(self.glb_path)
            write_glb(self.glb_path, self.gltf, self.bin_bytes)
            self.status_var.set(f"✅ Saved!  Backup → {os.path.basename(bak)}")
            messagebox.showinfo("Saved",
                f"File saved:\n  {self.glb_path}\n\nBackup created:\n  {bak}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _reset_all(self):
        if not self.glb_path:
            return
        if messagebox.askyesno("Reset", "Revert all materials to their original values?"):
            self.gltf["materials"] = deepcopy(self.original_materials)
            self._render_materials()
            self.status_var.set("All materials reset to original values.")

    # ── Material rendering ───────────────────────────────────────────────────

    def _render_materials(self):
        for w in self.mat_frame.winfo_children():
            w.destroy()
        self._mat_widgets.clear()
        materials = self.gltf.get("materials", [])
        if not materials:
            ttk.Label(self.mat_frame, text="This GLB has no materials.",
                      style="Header.TLabel").pack(padx=20, pady=20)
            return
        for idx, mat in enumerate(materials):
            self._build_material_card(idx, mat)

    def _build_material_card(self, idx: int, mat: dict):
        mat_name = mat.get("name", f"Material {idx}")
        type_str = material_type_label(mat)

        card = tk.Frame(self.mat_frame, bg="#313244",
                        highlightbackground="#45475a", highlightthickness=1)
        card.pack(fill="x", padx=6, pady=6, ipady=6)

        hrow = tk.Frame(card, bg="#313244")
        hrow.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(hrow, text=f"[{idx}]  {mat_name}", bg="#313244",
                 fg="#89b4fa", font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(hrow, text="↩ Reset", bg="#45475a", fg="#cdd6f4",
                  relief="flat", font=("Segoe UI", 8),
                  command=lambda i=idx: self._reset_material(i)).pack(side="right")

        tk.Label(card, text=type_str, bg="#313244", fg="#a6e3a1",
                 font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Separator(card, orient="horizontal").pack(fill="x", padx=8, pady=4)

        pbr = mat.setdefault("pbrMetallicRoughness", {})
        refs: dict = {}

        # Name
        row = tk.Frame(card, bg="#313244")
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text="Name", bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        name_var = tk.StringVar(value=mat_name)
        ttk.Entry(row, textvariable=name_var, width=30).pack(side="left")
        name_var.trace_add("write",
            lambda *_, v=name_var, i=idx: self._update_name(i, v.get()))
        refs["name_var"] = name_var

        # Base color
        base_factor = pbr.get("baseColorFactor", [1, 1, 1, 1])
        alpha_val   = base_factor[3] if len(base_factor) > 3 else 1.0
        hex_color   = factor_to_hex(base_factor)

        color_row = tk.Frame(card, bg="#313244")
        color_row.pack(fill="x", padx=12, pady=3)
        tk.Label(color_row, text="Base Color", bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        swatch = tk.Label(color_row, width=5, relief="solid", cursor="hand2", bg=hex_color)
        swatch.pack(side="left", padx=(0, 8))
        hex_var = tk.StringVar(value=hex_color)
        ttk.Entry(color_row, textvariable=hex_var, width=9).pack(side="left", padx=(0, 6))
        tk.Button(color_row, text="Pick…", bg="#45475a", fg="#cdd6f4",
                  relief="flat", font=("Segoe UI", 8),
                  command=lambda i=idx, sv=hex_var, sw=swatch:
                      self._pick_color(i, sv, sw)).pack(side="left")
        hex_var.trace_add("write",
            lambda *_, i=idx, sv=hex_var, sw=swatch: self._manual_hex(i, sv, sw))
        refs.update({"hex_var": hex_var, "swatch": swatch})

        # Alpha — manual entry
        self._add_entry_row(card, idx, "Alpha", alpha_val,
                            self._update_alpha, refs, "alpha_var", "#f5c2e7")

        # Metallic — manual entry
        self._add_entry_row(card, idx, "Metallic Factor",
                            pbr.get("metallicFactor", 0.0),
                            lambda v, i, k="metallicFactor": self._update_pbr_factor(i, k, v),
                            refs, "metallicFactor_var", "#fab387")

        # Roughness — manual entry
        self._add_entry_row(card, idx, "Roughness Factor",
                            pbr.get("roughnessFactor", 0.5),
                            lambda v, i, k="roughnessFactor": self._update_pbr_factor(i, k, v),
                            refs, "roughnessFactor_var", "#94e2d5")

        # Emissive color
        emissive = mat.get("emissiveFactor", [0.0, 0.0, 0.0])
        emissive_hex = factor_to_hex(emissive + [1.0])
        em_row = tk.Frame(card, bg="#313244")
        em_row.pack(fill="x", padx=12, pady=3)
        tk.Label(em_row, text="Emissive Color", bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        em_swatch = tk.Label(em_row, width=5, relief="solid", cursor="hand2", bg=emissive_hex)
        em_swatch.pack(side="left", padx=(0, 8))
        em_hex_var = tk.StringVar(value=emissive_hex)
        ttk.Entry(em_row, textvariable=em_hex_var, width=9).pack(side="left", padx=(0, 6))
        tk.Button(em_row, text="Pick…", bg="#45475a", fg="#cdd6f4",
                  relief="flat", font=("Segoe UI", 8),
                  command=lambda i=idx, sv=em_hex_var, sw=em_swatch:
                      self._pick_emissive(i, sv, sw)).pack(side="left")
        em_hex_var.trace_add("write",
            lambda *_, i=idx, sv=em_hex_var, sw=em_swatch:
                self._manual_emissive(i, sv, sw))
        refs["em_hex_var"] = em_hex_var
        refs["em_swatch"]  = em_swatch

        # Alpha mode
        mode_row = tk.Frame(card, bg="#313244")
        mode_row.pack(fill="x", padx=12, pady=3)
        tk.Label(mode_row, text="Alpha Mode", bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        mode_var = tk.StringVar(value=mat.get("alphaMode", "OPAQUE"))
        for mode in ("OPAQUE", "MASK", "BLEND"):
            tk.Radiobutton(mode_row, text=mode, variable=mode_var, value=mode,
                           bg="#313244", fg="#cdd6f4", selectcolor="#313244",
                           activebackground="#313244", activeforeground="#cdd6f4",
                           font=("Segoe UI", 9),
                           command=lambda m=mode_var, i=idx: self._update_alpha_mode(i, m.get())
                           ).pack(side="left", padx=6)
        refs["mode_var"] = mode_var

        # Double sided
        ds_row = tk.Frame(card, bg="#313244")
        ds_row.pack(fill="x", padx=12, pady=(3, 8))
        tk.Label(ds_row, text="Double Sided", bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        ds_var = tk.BooleanVar(value=mat.get("doubleSided", False))
        tk.Checkbutton(ds_row, variable=ds_var, bg="#313244", fg="#cdd6f4",
                       selectcolor="#313244", activebackground="#313244",
                       command=lambda v=ds_var, i=idx: self._update_double_sided(i, v.get())
                       ).pack(side="left")
        refs["ds_var"] = ds_var

        self._mat_widgets.append(refs)

    def _add_entry_row(self, parent, idx, label, value, callback, refs, ref_key, color):
        """Numeric entry field (0.0–1.0). Commits on Return or focus-out."""
        row = tk.Frame(parent, bg="#313244")
        row.pack(fill="x", padx=12, pady=3)

        tk.Label(row, text=label, bg="#313244", fg="#cdd6f4",
                 width=18, anchor="w", font=("Segoe UI", 9)).pack(side="left")

        str_var = tk.StringVar(value=f"{value:.4f}")
        entry = ttk.Entry(row, textvariable=str_var, width=10)
        entry.pack(side="left", padx=(0, 6))

        tk.Label(row, text="(0.0 – 1.0)", bg="#313244", fg="#6c7086",
                 font=("Segoe UI", 8)).pack(side="left")

        def apply(*_):
            raw = str_var.get().strip()
            try:
                v = clamp01(float(raw))
            except ValueError:
                # Restore last valid value from model data
                mat = self.gltf["materials"][idx]
                pbr = mat.get("pbrMetallicRoughness", {})
                if label == "Alpha":
                    v = pbr.get("baseColorFactor", [1,1,1,1])[3]
                elif label == "Metallic Factor":
                    v = pbr.get("metallicFactor", 0.0)
                elif label == "Roughness Factor":
                    v = pbr.get("roughnessFactor", 0.5)
                else:
                    v = 0.0
            str_var.set(f"{v:.4f}")
            callback(v, idx)

        entry.bind("<Return>", apply)
        entry.bind("<FocusOut>", apply)
        refs[ref_key] = str_var

    # ── Update callbacks ─────────────────────────────────────────────────────

    def _mat(self, idx):
        return self.gltf["materials"][idx]

    def _update_name(self, idx, value):
        self._mat(idx)["name"] = value

    def _update_pbr_factor(self, idx, key, value):
        self._mat(idx).setdefault("pbrMetallicRoughness", {})[key] = value

    def _update_alpha(self, value, idx):
        pbr = self._mat(idx).setdefault("pbrMetallicRoughness", {})
        factor = pbr.get("baseColorFactor", [1, 1, 1, 1])
        factor[3] = value
        pbr["baseColorFactor"] = factor

    def _update_alpha_mode(self, idx, mode):
        self._mat(idx)["alphaMode"] = mode

    def _update_double_sided(self, idx, value):
        self._mat(idx)["doubleSided"] = value

    def _pick_color(self, idx, hex_var, swatch):
        result = colorchooser.askcolor(color=hex_var.get(), title="Pick Base Color")
        if result and result[1]:
            hex_var.set(result[1])

    def _manual_hex(self, idx, hex_var, swatch):
        val = hex_var.get().strip()
        if len(val) == 7 and val.startswith("#"):
            try:
                pbr = self._mat(idx).setdefault("pbrMetallicRoughness", {})
                alpha = pbr.get("baseColorFactor", [1, 1, 1, 1])[3]
                pbr["baseColorFactor"] = hex_to_factor(val, alpha)
                swatch.configure(bg=val)
            except Exception:
                pass

    def _pick_emissive(self, idx, hex_var, swatch):
        result = colorchooser.askcolor(color=hex_var.get(), title="Pick Emissive Color")
        if result and result[1]:
            hex_var.set(result[1])

    def _manual_emissive(self, idx, hex_var, swatch):
        val = hex_var.get().strip()
        if len(val) == 7 and val.startswith("#"):
            try:
                factor = hex_to_factor(val, 1.0)
                self._mat(idx)["emissiveFactor"] = factor[:3]
                swatch.configure(bg=val)
            except Exception:
                pass

    def _reset_material(self, idx):
        self.gltf["materials"][idx] = deepcopy(self.original_materials[idx])
        self._render_materials()
        self.status_var.set(f"Material [{idx}] reset to original.")


# ─────────────────────────── Entry point ─────────────────────────────────────

if __name__ == "__main__":
    glb_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(glb_path)
    app.mainloop()