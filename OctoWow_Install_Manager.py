import os
import sys
import json
import shutil
import subprocess
import math
import threading
import queue
import urllib.request
import zipfile
import io
import re
import hashlib
import ssl
import socket
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# --- CONFIGURATION ---
CLIENT_ZIP_URL = "https://your-server.com/OctoWoW_Client.zip" # <-- CHANGE THIS TO YOUR ACTUAL CLIENT ZIP URL
CONFIG_FILE = "octowow_config.json"
VERSION = "2.3.1"

# --- THEME COLORS ---
BG_COLOR = "#0B0F19"         
SURFACE_COLOR = "#151A28"    
CARD_COLOR = "#1C2133"       
ACCENT_COLOR = "#6366F1"     
ACCENT_HOVER = "#4F46E5"
TEXT_MAIN = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
SUCCESS_COLOR = "#10B981"
WARNING_COLOR = "#F59E0B"
ERROR_COLOR = "#EF4444"
INFO_COLOR = "#3B82F6"

# --- UTILITY FUNCTIONS ---
def get_persist_path():
    if getattr(sys, 'frozen', False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_base_path():
    if getattr(sys, 'frozen', False): return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

class CTkToolTip:
    """Modern tooltip for CustomTkinter widgets."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        if not self.text: return
        x = self.widget.winfo_pointerx() + 15
        y = self.widget.winfo_pointery() + 15
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        self.tw.attributes("-topmost", True)
        frame = ctk.CTkFrame(self.tw, border_width=1, border_color="#2A2E3F", fg_color=CARD_COLOR, corner_radius=4)
        frame.pack()
        lbl = ctk.CTkLabel(frame, text=self.text, text_color=TEXT_MAIN, wraplength=300, justify="left", font=("Segoe UI", 11), padx=12, pady=8)
        lbl.pack()

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """Custom hardware-accelerated smooth scrolling frame using Lerp animation."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target_y = 0.0
        self._is_animating = False
        self._scroll_multiplier = 0.06  

    def _mouse_wheel_all(self, event):
        x, y = self.winfo_pointerxy()
        rx, ry = self.winfo_rootx(), self.winfo_rooty()
        if not (rx <= x <= rx + self.winfo_width() and ry <= y <= ry + self.winfo_height()): return
        if self._parent_canvas.bbox("all") is None: return
        
        content_height = self._parent_canvas.bbox("all")[3]
        frame_height = self._parent_canvas.winfo_height()
        if content_height <= frame_height: return

        if not self._is_animating:
            self._target_y = self._parent_canvas.yview()[0]

        direction = -1 if event.delta > 0 else 1
        ratio = frame_height / content_height
        adjusted_mult = self._scroll_multiplier * ratio * 2.5 
        
        self._target_y += direction * adjusted_mult
        self._target_y = max(0.0, min(1.0, self._target_y))

        if not self._is_animating:
            self._is_animating = True
            self._animate_scroll()

    def _animate_scroll(self):
        if not self.winfo_exists(): return
        current_y = self._parent_canvas.yview()[0]
        
        if abs(self._target_y - current_y) < 0.001:
            self._parent_canvas.yview_moveto(self._target_y)
            self._is_animating = False
            return

        new_y = current_y + (self._target_y - current_y) * 0.18 
        self._parent_canvas.yview_moveto(new_y)
        self.after(16, self._animate_scroll)

# ==========================================
# 1. MODEL: CONFIG MANAGER
# ==========================================
class ConfigManager:
    def __init__(self):
        self.path = os.path.join(get_persist_path(), CONFIG_FILE)
        self.data = self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f: return json.load(f)
            except: pass
        return {}

    def save(self):
        with open(self.path, 'w') as f: json.dump(self.data, f, indent=4)

    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value):
        self.data[key] = value
        self.save()

# ==========================================
# 2. CONTROLLER: GIT MANAGER
# ==========================================
class GitManager:
    @staticmethod
    def has_git():
        try:
            subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except: return False

    @staticmethod
    def check_update_available(repo_path):
        try:
            subprocess.run(["git", "fetch"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).strip()
            remote = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=repo_path, stderr=subprocess.PIPE, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).strip()
            return local != remote
        except: return False

    @staticmethod
    def pull_or_clone(url, target_path):
        """Forces a clean pull/update regardless of local file changes."""
        if os.path.exists(os.path.join(target_path, ".git")):
            subprocess.run(["git", "-C", target_path, "fetch", "--all"], check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            try: subprocess.run(["git", "-C", target_path, "reset", "--hard", "@{u}"], check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            except: subprocess.run(["git", "-C", target_path, "reset", "--hard", "FETCH_HEAD"], check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            if os.path.exists(target_path): shutil.rmtree(target_path)
            if url: subprocess.run(["git", "clone", url, target_path], check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)

# ==========================================
# 3. VIEW & CONTROLLER: UI AND INSTALL LOGIC
# ==========================================
class OctoWowApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"OctoWoW Install Manager v{VERSION}")
        self.geometry("1050x780")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)

        icon_path = os.path.join(get_base_path(), "PurpleWowLogo.ico")
        if os.path.exists(icon_path): self.iconbitmap(icon_path)

        self.config = ConfigManager()
        self.msg_queue = queue.Queue()
        self.slider_widgets = []
        self.client_dl_window = None
        
        self.addon_cards = []
        self.is_scanning_addons = False
        self.current_addon_data = [] 
        
        self.init_variables()
        self.build_ui()
        self.after(100, self.process_queue)
        self.trigger_addon_scan(show_loading=False)

    def init_variables(self):
        self.descriptions = {
            "autologin": "Automates the authentication process. Bypasses the standard login screen.",
            "dxvk_standard": "Includes DXVK v2.6.2. Translates legacy DirectX 9 calls into modern Vulkan API.",
            "dxvk_amd": "Uses DXVK v2.5.3, an older stable release that prevents crashing issues specific to AMD.",
            "ClassicAPI.dll": "Backports a massive part of the modern WoW API (550+ functions, Lua 5.1 syntax).",
            "nampower.dll": "Implements ping compensation. Bypasses a 1.12 client flaw to enable queueing spell casts.",
            "no1600x1200.dll": "Removes the hardcoded 1600x1200 resolution limit.",
            "perf_boost.dll": "Provides dynamic render distance controls (culling).",
            "UnitXP_SP3.dll": "Engine-level optimizations replacing legacy assembly.",
            "VanillaHelpers.dll": "Expands engine limits. Raises the client memory allocator from 2GB to 4GB.",
            "SuperWoWhook.dll": "Injects a massively expanded Lua API. Increases macro limit.",
            "transmogfix.dll": "Eliminates FPS drops caused by rapid equipment visual updates.",
            "weirdperformance.dll": "Engine-level optimizations: SIMD math replacements, etc.",
            "bigcursor.dll": "Upscales the hardware cursor for improved visibility on modern resolutions.",
            "customassets.dll": "Enables loading loose game asset files from the Data/ directory.",
            "logsessions.dll": "Organizes combat and chat logs into clean, per-character, per-day files automatically.",
            "minimapicons.dll": "Adds TBC/WotLK-style minimap tracking icons for NPCs and objects.",
            "pngscreenshots.dll": "Saves screenshots as compressed PNG files to completely eliminate frame drops.",
            "worldmarkers.dll": "Place up to 5 animated colored markers (Cataclysm style) in the world.",
            "fov": "Calculates horizontal Field of View mathematically scaled based on your screen ratio.",
            "farclip": "Increases the maximum terrain render distance.",
            "frill": "Changes the ground clutter (grass) render distance.",
            "nameplate": "Increases the distance at which enemy nameplates become visible.",
            "cam": "Increases the maximum camera zoom-out distance.",
            "sound": "Increases the maximum number of simultaneous audio channels.",
            "loot": "Reverses the auto-loot behavior so you always auto-loot.",
            "bg_sound": "Allows game sounds to continue playing while in the background.",
            "laa": "Patches the executable to be Large Address Aware (4GB RAM usage).",
            "cam_fix": "Fixes a bug where rotating the camera snaps your view.",
            "dep_fix": "Disables Data Execution Prevention (DEP) for WoW_Tweaked.exe.",
            "corrupt_bypass": "Bypasses GlueXML signature checks to prevent 'Corrupt Interface' errors."
        }

        self.wow_dir = ctk.StringVar(value=self.config.get('wow_dir', ''))
        self.gpu_type = ctk.StringVar(value=self.config.get('gpu_type', self.detect_gpu()))
        self.install_autologin = ctk.BooleanVar(value=self.config.get('install_autologin', True))
        self.tracked_addons = self.config.get('tracked_addons', [])

        self.core_plugins = {}
        for dll in ["ClassicAPI.dll", "nampower.dll", "no1600x1200.dll", "perf_boost.dll", "SuperWoWhook.dll", "transmogfix.dll", "UnitXP_SP3.dll", "VanillaHelpers.dll", "weirdperformance.dll"]:
            self.core_plugins[dll] = ctk.BooleanVar(value=self.config.get('core_plugins', {}).get(dll, True))

        self.optional_plugins = {}
        for dll in ["bigcursor.dll", "customassets.dll", "logsessions.dll", "minimapicons.dll", "pngscreenshots.dll", "worldmarkers.dll"]:
            self.optional_plugins[dll] = ctk.BooleanVar(value=self.config.get('optional_plugins', {}).get(dll, False))

        self.addon_dependencies = {"nampower.dll": "nampowersettings", "perf_boost.dll": "perfboostsettings", "UnitXP_SP3.dll": "UnitXP_SP3_Addon", "SuperWoWhook.dll": "SuperAPI"}

        t_conf = self.config.get('tweaks', {})
        self.vt_fov = ctk.DoubleVar(value=t_conf.get('vt_fov', 0))
        
        self.screen_w = self.winfo_screenwidth()
        self.screen_h = self.winfo_screenheight()
        self.detected_ratio = self.screen_w / self.screen_h
        self.ratio_options = {
            f"Auto ({self.screen_w}x{self.screen_h})": self.detected_ratio,
            "4:3 (Standard)": 4.0/3.0, "16:9 (Widescreen)": 16.0/9.0, "16:10 (Widescreen)": 16.0/10.0, "21:9 (Ultrawide)": 21.0/9.0, "32:9 (Super Ultrawide)": 32.0/9.0
        }
        self.ratio_var = ctk.StringVar(value=t_conf.get('ratio_var', list(self.ratio_options.keys())[0]))
        
        self.vt_farclip = ctk.IntVar(value=t_conf.get('vt_farclip', 1500))
        self.vt_frill = ctk.IntVar(value=t_conf.get('vt_frill', 300))
        self.vt_nameplate = ctk.IntVar(value=t_conf.get('vt_nameplate', 41))
        self.vt_soundchan = ctk.IntVar(value=t_conf.get('vt_soundchan', 64))
        self.vt_maxcam = ctk.IntVar(value=t_conf.get('vt_maxcam', 100))
        
        self.vt_quickloot = ctk.BooleanVar(value=t_conf.get('vt_quickloot', True))
        self.vt_bg_sound = ctk.BooleanVar(value=t_conf.get('vt_bg_sound', True))
        self.vt_laa = ctk.BooleanVar(value=t_conf.get('vt_laa', True))
        self.vt_cam_fix = ctk.BooleanVar(value=t_conf.get('vt_cam_fix', True))
        self.vt_dep_fix = ctk.BooleanVar(value=t_conf.get('vt_dep_fix', True))
        self.vt_corrupt_bypass = ctk.BooleanVar(value=t_conf.get('vt_corrupt_bypass', True))
        
        self.safety_override = ctk.BooleanVar(value=False)

        if self.vt_fov.get() == 0: self.on_ratio_change()

    def detect_gpu(self):
        try:
            output = subprocess.check_output("wmic path win32_VideoController get name", shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode()
            if "AMD" in output.upper() or "RADEON" in output.upper(): return "AMD"
            return "Standard"
        except: return "Standard" 

    def on_ratio_change(self, event=None):
        selection = self.ratio_var.get()
        ratio = self.ratio_options.get(selection, 4.0/3.0)
        default_ar, default_fov = 4.0 / 3.0, 1.570796
        fov = 2 * math.atan((ratio / default_ar) * math.tan(default_fov / 2))
        self.vt_fov.set(round(fov, 4))

    def toggle_safety_limits(self):
        override = self.safety_override.get()
        for slider, safe_max, extreme_max, var, val_lbl in self.slider_widgets:
            if override:
                slider.configure(to=extreme_max)
            else:
                slider.configure(to=safe_max)
                if var.get() > safe_max:
                    var.set(safe_max)
            # Force UI update
            slider.set(var.get())
            val_lbl.configure(text=str(int(var.get())))

    def save_all_state(self, *args):
        self.config.set('wow_dir', self.wow_dir.get())
        self.config.set('gpu_type', self.gpu_type.get())
        self.config.set('install_autologin', self.install_autologin.get())
        self.config.set('core_plugins', {k: v.get() for k, v in self.core_plugins.items()})
        self.config.set('optional_plugins', {k: v.get() for k, v in self.optional_plugins.items()})
        self.config.set('tracked_addons', self.tracked_addons)
        self.config.set('tweaks', {
            'vt_fov': self.vt_fov.get(), 'ratio_var': self.ratio_var.get(), 'vt_farclip': self.vt_farclip.get(),
            'vt_frill': self.vt_frill.get(), 'vt_nameplate': self.vt_nameplate.get(), 'vt_soundchan': self.vt_soundchan.get(),
            'vt_maxcam': self.vt_maxcam.get(), 'vt_quickloot': self.vt_quickloot.get(), 'vt_bg_sound': self.vt_bg_sound.get(),
            'vt_laa': self.vt_laa.get(), 'vt_cam_fix': self.vt_cam_fix.get(), 'vt_dep_fix': self.vt_dep_fix.get(),
            'vt_corrupt_bypass': self.vt_corrupt_bypass.get()
        })

    # --- UI BUILDING ---
    def build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- SIDEBAR ---
        self.sidebar = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1) 

        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=(30, 25), sticky="w")
        
        logo = ctk.CTkFrame(title_frame, fg_color="transparent")
        logo.pack(anchor="w")
        ctk.CTkLabel(logo, text="OCTO", font=("Segoe UI Black", 24), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkLabel(logo, text="WOW", font=("Segoe UI Black", 24), text_color=ACCENT_COLOR).pack(side="left")
        ctk.CTkLabel(title_frame, text=f"Install Manager v{VERSION}", font=("Segoe UI", 12), text_color=TEXT_MUTED).pack(anchor="w")

        self.nav_btns = {}
        nav_items = [
            ("⚙️ Game Settings", "Settings", self.show_settings),
            ("🔌 Client Mods", "Mods", self.show_mods),
            ("📦 Addon Manager", "Addons", self.show_addons),
            ("🚀 Game Updates", "Updater", self.show_updater)
        ]
        
        for i, (label, name, cmd) in enumerate(nav_items):
            btn = ctk.CTkButton(self.sidebar, text=f"  {label}", font=("Segoe UI", 14, "bold"), fg_color="transparent", 
                                text_color=TEXT_MAIN, hover_color=CARD_COLOR, anchor="w", height=45, command=cmd)
            btn.grid(row=i+1, column=0, padx=10, pady=4, sticky="ew")
            self.nav_btns[name] = btn

        ctk.CTkButton(self.sidebar, text="💾 Apply Changes", font=("Segoe UI", 14, "bold"), fg_color=CARD_COLOR, hover_color="#2A2E3F",
                      text_color=TEXT_MAIN, height=45, command=self.run_installation).grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        ctk.CTkButton(self.sidebar, text="▶ PLAY GAME", font=("Segoe UI", 16, "bold"), fg_color=SUCCESS_COLOR, hover_color="#059669",
                      text_color="#ffffff", height=55, command=self.launch_game).grid(row=7, column=0, padx=20, pady=(0, 30), sticky="ew")

        # --- MAIN CONTENT AREA ---
        self.main_container = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.frames = {}
        self.build_settings_tab()
        self.build_mods_tab()
        self.build_addons_tab()
        self.build_updater_tab()
        
        self.show_settings()

    def select_nav_btn(self, name):
        for btn_name, btn in self.nav_btns.items():
            if btn_name == name: btn.configure(fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER)
            else: btn.configure(fg_color="transparent", hover_color=CARD_COLOR)

    def hide_all_frames(self):
        for frame in self.frames.values(): frame.pack_forget()

    # --- SETTINGS TAB ---
    def show_settings(self):
        self.select_nav_btn("Settings")
        self.hide_all_frames()
        self.frames["Settings"].pack(fill="both", expand=True)

    def build_settings_tab(self):
        frame = SmoothScrollableFrame(self.main_container, fg_color="transparent")
        self.frames["Settings"] = frame

        ctk.CTkLabel(frame, text="Game Settings", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(10, 20), padx=10)

        card_dir = self.create_card(frame, "📁 Installation Directory")
        dir_row = ctk.CTkFrame(card_dir, fg_color="transparent")
        dir_row.pack(fill="x", pady=5)
        ctk.CTkEntry(dir_row, textvariable=self.wow_dir, width=380, fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left", padx=(0, 10))
        ctk.CTkButton(dir_row, text="Browse", width=80, fg_color=CARD_COLOR, hover_color="#2A2E3F", command=self.browse_dir).pack(side="left", padx=(0, 10))
        ctk.CTkButton(dir_row, text="Install New Client", width=140, fg_color=SUCCESS_COLOR, hover_color="#059669", font=("Segoe UI", 12, "bold"), command=self.install_new_client).pack(side="left")

        card_env = self.create_card(frame, "🖥️ Environment & Quality of Life")
        env_row = ctk.CTkFrame(card_env, fg_color="transparent")
        env_row.pack(fill="x", pady=5)
        ctk.CTkRadioButton(env_row, text="Standard DXVK (NVIDIA/Intel)", variable=self.gpu_type, value="Standard", text_color=TEXT_MAIN).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(env_row, text="AMD Specific DXVK", variable=self.gpu_type, value="AMD", text_color=TEXT_MAIN).pack(side="left", padx=(0, 20))
        
        qol_grid = ctk.CTkFrame(card_env, fg_color="transparent")
        qol_grid.pack(fill="x", pady=(15, 0))
        self.create_switch(qol_grid, "Auto Login Mod", self.install_autologin, "autologin").grid(row=0, column=0, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Always Auto-Loot", self.vt_quickloot, "loot").grid(row=0, column=1, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Background Sounds", self.vt_bg_sound, "bg_sound").grid(row=1, column=0, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Large Address Aware (4GB)", self.vt_laa, "laa").grid(row=1, column=1, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Fix Camera Skip", self.vt_cam_fix, "cam_fix").grid(row=2, column=0, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Corrupt Interface Bypass", self.vt_corrupt_bypass, "corrupt_bypass").grid(row=2, column=1, padx=(0,40), pady=8, sticky="w")
        self.create_switch(qol_grid, "Disable DEP (Admin)", self.vt_dep_fix, "dep_fix").grid(row=3, column=0, padx=(0,40), pady=8, sticky="w")

        card_eng = self.create_card(frame, "🛠️ Engine Adjustments")
        top_eng = ctk.CTkFrame(card_eng, fg_color="transparent")
        top_eng.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(top_eng, text="Aspect Ratio:", text_color=TEXT_MAIN).pack(side="left", padx=(0, 10))
        opts = list(self.ratio_options.keys())
        ctk.CTkComboBox(top_eng, variable=self.ratio_var, values=opts, command=self.on_ratio_change, width=180, fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(top_eng, text="FoV (Rad):", text_color=TEXT_MAIN).pack(side="left", padx=(0, 10))
        ctk.CTkEntry(top_eng, textvariable=self.vt_fov, width=80, fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left")
        
        sw = ctk.CTkSwitch(top_eng, text="Disable Safety Limits", variable=self.safety_override, command=self.toggle_safety_limits, progress_color=ERROR_COLOR)
        sw.pack(side="right")
        CTkToolTip(sw, "Warning: Exceeding max limits may cause game instability.")

        self.create_slider(card_eng, "Render Distance", self.vt_farclip, 777, 1500, 10000, "farclip")
        self.create_slider(card_eng, "Ground Clutter", self.vt_frill, 70, 300, 1000, "frill")
        self.create_slider(card_eng, "Nameplate Distance", self.vt_nameplate, 20, 41, 150, "nameplate")
        self.create_slider(card_eng, "Max Camera Zoom", self.vt_maxcam, 50, 100, 250, "cam")
        self.create_slider(card_eng, "Audio Channels", self.vt_soundchan, 12, 64, 128, "sound")

    def create_card(self, parent, title):
        card = ctk.CTkFrame(parent, fg_color=SURFACE_COLOR, corner_radius=8)
        card.pack(fill="x", pady=(0, 15), padx=10)
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack(anchor="w", padx=15, pady=(15, 5))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        return inner

    def create_switch(self, parent, text, var, desc_key):
        sw = ctk.CTkSwitch(parent, text=text, variable=var, text_color=TEXT_MAIN, progress_color=ACCENT_COLOR)
        CTkToolTip(sw, self.descriptions[desc_key])
        return sw

    def create_slider(self, parent, text, var, min_val, safe_max, extreme_max, desc_key):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=8)
        lbl = ctk.CTkLabel(row, text=text, text_color=TEXT_MAIN, width=150, anchor="w")
        lbl.pack(side="left")
        CTkToolTip(lbl, self.descriptions[desc_key])
        
        val_lbl = ctk.CTkLabel(row, text=str(var.get()), width=40, text_color=ACCENT_COLOR, font=("Segoe UI", 12, "bold"))
        val_lbl.pack(side="right")
        
        def update_lbl(val): val_lbl.configure(text=str(int(val)))
            
        current_max = extreme_max if self.safety_override.get() else safe_max
        slider = ctk.CTkSlider(row, from_=min_val, to=current_max, variable=var, command=update_lbl, button_color=ACCENT_COLOR, button_hover_color=ACCENT_HOVER, progress_color=CARD_COLOR)
        slider.pack(side="right", fill="x", expand=True, padx=15)
        self.slider_widgets.append((slider, safe_max, extreme_max, var, val_lbl))

    def browse_dir(self):
        d = filedialog.askdirectory(title="Select Vanilla 1.12 WoW Folder")
        if d:
            self.wow_dir.set(os.path.normpath(d))
            self.save_all_state()
            self.trigger_addon_scan(show_loading=True)

    # --- CLIENT BITTORRENT DOWNLOADER / UPDATER ---
    def install_new_client(self):
        target = filedialog.askdirectory(title="Select an Empty Folder to Install OctoWoW")
        if not target: return
        
        if os.listdir(target):
            if not messagebox.askyesno("Folder Not Empty", "The selected folder is not empty. Do you want to continue syncing the game here anyway?"):
                return
                
        self.wow_dir.set(os.path.normpath(target))
        self.save_all_state()
        
        self.client_dl_window = ctk.CTkToplevel(self)
        self.client_dl_window.title("Downloading OctoWoW Client")
        self.client_dl_window.geometry("550x400")
        self.client_dl_window.resizable(False, False)
        self.client_dl_window.attributes("-topmost", True)
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 275
        y = self.winfo_y() + (self.winfo_height() // 2) - 200
        self.client_dl_window.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(self.client_dl_window, text="Downloading OctoWoW Client via BitTorrent", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack(pady=(20, 5))
        self.dl_status = ctk.CTkLabel(self.client_dl_window, text="Connecting to seeders...", text_color=TEXT_MUTED)
        self.dl_status.pack(pady=5)
        
        self.dl_prog = ctk.CTkProgressBar(self.client_dl_window, width=450, progress_color=ACCENT_COLOR)
        self.dl_prog.set(0)
        self.dl_prog.pack(pady=15)
        
        self.dl_console = ctk.CTkTextbox(self.client_dl_window, width=480, height=140, fg_color=BG_COLOR, text_color=TEXT_MUTED, font=("Consolas", 11), state="disabled")
        self.dl_console.pack(pady=(0, 15))
        
        threading.Thread(target=self._sync_client_thread, args=(target, None, True), daemon=True).start()

    def ensure_aria2c(self):
        aria_path = os.path.join(get_persist_path(), "aria2c.exe")
        if os.path.exists(aria_path): return aria_path
        
        self.msg_queue.put(("client_dl_progress", (0, "Downloading BitTorrent engine...")))
        url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-32bit-build1.zip"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("aria2c.exe"):
                    with open(aria_path, "wb") as f: f.write(zf.read(name))
                    break
        return aria_path

    def _sync_client_thread(self, target_dir, new_hash=None, is_new_install=False):
        try:
            if not new_hash:
                import socket
                socket.setdefaulttimeout(10)
                
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                req = urllib.request.Request("https://dl.octowow.st/download/client.torrent", headers={'User-Agent': 'OctoUpdater/1.3.1'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    torrent_data = resp.read()
                    new_hash = hashlib.sha1(torrent_data).hexdigest()
                    
            aria_path = self.ensure_aria2c()
            torrent_url = "https://dl.octowow.st/download/client.torrent"
            
            cmd = [
                aria_path,
                f"--dir={target_dir}",
                "--seed-time=0",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                "--summary-interval=1",
                "--truncate-console-readout=false",
                "--console-log-level=info",
                "--check-integrity=true",
                "--continue=true",
                torrent_url
            ]
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Custom non-blocking byte reader to catch BitTorrent '\r' overwrites
            buffer = ""
            while True:
                char = proc.stdout.read(1)
                if not char and proc.poll() is not None:
                    break
                    
                if char in ('\r', '\n'):
                    line_clean = buffer.strip()
                    if line_clean:
                        # Match progress fractions: e.g. 1.1GiB/11GiB(9%)
                        frac_match = re.search(r'([0-9.]+[KMGTP]?i?B|0B)/([0-9.]+[KMGTP]?i?B|0B)\((\d+)%\)', line_clean, re.IGNORECASE)
                        
                        if frac_match:
                            dl_amt, total_amt, pct = frac_match.groups()
                            if "Checksum" in line_clean or "verify" in line_clean.lower():
                                self.msg_queue.put(("client_dl_progress", (int(pct)/100.0, f"Verifying Existing Files... {pct}% | {dl_amt} / {total_amt}")))
                            else:
                                spd_match = re.search(r'DL:([^\s\]]+)', line_clean)
                                eta_match = re.search(r'ETA:([^\]\s]+)', line_clean)
                                speed = spd_match.group(1) if spd_match else "0B"
                                eta = eta_match.group(1) if eta_match else "Unknown"
                                txt = f"Downloading Game Data... {pct}%\nSpeed: {speed}/s | ETA: {eta} | {dl_amt} / {total_amt}"
                                self.msg_queue.put(("client_dl_progress", (int(pct)/100.0, txt)))
                        else:
                            comp_match = re.search(r'Download complete:\s*(.+)', line_clean, re.IGNORECASE)
                            alloc_match = re.search(r'Allocating disk space.*\s(.+)', line_clean, re.IGNORECASE)

                            if comp_match:
                                fname = os.path.basename(comp_match.group(1).strip())
                                # Ignore the internal notification that it fetched the .torrent file
                                if fname and not fname.endswith('.torrent'):
                                    self.msg_queue.put(("client_dl_file", f"[✔️] Verified/Completed: {fname}"))
                            elif alloc_match:
                                fname = os.path.basename(alloc_match.group(1).strip())
                                if fname: self.msg_queue.put(("client_dl_file", f"[⚙️] Allocating space for: {fname}"))
                            elif "Checksum error" in line_clean:
                                self.msg_queue.put(("client_dl_file", f"[⚠️] Checksum mismatch found, repairing..."))
                    buffer = ""
                else:
                    buffer += char

            proc.wait()
            
            if proc.returncode == 0:
                if new_hash:
                    self.config.set('client_hash', new_hash)
                self.msg_queue.put(("client_dl_done", is_new_install))
            else:
                self.msg_queue.put(("client_dl_error", f"Update failed (aria2c error code {proc.returncode})"))
        except Exception as e:
            self.msg_queue.put(("client_dl_error", str(e)))

    # --- MODS TAB ---
    def show_mods(self):
        self.select_nav_btn("Mods")
        self.hide_all_frames()
        self.frames["Mods"].pack(fill="both", expand=True)

    def build_mods_tab(self):
        frame = SmoothScrollableFrame(self.main_container, fg_color="transparent")
        self.frames["Mods"] = frame

        ctk.CTkLabel(frame, text="Client Mods", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(10, 5), padx=10)
        ctk.CTkLabel(frame, text="Toggle core engine modifications and utilities.", text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 20))

        split = ctk.CTkFrame(frame, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=5)
        split.grid_columnconfigure(0, weight=1)
        split.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(split, fg_color=SURFACE_COLOR, corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(left, text="⭐ Recommended Core", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(left, text="Highly recommended for stability.", text_color=TEXT_MUTED, font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=(0, 10))
        
        for dll, var in self.core_plugins.items():
            sw = ctk.CTkSwitch(left, text=dll, variable=var, progress_color=SUCCESS_COLOR)
            sw.pack(anchor="w", padx=20, pady=8)
            CTkToolTip(sw, self.descriptions.get(dll, ""))

        right = ctk.CTkFrame(split, fg_color=SURFACE_COLOR, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(right, text="🛠️ Optional WeirdUtils", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(right, text="Additional quality-of-life plugins.", text_color=TEXT_MUTED, font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=(0, 10))
        
        for dll, var in self.optional_plugins.items():
            sw = ctk.CTkSwitch(right, text=dll, variable=var, progress_color=ACCENT_COLOR)
            sw.pack(anchor="w", padx=20, pady=8)
            CTkToolTip(sw, self.descriptions.get(dll, ""))

    # --- ADDON MANAGER TAB ---
    def show_addons(self):
        self.select_nav_btn("Addons")
        self.hide_all_frames()
        self.frames["Addons"].pack(fill="both", expand=True)

    def build_addons_tab(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.frames["Addons"] = frame

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(top, text="Addon Manager", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkButton(top, text="🔄 Check for Updates", fg_color=CARD_COLOR, hover_color="#2A2E3F", font=("Segoe UI", 12, "bold"), command=lambda: self.trigger_addon_scan(show_loading=True)).pack(side="right")

        ctk.CTkLabel(frame, text="Automatically scans your WoW directory. Add a Git URL to install new addons.", text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 15))

        ctrl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=10, pady=(10, 15))

        add_frame = ctk.CTkFrame(ctrl_frame, fg_color=SURFACE_COLOR, corner_radius=8)
        add_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.addon_url_var = ctk.StringVar()
        ctk.CTkEntry(add_frame, textvariable=self.addon_url_var, placeholder_text="https://github.com/username/addon.git", fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left", fill="x", expand=True, padx=(15, 10), pady=10)
        ctk.CTkButton(add_frame, text="➕ Install from Git URL", width=160, fg_color=CARD_COLOR, hover_color="#2A2E3F", font=("Segoe UI", 12, "bold"), command=self.add_addon).pack(side="left", padx=(0, 15), pady=10)

        search_frame = ctk.CTkFrame(ctrl_frame, fg_color=SURFACE_COLOR, corner_radius=8)
        search_frame.pack(side="right")
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_addons_ui())
        ctk.CTkEntry(search_frame, textvariable=self.search_var, placeholder_text="🔍 Search Addons...", width=180, fg_color=BG_COLOR, border_color=CARD_COLOR).pack(padx=15, pady=10)

        self.addon_scroll = SmoothScrollableFrame(frame, fg_color="transparent")
        self.addon_scroll.pack(fill="both", expand=True, padx=5)

    def trigger_addon_scan(self, show_loading=True):
        if self.is_scanning_addons: return
        self.is_scanning_addons = True
        
        if show_loading:
            for widget in self.addon_scroll.winfo_children(): widget.destroy()
            load_frame = ctk.CTkFrame(self.addon_scroll, fg_color="transparent")
            load_frame.pack(expand=True, pady=40)
            ctk.CTkLabel(load_frame, text="⏳", font=("Segoe UI", 36)).pack(pady=(0,10))
            ctk.CTkLabel(load_frame, text="Scanning Addons & Checking GitHub...", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack()
            ctk.CTkLabel(load_frame, text="This might take a minute depending on how many addons you have.", text_color=TEXT_MUTED).pack()
        
        threading.Thread(target=self.scan_addons_thread, daemon=True).start()

    def strip_wow_colors(self, text): return re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', text).strip()

    def parse_toc(self, toc_path):
        metadata = {"Title": "", "Version": "Unknown", "Notes": "No description provided.", "Author": "Unknown"}
        if not os.path.exists(toc_path): return metadata
        try:
            with open(toc_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if line.startswith("##"):
                        parts = line[2:].split(":", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            if key in metadata: metadata[key] = self.strip_wow_colors(parts[1])
        except: pass
        return metadata

    def scan_addons_thread(self):
        wow_dir = self.wow_dir.get().strip()
        addons_dir = os.path.join(wow_dir, "Interface", "AddOns")
        addon_data = []
        has_git = GitManager.has_git()
        
        if os.path.exists(addons_dir):
            for folder in os.listdir(addons_dir):
                if folder.startswith(("Blizzard_", "Turtle_")): continue
                fpath = os.path.join(addons_dir, folder)
                if os.path.isdir(fpath):
                    is_git = os.path.exists(os.path.join(fpath, ".git"))
                    url = next((u for u in self.tracked_addons if u.rstrip('/').split('/')[-1].replace('.git','') == folder), None)
                    
                    needs_update = False
                    if is_git and has_git:
                        needs_update = GitManager.check_update_available(fpath)

                    toc_path = os.path.join(fpath, f"{folder}.toc")
                    meta = self.parse_toc(toc_path)

                    addon_data.append({
                        "folder": folder,
                        "title": meta["Title"] if meta["Title"] else folder,
                        "version": meta["Version"],
                        "author": meta["Author"],
                        "notes": meta["Notes"],
                        "needs_update": needs_update,
                        "url": url,
                        "missing": False,
                        "managed": bool(url or is_git)
                    })
        
        for url in self.tracked_addons:
            folder = url.rstrip('/').split('/')[-1].replace('.git','')
            if not any(a["folder"] == folder for a in addon_data):
                addon_data.append({
                    "folder": folder, "title": folder, "version": "-", "author": "-",
                    "notes": f"Will be downloaded on next update.",
                    "needs_update": False, "url": url, "missing": True, "managed": True
                })
                
        self.msg_queue.put(("render_addons", addon_data))

    def build_all_addon_cards(self, addon_data):
        for widget in self.addon_scroll.winfo_children(): widget.destroy()
        self.addon_cards = []
        
        self.upd_header = ctk.CTkFrame(self.addon_scroll, fg_color="transparent")
        ctk.CTkLabel(self.upd_header, text="⚠️ Updates Available", font=("Segoe UI", 16, "bold"), text_color=WARNING_COLOR).pack(side="left")
        
        self.btn_upd_all = ctk.CTkButton(self.upd_header, text="⬇ Update All", fg_color=WARNING_COLOR, hover_color="#D97706", text_color="#fff", font=("Segoe UI", 12, "bold"))
        self.btn_upd_all.pack(side="right")
        self.btn_upd_all.configure(command=self.sync_all_available_updates)

        self.inst_header = ctk.CTkFrame(self.addon_scroll, fg_color="transparent")
        ctk.CTkLabel(self.inst_header, text="📦 Installed Addons", font=("Segoe UI", 16, "bold"), text_color=TEXT_MAIN).pack(side="left")

        self.no_results_lbl = ctk.CTkLabel(self.addon_scroll, text="No addons match your search.", text_color=TEXT_MUTED)

        if not addon_data:
            self.no_results_lbl.configure(text="No addons found. Set your WoW directory or add a Git URL.")
            self.no_results_lbl.pack(pady=40)
            return

        updates = sorted([a for a in addon_data if a["needs_update"] or a["missing"]], key=lambda x: x["title"].lower())
        installed = sorted([a for a in addon_data if not a["needs_update"] and not a["missing"]], key=lambda x: x["title"].lower())

        for addon in updates:
            card = self.create_addon_card_widget(addon)
            self.addon_cards.append({'type': 'update', 'frame': card, 'data': addon})

        for addon in installed:
            card = self.create_addon_card_widget(addon)
            self.addon_cards.append({'type': 'installed', 'frame': card, 'data': addon})

        self.filter_addons_ui()

    def filter_addons_ui(self, *args):
        query = self.search_var.get().lower()
        
        self.upd_header.pack_forget()
        self.inst_header.pack_forget()
        self.no_results_lbl.pack_forget()
        for card in self.addon_cards: card['frame'].pack_forget()
        
        matched_updates = [c for c in self.addon_cards if c['type'] == 'update' and (query in c['data']['title'].lower() or query in c['data']['folder'].lower())]
        matched_installed = [c for c in self.addon_cards if c['type'] == 'installed' and (query in c['data']['title'].lower() or query in c['data']['folder'].lower())]
        
        if matched_updates:
            self.upd_header.pack(fill="x", pady=(10, 5), padx=5)
            for c in matched_updates: c['frame'].pack(fill="x", pady=6, padx=5)
            
        if matched_installed:
            self.inst_header.pack(fill="x", pady=(20, 5), padx=5)
            for c in matched_installed: c['frame'].pack(fill="x", pady=6, padx=5)
            
        if not matched_updates and not matched_installed and self.addon_cards:
            self.no_results_lbl.configure(text="No addons match your search.")
            self.no_results_lbl.pack(pady=40)

    def create_addon_card_widget(self, addon):
        card = ctk.CTkFrame(self.addon_scroll, fg_color=SURFACE_COLOR, corner_radius=8, height=75)
        card.pack_propagate(False)
        card.grid_columnconfigure(1, weight=1)
        
        icon_color = ACCENT_COLOR if addon["managed"] else TEXT_MUTED
        ctk.CTkLabel(card, text="📦", font=("Segoe UI", 24), text_color=icon_color).grid(row=0, column=0, padx=(15, 10), pady=18)
        
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="w", pady=15)
        
        title_color = TEXT_MAIN if not addon["missing"] else ERROR_COLOR
        ctk.CTkLabel(info_frame, text=addon["title"], font=("Segoe UI", 15, "bold"), text_color=title_color).pack(anchor="w")
        
        sub_text = f"v{addon['version']}  •  By {addon['author']}"
        if addon["missing"]: sub_text = "Missing (Will download on update)"
        sub_lbl = ctk.CTkLabel(info_frame, text=sub_text, font=("Segoe UI", 11), text_color=TEXT_MUTED)
        sub_lbl.pack(anchor="w")

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e", padx=15, pady=18)
        
        upd_btn = None
        if addon["needs_update"] or addon["missing"]:
            upd_btn = ctk.CTkButton(btn_frame, text="⬇ Update", font=("Segoe UI", 12, "bold"), fg_color=WARNING_COLOR, hover_color="#D97706", width=100)
            upd_btn.pack(side="left", padx=(0, 10))

        btn_info = ctk.CTkButton(btn_frame, text="i", font=("Georgia", 16, "bold"), width=32, height=32, corner_radius=16, 
                                 fg_color=INFO_COLOR, hover_color="#2563EB", command=lambda a=addon: self.show_addon_details(a))
        btn_info.pack(side="left", padx=(0, 10))
        CTkToolTip(btn_info, "View Description")

        btn_del = ctk.CTkButton(btn_frame, text="🗑", font=("Segoe UI Emoji", 14), width=32, height=32, corner_radius=16, 
                                fg_color=ERROR_COLOR, hover_color="#DC2626", command=lambda a=addon: self.prompt_delete_addon(a["folder"], a["url"]))
        btn_del.pack(side="left")
        CTkToolTip(btn_del, "Uninstall Addon")
        
        pb = ctk.CTkProgressBar(card, progress_color=SUCCESS_COLOR, fg_color=CARD_COLOR, height=4, corner_radius=0)
        pb.set(0)
        
        if upd_btn:
            upd_btn.configure(command=lambda: self.start_single_update(addon, upd_btn, pb))
            
        card.ui_elements = {'sub_lbl': sub_lbl, 'upd_btn': upd_btn, 'pb': pb, 'btn_frame': btn_frame, 'btn_info': btn_info, 'btn_del': btn_del}
        return card

    def show_addon_details(self, addon):
        top = tk.Toplevel(self)
        top.title("Addon Details")
        top.geometry("450x320")
        top.resizable(False, False)
        top.attributes("-topmost", True)
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 225
        y = self.winfo_y() + (self.winfo_height() // 2) - 160
        top.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(top, fg_color=BG_COLOR, corner_radius=0)
        frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(frame, text="📦 " + addon["title"], font=("Segoe UI", 18, "bold"), text_color=ACCENT_COLOR).pack(pady=(20, 5))
        ctk.CTkLabel(frame, text=f"Version: {addon['version']}  |  Author: {addon['author']}", font=("Segoe UI", 12), text_color=TEXT_MUTED).pack()
        
        box = ctk.CTkScrollableFrame(frame, fg_color=SURFACE_COLOR, corner_radius=8)
        box.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(box, text=addon["notes"], font=("Segoe UI", 12), text_color=TEXT_MAIN, wraplength=370, justify="left").pack(anchor="nw", padx=10, pady=10)

    def add_addon(self):
        url = self.addon_url_var.get().strip()
        if url and url not in self.tracked_addons:
            self.tracked_addons.append(url)
            self.save_all_state()
            self.addon_url_var.set("")
            self.trigger_addon_scan(show_loading=True)

    def prompt_delete_addon(self, folder, url):
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to completely uninstall and delete {folder}?"):
            if url and url in self.tracked_addons:
                self.tracked_addons.remove(url)
                self.save_all_state()
                
            wow_dir = self.wow_dir.get().strip()
            addon_path = os.path.join(wow_dir, "Interface", "AddOns", folder)
            if os.path.exists(addon_path): shutil.rmtree(addon_path, ignore_errors=True)
                
            self.trigger_addon_scan(show_loading=True)

    # --- IN-PLACE INDIVIDUAL ADDON UPDATING ---
    def start_single_update(self, addon, upd_btn, pb):
        if not GitManager.has_git():
            messagebox.showerror("Git Not Found", "Git is not installed. Please install Git for Windows.")
            return

        upd_btn.pack_forget()
        pb.pack(fill="x", side="bottom")
        pb.start()
        
        wow_dir = self.wow_dir.get().strip()
        addons_dir = os.path.join(wow_dir, "Interface", "AddOns")
        
        def worker():
            try:
                url = addon["url"]
                folder = addon["folder"]
                target_path = os.path.join(addons_dir, folder)
                if url: GitManager.pull_or_clone(url, target_path)
                else: GitManager.pull_or_clone("", target_path)
                self.msg_queue.put(("single_update_done", (folder, True)))
            except Exception as e:
                self.msg_queue.put(("single_update_done", (folder, False)))
                
        threading.Thread(target=worker, daemon=True).start()

    def sync_all_available_updates(self):
        if not GitManager.has_git():
            messagebox.showerror("Git Not Found", "Git is not installed. Please install Git for Windows.")
            return

        self.btn_upd_all.configure(state="disabled", text="Updating...")
        
        updates = [c for c in self.addon_cards if c['type'] == 'update']
        for c in updates:
            addon = c['data']
            ui = c['frame'].ui_elements
            if ui['upd_btn'] and ui['upd_btn'].winfo_ismapped():
                self.start_single_update(addon, ui['upd_btn'], ui['pb'])

    def rescan_single_addon(self, folder):
        target_card = None
        for c in self.addon_cards:
            if c['data']['folder'] == folder:
                target_card = c
                break
        if not target_card: return
        
        wow_dir = self.wow_dir.get().strip()
        fpath = os.path.join(wow_dir, "Interface", "AddOns", folder)
        meta = self.parse_toc(os.path.join(fpath, f"{folder}.toc"))
        
        addon = target_card['data']
        addon['title'] = meta["Title"] if meta["Title"] else folder
        addon['version'] = meta["Version"]
        addon['author'] = meta["Author"]
        addon['notes'] = meta["Notes"]
        addon['needs_update'] = False
        addon['missing'] = False
        
        target_card['type'] = 'installed'
        
        ui = target_card['frame'].ui_elements
        ui['sub_lbl'].configure(text=f"v{addon['version']}  •  By {addon['author']}")
        ui['pb'].stop()
        ui['pb'].pack_forget()
        
        for w in ui['btn_frame'].winfo_children(): w.destroy()
        
        ctk.CTkLabel(ui['btn_frame'], text="✔️ Updated", text_color=SUCCESS_COLOR, font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 15))
        
        btn_info = ctk.CTkButton(ui['btn_frame'], text="i", font=("Georgia", 16, "bold"), width=32, height=32, corner_radius=16, 
                                 fg_color=INFO_COLOR, hover_color="#2563EB", command=lambda a=addon: self.show_addon_details(a))
        btn_info.pack(side="left", padx=(0, 10))
        CTkToolTip(btn_info, "View Description")

        btn_del = ctk.CTkButton(ui['btn_frame'], text="🗑", font=("Segoe UI Emoji", 14), width=32, height=32, corner_radius=16, 
                                fg_color=ERROR_COLOR, hover_color="#DC2626", command=lambda a=addon: self.prompt_delete_addon(a["folder"], a["url"]))
        btn_del.pack(side="left")
        CTkToolTip(btn_del, "Uninstall Addon")

        if not any(c['type'] == 'update' for c in self.addon_cards):
            self.btn_upd_all.pack_forget()

    # --- GAME UPDATER TAB ---
    def show_updater(self):
        self.select_nav_btn("Updater")
        self.hide_all_frames()
        self.frames["Updater"].pack(fill="both", expand=True)

    def build_updater_tab(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.frames["Updater"] = frame

        center = ctk.CTkFrame(frame, fg_color="transparent")
        center.pack(expand=True)

        ctk.CTkLabel(center, text="OctoWoW Client Updater", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(pady=(0, 5))
        ctk.CTkLabel(center, text="Synchronizes your core game files directly with the official OctoWoW torrent network.", font=("Segoe UI", 13), text_color=TEXT_MUTED).pack(pady=(0, 30))
        
        self.lbl_update_status = ctk.CTkLabel(center, text="Ready.", font=("Segoe UI", 13, "bold"), text_color=TEXT_MAIN)
        self.lbl_update_status.pack(pady=(10, 5))
        
        self.progress_update = ctk.CTkProgressBar(center, width=450, progress_color=ACCENT_COLOR, fg_color=CARD_COLOR)
        self.progress_update.set(0)
        self.progress_update.pack(pady=10)

        self.updater_console = ctk.CTkTextbox(center, width=480, height=120, fg_color=BG_COLOR, text_color=TEXT_MUTED, font=("Consolas", 11), state="disabled")
        self.updater_console.pack(pady=(10, 20))
        
        self.btn_check_update = ctk.CTkButton(center, text="🚀 Check for Game Updates", font=("Segoe UI", 14, "bold"), height=45, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, command=self.check_updates)
        self.btn_check_update.pack(pady=10)

    def check_updates(self):
        wow_dir = self.wow_dir.get().strip()
        if not wow_dir or not os.path.exists(os.path.join(wow_dir, "WoW.exe")):
            messagebox.showerror("Error", "Please set a valid WoW directory in the Game Settings tab first.")
            return

        self.btn_check_update.configure(state="disabled")
        self.lbl_update_status.configure(text="Checking OctoWoW servers...")
        threading.Thread(target=self._check_updates_thread, daemon=True).start()

    def _check_updates_thread(self):
        try:
            import socket
            socket.setdefaulttimeout(10)
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request("https://dl.octowow.st/download/client.torrent", headers={'User-Agent': 'OctoUpdater/1.3.1'})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                torrent_data = resp.read()
                latest_hash = hashlib.sha1(torrent_data).hexdigest()
                
            current_hash = self.config.get('client_hash', '')
            
            if latest_hash != current_hash:
                self.msg_queue.put(("updater_prompt", latest_hash))
            else:
                self.msg_queue.put(("updater_status", "Your OctoWoW client is completely up to date!"))
                self.msg_queue.put(("updater_btn", "normal"))
        except Exception as e:
            self.msg_queue.put(("updater_status", "Failed to reach servers. Please check connection."))
            self.msg_queue.put(("updater_btn", "normal"))

    def prompt_download_update(self, new_hash):
        if messagebox.askyesno("Game Update Available", "An update to the base OctoWoW client is available!\n\nWould you like to synchronize and download it now?"):
            self.lbl_update_status.configure(text="Starting BitTorrent engine...")
            self.progress_update.set(0)
            
            self.updater_console.configure(state="normal")
            self.updater_console.delete("1.0", "end")
            self.updater_console.configure(state="disabled")
            
            target_dir = self.wow_dir.get().strip()
            threading.Thread(target=self._sync_client_thread, args=(target_dir, new_hash, False), daemon=True).start()
        else:
            self.lbl_update_status.configure(text="Update cancelled.")
            self.btn_check_update.configure(state='normal')

    # --- INSTALLATION & DEPLOYMENT LOGIC ---
    def validate_installation_dir(self, target_dir):
        if not target_dir:
            messagebox.showerror("Directory Error", "Please select a Vanilla 1.12 installation directory.")
            return False
        if not os.path.exists(os.path.join(target_dir, "WoW.exe")) or not os.path.isdir(os.path.join(target_dir, "Data")):
            messagebox.showerror("Invalid Directory", "This does not look like a valid Vanilla 1.12 directory.\nPlease make sure WoW.exe is inside.")
            return False
        return True

    def validate_limits(self):
        if self.safety_override.get(): return True 
        if self.vt_farclip.get() > 1500 or self.vt_frill.get() > 300 or self.vt_nameplate.get() > 41 or self.vt_maxcam.get() > 100 or self.vt_soundchan.get() > 64 or self.vt_fov.get() > 2.2689:
            messagebox.showerror("Limit Exceeded", "One of your Vanilla Tweaks values exceeds the safe limit.\nPlease lower it, or check 'Disable Safety Limits'.")
            return False
        return True

    def clean_unselected_files(self, target):
        if not self.install_autologin.get():
            glue_dir = os.path.join(target, "Data", "Interface", "GlueXML")
            for file_name in ["AutoLogin.lua", "AutoLogin.xml", "GlueXML.toc"]:
                file_path = os.path.join(glue_dir, file_name)
                if os.path.exists(file_path):
                    try: os.remove(file_path)
                    except: pass

        for dll_name, var in self.core_plugins.items():
            if not var.get():
                dll_path = os.path.join(target, dll_name)
                if os.path.exists(dll_path):
                    try: os.remove(dll_path)
                    except: pass
                addon_folder = self.addon_dependencies.get(dll_name)
                if addon_folder:
                    addon_path = os.path.join(target, "Interface", "AddOns", addon_folder)
                    if os.path.exists(addon_path): shutil.rmtree(addon_path, ignore_errors=True)

        for dll_name, var in self.optional_plugins.items():
            if not var.get():
                dll_path = os.path.join(target, dll_name)
                if os.path.exists(dll_path):
                    try: os.remove(dll_path)
                    except: pass

    def copy_base_files(self, target):
        payload_dir = os.path.join(get_base_path(), "Payload")
        if not os.path.exists(payload_dir): return 
        if self.install_autologin.get() and os.path.exists(os.path.join(payload_dir, "Data")):
            shutil.copytree(os.path.join(payload_dir, "Data"), os.path.join(target, "Data"), dirs_exist_ok=True)
        if os.path.exists(os.path.join(payload_dir, "Interface")):
            shutil.copytree(os.path.join(payload_dir, "Interface"), os.path.join(target, "Interface"), dirs_exist_ok=True)
        for file in ["VanillaFixes.exe", "VfPatcher.dll", "dxvk.conf"]:
            source_file = os.path.join(payload_dir, file)
            if os.path.exists(source_file): shutil.copy2(source_file, target)

    def configure_dxvk(self, target):
        payload_dir = os.path.join(get_base_path(), "Payload")
        dxvk_folder = "DXVK_AMD" if self.gpu_type.get() == "AMD" else "DXVK_Standard"
        d3d9_src = os.path.join(payload_dir, dxvk_folder, "d3d9.dll")
        if os.path.exists(d3d9_src): shutil.copy2(d3d9_src, target)

    def configure_plugins(self, target):
        payload_base = os.path.join(get_base_path(), "Payload")
        payload_weirdu = os.path.join(payload_base, "WeirdUtils")
        dlls_text_lines = ["dxvk"]

        for dll_name, var in self.core_plugins.items():
            if var.get():
                source_dll = os.path.join(payload_base, dll_name)
                if os.path.exists(source_dll): shutil.copy2(source_dll, target)
                dlls_text_lines.append(dll_name) 

        for dll_name, var in self.optional_plugins.items():
            if var.get():
                source_dll = os.path.join(payload_weirdu, dll_name)
                if os.path.exists(source_dll): shutil.copy2(source_dll, target)
                dlls_text_lines.append(dll_name)

        with open(os.path.join(target, "dlls.txt"), "w") as f:
            f.write("\n".join(dlls_text_lines))

    def run_vanilla_tweaks(self, target):
        wow_exe = os.path.join(target, "WoW.exe")
        tweaks_exe = os.path.join(get_base_path(), "vanilla-tweaks.exe")

        if not os.path.exists(tweaks_exe): return

        args = [tweaks_exe]
        if abs(self.vt_fov.get() - 1.5708) < 0.0001: args.append("--no-fov")
        else: args.extend(["--fov", str(self.vt_fov.get())])
        if self.vt_farclip.get() == 777: args.append("--no-farclip")
        else: args.extend(["--farclip", str(self.vt_farclip.get())])
        if self.vt_frill.get() == 70: args.append("--no-frilldistance")
        else: args.extend(["--frilldistance", str(self.vt_frill.get())])
        if self.vt_nameplate.get() == 20: args.append("--no-nameplatedistance")
        else: args.extend(["--nameplatedistance", str(self.vt_nameplate.get())])
        if self.vt_soundchan.get() == 12: args.append("--no-soundchannels")
        else: args.extend(["--soundchannels", str(self.vt_soundchan.get())])
        if self.vt_maxcam.get() != 50: args.extend(["--maxcameradistance", str(self.vt_maxcam.get())])

        if not self.vt_quickloot.get(): args.append("--no-quickloot")
        if not self.vt_bg_sound.get(): args.append("--no-sound-in-background")
        if not self.vt_laa.get(): args.append("--no-largeaddressaware")
        if not self.vt_cam_fix.get(): args.append("--no-cameraskipfix")

        args.extend(["-o", os.path.join(target, "WoW_Tweaked.exe")])
        args.append(wow_exe)
        subprocess.run(args, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def apply_corrupt_interface_bypass(self, target):
        if not self.vt_corrupt_bypass.get(): return
        exe_path = os.path.join(target, "WoW_Tweaked.exe")
        if not os.path.exists(exe_path): exe_path = os.path.join(target, "WoW.exe")
        try:
            with open(exe_path, "r+b") as f:
                patches = {0x2f113a: b'\xeb', 0x2f113b: b'\x19', 0x2f1158: b'\x03', 0x2f11a7: b'\x03', 0x2f11f0: b'\xeb', 0x2f11f1: b'\xb2'}
                for offset, byte_val in patches.items():
                    f.seek(offset)
                    f.write(byte_val)
        except: pass

    def apply_process_mitigations(self):
        if not self.vt_dep_fix.get(): return
        ps_cmd = "Set-ProcessMitigation -Name WoW_Tweaked.exe -Disable DEP, EmulateAtlThunks"
        full_cmd = f"Start-Process powershell -WindowStyle Hidden -Verb RunAs -ArgumentList \"-Command {ps_cmd}\""
        try: subprocess.run(["powershell", "-Command", full_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception: pass

    def create_launcher_shortcut(self, target_dir):
        shortcut_path = os.path.join(target_dir, "Play Modernized WoW.lnk")
        vanilla_fixes_exe = os.path.join(target_dir, "VanillaFixes.exe")
        source_icon = os.path.join(get_base_path(), "PurpleWowLogo.ico")
        target_icon = os.path.join(target_dir, "PurpleWowLogo.ico")
        icon_vbs_line = ""
        
        if os.path.exists(source_icon):
            try:
                shutil.copy2(source_icon, target_icon)
                icon_vbs_line = f'oLink.IconLocation = "{target_icon}, 0"'
            except: pass

        vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{vanilla_fixes_exe}"
oLink.Arguments = "WoW_Tweaked.exe"
oLink.WorkingDirectory = "{target_dir}"
oLink.Description = "Launch Vanilla WoW with VanillaFixes and Tweaks"
{icon_vbs_line}
oLink.Save
"""
        vbs_path = os.path.join(target_dir, "create_shortcut.vbs")
        with open(vbs_path, "w") as f: f.write(vbs_script)
        try: subprocess.run(["cscript", "//nologo", vbs_path], creationflags=0x08000000)
        finally:
            if os.path.exists(vbs_path): os.remove(vbs_path)

    def run_installation(self, silent=False):
        self.save_all_state()
        target_dir = self.wow_dir.get().strip()
        if not self.validate_installation_dir(target_dir): return
        if not self.validate_limits(): return

        try:
            self.clean_unselected_files(target_dir)
            self.copy_base_files(target_dir)
            self.configure_dxvk(target_dir)
            self.configure_plugins(target_dir)
            self.run_vanilla_tweaks(target_dir)
            self.apply_corrupt_interface_bypass(target_dir)
            self.apply_process_mitigations()
            self.create_launcher_shortcut(target_dir)
            if not silent:
                messagebox.showinfo("Success", "Installation and patching complete!\n\nYou can launch the game using the PLAY GAME button.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Installation Error", str(e))

    def launch_game(self):
        target_dir = self.wow_dir.get().strip()
        if not target_dir or not os.path.exists(os.path.join(target_dir, "WoW.exe")):
            messagebox.showerror("Launch Error", "Valid WoW directory not found. Please set it in Game Settings.")
            return
            
        vf_path = os.path.join(target_dir, "VanillaFixes.exe")
        target_exe = vf_path if os.path.exists(vf_path) else os.path.join(target_dir, "WoW.exe")
        
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([target_exe, "WoW_Tweaked.exe"], cwd=target_dir, creationflags=flags)
        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to launch game: {e}")

    # --- MAIN QUEUE LOOP ---
    def process_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "render_addons":
                    self.is_scanning_addons = False
                    self.build_all_addon_cards(data)
                elif msg_type == "single_update_done":
                    folder, success = data
                    if not success: messagebox.showerror("Update Failed", f"Failed to update {folder}. Please check your internet connection or repository URL.")
                    self.rescan_single_addon(folder)
                elif msg_type == "sync_progress":
                    if hasattr(self, 'sync_lbl'): self.sync_lbl.configure(text=data)
                elif msg_type == "sync_complete":
                    self.trigger_addon_scan(show_loading=True)
                elif msg_type == "client_dl_progress":
                    pct, txt = data
                    if self.client_dl_window and self.client_dl_window.winfo_exists():
                        self.dl_prog.set(pct)
                        self.dl_status.configure(text=txt)
                    else:
                        self.progress_update.set(pct)
                        self.lbl_update_status.configure(text=txt)
                elif msg_type == "client_dl_file":
                    if self.client_dl_window and self.client_dl_window.winfo_exists():
                        self.dl_console.configure(state="normal")
                        self.dl_console.insert("end", data + "\n")
                        self.dl_console.see("end")
                        self.dl_console.configure(state="disabled")
                    else:
                        if hasattr(self, 'updater_console'):
                            self.updater_console.configure(state="normal")
                            self.updater_console.insert("end", data + "\n")
                            self.updater_console.see("end")
                            self.updater_console.configure(state="disabled")
                elif msg_type == "client_dl_done":
                    is_new_install = data
                    if self.client_dl_window and self.client_dl_window.winfo_exists():
                        self.client_dl_window.destroy()
                    
                    self.run_installation(silent=True)
                    
                    msg = "OctoWoW downloaded successfully!" if is_new_install else "OctoWoW client download and synchronization complete!\nYour mods and tweaks have been automatically re-applied."
                    messagebox.showinfo("Success", msg)
                    
                    if not is_new_install:
                        self.lbl_update_status.configure(text="Update complete.")
                        self.progress_update.set(1.0)
                        self.btn_check_update.configure(state="normal")
                    self.trigger_addon_scan(show_loading=False)
                elif msg_type == "client_dl_error":
                    if self.client_dl_window and self.client_dl_window.winfo_exists():
                        self.client_dl_window.destroy()
                    self.lbl_update_status.configure(text=data)
                    self.btn_check_update.configure(state="normal")
                    messagebox.showerror("Download Error", f"Failed to sync client: {data}")
                elif msg_type == "updater_status":
                    self.lbl_update_status.configure(text=data)
                elif msg_type == "updater_btn":
                    self.btn_check_update.configure(state=data)
                elif msg_type == "updater_prompt":
                    self.prompt_download_update(data)
        except queue.Empty: pass
        finally: self.after(100, self.process_queue)

if __name__ == "__main__":
    app = OctoWowApp()
    app.mainloop()