"""Arranque local del asistente.

Por defecto escucha solo en 127.0.0.1 (uso personal en el mismo computador).
Para abrirlo desde el celular en la misma red:  python run_app.py --lan
"""

import argparse
import socket
import sys

import uvicorn


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> int:
    parser = argparse.ArgumentParser(description="RigMind — asistente de reportes de pozo")
    parser.add_argument("--lan", action="store_true", help="exponer en la red local (celular/tablet)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    ip = get_local_ip() if args.lan else "127.0.0.1"

    print("=" * 70)
    print(" RIGMIND — ASISTENTE DE REPORTES DE POZO")
    print("=" * 70)
    print(f" • En este computador: http://localhost:{args.port}")
    if args.lan:
        print(f" • En el celular (misma red): http://{ip}:{args.port}")
        print("   ⚠️  Modo LAN: sin autenticación. Úselo solo en una red de confianza.")
    else:
        print(" • Modo local. Para abrirlo desde el celular: python run_app.py --lan")
    print(" • Ctrl + C para detener.\n")

    uvicorn.run("src.app:app", host=host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
