# EVE iT — Suite Roadmap

## Product direction

EVE iT is no longer treated as only an ISK tracker.
From now on, it is positioned as a **desktop utility suite for EVE multiboxing**.

Core modules:
- Tracker
- HUD
- Replicator
- Translator
- Control Center

Main priority:
- the application must feel as fluid as possible
- clarity and responsiveness come before adding more complexity

---

## Working method

We will build EVE iT with a fixed ecosystem:

- **ChatGPT** → product direction, roadmap, architecture, decisions, review
- **Antigravity** → UI and UX work, layouts, desktop flow, visual refinement
- **Codex** → real code implementation, refactors, file moves, technical cleanup
- **Claude** → second review, logic gaps, challenge decisions before major changes

Rule:
- one source of truth = GitHub repository
- one phase at a time
- no large rewrites unless absolutely necessary
- protect what already works

---

## Phase 0 — Reposition the product

### Goal
Make the repo and product direction match the real vision.

### Tasks
1. Update README.
2. Define EVE iT as a multiboxing suite.
3. List the official modules.
4. Make "fluid desktop experience" the main UX principle.

### Definition of done
- README no longer presents the project as only an ISK tracker
- product direction is clear before more development continues

---

## Phase 1 — Stabilize the current app

### Goal
Keep the current app working and make sure development continues on a stable base.

### Tasks
1. Confirm the app launches reliably.
2. Confirm tracker, dashboard, tray, overlay hooks, and major windows still work.
3. Fix only blocking errors.
4. Avoid feature expansion during stabilization.

### Definition of done
- current application starts cleanly
- no active blockers before structural cleanup starts

---

## Phase 2 — Reorganize the repository structure

### Goal
Prepare the codebase to grow as a suite instead of a single-purpose tool.

### Target structure

```text
main.py
requirements.txt
README.md

docs/
core/
modules/
ui/
services/
assets/
```

Suggested logical split:
- `core/` → tracking, parsing, watcher logic
- `modules/` → tracker, hud, replicator, translator
- `ui/desktop/` → tray, control windows, desktop shell
- `ui/dashboard/` → streamlit dashboard parts
- `services/` → shared utilities, APIs, formatting, i18n, overlay bridge

### Tasks
1. Define target folders.
2. Move files gradually, not all at once.
3. Keep imports working after each step.
4. Commit each structural move separately.

### Definition of done
- repository structure reflects the suite vision
- files are easier to find and reason about

---

## Phase 3 — Slim down `main.py`

### Goal
Turn `main.py` into a clean bootstrap file instead of a large control hub.

### Tasks
1. Keep only startup responsibilities in `main.py`.
2. Move helper logic out into dedicated modules.
3. Keep singleton, logging, and application startup clean and readable.
4. Preserve current behavior.

### Definition of done
- `main.py` is much easier to read
- boot flow is still stable

---

## Phase 4 — Split the dashboard

### Goal
Reduce the size and fragility of `app.py`.

### Suggested split
- `ui/dashboard/app.py`
- `ui/dashboard/state.py`
- `ui/dashboard/sidebar.py`
- `ui/dashboard/welcome.py`
- `ui/dashboard/dashboard_view.py`
- `ui/dashboard/charts.py`
- `ui/dashboard/character_cards.py`
- `ui/dashboard/language.py`
- `ui/dashboard/theme.py`
- `ui/dashboard/overlay_bridge.py`

### Tasks
1. Move one dashboard responsibility at a time.
2. Keep the visual behavior unchanged during the split.
3. Preserve the anti-flicker architecture.

### Definition of done
- dashboard is modular
- future changes are safer and faster

---

## Phase 5 — Build the Control Center

### Goal
Create the real desktop home of EVE iT.

### Purpose
The Control Center becomes the main user-facing shell of the suite.
It should feel fast, clean, and operational.

### It should show
- tracker status
- HUD status
- replicator status
- translator status
- dashboard status
- current session summary
- quick actions
- recent alerts or errors

### Tasks
1. Design the Control Center in Antigravity.
2. Implement it in Qt/PySide.
3. Connect it to the controller state.
4. Make it the main hub for launching and controlling modules.

### Definition of done
- EVE iT feels like one suite instead of separate tools

---

## Phase 6 — Formalize the modules

### Goal
Make each major feature behave like a proper product module.

### Modules
#### Tracker
- logs
- sessions
- rates
- ESS / income logic

#### HUD
- overlay
- quick status
- quick controls

#### Replicator
- wizard
- overlay duplication
- configuration

#### Translator
- configuration
- overlay
- translation pipeline

### Definition of done
- each module can be started, stopped, and reasoned about more independently

---

## Phase 7 — Performance and fluidity pass

### Goal
Make fluidity the defining product quality.

### Tasks
1. Remove UI flicker.
2. Reduce startup friction.
3. Reduce unnecessary rerenders.
4. Improve responsiveness of desktop windows.
5. Review update frequency and background loops.
6. Keep overlays lightweight.
7. Reduce visible lag when opening modules.

### Definition of done
- application feels smooth in normal daily usage

---

## Phase 8 — Product polish

### Goal
Make the suite feel complete and intentional.

### Tasks
1. Unify naming across the app.
2. Improve settings and configuration flow.
3. Improve visual consistency.
4. Improve onboarding.
5. Improve error messages.
6. Improve module discoverability.

### Definition of done
- EVE iT feels like a coherent desktop suite

---

## Immediate next step

Start with:

### Step 1
Update the README so the repository clearly presents EVE iT as a multiboxing suite.

### Step 2
Then create the target folder structure for the future refactor.

We do not migrate to Tauri now.
We continue with Python as the core, PySide6 for the desktop shell, and Streamlit as the analytics surface until a later decision is needed.
