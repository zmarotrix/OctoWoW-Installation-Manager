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
import tempfile
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# --- OPTIONAL DRAG AND DROP ---
HAS_DND = False
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    pass

# --- CONFIGURATION ---
CLIENT_ZIP_URL = "https://your-server.com/OctoWoW_Client.zip" # <-- CHANGE THIS TO YOUR ACTUAL CLIENT ZIP URL
CONFIG_FILE = "octowow_config.json"
VERSION = "2.5.3"

# Standard Vanilla 1.12 MPQ files that should be ignored by the Game Mods manager
BASE_MPQ_BLACKLIST = {
    "backup.mpq", "base.mpq", "dbc.mpq", "fonts.mpq", "interface.mpq", 
    "misc.mpq", "model.mpq", "patch.mpq", "patch-1.mpq", "patch-2.mpq", 
    "patch-3.mpq", "patch-4.mpq", "patch-5.mpq", "patch-6.mpq", "patch-7.mpq", 
    "patch-8.mpq", "patch-9.mpq", "patch-a.mpq", "sound.mpq", "speech.mpq", 
    "terrain.mpq", "texture.mpq", "wmo.mpq"
}

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

def bdecode(data):
    """Dependency-free recursive Bencode parser for torrent mapping."""
    def decode(index):
        if index >= len(data): raise ValueError("EOF")
        c = data[index:index+1]
        if c == b'i':
            end = data.find(b'e', index)
            return int(data[index+1:end]), end + 1
        elif c == b'l':
            lst = []
            index += 1
            while index < len(data) and data[index:index+1] != b'e':
                val, index = decode(index)
                lst.append(val)
            return lst, index + 1
        elif c == b'd':
            dct = {}
            index += 1
            while index < len(data) and data[index:index+1] != b'e':
                k, index = decode(index)
                v, index = decode(index)
                dct[k] = v
            return dct, index + 1
        elif c in b'0123456789':
            colon = data.find(b':', index)
            length = int(data[index:colon])
            start = colon + 1
            end = start + length
            return data[start:end], end
        raise ValueError(f"Invalid char at {index}")
    return decode(0)[0]

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
        if not self.winfo_ismapped(): return 
        
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

if HAS_DND:
    class BaseApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class BaseApp(ctk.CTk):
        pass

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
# 2. CONTROLLER: ADDON MANAGER
# ==========================================
class AddonManager:
    @staticmethod
    def get_github_api_info(url):
        """Resolves the default branch ZIP and SHA commit of a GitHub repo URL."""
        if "github.com" not in url: return None, url
        url = url.rstrip('/')
        if url.endswith(".git"): url = url[:-4]
        parts = url.split('/')
        user, repo = parts[-2], parts[-1]
        
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{user}/{repo}", headers={'User-Agent': 'OctoWow'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                branch = data.get("default_branch", "master")
                
            req_commit = urllib.request.Request(f"https://api.github.com/repos/{user}/{repo}/commits/{branch}", headers={'User-Agent': 'OctoWow'})
            with urllib.request.urlopen(req_commit, timeout=8) as resp:
                cdata = json.loads(resp.read().decode())
                sha = cdata.get("sha", "")
                
            zip_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
            return sha, zip_url
        except Exception:
            # Fallback if rate limited or failing
            return None, f"https://github.com/{user}/{repo}/archive/refs/heads/master.zip"

    @staticmethod
    def install_addon(url, addons_dir):
        """Downloads, extracts, locates .toc, and logically renames addon folders before moving."""
        sha, zip_url = AddonManager.get_github_api_info(url)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "addon.zip")
            req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp, open(zip_path, 'wb') as f:
                shutil.copyfileobj(resp, f)
                
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmpdir)
                
            extracted_items = [item for item in os.listdir(tmpdir) if item != "addon.zip"]
            if not extracted_items: raise Exception("ZIP file contained no contents")
            
            extracted_root = os.path.join(tmpdir, extracted_items[0])
            if not os.path.isdir(extracted_root):
                extracted_root = tmpdir
                
            addon_dirs = []
            
            # 1. Search for .toc files directly in the root of the extracted repo folder
            tocs_in_root = [f for f in os.listdir(extracted_root) if f.endswith('.toc')]
            if tocs_in_root:
                addon_dirs.append((extracted_root, tocs_in_root[0][:-4]))
            else:
                # 2. Search deeper in immediate subdirectories (typical for addon-packs like pfUI/DBM)
                for item in os.listdir(extracted_root):
                    subpath = os.path.join(extracted_root, item)
                    if os.path.isdir(subpath):
                        tocs = [f for f in os.listdir(subpath) if f.endswith('.toc')]
                        if tocs:
                            addon_dirs.append((subpath, tocs[0][:-4]))
                            
            if not addon_dirs:
                raise Exception("No .toc (addon configuration files) found in this repository.")
                
            # Move the correct folders out and rename them to match the TOC
            for src, name in addon_dirs:
                dest = os.path.join(addons_dir, name)
                if os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.move(src, dest)
                
                # Save metadata for update tracking
                meta_path = os.path.join(dest, ".octowow_meta")
                with open(meta_path, 'w') as f:
                    json.dump({"url": url, "sha": sha}, f)

    @staticmethod
    def install_local_addon(zip_path, addons_dir):
        """Extracts a local ZIP file, locates .toc, and logically renames addon folders before moving."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmpdir)
                
            extracted_items = [item for item in os.listdir(tmpdir)]
            if not extracted_items: raise Exception("ZIP file contained no contents")
            
            # Find the root containing the data
            extracted_root = os.path.join(tmpdir, extracted_items[0])
            if not os.path.isdir(extracted_root) or len(extracted_items) > 1:
                extracted_root = tmpdir
                
            addon_dirs = []
            
            # 1. Search for .toc files directly in the root
            tocs_in_root = [f for f in os.listdir(extracted_root) if f.endswith('.toc')]
            if tocs_in_root:
                addon_dirs.append((extracted_root, tocs_in_root[0][:-4]))
            else:
                # 2. Search deeper in immediate subdirectories (typical for addon-packs)
                for item in os.listdir(extracted_root):
                    subpath = os.path.join(extracted_root, item)
                    if os.path.isdir(subpath):
                        tocs = [f for f in os.listdir(subpath) if f.endswith('.toc')]
                        if tocs:
                            addon_dirs.append((subpath, tocs[0][:-4]))
                            
            if not addon_dirs:
                raise Exception("No .toc (addon configuration files) found in this ZIP.")
                
            # Move the correct folders out and rename them to match the TOC
            for src, name in addon_dirs:
                dest = os.path.join(addons_dir, name)
                if os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.move(src, dest)

# ==========================================
# 3. VIEW & CONTROLLER: UI AND INSTALL LOGIC
# ==========================================
class OctoWowApp(BaseApp):
    def __init__(self):
        super().__init__()
        
        ctk.set_appearance_mode("dark")
        self.title(f"OctoWoW Installation Manager v{VERSION}")
        self.geometry("1050x780")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)

        icon_path = os.path.join(get_base_path(), "PurpleWowLogo.ico")
        if os.path.exists(icon_path): self.iconbitmap(icon_path)

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.handle_file_drop)

        self.config = ConfigManager()
        self.msg_queue = queue.Queue()
        self.slider_widgets = []
        
        self.addon_cards = []
        self.is_scanning_addons = False
        
        self.pending_mpqs = []
        self.mpq_temp_dir = os.path.join(get_persist_path(), "temp_mpq_extraction")
        if os.path.exists(self.mpq_temp_dir): shutil.rmtree(self.mpq_temp_dir, ignore_errors=True)
        
        self.init_variables()
        self.build_ui()
        self.after(100, self.process_queue)
        self.trigger_addon_scan(show_loading=False)
        self.check_app_updates()

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
        
        self.game_mods_meta = self.config.get('game_mods_meta', {})

        self.core_plugins = {}
        for dll in ["ClassicAPI.dll", "nampower.dll", "no1600x1200.dll", "perf_boost.dll", "SuperWoWhook.dll", "transmogfix.dll", "UnitXP_SP3.dll", "VanillaHelpers.dll", "weirdperformance.dll"]:
            self.core_plugins[dll] = ctk.BooleanVar(value=self.config.get('core_plugins', {}).get(dll, True))

        self.optional_plugins = {}
        for dll in ["bigcursor.dll", "customassets.dll", "logsessions.dll", "minimapicons.dll", "pngscreenshots.dll", "worldmarkers.dll"]:
            self.optional_plugins[dll] = ctk.BooleanVar(value=self.config.get('optional_plugins', {}).get(dll, False))

        self.custom_plugins_config = self.config.get('custom_plugins', {})
        self.custom_plugins = {}
        for dll, state in self.custom_plugins_config.items():
            self.custom_plugins[dll] = ctk.BooleanVar(value=state)

        self.addon_dependencies = {"nampower.dll": "nampowersettings", "perf_boost.dll": "perfboostsettings", "UnitXP_SP3.dll": "UnitXP_SP3_Addon", "SuperWoWhook.dll": "SuperAPI"}

        self.GITHUB_MODS = {
            "ClassicAPI.dll": "brues-code/ClassicAPI",
            "SuperWoWhook.dll": "balakethelock/SuperWoW",
            "VanillaHelpers.dll": "isfir/VanillaHelpers"
        }
        self.plugin_sources = {}
        for dll in self.GITHUB_MODS.keys():
            self.plugin_sources[dll] = ctk.StringVar(value=self.config.get('plugin_sources', {}).get(dll, "Recommended"))

        t_conf = self.config.get('tweaks', {})
        self.vt_fov = ctk.DoubleVar(value=t_conf.get('vt_fov', 0))
        
        self.screen_w = self.winfo_screenwidth()
        self.screen_h = self.winfo_screenheight()
        
        try:
            import ctypes
            self.screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            self.screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            pass

        self.detected_ratio = self.screen_w / self.screen_h
        self.ratio_options = {
            f"Auto ({self.screen_w}x{self.screen_h})": self.detected_ratio,
            "4:3 (Standard)": 4.0/3.0, "16:9 (Widescreen)": 16.0/9.0, 
            "16:10 (Widescreen)": 16.0/10.0, "21:9 (Ultrawide)": 21.0/9.0, 
            "32:9 (Super Ultrawide)": 32.0/9.0
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

        # --- AUTO-SAVE BINDINGS ---
        all_vars = [
            self.wow_dir, self.gpu_type, self.install_autologin, self.ratio_var,
            self.vt_fov, self.vt_farclip, self.vt_frill, self.vt_nameplate,
            self.vt_soundchan, self.vt_maxcam, self.vt_quickloot, self.vt_bg_sound,
            self.vt_laa, self.vt_cam_fix, self.vt_dep_fix, self.vt_corrupt_bypass,
            self.safety_override
        ]
        
        for v in all_vars:
            v.trace_add("write", self.save_all_state)
            
        for d in (self.core_plugins, self.optional_plugins, self.custom_plugins, self.plugin_sources):
            for v in d.values():
                v.trace_add("write", self.save_all_state)

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
            slider.set(var.get())
            val_lbl.configure(text=str(int(var.get())))

    def save_all_state(self, *args):
        self.config.set('wow_dir', self.wow_dir.get())
        self.config.set('gpu_type', self.gpu_type.get())
        self.config.set('install_autologin', self.install_autologin.get())
        self.config.set('core_plugins', {k: v.get() for k, v in self.core_plugins.items()})
        self.config.set('optional_plugins', {k: v.get() for k, v in self.optional_plugins.items()})
        self.config.set('custom_plugins', {k: v.get() for k, v in self.custom_plugins.items()})
        self.config.set('plugin_sources', {k: v.get() for k, v in self.plugin_sources.items()})
        self.config.set('tracked_addons', self.tracked_addons)
        self.config.set('game_mods_meta', self.game_mods_meta)
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

        self.sidebar = ctk.CTkFrame(self, fg_color=SURFACE_COLOR, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(7, weight=1) 

        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=(30, 25), sticky="w")
        
        logo = ctk.CTkFrame(title_frame, fg_color="transparent")
        logo.pack(anchor="w")
        ctk.CTkLabel(logo, text="OCTO", font=("Segoe UI Black", 24), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkLabel(logo, text="WOW", font=("Segoe UI Black", 24), text_color=ACCENT_COLOR).pack(side="left")
        ctk.CTkLabel(title_frame, text=f"Installation Manager v{VERSION}", font=("Segoe UI", 12), text_color=TEXT_MUTED).pack(anchor="w")

        self.nav_btns = {}
        nav_items = [
            ("⚙️ Game Settings", "Settings"),
            ("🔌 Client Tweaks", "Tweaks"),
            ("🎨 Game Mods", "GameMods"),
            ("📦 Addon Manager", "Addons"),
            ("🚀 Game Updates", "Updater")
        ]
        
        for i, (label, name) in enumerate(nav_items):
            btn = ctk.CTkButton(self.sidebar, text=f"  {label}", font=("Segoe UI", 14, "bold"), fg_color="transparent", 
                                text_color=TEXT_MAIN, hover_color=CARD_COLOR, anchor="w", height=45, 
                                command=lambda n=name: self.show_tab(n))
            btn.grid(row=i+1, column=0, padx=10, pady=4, sticky="ew")
            self.nav_btns[name] = btn

        self.app_update_btn = ctk.CTkButton(self.sidebar, text="🔄 Checking for updates...", font=("Segoe UI", 11, "bold"), 
                                            fg_color="transparent", hover_color=CARD_COLOR, text_color=TEXT_MUTED, 
                                            height=30, state="disabled")
        self.app_update_btn.grid(row=8, column=0, padx=20, pady=(0, 10), sticky="ew")

        ctk.CTkButton(self.sidebar, text="💾 Apply Changes", font=("Segoe UI", 14, "bold"), fg_color=CARD_COLOR, hover_color="#2A2E3F",
                      text_color=TEXT_MAIN, height=45, command=self.run_installation).grid(row=9, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        ctk.CTkButton(self.sidebar, text="▶ PLAY GAME", font=("Segoe UI", 16, "bold"), fg_color=SUCCESS_COLOR, hover_color="#059669",
                      text_color="#ffffff", height=55, command=self.launch_game).grid(row=10, column=0, padx=20, pady=(0, 30), sticky="ew")

        self.main_container = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        self.frames = {}
        self.current_tab = None 
        
        self.build_settings_tab()
        self.build_tweaks_tab()
        self.build_game_mods_tab()
        self.build_addons_tab()
        self.build_updater_tab()
        
        self.show_tab("Settings")

    def show_tab(self, tab_name):
        if self.current_tab == tab_name: return

        for btn_name, btn in self.nav_btns.items():
            if btn_name == tab_name: 
                btn.configure(fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER)
            else: 
                btn.configure(fg_color="transparent", hover_color=CARD_COLOR)

        if self.current_tab and self.current_tab in self.frames:
            self.frames[self.current_tab].grid_remove()

        if tab_name in self.frames:
            self.frames[tab_name].grid(row=0, column=0, sticky="nsew")
            
        self.current_tab = tab_name
        
    def check_app_updates(self):
        def worker():
            try:
                url = "https://api.github.com/repos/zmarotrix/OctoWoW-Installation-Manager/releases/latest"
                req = urllib.request.Request(url, headers={'User-Agent': 'OctoWowApp'})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    latest_ver = data.get('tag_name', '').lstrip('v')
                    current_ver = VERSION.lstrip('v')
                    
                    if latest_ver and latest_ver != current_ver:
                        self.msg_queue.put(("app_update_available", data.get('html_url')))
                    else:
                        self.msg_queue.put(("app_update_none", None))
            except Exception as e:
                self.msg_queue.put(("app_update_error", str(e)))
                
        threading.Thread(target=worker, daemon=True).start()


    # --- SETTINGS TAB ---
    def build_settings_tab(self):
        tab_container = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR, corner_radius=0)
        self.frames["Settings"] = tab_container

        frame = SmoothScrollableFrame(tab_container, fg_color=BG_COLOR)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="Game Settings", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(10, 20), padx=10)

        card_dir = self.create_card(frame, "📁 Installation Directory")
        dir_row = ctk.CTkFrame(card_dir, fg_color="transparent")
        dir_row.pack(fill="x", pady=5)
        ctk.CTkEntry(dir_row, textvariable=self.wow_dir, width=420, fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left", padx=(0, 10))
        ctk.CTkButton(dir_row, text="Browse Folder", width=120, fg_color=CARD_COLOR, hover_color="#2A2E3F", command=self.browse_dir).pack(side="left", padx=(0, 10))
        
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
        d = filedialog.askdirectory(title="Select or Create WoW Folder")
        if d:
            self.wow_dir.set(os.path.normpath(d))
            self.save_all_state()
            self.trigger_addon_scan(show_loading=True)
            self.scan_game_mods()

    # --- CLIENT BITTORRENT DOWNLOADER / UPDATER ---
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
            temp_dir = os.path.join(get_persist_path(), "temp_download")
            os.makedirs(temp_dir, exist_ok=True)
            torrent_path = os.path.join(temp_dir, "client.torrent")
            input_file_path = os.path.join(temp_dir, "aria_input.txt")
            
            socket.setdefaulttimeout(10)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            self.msg_queue.put(("client_dl_progress", (0.0, "Fetching game metadata...")))
            req = urllib.request.Request("https://dl.octowow.st/download/client.torrent", headers={'User-Agent': 'OctoUpdater/1.3.1'})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                torrent_data = resp.read()
                if not new_hash:
                    new_hash = hashlib.sha1(torrent_data).hexdigest()
                    
            with open(torrent_path, "wb") as f:
                f.write(torrent_data)
                
            try:
                torrent_dict = bdecode(torrent_data)
                info = torrent_dict.get(b'info', {})
                
                # --- PRE-SCAN FOR IMMEDIATE FEEDBACK ---
                self.msg_queue.put(("client_dl_progress", (0.0, "Pre-scanning local files...")))
                missing_or_bad = 0
                total_files = 0
                
                if b'files' in info:
                    for i, file_info in enumerate(info[b'files']):
                        total_files += 1
                        path_parts = [p.decode('utf-8', 'ignore') for p in file_info[b'path']]
                        rel_path = "/".join(path_parts)
                        expected_length = file_info[b'length']
                        full_path = os.path.join(target_dir, rel_path)
                        
                        # Python instantly flags missing or tampered files before torrent engine starts
                        if not os.path.exists(full_path):
                            self.msg_queue.put(("client_dl_file", f"[🔍] Missing: {rel_path}"))
                            missing_or_bad += 1
                        elif os.path.getsize(full_path) != expected_length:
                            self.msg_queue.put(("client_dl_file", f"[🔍] Size mismatch: {rel_path}"))
                            missing_or_bad += 1
                else:
                    total_files = 1
                    name = info.get(b'name', b'').decode('utf-8', 'ignore')
                    expected_length = info.get(b'length', 0)
                    full_path = os.path.join(target_dir, name)
                    if not os.path.exists(full_path):
                        self.msg_queue.put(("client_dl_file", f"[🔍] Missing: {name}"))
                        missing_or_bad += 1
                    elif os.path.getsize(full_path) != expected_length:
                        self.msg_queue.put(("client_dl_file", f"[🔍] Size mismatch: {name}"))
                        missing_or_bad += 1

                if missing_or_bad == 0 and total_files > 0:
                    self.msg_queue.put(("client_dl_file", f"[✔️] Pre-scan complete. All {total_files} files present. Verifying integrity..."))
                elif total_files > 0:
                    self.msg_queue.put(("client_dl_file", f"[⚠️] Pre-scan found {missing_or_bad} missing/changed files out of {total_files}."))

                # --- GENERATE ARIA2C INPUT FILE ---
                with open(input_file_path, "w", encoding="utf-8") as f:
                    f.write(f"{os.path.abspath(torrent_path)}\n")
                    f.write(f"  dir={os.path.abspath(target_dir)}\n")
                    
                    if b'files' in info:
                        for i, file_info in enumerate(info[b'files']):
                            path_parts = [p.decode('utf-8', 'ignore') for p in file_info[b'path']]
                            rel_path = "/".join(path_parts)
                            f.write(f"  index-out={i+1}={rel_path}\n")
                    else:
                        name = info.get(b'name', b'').decode('utf-8', 'ignore')
                        f.write(f"  index-out=1={name}\n")
            except Exception as e:
                self.msg_queue.put(("client_dl_error", f"Failed to parse or map torrent structure: {e}"))
                return
                
            aria_path = self.ensure_aria2c()
            
            cmd = [
                aria_path,
                "--seed-time=0",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                "--summary-interval=1",
                "--truncate-console-readout=false",
                "--console-log-level=info",
                "--check-integrity=true",
                "--continue=true",
                f"--input-file={input_file_path}"
            ]
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
            
            buffer = ""
            while True:
                char = proc.stdout.read(1)
                if not char and proc.poll() is not None:
                    break
                    
                if char in ('\r', '\n'):
                    line_clean = buffer.strip()
                    if line_clean:
                        # 1. Parse Master Progress Bar Updates
                        frac_match = re.search(r'([0-9.]+[KMGTP]?i?B|0B)/([0-9.]+[KMGTP]?i?B|0B)\((\d+)%\)', line_clean, re.IGNORECASE)
                        if frac_match:
                            dl_amt, total_amt, pct = frac_match.groups()
                            
                            if "Verify:" in line_clean or "Checksum" in line_clean:
                                self.msg_queue.put(("client_dl_progress", (int(pct)/100.0, f"Verifying Hash Integrity... {pct}% | {dl_amt} / {total_amt}")))
                            else:
                                spd_match = re.search(r'DL:([^\s\]]+)', line_clean)
                                eta_match = re.search(r'ETA:([^\]\s]+)', line_clean)
                                speed = spd_match.group(1) if spd_match else "0B"
                                eta = eta_match.group(1) if eta_match else "Unknown"
                                txt = f"Downloading Game Data... {pct}%\nSpeed: {speed}/s | ETA: {eta} | {dl_amt} / {total_amt}"
                                self.msg_queue.put(("client_dl_progress", (int(pct)/100.0, txt)))
                        else:
                            # 2. Parse Detailed File-Level Activities
                            comp_match = re.search(r'Download complete:\s*(.+)', line_clean, re.IGNORECASE)
                            alloc_match = re.search(r'Allocating disk space.*\s(.+)', line_clean, re.IGNORECASE)
                            err_match = re.search(r'Checksum error detected in\s*(.+)', line_clean, re.IGNORECASE)
                            val_match = re.search(r'File\s+(.+?)\s+is complete', line_clean, re.IGNORECASE)

                            if comp_match:
                                fname = os.path.basename(comp_match.group(1).strip())
                                if fname and not fname.endswith('.torrent'):
                                    self.msg_queue.put(("client_dl_file", f"[✔️] Downloaded: {fname}"))
                            elif alloc_match:
                                fname = os.path.basename(alloc_match.group(1).strip())
                                if fname: 
                                    self.msg_queue.put(("client_dl_file", f"[⚙️] Allocating space for: {fname}"))
                            elif err_match:
                                fname = os.path.basename(err_match.group(1).strip())
                                self.msg_queue.put(("client_dl_file", f"[⚠️] Integrity check failed: {fname} (Queued for download)"))
                            elif val_match:
                                fname = os.path.basename(val_match.group(1).strip())
                                if fname and not fname.endswith('.torrent'):
                                    self.msg_queue.put(("client_dl_file", f"[✔️] Validated: {fname}"))

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

    # --- CLIENT TWEAKS TAB ---
    def build_tweaks_tab(self):
        tab_container = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR, corner_radius=0)
        self.frames["Tweaks"] = tab_container

        frame = SmoothScrollableFrame(tab_container, fg_color=BG_COLOR)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="Client Tweaks", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(10, 5), padx=10)
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
            row = ctk.CTkFrame(left, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=8)
            
            sw = ctk.CTkSwitch(row, text=dll, variable=var, text_color=TEXT_MAIN, progress_color=SUCCESS_COLOR)
            sw.pack(side="left")
            CTkToolTip(sw, self.descriptions.get(dll, ""))
            
            if dll in self.GITHUB_MODS:
                opt = ctk.CTkOptionMenu(row, values=["Recommended", "Latest (GitHub)"], variable=self.plugin_sources[dll], text_color=TEXT_MAIN, width=135, height=24, font=("Segoe UI", 11))
                opt.pack(side="right")

        right = ctk.CTkFrame(split, fg_color=SURFACE_COLOR, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(right, text="🛠️ Optional WeirdUtils", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(right, text="Additional quality-of-life plugins.", text_color=TEXT_MUTED, font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=(0, 10))
        
        for dll, var in self.optional_plugins.items():
            row = ctk.CTkFrame(right, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=8)
            
            sw = ctk.CTkSwitch(row, text=dll, variable=var, text_color=TEXT_MAIN, progress_color=ACCENT_COLOR)
            sw.pack(side="left")
            CTkToolTip(sw, self.descriptions.get(dll, ""))

        # --- CUSTOM USER PLUGINS SECTION ---
        custom_inner = self.create_card(frame, "🔧 Custom User Plugins")
        
        top_custom = ctk.CTkFrame(custom_inner, fg_color="transparent")
        top_custom.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(top_custom, text="Manage your own third-party DLLs. They will automatically be added/removed from your dlls.txt file.", text_color=TEXT_MUTED, font=("Segoe UI", 11)).pack(side="left")
        ctk.CTkButton(top_custom, text="➕ Add Custom DLL", height=24, font=("Segoe UI", 11, "bold"), fg_color=CARD_COLOR, hover_color="#2A2E3F", command=self.add_custom_dll).pack(side="right")
        
        self.custom_plugins_list_frame = ctk.CTkFrame(custom_inner, fg_color="transparent")
        self.custom_plugins_list_frame.pack(fill="both", expand=True)
        self.refresh_custom_dlls_ui()

        # --- CREDITS SECTION ---
        credits_card = self.create_card(frame, "📜 Open-Source Credits & Sources")
        ctk.CTkLabel(credits_card, text="This modernization tool packages the incredible work of several open-source developers.", text_color=TEXT_MUTED, font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=(0, 5))
        
        grid_frame = ctk.CTkFrame(credits_card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        
        credits = [
            ("VanillaFixes", "https://github.com/hannesmann/vanillafixes", None),
            ("VanillaHelpers", "https://github.com/isfir/VanillaHelpers", None),
            ("PerfBoost", "https://gitea.com/avitasia/perf_boost", "https://gitea.com/avitasia/PerfBoostSettings"),
            ("UnitXP_SP3", "https://codeberg.org/konaka/UnitXP_SP3", "https://codeberg.org/konaka/UnitXP_SP3_Addon"),
            ("Nampower", "https://gitea.com/avitasia/nampower", "https://gitea.com/avitasia/NampowerSettings"),
            ("SuperWoW", "https://github.com/balakethelock/SuperWoW", "https://github.com/balakethelock/SuperAPI"),
            ("ClassicAPI", "https://github.com/brues-code/ClassicAPI", None),
            ("Vanilla-Autologin", "https://github.com/MarcelineVQ/turtle-autologin", None),
            ("WeirdUtils Suite", "https://codeberg.org/MarcelineVQ/WeirdUtils", None),
            ("no1600x1200", None, None)
        ]
        
        for i, (name, mod_url, addon_url) in enumerate(credits):
            r, c = divmod(i, 3)
            grid_frame.grid_columnconfigure(c, weight=1)
            
            c_frame = ctk.CTkFrame(grid_frame, fg_color=BG_COLOR, corner_radius=6)
            c_frame.grid(row=r, column=c, sticky="nsew", padx=5, pady=5)
            
            ctk.CTkLabel(c_frame, text=name, font=("Segoe UI", 13, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=10, pady=(8, 2))
            
            btn_row = ctk.CTkFrame(c_frame, fg_color="transparent")
            btn_row.pack(anchor="w", fill="x", padx=10, pady=(0, 8))
            
            if mod_url:
                ctk.CTkButton(btn_row, text="Mod ↗", font=("Segoe UI", 10, "bold"), width=50, height=22, 
                              fg_color=CARD_COLOR, hover_color="#2A2E3F", text_color=ACCENT_COLOR,
                              command=lambda u=mod_url: webbrowser.open(u)).pack(side="left", padx=(0, 5))
            if addon_url:
                ctk.CTkButton(btn_row, text="Addon ↗", font=("Segoe UI", 10, "bold"), width=50, height=22, 
                              fg_color=CARD_COLOR, hover_color="#2A2E3F", text_color=SUCCESS_COLOR,
                              command=lambda u=addon_url: webbrowser.open(u)).pack(side="left")
            if not mod_url and not addon_url:
                ctk.CTkLabel(btn_row, text="Legacy Engine File", font=("Segoe UI", 10, "italic"), text_color=TEXT_MUTED).pack(side="left")


    def refresh_custom_dlls_ui(self):
        for w in self.custom_plugins_list_frame.winfo_children(): w.destroy()
        
        if not self.custom_plugins:
            lbl = ctk.CTkLabel(self.custom_plugins_list_frame, text="No custom DLLs managed. Click 'Add Custom DLL' to import one.", text_color=TEXT_MUTED, font=("Segoe UI", 11, "italic"))
            lbl.pack(pady=10)
            return
            
        for dll, var in self.custom_plugins.items():
            row = ctk.CTkFrame(self.custom_plugins_list_frame, fg_color=BG_COLOR, corner_radius=6)
            row.pack(fill="x", pady=4, padx=5)
            
            sw = ctk.CTkSwitch(row, text=dll, variable=var, text_color=TEXT_MAIN, progress_color=INFO_COLOR, font=("Segoe UI", 12, "bold"))
            sw.pack(side="left", padx=15, pady=10)
            
            btn_del = ctk.CTkButton(row, text="🗑", font=("Segoe UI Emoji", 14), width=32, height=32, corner_radius=16, fg_color=ERROR_COLOR, hover_color="#DC2626", command=lambda d=dll: self.remove_custom_dll(d))
            btn_del.pack(side="right", padx=10, pady=5)
            CTkToolTip(btn_del, "Permanently Remove DLL")

    def add_custom_dll(self):
        wow_dir = self.wow_dir.get().strip()
        if not wow_dir or not os.path.exists(os.path.join(wow_dir, "WoW.exe")):
            messagebox.showerror("Error", "Please set a valid WoW directory in Game Settings first.")
            return
        
        filepath = filedialog.askopenfilename(title="Select Custom DLL", filetypes=[("DLL Files", "*.dll")])
        if not filepath: return
        
        filename = os.path.basename(filepath)
        
        # Check if the DLL belongs to our standard core/optional plugins
        managed_defaults = list(self.core_plugins.keys()) + list(self.optional_plugins.keys())
        if filename.lower() in [m.lower() for m in managed_defaults]:
            messagebox.showerror("Error", "This DLL is already managed natively by the app.")
            return
            
        if filename in self.custom_plugins:
            messagebox.showinfo("Info", "This DLL is already in your custom plugins list.")
            return
            
        target_path = os.path.join(wow_dir, filename)
        
        # Only copy if they didn't just select the file that is ALREADY in the WoW directory
        if os.path.normpath(filepath).lower() != os.path.normpath(target_path).lower():
            try:
                shutil.copy2(filepath, target_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy DLL to WoW folder:\n{e}")
                return
                
        var = ctk.BooleanVar(value=True)
        var.trace_add("write", self.save_all_state)
        self.custom_plugins[filename] = var
        self.save_all_state()
        self.refresh_custom_dlls_ui()

    def remove_custom_dll(self, dll_name):
        if messagebox.askyesno("Remove Custom DLL", f"Are you sure you want to completely remove '{dll_name}'?\n\nThis will delete the file from your game folder and remove it from the manager."):
            del self.custom_plugins[dll_name]
            self.save_all_state()
            
            wow_dir = self.wow_dir.get().strip()
            if wow_dir:
                target_path = os.path.join(wow_dir, dll_name)
                if os.path.exists(target_path):
                    try: os.remove(target_path)
                    except: pass
            
            self.refresh_custom_dlls_ui()

    # --- GAME MODS TAB (MPQ MANAGER) ---
    def build_game_mods_tab(self):
        frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
        self.frames["GameMods"] = frame

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 15))
        
        ctk.CTkLabel(top, text="Game Mods", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkButton(top, text="➕ Add Mod (MPQ/ZIP)", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, font=("Segoe UI", 12, "bold"), command=self.add_game_mod).pack(side="right")
        
        sub_text = "Manage custom MPQ modifications. Drag and drop .mpq or .zip files anywhere to install." if HAS_DND else "Manage custom MPQ modifications. (Install tkinterdnd2 for Drag & Drop support)."
        ctk.CTkLabel(frame, text=sub_text, text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 15))

        self.game_mods_scroll = SmoothScrollableFrame(frame, fg_color="transparent")
        self.game_mods_scroll.pack(fill="both", expand=True, padx=5)
        
        self.scan_game_mods()

    def scan_game_mods(self):
        wow_dir = self.wow_dir.get().strip()
        data_dir = os.path.join(wow_dir, "Data")
        
        for widget in self.game_mods_scroll.winfo_children(): widget.destroy()
        
        if not wow_dir or not os.path.exists(data_dir):
            lbl = ctk.CTkLabel(self.game_mods_scroll, text="Please set a valid WoW directory in Game Settings to manage MPQs.", text_color=TEXT_MUTED)
            lbl.pack(pady=40)
            return
            
        custom_mpqs = []
        for f in os.listdir(data_dir):
            low = f.lower()
            if low in BASE_MPQ_BLACKLIST: continue
            
            if low.endswith('.mpq') or low.endswith('.mpq.disabled'):
                base_name = f if low.endswith('.mpq') else f[:-9] 
                is_enabled = low.endswith('.mpq')
                custom_mpqs.append((base_name, f, is_enabled))
                
        if not custom_mpqs:
            lbl = ctk.CTkLabel(self.game_mods_scroll, text="No custom Game Mods found in your Data folder.", text_color=TEXT_MUTED)
            lbl.pack(pady=40)
            return

        for base_name, actual_name, is_enabled in sorted(custom_mpqs, key=lambda x: x[0].lower()):
            self.create_game_mod_card(base_name, actual_name, is_enabled)

    def create_game_mod_card(self, base_name, actual_name, is_enabled):
        meta = self.game_mods_meta.get(base_name, {})
        title = meta.get("title", base_name)
        desc = meta.get("desc", "No description provided.")

        card = ctk.CTkFrame(self.game_mods_scroll, fg_color=SURFACE_COLOR, corner_radius=8)
        card.pack(fill="x", padx=5, pady=6)
        
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=12)
        
        title_lbl = ctk.CTkLabel(info_frame, text=title, font=("Segoe UI", 15, "bold"), text_color=TEXT_MAIN)
        title_lbl.pack(anchor="w")
        
        ctk.CTkLabel(info_frame, text=f"File: {base_name}", font=("Segoe UI", 11), text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(info_frame, text=desc, font=("Segoe UI", 12), text_color=TEXT_MAIN, wraplength=500, justify="left").pack(anchor="w")

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=15, pady=15)
        
        var = ctk.BooleanVar(value=is_enabled)
        
        def on_toggle(*args, bn=base_name, an=actual_name, v=var):
            target_name = bn if v.get() else bn + ".disabled"
            if an != target_name:
                wow_dir = self.wow_dir.get().strip()
                old_path = os.path.join(wow_dir, "Data", an)
                new_path = os.path.join(wow_dir, "Data", target_name)
                try:
                    os.rename(old_path, new_path)
                    self.scan_game_mods() 
                except Exception as e:
                    messagebox.showerror("Rename Error", f"Could not toggle {bn}.\n{e}")
                    v.set(not v.get())

        sw = ctk.CTkSwitch(btn_frame, text="Enabled", variable=var, command=on_toggle, text_color=TEXT_MAIN, progress_color=SUCCESS_COLOR)
        sw.pack(side="left", padx=(0, 15))
        
        btn_edit = ctk.CTkButton(btn_frame, text="✏️", font=("Segoe UI Emoji", 14), width=32, height=32, corner_radius=16, 
                                 fg_color=CARD_COLOR, hover_color="#2A2E3F", command=lambda: self.prompt_mpq_meta(base_name, os.path.join(self.wow_dir.get(), "Data", actual_name), True))
        btn_edit.pack(side="left", padx=(0, 10))
        CTkToolTip(btn_edit, "Edit Details")

        btn_del = ctk.CTkButton(btn_frame, text="🗑", font=("Segoe UI Emoji", 14), width=32, height=32, corner_radius=16, 
                                fg_color=ERROR_COLOR, hover_color="#DC2626", command=lambda: self.delete_game_mod(base_name, actual_name))
        btn_del.pack(side="left")
        CTkToolTip(btn_del, "Delete MPQ File")

    def delete_game_mod(self, base_name, actual_name):
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete {actual_name}?"):
            path = os.path.join(self.wow_dir.get().strip(), "Data", actual_name)
            try:
                if os.path.exists(path): os.remove(path)
                if base_name in self.game_mods_meta:
                    del self.game_mods_meta[base_name]
                    self.save_all_state()
                self.scan_game_mods()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete file:\n{e}")

    def add_game_mod(self):
        if not self.wow_dir.get().strip() or not os.path.exists(os.path.join(self.wow_dir.get(), "Data")):
            messagebox.showerror("Error", "Please set a valid WoW directory in Game Settings first.")
            return
            
        files = filedialog.askopenfilenames(title="Select Game Mod (MPQ or ZIP)", filetypes=[("Mod Files", "*.mpq *.zip"), ("All Files", "*.*")])
        if files: self.handle_file_drop_list(files)

    def handle_file_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            self.handle_file_drop_list(files)

    def handle_file_drop_list(self, files):
        wow_dir = self.wow_dir.get().strip()
        if not wow_dir or not os.path.exists(os.path.join(wow_dir, "WoW.exe")):
            messagebox.showerror("Error", "Please set a valid WoW directory in Game Settings first.")
            return

        mpqs, dlls, zips = [], [], []
        for f in files:
            low = f.lower()
            if low.endswith(".mpq"): mpqs.append(f)
            elif low.endswith(".dll"): dlls.append(f)
            elif low.endswith(".zip"): zips.append(f)

        if mpqs:
            self.show_tab("GameMods")
            self.handle_dropped_mpqs(mpqs)
        if dlls:
            self.show_tab("Tweaks")
            for dll in dlls:
                self.install_custom_dll(dll)
        if zips:
            self.show_tab("Addons")
            self.install_dropped_addons(zips)

    def handle_dropped_mpqs(self, files):
        def process_files():
            for f in files:
                if f.lower().endswith(".mpq"):
                    self.pending_mpqs.append((f, os.path.basename(f)))
            self.msg_queue.put(("mpq_process_next", None))
            
        threading.Thread(target=process_files, daemon=True).start()

    def install_dropped_addons(self, zips):
        wow_dir = self.wow_dir.get().strip()
        addons_dir = os.path.join(wow_dir, "Interface", "AddOns")
        
        def worker():
            for zip_path in zips:
                try:
                    AddonManager.install_local_addon(zip_path, addons_dir)
                except Exception as e:
                    self.msg_queue.put(("app_update_error", f"Failed to format and install addon from ZIP ({os.path.basename(zip_path)}):\n{e}"))
            
            self.msg_queue.put(("trigger_addon_scan", None))
            
        self.is_scanning_addons = True
        
        for widget in self.addon_scroll.winfo_children(): widget.destroy()
        load_frame = ctk.CTkFrame(self.addon_scroll, fg_color="transparent")
        load_frame.pack(expand=True, pady=40)
        ctk.CTkLabel(load_frame, text="⏳", font=("Segoe UI", 36)).pack(pady=(0,10))
        ctk.CTkLabel(load_frame, text="Extracting and Installing Addons...", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack()
        
        threading.Thread(target=worker, daemon=True).start()


    def prompt_mpq_meta(self, filename, filepath, is_editing=False):
        top = ctk.CTkToplevel(self)
        top.title("Edit Mod Details" if is_editing else "New Game Mod Detected")
        top.geometry("450x380")
        top.resizable(False, False)
        top.attributes("-topmost", True)
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 225
        y = self.winfo_y() + (self.winfo_height() // 2) - 190
        top.geometry(f"+{x}+{y}")
        top.grab_set()

        frame = ctk.CTkFrame(top, fg_color=BG_COLOR, corner_radius=0)
        frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(frame, text="🎨 Mod Details", font=("Segoe UI", 20, "bold"), text_color=ACCENT_COLOR).pack(pady=(20, 5))
        ctk.CTkLabel(frame, text=f"File: {filename}", font=("Segoe UI", 12), text_color=TEXT_MUTED).pack(pady=(0, 20))
        
        meta = self.game_mods_meta.get(filename, {})
        
        ctk.CTkLabel(frame, text="Title:", font=("Segoe UI", 12, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=30)
        title_var = ctk.StringVar(value=meta.get("title", filename.replace(".mpq", "").replace("-", " ").title()))
        ctk.CTkEntry(frame, textvariable=title_var, width=390, fg_color=SURFACE_COLOR, border_color=CARD_COLOR).pack(padx=30, pady=(5, 15))

        ctk.CTkLabel(frame, text="Description:", font=("Segoe UI", 12, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=30)
        desc_box = ctk.CTkTextbox(frame, width=390, height=80, fg_color=SURFACE_COLOR, border_color=CARD_COLOR, border_width=2)
        desc_box.pack(padx=30, pady=(5, 20))
        desc_box.insert("1.0", meta.get("desc", ""))
        
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, side="bottom", pady=20)
        
        def save():
            self.game_mods_meta[filename] = {"title": title_var.get().strip(), "desc": desc_box.get("1.0", "end").strip()}
            self.save_all_state()
            
            if not is_editing:
                target_path = os.path.join(self.wow_dir.get().strip(), "Data", filename)
                try:
                    shutil.copy2(filepath, target_path)
                    if self.mpq_temp_dir in filepath:
                        os.remove(filepath)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not copy {filename} to Data folder.\n{e}")
                    
            top.grab_release()
            top.destroy()
            self.scan_game_mods()
            if not is_editing: self.process_next_pending_mpq()

        def cancel():
            if not is_editing and self.mpq_temp_dir in filepath and os.path.exists(filepath):
                try: os.remove(filepath)
                except: pass
            top.grab_release()
            top.destroy()
            if not is_editing: self.process_next_pending_mpq()

        skip_text = "Cancel" if is_editing else "Skip / Cancel"
        ctk.CTkButton(btn_frame, text=skip_text, fg_color=CARD_COLOR, hover_color="#2A2E3F", command=cancel, width=100).pack(side="left")
        ctk.CTkButton(btn_frame, text="Save Mod", fg_color=SUCCESS_COLOR, hover_color="#059669", font=("Segoe UI", 12, "bold"), command=save).pack(side="right")

    def process_next_pending_mpq(self):
        if not self.pending_mpqs:
            if os.path.exists(self.mpq_temp_dir): shutil.rmtree(self.mpq_temp_dir, ignore_errors=True)
            return
            
        filepath, filename = self.pending_mpqs.pop(0)
        if filename.lower() in BASE_MPQ_BLACKLIST:
            self.process_next_pending_mpq()
            return
            
        self.prompt_mpq_meta(filename, filepath, is_editing=False)


    # --- ADDON MANAGER TAB ---
    def build_addons_tab(self):
        frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
        self.frames["Addons"] = frame

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(top, text="Addon Manager", font=("Segoe UI", 24, "bold"), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkButton(top, text="🔄 Refresh List", fg_color=CARD_COLOR, hover_color="#2A2E3F", font=("Segoe UI", 12, "bold"), command=lambda: self.trigger_addon_scan(show_loading=True)).pack(side="right")

        ctk.CTkLabel(frame, text="Automatically scans your WoW directory. Provide a GitHub URL to install standard addons directly.", text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 15))

        ctrl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=10, pady=(10, 15))

        add_frame = ctk.CTkFrame(ctrl_frame, fg_color=SURFACE_COLOR, corner_radius=8)
        add_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.addon_url_var = ctk.StringVar()
        ctk.CTkEntry(add_frame, textvariable=self.addon_url_var, placeholder_text="https://github.com/username/addon", fg_color=BG_COLOR, border_color=CARD_COLOR).pack(side="left", fill="x", expand=True, padx=(15, 10), pady=10)
        ctk.CTkButton(add_frame, text="➕ Install from GitHub", width=160, fg_color=CARD_COLOR, hover_color="#2A2E3F", font=("Segoe UI", 12, "bold"), command=self.add_addon).pack(side="left", padx=(0, 15), pady=10)

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
            ctk.CTkLabel(load_frame, text="Scanning Addons...", font=("Segoe UI", 16, "bold"), text_color=ACCENT_COLOR).pack()
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
        
        if os.path.exists(addons_dir):
            for folder in os.listdir(addons_dir):
                if folder.startswith(("Blizzard_", "Turtle_")): continue
                fpath = os.path.join(addons_dir, folder)
                if os.path.isdir(fpath):
                    
                    # Check for our tracker meta to know if we manage it
                    meta_path = os.path.join(fpath, ".octowow_meta")
                    meta_data_json = {}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r') as f: meta_data_json = json.load(f)
                        except: pass
                        
                    url = meta_data_json.get("url") or next((u for u in self.tracked_addons if u.rstrip('/').split('/')[-1].replace('.git','') == folder), None)

                    # Update logic: If it's a URL we manage, we fetch the latest SHA from github to flag it. 
                    # This gracefully handles rate-limiting without crashing.
                    needs_update = False
                    if url and "github.com" in url:
                        remote_sha, _ = AddonManager.get_github_api_info(url)
                        if remote_sha and meta_data_json.get("sha") and remote_sha != meta_data_json.get("sha"):
                            needs_update = True

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
                        "managed": bool(url)
                    })
        
        for url in self.tracked_addons:
            folder = url.rstrip('/').split('/')[-1].replace('.git','')
            if not any(a["folder"] == folder or (a.get("url") == url) for a in addon_data):
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
            self.no_results_lbl.configure(text="No addons found. Set your WoW directory or provide a GitHub URL.")
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
        upd_btn.pack_forget()
        pb.pack(fill="x", side="bottom")
        pb.start()
        
        wow_dir = self.wow_dir.get().strip()
        addons_dir = os.path.join(wow_dir, "Interface", "AddOns")
        
        def worker():
            folder = addon["folder"]
            try:
                url = addon["url"]
                if url:
                    AddonManager.install_addon(url, addons_dir)
                self.msg_queue.put(("single_update_done", (folder, True)))
            except Exception as e:
                print(f"Failed to fetch {folder}: {e}")
                self.msg_queue.put(("single_update_done", (folder, False)))
                
        threading.Thread(target=worker, daemon=True).start()

    def sync_all_available_updates(self):
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
    def build_updater_tab(self):
        frame = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
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
        if not wow_dir:
            messagebox.showerror("Error", "Please set an installation directory in the Game Settings tab first.")
            return
            
        if not os.path.exists(os.path.join(wow_dir, "WoW.exe")):
            if messagebox.askyesno("Game Not Found", "WoW.exe was not found in the selected directory.\n\nWould you like to download and install the OctoWoW client now?"):
                self.prompt_download_update(None, is_new_install=True)
            return

        self.btn_check_update.configure(state="disabled")
        self.lbl_update_status.configure(text="Checking OctoWoW servers...")
        threading.Thread(target=self._check_updates_thread, daemon=True).start()

    def _check_updates_thread(self):
        try:
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
                self.msg_queue.put(("updater_prompt", (latest_hash, False)))
            else:
                self.msg_queue.put(("updater_status", "Your OctoWoW client is completely up to date!"))
                self.msg_queue.put(("updater_btn", "normal"))
        except Exception as e:
            self.msg_queue.put(("updater_status", "Failed to reach servers. Please check connection."))
            self.msg_queue.put(("updater_btn", "normal"))

    def prompt_download_update(self, new_hash, is_new_install=False):
        msg = "An update to the base OctoWoW client is available!\n\nWould you like to synchronize and download it now?"
        if is_new_install:
            msg = "You are about to download the full OctoWoW client (~6GB).\nThis may take a while depending on your internet connection.\n\nContinue?"
            
        if messagebox.askyesno("Client Download", msg):
            self.show_tab("Updater")
            self.lbl_update_status.configure(text="Starting BitTorrent engine...")
            self.progress_update.set(0)
            
            self.updater_console.configure(state="normal")
            self.updater_console.delete("1.0", "end")
            self.updater_console.configure(state="disabled")
            
            target_dir = self.wow_dir.get().strip()
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                
            threading.Thread(target=self._sync_client_thread, args=(target_dir, new_hash, is_new_install), daemon=True).start()
        else:
            self.lbl_update_status.configure(text="Update cancelled.")
            self.btn_check_update.configure(state='normal')

    # --- INSTALLATION & DEPLOYMENT LOGIC ---
    def validate_installation_dir(self, target_dir):
        if not target_dir:
            messagebox.showerror("Directory Error", "Please select a Vanilla 1.12 installation directory.")
            return False
        if not os.path.exists(os.path.join(target_dir, "WoW.exe")):
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
        dlls_txt_path = os.path.join(target, "dlls.txt")
        
        # 1. Define all the DLLs that this app explicitly manages
        managed_dlls = {"dxvk"}
        managed_dlls.update(self.core_plugins.keys())
        managed_dlls.update(self.optional_plugins.keys())
        managed_dlls.update(self.custom_plugins.keys())
        managed_dlls_lower = {m.lower() for m in managed_dlls}
        
        # 2. Read the existing dlls.txt to find user-added custom DLLs
        custom_dlls = []
        if os.path.exists(dlls_txt_path):
            try:
                # Use utf-8-sig to automatically strip hidden Byte Order Marks (BOM)
                with open(dlls_txt_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    for line in f:
                        clean_line = line.strip()
                        # If it's not empty and not in our managed list, it's a completely unmanaged background DLL
                        if clean_line and clean_line.lower() not in managed_dlls_lower:
                            if clean_line not in custom_dlls:
                                custom_dlls.append(clean_line)
            except Exception as e:
                print(f"Error reading existing dlls.txt: {e}")

        # 3. Start building the new file content with our required base
        raw_lines_to_write = ["dxvk"]

        def download_github_dll(repo, dest):
            try:
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'OctoWowApp'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                
                dl_url = next((a['browser_download_url'] for a in data.get('assets', []) if a['name'].endswith('.dll')), None)
                if dl_url:
                    req = urllib.request.Request(dl_url, headers={'User-Agent': 'OctoWowApp'})
                    with urllib.request.urlopen(req, timeout=15) as resp, open(dest, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                    return True
            except Exception as e:
                print(f"Failed to download {repo} from GitHub: {e}")
            return False

        # Add enabled core plugins
        for dll_name, var in self.core_plugins.items():
            if var.get():
                source_dll = os.path.join(payload_base, dll_name)
                target_dll = os.path.join(target, dll_name)
                
                src_pref = self.plugin_sources.get(dll_name, ctk.StringVar(value="Recommended")).get()
                dl_success = False
                
                if src_pref == "Latest (GitHub)" and dll_name in self.GITHUB_MODS:
                    dl_success = download_github_dll(self.GITHUB_MODS[dll_name], target_dll)
                    
                if not dl_success and os.path.exists(source_dll): 
                    shutil.copy2(source_dll, target_dll)
                    
                raw_lines_to_write.append(dll_name) 

        # Add enabled optional plugins
        for dll_name, var in self.optional_plugins.items():
            if var.get():
                source_dll = os.path.join(payload_weirdu, dll_name)
                target_dll = os.path.join(target, dll_name)
                if os.path.exists(source_dll): shutil.copy2(source_dll, target_dll)
                raw_lines_to_write.append(dll_name)

        # Add enabled custom plugins (verifying they actually still exist on the drive)
        for dll_name, var in self.custom_plugins.items():
            if var.get():
                if os.path.exists(os.path.join(target, dll_name)):
                    raw_lines_to_write.append(dll_name)
                
        # 4. Append the completely unmanaged background DLLs back to the list
        raw_lines_to_write.extend(custom_dlls)

        # 5. STRICT DEDUPLICATION (Preserving Order)
        # This guarantees that a duplicate can NEVER be written to the file, 
        # even if the user manually messed with it or there was an encoding glitch.
        final_dlls_list = []
        seen = set()
        for dll in raw_lines_to_write:
            cleaned = dll.strip()
            if not cleaned: continue
            lowered = cleaned.lower()
            if lowered not in seen:
                seen.add(lowered)
                final_dlls_list.append(cleaned)

        # 6. Save the final deduplicated list
        try:
            with open(dlls_txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(final_dlls_list))
        except Exception as e:
            print(f"Failed to write to dlls.txt: {e}")

        

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
        if not self.validate_installation_dir(target_dir): return False
        if not self.validate_limits(): return False

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
            return True
        except Exception as e:
            messagebox.showerror("Installation Error", f"Failed to modify game files. Is the game currently running?\n\nDetails: {e}")
            return False

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
                    if not success: messagebox.showerror("Update Failed", f"Failed to download or parse {folder}. Please check the URL or GitHub API limits.")
                    self.rescan_single_addon(folder)
                elif msg_type == "mpq_process_next":
                    self.process_next_pending_mpq()
                elif msg_type == "client_dl_progress":
                    pct, txt = data
                    self.progress_update.set(pct)
                    self.lbl_update_status.configure(text=txt)
                elif msg_type == "client_dl_file":
                    if hasattr(self, 'updater_console'):
                        self.updater_console.configure(state="normal")
                        self.updater_console.insert("end", data + "\n")
                        self.updater_console.see("end")
                        self.updater_console.configure(state="disabled")
                elif msg_type == "client_dl_done":
                    is_new_install = data
                    
                    # Ensure patching actually worked before calling it a success
                    patch_success = self.run_installation(silent=True)
                    
                    if patch_success:
                        msg = "OctoWoW downloaded successfully!" if is_new_install else "OctoWoW client download and synchronization complete!\nYour mods and tweaks have been automatically re-applied."
                        messagebox.showinfo("Success", msg)
                        self.lbl_update_status.configure(text="Update complete.")
                    else:
                        self.lbl_update_status.configure(text="Update finished, but tweaks failed to apply.")
                        
                    self.progress_update.set(1.0)
                    self.btn_check_update.configure(state="normal")
                    self.trigger_addon_scan(show_loading=True)
                elif msg_type == "client_dl_error":
                    self.lbl_update_status.configure(text=data)
                    self.btn_check_update.configure(state="normal")
                    messagebox.showerror("Download Error", f"Failed to sync client: {data}")
                elif msg_type == "updater_status":
                    self.lbl_update_status.configure(text=data)
                elif msg_type == "updater_btn":
                    self.btn_check_update.configure(state=data)
                elif msg_type == "updater_prompt":
                    latest_hash, is_new_install = data
                    self.prompt_download_update(latest_hash, is_new_install)
                elif msg_type == "app_update_available":
                    self.app_update_url = data
                    self.app_update_btn.configure(
                        text="⚠️ App Update Available!", 
                        text_color="#ffffff",
                        fg_color=WARNING_COLOR,
                        hover_color="#D97706",
                        state="normal", 
                        command=lambda: webbrowser.open(self.app_update_url)
                    )
                elif msg_type == "app_update_none":
                    self.app_update_btn.grid_forget() 
                elif msg_type == "app_update_error":
                    self.app_update_btn.grid_forget()
                elif msg_type == "trigger_addon_scan":
                    self.trigger_addon_scan(show_loading=True)
        except queue.Empty: pass
        finally: self.after(100, self.process_queue)

if __name__ == "__main__":
    app = OctoWowApp()
    app.mainloop()