# EVE iT Suite - Development Intelligence Report (AI-to-AI Context)

## 1. Project Identity & Architecture
**Project Name:** EVE iT Suite
**Core Purpose:** An immersive "Command Bridge" dashboard for EVE Online multi-boxing management.
**Visual Language:** "Tactical Deep-Space" (Industrial, High-Contrast, Militarized Telemetry).
**Tech Stack:** 
- **Backend:** Python 3.11+
- **UI Framework:** PySide6 (Qt for Python)
- **Engine:** Low-level Win32 API (ctypes: user32.dll, gdi32.dll, dwmapi.dll)
- **Styling:** Custom Python-dictionary based Design System (`DesignConfig`) with high-transparency and glassmorphism.

## 2. Core Modules & Key Features

### A. Replicator Engine (The "Heart")
- **High-Speed Capture:** Dual-path engine (GDI BitBlt for speed, PrintWindow for obscured windows).
- **Precision ROI:** Uses relative coordinates (0.0 to 1.0) for resolution-independent capture.
- **Precision Clamping:** Mandatory pixel-level clipping to prevent Win32 out-of-bounds errors (Fixes "Phyrox Perez" freeze bug).
- **Stealth Mode:** Implements `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` to prevent the UI from leaking into game replicas.
- **Vitality Monitor:** Heartbeat system that detects stale frames (>2s) and triggers auto-recovery of window handles.

### B. Fleet Manager (The "Hub")
- **Tactical Reordering:** QListWidget with customized Drag & Drop and real-time cache synchronization.
- **Command Anchor V5:** Automatically promotes the #1 account to the foreground during region selection to ensure flagship-level calibration.
- **Persistence:** JSON-based config (`replicator.json`), with aggressive cleanup on corruption to prevent handle stale-mate.

### C. Interaction & Broadcast
- **Click Portal:** Mappings from overlay local space back to EVE window client space using `PostMessageW`.
- **Keyboard Shortcuts:** Precision movement (Arrows), Zoom (Wheel), and ROI Cropping (Alt+Wheel / Ctrl+Wheel).

## 3. Critical Fixes & "Lessons Learned" (Context for Future Edits)
- **Ghosting Resolution:** Always filter windows using `user32.IsHungAppWindow` and check for "Ghost" window classes to avoid hanging the capture thread on zombie processes.
- **Black-Frame Fallback:** Never accept a 100% black frame as valid unless verified by multi-point validation (5-point tactical grid). This ensures the `PrintWindow` fallback kicks in for hardware-accelerated windows.
- **GDI Resource Management:** Strict `try...finally` blocks for `ReleaseDC`, `DeleteDC`, and `DeleteObject` to prevent kernel-level memory exhaustion.

## 4. Coding Patterns & Best Practices
- **Win32 Interaction:** Prefer `PostMessageW` over `SendMessage` for non-blocking UI response.
- **Safety:** Always wrap external window interactions in `try/except` and verify `IsWindow(hwnd)` before calling GDI functions.
- **Design Philosophy:** No browser defaults. Use curated palettes (HSL), industrial typography (Consolas/Inter), and subtle micro-animations (Flash-on-click).

## 5. File Structure Reference
- `main.py`: Application entry, stealth mode initialization, and lifecycle management.
- `controller/replicator_wizard.py`: Fleet management and fleet reordering logic.
- `overlay/win32_capture.py`: Core Win32 capture engine and window discovery.
- `overlay/replication_overlay.py`: Individual replica UI and capture thread management.
- `styles/design_system.py`: Centralized design tokens and theme configuration.

---
**Current Status:** Optimized for high-performance multi-boxing. The "Phyrox Perez" region-freeze is resolved. Stealth mode is active.
