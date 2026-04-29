import unittest
from pathlib import Path
import subprocess
import os

class TestSensitiveFilesIgnored(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.gitignore_path = self.root / ".gitignore"

    def test_gitignore_contains_sensitive_rules(self):
        """Verifica que .gitignore contenga las reglas para proteger la sesión ESI."""
        if not self.gitignore_path.exists():
            self.fail(".gitignore no encontrado en el root del proyecto.")
            
        content = self.gitignore_path.read_text(encoding="utf-8")
        
        required_rules = [
            "config/esi_session.json",
            "config/esi_session.json.corrupt.*",
            "config/*.session.json",
            "data/esi_session.json",
            "data/esi_session.json.corrupt.*"
        ]
        
        for rule in required_rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, content, f"La regla '{rule}' falta en .gitignore")

    def test_esi_session_not_tracked(self):
        """
        Verifica que config/esi_session.json no esté trackeado por Git.
        Nota: Este test requiere que git esté disponible en el PATH.
        """
        try:
            # git ls-files devuelve el archivo si está trackeado
            result = subprocess.run(
                ["git", "ls-files", "config/esi_session.json"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                check=True
            )
            self.assertEqual(result.stdout.strip(), "", "¡ERROR! config/esi_session.json está siendo trackeado por Git.")
        except subprocess.CalledProcessError:
            # Si git falla (ej. no es un repo git en este entorno de test), saltamos
            self.skipTest("Git no disponible o no es un repositorio git.")
        except FileNotFoundError:
            self.skipTest("Comando 'git' no encontrado.")

    def test_no_sensitive_tokens_in_tracked_files(self):
        """
        Escaneo básico para asegurar que no se hayan colado tokens reales 
        (ej. Authorization: Bearer <token_real>).
        """
        # Solo escaneamos una muestra de archivos core/config
        core_files = list((self.root / "core").glob("*.py"))
        
        for p in core_files:
            content = p.read_text(encoding="utf-8")
            # Un token real suele ser largo y base64-ish.
            # Aquí buscamos patrones de tokens harcodeados sospechosos.
            if 'Authorization": "Bearer ' in content and "Bearer {" not in content:
                # Si hay un Bearer seguido de algo que no parece una variable {token}
                self.fail(f"Posible token hardcodeado detectado en {p.name}")

if __name__ == "__main__":
    unittest.main()
