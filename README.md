# OctoWoW Install Manager

A modern, CustomTkinter-based configuration, modding, and addon management tool tailored specifically for the OctoWoW (Vanilla 1.12.1) client. 

This manager is built to function like a professional desktop gaming launcher. It provides a sleek graphical interface to manage client settings, wraps `vanilla-tweaks.exe` for deep-engine adjustments (like Widescreen FoV and memory limits), safely deploys core `.dll` engine hooks (like SuperWoW and DXVK), and features a fully threaded **Git Addon Manager** and **Client Downloader**.

---

## ✨ Key Features
* **Modern UI:** Built on `CustomTkinter` with hardware-accelerated smooth scrolling, dark mode styling, and dynamic card-based layouts.
* **Git Addon Manager:** Automatically scans your `Interface/AddOns` folder, parses `.toc` metadata, and uses Git to seamlessly track, clone, and "Update All" of your addons with a single click.
* **Client Downloader:** Download and extract the full OctoWoW client `.zip` directly to your PC without leaving the app.
* **App Auto-Updater:** Built-in self-updating mechanism that checks GitHub releases, downloads the newest version, and patches itself in place.
* **Engine Tweaks & Mods:** Effortlessly toggle complex 1.12 modifications like *VanillaFixes*, *UnitXP_SP3*, and the *WeirdUtils* suite.

---

## 🎮 For Players: How to Download
If you are just looking to install the game or update your addons, **you do not need to build this from source or download the files below.**

Go to the **[Releases](../../releases)** tab on the right side of this GitHub page and download the latest `.exe` file. The release executable comes with the entire payload of DLLs, Addon Dependencies, and executables **pre-installed and packed inside it.**

*(Note: To use the Addon Manager tab, you must have [Git for Windows](https://git-scm.com/download/win) installed on your PC.)*

---

## 🛠️ For Developers: Building from Source
This repository contains **only the UI source code (`OctoWow_Install_Manager.py`)**. It does not contain the third-party `.dll` payloads or executable patchers required to actually run the compiler. Keeping the payload out of the repository keeps it lightweight and respects the original creators' licenses.

### Prerequisites
1. Python 3.8+
2. Install the required UI library: `pip install customtkinter`
3. Install PyInstaller: `pip install pyinstaller`

### Dependency Sources
*Disclaimer: The links below point to the original repositories. Over time, these may become out-of-date, move, or be deleted. If a link is dead, you will need to source the binary from community archives.*

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
Before compiling, your workspace must look exactly like this:

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
This will generate the final, standalone executable inside the `dist` folder.