# OctoWoW Installation Manager

A configuration, modding, and addon management tool for the OctoWoW (Vanilla 1.12.1) client. 

This tool provides a graphical interface to manage client settings, wraps `vanilla-tweaks.exe` for engine adjustments, deploys core `.dll` engine hooks, manages custom `.mpq` patches, and handles addon synchronization from GitHub or local archives.

---

> **⚠️ Windows Defender / Antivirus Warning**  
> You may receive a warning from Windows Defender or other antivirus software when downloading or running this application. This is a standard **false positive** caused by two things:
> 1. **Executable Patching:** The app uses `vanilla-tweaks.exe` to modify the engine limits of your `WoW.exe` file (creating `WoW_Tweaked.exe`). Antivirus software heavily scrutinizes any program that patches other executables.
> 2. **App Compilation:** This application is bundled into a single `.exe` using PyInstaller, which is frequently flagged by heuristic scanners.  
> 
> *If the application is blocked or deleted, you may need to add it or your WoW folder to your antivirus exclusions. All source code is publicly available in this repository for full transparency.*

---

## Features
* **Game Settings & Engine Adjustments:** Integrates `vanilla-tweaks.exe` to calculate aspect ratios and expand engine limits (FoV, render distance, ground clutter, and camera zoom). Automatically applies memory limit expansions (Large Address Aware), DEP mitigations, and interface corruption bypasses.
* **Game Mods (MPQ Manager):** Automatically detects custom `.mpq` patches in the `Data` folder. Allows users to toggle mods on and off without deleting them, and edit custom titles/descriptions that save to the app's configuration.
* **Smart Addon Manager:** Scans the `Interface/AddOns` folder and uses the GitHub API to track and download the latest source code. It automatically locates `.toc` metadata and formats the folder names correctly so they load in-game. Supports batch updating and installing from local `.zip` files.
* **Client Tweaks & Custom DLLs:** Provides toggles for 1.12 modifications including *VanillaFixes*, *UnitXP_SP3*, and the *WeirdUtils* suite, with options to pull the latest versions directly from GitHub. Users can also import and toggle their own custom `.dll` hooks. The app safely manages `dlls.txt` to preserve all custom and unmanaged background DLLs.
* **BitTorrent Game Updater:** Integrates an `aria2c` engine to hash-check existing files and download missing or updated data directly into the game folder. Includes a pre-scan step for clear console feedback on file integrity before downloading begins.
* **Smart Drag & Drop:** Drop `.mpq`, `.dll`, or `.zip` files anywhere onto the application to instantly detect the file type, route it to the correct tab, and install it.

---
<img width="1044" height="808" alt="image" src="https://github.com/user-attachments/assets/b9d74f18-e25a-483c-b25a-b5d3f7b2fed0" />
<img width="1041" height="803" alt="image" src="https://github.com/user-attachments/assets/acc6686c-c4c9-4c99-9e06-905767673239" />
<img width="1044" height="811" alt="image" src="https://github.com/user-attachments/assets/8c5978e2-2b69-45fd-bf7f-4e345e4bf2e1" />


## For Players: How to Download
If you are looking to install the game, manage mods, or update your addons, **you do not need to build this from source.**

Go to the **[Releases](../../releases)** tab on the right side of this GitHub page and download the latest `.exe` file. The release executable comes with the necessary DLLs, Addon Dependencies, and patchers pre-packaged inside it.

---

## For Developers: Building from Source
This repository contains **only the UI source code (`OctoWow_Install_Manager.py`)**. It does not contain the third-party `.dll` payloads or executable patchers required to run the compiler. 

### Prerequisites
1. Python 3.8+
2. Install the required UI library: `pip install customtkinter`
3. Install PyInstaller: `pip install pyinstaller`
*(Note: standard library modules like `tkinter`, `urllib`, and `zipfile` are used for the rest of the application).*

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
