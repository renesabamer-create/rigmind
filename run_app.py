import uvicorn
import socket

def get_local_ip():
    """Gets the local network IP so the user can connect from their phone."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 8000
    print("=" * 70)
    print(" 🛢️  PETROREPORTS: WELL INTERVENTION & WORKOVER REPORTING APP")
    print("=" * 70)
    print(f" • Acceso desde tu computador: http://localhost:{port}")
    print(f" • Acceso desde tu celular (mismo Wi-Fi): http://{local_ip}:{port}")
    print("=" * 70)
    print(" Presiona Ctrl + C para detener el servidor.\n")
    
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=True)
