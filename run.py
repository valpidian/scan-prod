import socket
import sys

from app import create_app
from config import Config


def _port_is_free(host, port):
    """Returneaza True daca portul nu e ocupat."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


app = create_app()


if __name__ == "__main__":
    host = Config.HOST
    port = Config.PORT

    if not _port_is_free(host, port):
        print(f"[EROARE] Serverul ruleaza deja pe {host}:{port}. Opreste instanta existenta inainte.", flush=True)
        sys.exit(1)

    print(f"[OK] Pornire server pe http://{host}:{port}", flush=True)
    app.run(
        host=host,
        port=port,
        debug=Config.DEBUG,
        use_reloader=False,
        threaded=True,
    )
