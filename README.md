# OctoWoW Install Manager

A configuration, modding, and addon management tool for the OctoWoW (Vanilla 1.12.1) client. 

This tool provides a graphical interface to manage client settings, wraps `vanilla-tweaks.exe` for engine adjustments (such as Widescreen FoV and memory limits), deploys core `.dll` engine hooks (like SuperWoW and DXVK), and handles addon synchronization via Git.

---

## Features
* **Git Addon Manager:** Scans the `Interface/AddOns` folder, parses `.toc` metadata, and uses Git to track, clone, and update addons in place.
* **Client Downloader:** Downloads and extracts the OctoWoW client `.zip` directly to the user's local disk.
* **App Auto-Updater:** Checks GitHub releases to download and apply updates to the manager itself.
* **Engine Tweaks & Mods:** Provides toggles for 1.12 modifications including *VanillaFixes*, *UnitXP_SP3*, and the *WeirdUtils* suite.

---
<img width="1052" height="782" alt="image" src="https://github.com/user-attachments/assets/aa3bb253-94af-4463-85c0-dc2f981daf70" />
<img width="1052" height="782" alt="image" src="https://github.com/user-attachments/assets/d76da00e-579e-4207-9057-70fe89210905" />


## For Players: How to Download
If you are looking to install the game, manage mods, or update your addons, **you do not need to build this from source.**

Go to the **[Releases](../../releases)** tab on the right side of this GitHub page and download the latest `.exe` file. The release executable comes with the necessary DLLs, Addon Dependencies, and patchers pre-packaged inside it.

*(Note: To use the Addon Manager functionality, you must have [Git for Windows](https://git-scm.com/download/win) installed on your system.)*

---

## For Developers: Building from Source
This repository contains **only the UI source code (`OctoWow_Install_Manager.py`)**. It does not contain the third-party `.dll` payloads or executable patchers required to run the compiler. 

### Prerequisites
1. Python 3.8+
2. Install the required UI library: `pip install customtkinter`
3. Install PyInstaller: `pip install pyinstaller`

### Dependency Sources
*Disclaimer: The links below point to the original repositories. If a link becomes inactive, you will need to source the binary from community archives.*

**Core Engine & Loaders:**
*   **VanillaFixes (Launcher & DXVK):** [hannesmann/vanillafixes](https://github.com/hannesmann/vanillafixes)
*   **Vanilla Tweaks:** CLI Executable [brndd/vanilla-tweaks](https://github.com/brndd/vanilla-tweaks)
*   **no1600x1200:** Legacy DLL (Community Archived)

**API Expansions & Overhauls:**
*   **SuperWoW & SuperAPI:** [balakethelock/SuperWoW](https://github.com/balakethelock/SuperWoW)
*   **ClassicAPI:** [brues-code/ClassicAPI](https://github.com/brues-code/ClassicAPI)
*   **VanillaHelpers:** [isfir/VanillaHelpers](https://github.com/isfir/VanillaHelpers)

**Performance & Networking:**
*   **PerfBoost:** [Mod Source](https://gitea.com/avitasia/perf_boost) | [Addon Source](https://gitea.com/avitasia/PerfBoostSettings)
*   **UnitXP_SP3:** [Mod Source](https://codeberg.org/konaka/UnitXP_SP3) | [Addon Source](https://codeberg.org/konaka/UnitXP_SP3_Addon)
*   **Nampower v4.2.0:** [Mod Source](https://gitea.com/avitasia/nampower) | [Addon Source](https://gitea.com/avitasia/NampowerSettings)

**Quality of Life (WeirdUtils Suite):**
*   **WeirdUtils:** [MarcelineVQ/WeirdUtils](https://codeberg.org/MarcelineVQ/WeirdUtils) 
    *(Includes: `worldmarkers.dll`, `minimapicons.dll`, `pngscreenshots.dll`, `logsessions.dll`, `customassets.dll`, `bigcursor.dll`, `weirdperformance.dll`, and `transmogfix.dll`)*
*   **Vanilla-Autologin:** [MarcelineVQ/turtle-autologin](https://github.com/MarcelineVQ/turtle-autologin)

### Required Folder Structure
Before compiling, your workspace must be organized exactly as follows:

```text
📁 Project_Root
 ├── 📄 OctoWow_Install_Manager.py
 ├── 📄 vanilla-tweaks.exe
 ├── 📄 PurpleWowLogo.ico
 └── 📁 Payload
      ├── 📄 dxvk.conf
      ├── 📄 VanillaFixes.exe
      ├── 📄 VfPatcher.dll
      ├── 📄 SuperWoWhook.dll
      ├── 📄 ClassicAPI.dll
      ├── ... (and all other core/optional DLLs listed above)
      ├── 📁 WeirdUtils
      │    └── ... (Optional DLLs)
      ├── 📁 DXVK_AMD
      │    └── 📄 d3d9.dll
      ├── 📁 DXVK_Standard
      │    └── 📄 d3d9.dll
      ├── 📁 Data
      │    └── 📁 Interface
      │         └── 📁 GlueXML
      │              └── ... (AutoLogin files)
      └── 📁 Interface
           └── 📁 AddOns
                ├── 📁 nampowersettings
                ├── 📁 perfboostsettings
                ├── 📁 SuperAPI
                └── 📁 UnitXP_SP3_Addon
```

### Compiling
Once your payload folder is populated, open your terminal in the root directory and compile using PyInstaller:

```cmd
pyinstaller --noconsole --onefile --icon="PurpleWowLogo.ico" --hidden-import customtkinter --add-data "Payload;Payload" --add-data "vanilla-tweaks.exe;." --add-data "PurpleWowLogo.ico;." OctoWow_Install_Manager.py
```
This will generate the standalone executable inside the `dist` folder.
```
