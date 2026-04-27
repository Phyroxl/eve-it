# WARNING: THIS IS A DEVELOPMENT TOOL ONLY.
# DO NOT RUN THIS SCRIPT IN A PRODUCTION ENVIRONMENT.
# It is intended only for generating mock data for UI testing.

import sys
import os

# Añadir el directorio actual al path para importar core
sys.path.append(os.getcwd())

from core.wallet_poller import WalletPoller

def main():
    poller = WalletPoller()
    print("Generando datos demo para el Piloto Principal (ID: 0)...")
    poller.ensure_demo_data(0)
    
    # También generamos para un ID ficticio que parezca real
    print("Generando datos demo para 'Azode' (ID: 12345)...")
    poller.ensure_demo_data(12345)
    
    print("Sincronización simulada completada.")

if __name__ == "__main__":
    main()
