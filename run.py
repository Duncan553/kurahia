"""
run.py — Production entry point using Waitress (no dev server in prod).
For development, use `flask run` instead (auto-reload, debugger).
"""
from waitress import serve
from app import create_app

app = create_app("production")

if __name__ == "__main__":
    # Waitress is a pure-Python WSGI server — safe for production
    # Bind to localhost; put Nginx or Caddy in front for TLS termination
    serve(app, host="127.0.0.1", port=5000, threads=4)
