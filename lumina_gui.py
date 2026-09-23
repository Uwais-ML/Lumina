"""
lumina_gui.py — Lumina AI Tkinter Control Panel
Run: python3 lumina_gui.py   or   lumina --gui
"""

import os, sys, subprocess, threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR   = os.path.join(PROJECT_ROOT, "models")
LUMINA_PY    = os.path.join(PROJECT_ROOT, "Lumina.py")

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0d1117"
SIDEBAR = "#161b22"
PANEL   = "#1c2128"
BORDER  = "#30363d"
ACCENT  = "#00d2ff"
PURPLE  = "#a020f0"
GREEN   = "#2ecc71"
AMBER   = "#f1c40f"
RED     = "#e74c3c"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"
INPUT   = "#21262d"
HOV     = "#2d333b"

# macOS-safe fonts
F_TITLE = ("Helvetica", 15, "bold")
F_HEAD  = ("Helvetica", 11, "bold")
F_BODY  = ("Helvetica", 11)
F_MONO  = ("Courier", 11)
F_TINY  = ("Helvetica", 9, "bold")


# ── Helpers ───────────────────────────────────────────────────────────────────

def models():
    if not os.path.isdir(MODELS_DIR):
        return ["(no models found)"]
    lst = [f[:-5] for f in sorted(os.listdir(MODELS_DIR)) if f.endswith(".gguf")]
    return lst or ["(no models found)"]


def bundled_python():
    if sys.platform == "win32":
        rel_paths = ["python-dependencies/windows/python.exe"]
    elif sys.platform == "darwin":
        rel_paths = [
            "python-dependencies/macos-intel/bin/python3",
            "python-dependencies/macos-arm/bin/python3",
            "python-dependencies/macos-intel/lib/python3.10/bin/python3",
        ]
    else:
        rel_paths = ["python-dependencies/linux/bin/python3"]

    for rel in rel_paths:
        p = os.path.join(PROJECT_ROOT, rel)
        if os.path.isfile(p):
            return p
    return sys.executable


def entry(parent, var, w=26):
    e = tk.Entry(parent, textvariable=var, width=w, bg=INPUT, fg=TEXT,
                 insertbackground=ACCENT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT, font=F_MONO)
    return e


def spin(parent, var, lo, hi, inc=1, w=12):
    return tk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                      increment=inc, width=w, bg=INPUT, fg=TEXT,
                      buttonbackground=HOV, relief="flat",
                      highlightthickness=1, highlightbackground=BORDER,
                      highlightcolor=ACCENT, font=F_MONO)


def check(parent, text, var):
    return tk.Checkbutton(parent, text=text, variable=var,
                          bg=PANEL, fg=TEXT, activebackground=PANEL,
                          activeforeground=ACCENT, selectcolor=INPUT,
                          font=F_BODY)


def combo(parent, var, vals, w=26):
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("D.TCombobox", fieldbackground=INPUT, background=INPUT,
                foreground=TEXT, selectbackground=HOV, selectforeground=ACCENT,
                arrowcolor=ACCENT, bordercolor=BORDER)
    s.map("D.TCombobox", fieldbackground=[("readonly", INPUT)])
    cb = ttk.Combobox(parent, textvariable=var, values=vals, width=w,
                      style="D.TCombobox", font=F_MONO, state="readonly")
    return cb


def lbl(parent, text, fg=MUTED):
    return tk.Label(parent, text=text, bg=PANEL, fg=fg, font=F_BODY, anchor="w")


def tip_label(parent, text, tooltip=""):
    l = lbl(parent, text)
    if tooltip:
        _Tip(l, tooltip)
    return l


class _Tip:
    def __init__(self, w, text):
        self.w, self.text, self.win = w, text, None
        w.bind("<Enter>", self._show)
        w.bind("<Leave>", self._hide)

    def _show(self, _=None):
        x = self.w.winfo_rootx() + 16
        y = self.w.winfo_rooty() + self.w.winfo_height() + 2
        self.win = tk.Toplevel(self.w)
        self.win.wm_overrideredirect(True)
        self.win.wm_geometry(f"+{x}+{y}")
        tk.Label(self.win, text=self.text, bg="#2d333b", fg=TEXT,
                 font=("Helvetica", 10), relief="flat",
                 padx=8, pady=5, wraplength=300, justify="left").pack()

    def _hide(self, _=None):
        if self.win:
            self.win.destroy()
            self.win = None


def field_row(grid_parent, row_idx, label_text, widget, tooltip=""):
    l = tip_label(grid_parent, label_text, tooltip)
    l.grid(row=row_idx, column=0, sticky="w", padx=(14, 8), pady=5)
    widget.grid(row=row_idx, column=1, sticky="w", padx=(0, 14), pady=5)
    return row_idx + 1


# ── Main App ──────────────────────────────────────────────────────────────────

class LuminaGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lumina — Control Panel")
        self.configure(bg=BG)
        self.geometry("1060x740")
        self.minsize(860, 580)

        self._proc        = None
        self._active      = None
        self._panels      = {}   # key → {"btn": Frame, "panel": Frame}

        self._build_layout()
        self._build_all_panels()
        self._select(next(iter(self._panels)))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Top bar
        top = tk.Frame(self, bg=SIDEBAR, height=46)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="✦  LUMINA AI  Control Panel", bg=SIDEBAR,
                 fg=ACCENT, font=F_TITLE).pack(side="left", padx=18, pady=10)

        # Body
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = tk.Frame(body, bg=SIDEBAR, width=180)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        tk.Label(self._sidebar, text="COMMANDS", bg=SIDEBAR, fg=MUTED,
                 font=F_TINY).pack(pady=(14, 6), padx=12, anchor="w")

        # Panel host — all command panels live here, only one visible at a time
        self._host = tk.Frame(body, bg=PANEL)
        self._host.pack(side="left", fill="both", expand=True)

        # Bottom console
        self._build_console()

    def _build_console(self):
        bot = tk.Frame(self, bg=SIDEBAR)
        bot.pack(fill="x", side="bottom")

        bar = tk.Frame(bot, bg=SIDEBAR)
        bar.pack(fill="x")
        tk.Label(bar, text="OUTPUT", bg=SIDEBAR, fg=MUTED,
                 font=F_TINY).pack(side="left", padx=14, pady=6)

        def btn(text, cmd, bg, fg="white", state="normal"):
            return tk.Button(bar, text=text, command=cmd, bg=bg, fg=fg,
                             activebackground=HOV, font=F_BODY,
                             relief="flat", padx=12, pady=3,
                             cursor="hand2", state=state)

        self._run_btn  = btn("▶  Run",   self._run,   GREEN)
        self._stop_btn = btn("■  Stop",  self._stop,  RED, state="disabled")
        self._clr_btn  = btn("⌫  Clear", self._clear, INPUT, MUTED)
        for b in (self._clr_btn, self._stop_btn, self._run_btn):
            b.pack(side="right", padx=4, pady=4)

        self._con = scrolledtext.ScrolledText(
            bot, height=10, bg="#010409", fg=TEXT,
            font=F_MONO, relief="flat", state="disabled", wrap="word")
        self._con.pack(fill="x")
        self._con.tag_config("ok",   foreground=GREEN)
        self._con.tag_config("err",  foreground=RED)
        self._con.tag_config("warn", foreground=AMBER)
        self._con.tag_config("info", foreground=ACCENT)
        self._con.tag_config("dim",  foreground=MUTED)

    # ── Sidebar button ────────────────────────────────────────────────────────

    def _sidebar_btn(self, key, icon, label):
        f = tk.Frame(self._sidebar, bg=SIDEBAR, cursor="hand2")
        f.pack(fill="x", padx=6, pady=2)
        tk.Label(f, text=icon, bg=SIDEBAR, fg=MUTED,
                 font=("Helvetica", 13), width=2).pack(side="left", padx=(4, 2), pady=6)
        tk.Label(f, text=label, bg=SIDEBAR, fg=TEXT,
                 font=F_BODY, anchor="w").pack(side="left", pady=6)

        def click(_=None):
            self._select(key)

        for w in f.winfo_children() + [f]:
            w.bind("<Button-1>", click)
            w.bind("<Enter>",  lambda e, fr=f: self._hover(fr, True))
            w.bind("<Leave>",  lambda e, fr=f, k=key: self._hover(fr, False, k))

        self._panels[key] = {"btn": f}

    def _hover(self, frame, on, key=None):
        if key and key == self._active:
            return
        bg = HOV if on else (PANEL if (key and key == self._active) else SIDEBAR)
        frame.configure(bg=bg)
        for c in frame.winfo_children():
            c.configure(bg=bg)

    def _select(self, key):
        # Hide old
        if self._active and "panel" in self._panels[self._active]:
            self._panels[self._active]["panel"].pack_forget()
            old_btn = self._panels[self._active]["btn"]
            old_btn.configure(bg=SIDEBAR)
            for c in old_btn.winfo_children():
                c.configure(bg=SIDEBAR)

        # Show new
        self._active = key
        btn = self._panels[key]["btn"]
        btn.configure(bg=PANEL)
        for c in btn.winfo_children():
            c.configure(bg=PANEL)
        if "panel" in self._panels[key]:
            self._panels[key]["panel"].pack(fill="both", expand=True)

    # ── Panel scaffold ────────────────────────────────────────────────────────

    def _make_panel(self, key, title, subtitle):
        """Create a panel Frame (child of host), add header, return scrollable inner frame."""
        outer = tk.Frame(self._host, bg=PANEL)
        # DON'T pack — _select will pack/unpack it

        # Coloured left-border header
        hdr = tk.Frame(outer, bg=PANEL)
        hdr.pack(fill="x", pady=(0, 0))
        tk.Frame(hdr, bg=PURPLE, width=4).pack(side="left", fill="y")
        th = tk.Frame(hdr, bg=PANEL)
        th.pack(side="left", fill="x", padx=10, pady=10)
        tk.Label(th, text=title, bg=PANEL, fg=TEXT, font=F_TITLE, anchor="w").pack(anchor="w")
        tk.Label(th, text=subtitle, bg=PANEL, fg=MUTED, font=F_BODY, anchor="w").pack(anchor="w")
        tk.Frame(outer, bg=BORDER, height=1).pack(fill="x")

        # Scrollable content area
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=PANEL)
        inner.columnconfigure(1, weight=1)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        self._panels[key]["panel"] = outer
        return inner

    def _section(self, parent, text, row_idx):
        """A subtle section divider label inside the grid."""
        tk.Label(parent, text=f"  {text}", bg=PANEL, fg=ACCENT,
                 font=F_TINY, anchor="w").grid(
            row=row_idx, column=0, columnspan=2,
            sticky="ew", padx=14, pady=(12, 2))
        return row_idx + 1

    # ── All panels ────────────────────────────────────────────────────────────

    def _build_all_panels(self):
        self._panel_launch()
        self._panel_switch()
        self._panel_rag()
        self._panel_agentic()
        self._panel_test()
        self._simple("--models",      "🌐", "Model Store",      "Launch the LLM model store web server.")
        self._simple("--bench",       "⚡", "Benchmark",         "Run hardware benchmark across local LLM models.")
        self._simple("--assess",      "📊", "System Assess",     "Estimate bandwidth and tokens/sec for target models.")
        self._simple("--download",    "⬇",  "Download Model",    "Download a custom model from HuggingFace.")
        self._simple("--setup",       "📦", "Setup",             "Download all base GGUF models.")
        self._simple("--embed",       "🧠", "Embed Context",     "Embed stored conversation context into vector store.")
        self._simple("--dependencies","📋", "Dependencies",      "Install ALL required Python dependencies into the bundled env.")
        self._panel_install()

    # --launch ─────────────────────────────────────────────────────────────────

    def _panel_launch(self):
        key = "--launch"
        self._sidebar_btn(key, "🚀", "Launch Model")
        pf = self._make_panel(key, "Launch Model",
                              "Start a GGUF model via the llamafile server.")
        mdls = models()
        self.lm_model    = tk.StringVar(value=mdls[0])
        self.lm_port     = tk.IntVar(value=0)
        self.lm_host     = tk.StringVar(value="127.0.0.1")
        self.lm_timeout  = tk.DoubleVar(value=30.0)
        self.lm_attempts = tk.IntVar(value=5)

        r = 0
        r = self._section(pf, "MODEL", r)
        r = field_row(pf, r, "Model", combo(pf, self.lm_model, mdls),
                      "GGUF model to launch (from models/ folder).")
        r = self._section(pf, "SERVER", r)
        r = field_row(pf, r, "Port  (0 = auto-select)", spin(pf, self.lm_port, 0, 65535),
                      "Port to bind. 0 = pick a free port automatically.")
        r = field_row(pf, r, "Host", entry(pf, self.lm_host, 18),
                      "Host address (127.0.0.1 = localhost only).")
        r = self._section(pf, "TIMEOUTS", r)
        r = field_row(pf, r, "Startup timeout (s)", spin(pf, self.lm_timeout, 5, 300, 5),
                      "Max seconds to wait for the server ready signal.")
        r = field_row(pf, r, "Max port attempts", spin(pf, self.lm_attempts, 1, 20),
                      "How many times to retry finding a free port.")

    # --switch ─────────────────────────────────────────────────────────────────

    def _panel_switch(self):
        key = "--switch"
        self._sidebar_btn(key, "🔁", "SmartSwitch")
        pf = self._make_panel(key, "SmartSwitch",
                              "RAM/VRAM watchdog — auto-swaps degraded model with fallback.")
        mdls = models()
        self.sw_model     = tk.StringVar(value=mdls[0])
        self.sw_allow     = tk.DoubleVar(value=0.25)
        self.sw_interval  = tk.DoubleVar(value=2.0)
        self.sw_tps       = tk.DoubleVar(value=0.75)
        self.sw_mintps    = tk.IntVar(value=2)
        self.sw_kill      = tk.DoubleVar(value=3.0)
        self.sw_sockwait  = tk.DoubleVar(value=1.5)
        self.sw_vram      = tk.DoubleVar(value=300.0)
        self.sw_gpu       = tk.IntVar(value=0)
        self.sw_settle    = tk.DoubleVar(value=3.0)
        self.sw_inittout  = tk.DoubleVar(value=30.0)
        self.sw_grace     = tk.DoubleVar(value=10.0)
        self.sw_loglevel  = tk.StringVar(value="INFO")
        self.sw_novram    = tk.BooleanVar(value=False)
        self.sw_noreplay  = tk.BooleanVar(value=False)

        r = 0
        r = self._section(pf, "FALLBACK MODEL", r)
        r = field_row(pf, r, "Fallback model", combo(pf, self.sw_model, mdls),
                      "Model to switch to when primary degrades.")
        r = self._section(pf, "MEMORY THRESHOLDS", r)
        r = field_row(pf, r, "RAM allowance  (0–1)", spin(pf, self.sw_allow, 0.0, 1.0, 0.05),
                      "Fractional RAM/VRAM growth above baseline before switching. 0.25 = 25%.")
        r = field_row(pf, r, "VRAM delta (MB)", spin(pf, self.sw_vram, 0, 8192, 50),
                      "If RAM growth < this after launch, model is GPU-loaded → VRAM tracked.")
        r = field_row(pf, r, "GPU index", spin(pf, self.sw_gpu, 0, 16),
                      "GPU device index (for multi-GPU machines).")
        r = self._section(pf, "PERFORMANCE THRESHOLDS", r)
        r = field_row(pf, r, "TPS threshold  (0–1)", spin(pf, self.sw_tps, 0.1, 1.0, 0.05),
                      "Fraction of baseline T/s below which switch triggers. 0.75 = <75% of baseline.")
        r = field_row(pf, r, "Min TPS samples", spin(pf, self.sw_mintps, 1, 20),
                      "Min T/s entries collected before degradation check activates.")
        r = self._section(pf, "TIMING", r)
        r = field_row(pf, r, "Check interval (s)", spin(pf, self.sw_interval, 0.5, 60.0, 0.5),
                      "How often (seconds) to poll RAM/VRAM usage.")
        r = field_row(pf, r, "Kill timeout (s)", spin(pf, self.sw_kill, 1.0, 30.0, 0.5),
                      "Seconds to wait for graceful termination before SIGKILL.")
        r = field_row(pf, r, "Socket wait (s)", spin(pf, self.sw_sockwait, 0.0, 30.0, 0.5),
                      "Seconds to wait after kill before relaunching.")
        r = field_row(pf, r, "Settle time (s)", spin(pf, self.sw_settle, 1.0, 30.0, 0.5),
                      "Seconds to let memory stabilize after model is ready.")
        r = field_row(pf, r, "Init timeout (s)", spin(pf, self.sw_inittout, 5, 300, 5),
                      "Max seconds to wait for model ready signal during initialization.")
        r = field_row(pf, r, "Grace period (s)", spin(pf, self.sw_grace, 0, 120, 5),
                      "Seconds after init to ignore startup memory spikes.")
        r = self._section(pf, "LOGGING & FLAGS", r)
        r = field_row(pf, r, "Log level", combo(pf, self.sw_loglevel,
                                                 ["DEBUG","INFO","WARNING","ERROR","CRITICAL"], 14),
                      "Logging verbosity.")
        tk.Frame(pf, bg=PANEL).grid(row=r, column=0, pady=2)
        r += 1
        chk = tk.Frame(pf, bg=PANEL)
        chk.grid(row=r, column=0, columnspan=2, sticky="w", padx=14, pady=6)
        check(chk, "  No VRAM  (always track system RAM)", self.sw_novram).pack(side="left", padx=(0, 20))
        check(chk, "  No auto-replay of buffered query",    self.sw_noreplay).pack(side="left")

    # --rag ────────────────────────────────────────────────────────────────────

    def _panel_rag(self):
        key = "--rag"
        self._sidebar_btn(key, "📄", "RAG Pipeline")
        pf = self._make_panel(key, "RAG Pipeline",
                              "Load a document into a vector store and answer questions with an LLM.")
        self.rag_file    = tk.StringVar(value="")
        self.rag_port    = tk.IntVar(value=0)
        self.rag_chunk   = tk.IntVar(value=500)
        self.rag_overlap = tk.IntVar(value=50)
        self.rag_k       = tk.IntVar(value=3)
        self.rag_stype   = tk.StringVar(value="similarity")
        self.rag_dbdir   = tk.StringVar(value="./chroma_db")
        self.rag_turns   = tk.IntVar(value=10)
        self.rag_ctx     = tk.BooleanVar(value=False)
        self.rag_rebuild = tk.BooleanVar(value=False)

        r = 0
        r = self._section(pf, "DOCUMENT", r)

        # File picker row — manual layout
        tip_label(pf, "Document file",
                  "Text/Markdown/PDF file to load into the vector store.").grid(
            row=r, column=0, sticky="w", padx=(14, 8), pady=5)
        fp = tk.Frame(pf, bg=PANEL)
        fp.grid(row=r, column=1, sticky="ew", padx=(0, 14), pady=5)
        entry(fp, self.rag_file, 28).pack(side="left", fill="x", expand=True)
        tk.Button(fp, text=" Browse ", command=self._browse_doc,
                  bg=INPUT, fg=ACCENT, activebackground=HOV,
                  relief="flat", font=F_BODY, cursor="hand2").pack(side="left", padx=(4, 0))
        r += 1

        r = field_row(pf, r, "Port  (0 = auto)", spin(pf, self.rag_port, 0, 65535),
                      "LLM server port. 0 = read from env or prompt.")
        r = self._section(pf, "CHUNKING", r)
        r = field_row(pf, r, "Chunk size (tokens)", spin(pf, self.rag_chunk, 100, 4096, 50),
                      "Token chunk size for splitting the document.")
        r = field_row(pf, r, "Overlap (tokens)", spin(pf, self.rag_overlap, 0, 512, 10),
                      "Overlap between adjacent chunks.")
        r = field_row(pf, r, "Top-K chunks", spin(pf, self.rag_k, 1, 20),
                      "Number of chunks to retrieve per query.")
        r = field_row(pf, r, "Search type", combo(pf, self.rag_stype, ["similarity","mmr"], 14),
                      "similarity = cosine distance.  mmr = diverse results.")

        r = self._section(pf, "STORAGE", r)
        tip_label(pf, "Vector DB dir",
                  "Directory for the Chroma vector database.").grid(
            row=r, column=0, sticky="w", padx=(14, 8), pady=5)
        dp = tk.Frame(pf, bg=PANEL)
        dp.grid(row=r, column=1, sticky="ew", padx=(0, 14), pady=5)
        entry(dp, self.rag_dbdir, 26).pack(side="left", fill="x", expand=True)
        tk.Button(dp, text=" Browse ", command=self._browse_db,
                  bg=INPUT, fg=ACCENT, activebackground=HOV,
                  relief="flat", font=F_BODY, cursor="hand2").pack(side="left", padx=(4, 0))
        r += 1

        r = self._section(pf, "SESSION", r)
        r = field_row(pf, r, "Max turns", spin(pf, self.rag_turns, 1, 100),
                      "Maximum Q&A turns per session.")
        tk.Frame(pf, bg=PANEL).grid(row=r, column=0, pady=2)
        r += 1
        chk = tk.Frame(pf, bg=PANEL)
        chk.grid(row=r, column=0, columnspan=2, sticky="w", padx=14, pady=6)
        check(chk, "  Context persistence (save Q&A to memory)", self.rag_ctx).pack(side="left", padx=(0, 20))
        check(chk, "  Force rebuild vector DB",                   self.rag_rebuild).pack(side="left")

    def _browse_doc(self):
        p = filedialog.askopenfilename(
            parent=self, title="Select Document",
            filetypes=[("Text / Markdown","*.txt *.md *.csv *.json"),
                       ("All files","*.*")])
        if p: self.rag_file.set(p)

    def _browse_db(self):
        p = filedialog.askdirectory(parent=self, title="Select Vector DB Directory")
        if p: self.rag_dbdir.set(p)

    # --agentic ────────────────────────────────────────────────────────────────

    def _panel_agentic(self):
        key = "--agentic"
        self._sidebar_btn(key, "🤖", "Agentic")
        pf = self._make_panel(key, "Agentic AI",
                              "Autonomous agent that chains tools to complete complex tasks.")
        self.ag_port    = tk.IntVar(value=54993)
        self.ag_model   = tk.StringVar(value="qwen")
        self.ag_temp    = tk.DoubleVar(value=0.2)
        self.ag_maxtok  = tk.IntVar(value=256)
        self.ag_iters   = tk.IntVar(value=5)
        self.ag_verbose = tk.BooleanVar(value=False)
        self.ag_loglvl  = tk.StringVar(value="INFO")

        r = 0
        r = self._section(pf, "QUERY", r)
        tip_label(pf, "Query / Task",
                  "Describe the task for the agent to execute.").grid(
            row=r, column=0, sticky="nw", padx=(14, 8), pady=5)
        self.ag_query_text = tk.Text(
            pf, height=4, width=42, bg=INPUT, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT, font=F_MONO, wrap="word")
        self.ag_query_text.grid(row=r, column=1, sticky="ew", padx=(0,14), pady=5)
        r += 1

        r = self._section(pf, "MODEL", r)
        r = field_row(pf, r, "Port", spin(pf, self.ag_port, 1, 65535),
                      "LLM API port.")
        r = field_row(pf, r, "Model name", entry(pf, self.ag_model, 18),
                      "LLM model identifier string.")
        r = self._section(pf, "GENERATION", r)
        r = field_row(pf, r, "Temperature  (0–1)", spin(pf, self.ag_temp, 0.0, 1.0, 0.05),
                      "0 = deterministic, 1 = very creative.")
        r = field_row(pf, r, "Max tokens", spin(pf, self.ag_maxtok, 64, 8192, 64),
                      "Max tokens per LLM response in the agent loop.")
        r = field_row(pf, r, "Max iterations", spin(pf, self.ag_iters, 1, 50),
                      "Maximum number of tool execution iterations before stopping.")
        r = self._section(pf, "LOGGING & FLAGS", r)
        r = field_row(pf, r, "Log level",
                      combo(pf, self.ag_loglvl, ["DEBUG","INFO","WARNING","ERROR"], 14),
                      "Logging verbosity.")
        tk.Frame(pf, bg=PANEL).grid(row=r, column=0, pady=2)
        r += 1
        chk = tk.Frame(pf, bg=PANEL)
        chk.grid(row=r, column=0, columnspan=2, sticky="w", padx=14, pady=6)
        check(chk, "  Verbose output", self.ag_verbose).pack(side="left")

    # --test ───────────────────────────────────────────────────────────────────

    def _panel_test(self):
        key = "--test"
        self._sidebar_btn(key, "🧪", "Test & Benchmark")
        pf = self._make_panel(key, "Test & Benchmark Suite",
                              "Run automated speed, router, and failover latency tests.")
        self.ts_suite = tk.StringVar(value="all")

        r = 0
        r = self._section(pf, "TEST SUITE SELECTION", r)
        r = field_row(pf, r, "Target suite",
                      combo(pf, self.ts_suite,
                            ["all", "bench", "router", "stress"], 18),
                      "all = full test suite.  bench = Assesser vs Actual T/s.  router = Intent Router.  stress = SmartSwitch Failover.")
        
        tk.Label(pf, text="Output report will be written to logs/benchmark_report.md and logs/benchmark_report.json.\nPress  ▶ Run  to execute.",
                 bg=PANEL, fg=MUTED, font=("Helvetica", 11), justify="left").grid(
            row=r, column=0, columnspan=2, padx=14, pady=15, sticky="w")

    # --install ────────────────────────────────────────────────────────────────

    def _panel_install(self):
        key = "--install"
        self._sidebar_btn(key, "📥", "Install Package")
        pf = self._make_panel(key, "Install Package",
                              "Install Python package(s) into the bundled env.")
        self.inst_pkg = tk.StringVar(value="")
        r = 0
        r = self._section(pf, "PACKAGE", r)
        r = field_row(pf, r, "Package name(s)", entry(pf, self.inst_pkg, 34),
                      "Space-separated names, e.g.  numpy pandas requests")

    # simple panels ────────────────────────────────────────────────────────────

    def _simple(self, key, icon, label, desc):
        self._sidebar_btn(key, icon, label)
        pf = self._make_panel(key, label, desc)
        tk.Label(pf, text="No extra arguments needed.\nPress  ▶ Run  to execute.",
                 bg=PANEL, fg=MUTED, font=("Helvetica", 13),
                 justify="left").grid(row=0, column=0, columnspan=2, padx=16, pady=20, sticky="w")

    # ── Build CLI args ────────────────────────────────────────────────────────

    def _build_cmd(self):
        key  = self._active
        args = [key]

        if key == "--launch":
            m = self.lm_model.get().strip()
            if m and "no models" not in m: args += ["--model", m]
            p = self.lm_port.get()
            if p > 0: args += ["--port", str(p)]
            h = self.lm_host.get().strip()
            if h != "127.0.0.1": args += ["--host", h]
            args += ["--startup-timeout", str(self.lm_timeout.get()),
                     "--max-attempts",    str(self.lm_attempts.get())]

        elif key == "--switch":
            m = self.sw_model.get().strip()
            if m and "no models" not in m: args += ["--base-model", m]
            args += ["--ram-allowance",   str(self.sw_allow.get()),
                     "--interval",        str(self.sw_interval.get()),
                     "--tps-threshold",   str(self.sw_tps.get()),
                     "--min-tps-samples", str(self.sw_mintps.get()),
                     "--kill-timeout",    str(self.sw_kill.get()),
                     "--socket-wait",     str(self.sw_sockwait.get()),
                     "--vram-delta-mb",   str(self.sw_vram.get()),
                     "--gpu-index",       str(self.sw_gpu.get()),
                     "--settle-time",     str(self.sw_settle.get()),
                     "--init-timeout",    str(self.sw_inittout.get()),
                     "--grace-period",    str(self.sw_grace.get()),
                     "--log-level",       self.sw_loglevel.get()]
            if self.sw_novram.get():   args.append("--no-vram")
            if self.sw_noreplay.get(): args.append("--no-auto-replay")

        elif key in ("--rag", "--context", "--embed"):
            f = self.rag_file.get().strip()
            if f: args += ["--file", f]
            p = self.rag_port.get()
            if p > 0: args += ["--port", str(p)]
            args += ["--chunk-size",  str(self.rag_chunk.get()),
                     "--overlap",     str(self.rag_overlap.get()),
                     "--k",           str(self.rag_k.get()),
                     "--search-type", self.rag_stype.get(),
                     "--max-turns",   str(self.rag_turns.get())]
            db = self.rag_dbdir.get().strip()
            if db and db != "./chroma_db": args += ["--db-dir", db]
            if self.rag_ctx.get():     args.append("--context")
            if self.rag_rebuild.get(): args.append("--force-rebuild")

        elif key == "--agentic":
            q = self.ag_query_text.get("1.0", "end").strip()
            if q: args += ["--query", q]
            args += ["--port",        str(self.ag_port.get()),
                     "--model",       self.ag_model.get().strip(),
                     "--temperature", str(self.ag_temp.get()),
                     "--max-tokens",  str(self.ag_maxtok.get()),
                     "--iterations",  str(self.ag_iters.get()),
                     "--log-level",   self.ag_loglvl.get()]
            if self.ag_verbose.get(): args.append("--verbose")

        elif key == "--test":
            args.append(self.ts_suite.get().strip())

        elif key == "--install":
            pkgs = self.inst_pkg.get().strip()
            if pkgs: args += pkgs.split()

        return args

    # ── Run / Stop ────────────────────────────────────────────────────────────

    def _run(self):
        if self._proc and self._proc.poll() is None:
            self._emit("⚠  Already running — stop it first.\n", "warn"); return

        key = self._active
        if key == "--agentic" and not self.ag_query_text.get("1.0", "end").strip():
            self._emit("⚠  Please enter a task or query for the Agentic runner in the Query text box above.\n", "warn")
            return
        if key == "--install" and not self.inst_pkg.get().strip():
            self._emit("⚠  Please enter space-separated package name(s) to install.\n", "warn")
            return

        argv    = self._build_cmd()
        python  = bundled_python()
        cmd     = [python, LUMINA_PY] + argv
        display = " ".join(f'"{a}"' if " " in a else a for a in cmd)
        self._emit(f"▶  {display}\n", "info")

        env = os.environ.copy()
        sp  = os.path.join(PROJECT_ROOT, "python-dependencies",
                           "macos-intel", "lib", "python3.10", "site-packages")
        if os.path.isdir(sp):
            env["PYTHONPATH"] = sp

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=PROJECT_ROOT, env=env)
        except Exception as e:
            self._emit(f"[!] Launch failed: {e}\n", "err"); return

        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        threading.Thread(target=self._stream, daemon=True).start()

    def _stream(self):
        try:
            for line in self._proc.stdout:
                tag = self._tag(line)
                self._emit(line, tag)
        except Exception:
            pass
        rc = self._proc.wait()
        tag = "ok" if rc == 0 else "err"
        self._emit(f"\n── Process exited (code {rc}) ──\n", tag)
        self.after(0, lambda: (self._run_btn.configure(state="normal"),
                               self._stop_btn.configure(state="disabled")))

    def _stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._emit("\n■  Stop requested (SIGTERM)\n", "warn")
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    @staticmethod
    def _tag(line):
        l = line.lower()
        if any(k in l for k in ("error","[!]","failed","exception","traceback")): return "err"
        if any(k in l for k in ("✔","✓","[+]","success","ready","listening")):    return "ok"
        if any(k in l for k in ("warning","warn","[*]")):                         return "warn"
        return None

    def _emit(self, text, tag=None):
        def _do():
            self._con.configure(state="normal")
            self._con.insert("end", text, tag or "")
            self._con.see("end")
            self._con.configure(state="disabled")
        self.after(0, _do)

    def _clear(self):
        self._con.configure(state="normal")
        self._con.delete("1.0", "end")
        self._con.configure(state="disabled")


if __name__ == "__main__":
    app = LuminaGUI()
    app.mainloop()
