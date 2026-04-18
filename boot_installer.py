import sys
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox

# Colores Estilo EVE iT
COLOR_BG = "#0d1117"
COLOR_CYAN = "#00c8ff"
COLOR_TEXT = "#c8e6ff"
COLOR_BAR_BG = "#16212e"

class SplashInstaller:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EVE iT Installer")
        self.root.overrideredirect(True) # Sin bordes
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLOR_BG)
        
        # Tamaño y Posición
        self.width, self.height = 450, 220
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - self.width) // 2
        y = (screen_h - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Lógica de Arrastre
        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._do_drag)

        self._init_ui()
        
        # Iniciar instalación en hilo separado
        self.install_thread = threading.Thread(target=self._run_installation, daemon=True)
        self.install_thread.start()
        
        self.root.mainloop()

    def _init_ui(self):
        # Marco Principal con "Glow" simulado por borde
        self.main_frame = tk.Frame(self.root, bg=COLOR_BG, highlightbackground=COLOR_CYAN, highlightthickness=1)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Gear Icon (Simulado con texto/simbolo)
        tk.Label(self.main_frame, text="\u2699", font=("Segoe UI Symbol", 28), fg=COLOR_CYAN, bg=COLOR_BG).pack(pady=(20, 0))
        
        tk.Label(self.main_frame, text="EVE iT — SISTEMA DE INICIO", font=("Arial Black", 14), fg=COLOR_CYAN, bg=COLOR_BG).pack()
        
        self.status_var = tk.StringVar(value="Inicializando protocolos...")
        self.status_label = tk.Label(self.main_frame, textvariable=self.status_var, font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_BG)
        self.status_label.pack(pady=(20, 5))

        # Barra de Progreso Customizada (Canvas)
        self.canvas = tk.Canvas(self.main_frame, width=350, height=8, bg=COLOR_BAR_BG, highlightthickness=0)
        self.canvas.pack(pady=5)
        self.progress_bar = self.canvas.create_rectangle(0, 0, 0, 8, fill=COLOR_CYAN, outline="")

    def _update_progress(self, percent, status_text):
        self.status_var.set(status_text)
        width = int((percent / 100) * 350)
        self.canvas.coords(self.progress_bar, 0, 0, width, 8)
        self.root.update_idletasks()

    def _start_drag(self, event):
        self.x = event.x
        self.y = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + event.x - self.x
        y = self.root.winfo_y() + event.y - self.y
        self.root.geometry(f"+{x}+{y}")

    def _run_installation(self):
        try:
            # 1. Crear venv
            self.root.after(0, self._update_progress, 15, "Creando entorno virtual neural...")
            if not os.path.exists("venv"):
                subprocess.run([sys.executable, "-m", "venv", "venv"], check=True, capture_output=True)
            
            # 2. Pip install
            self.root.after(0, self._update_progress, 35, "Descargando módulos de traducción...")
            pip_exe = os.path.join("venv", "Scripts", "pip.exe") if os.name == 'nt' else os.path.join("venv", "bin", "pip")
            
            process = subprocess.Popen(
                [pip_exe, "install", "-r", "requirements.txt", "--progress-bar", "off"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # Leer salida para feedback visual
            pkg_count = 0
            for line in process.stdout:
                if "Successfully installed" in line:
                    pkg_count += 1
                progress = min(95, 35 + (pkg_count * 8))
                msg = f"Instalando: {line.strip()[:35]}..."
                self.root.after(0, self._update_progress, progress, msg)

            process.wait()
            
            if process.returncode == 0:
                self.root.after(0, self._update_progress, 100, "¡Sistema calibrado! Iniciando...")
                time.sleep(1.5)
                self.root.after(0, self.root.destroy)
            else:
                self.root.after(0, lambda: messagebox.showerror("Error", "Fallo en la descarga de paquetes. Revisa tu conexión."))
                self.root.after(0, self.root.destroy)
                sys.exit(1)

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Crash", f"Error crítico: {str(e)}"))
            self.root.after(0, self.root.destroy)
            sys.exit(1)

if __name__ == "__main__":
    SplashInstaller()
