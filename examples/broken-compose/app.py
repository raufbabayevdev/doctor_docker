import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler


SECRET_KEY = os.environ.get("SECRET_KEY")
APP_MODE = os.environ.get("APP_MODE", "production")


if not SECRET_KEY:
    print("ERROR: SECRET_KEY environment variable is missing.")
    print("Fix: copy .env.example to .env and set SECRET_KEY.")
    sys.exit(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        message = f"doctor-docker broken example is running in {APP_MODE} mode.\n"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))

    print(f"Starting server on port {port}...")
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
