"""
Anas-24 Birthday Game — Backend Server
Serves static files + REST API for game state persistence (Neon Postgres).
"""

import http.server
import json
import os
import urllib.parse
import psycopg2
import psycopg2.extras

# ── Config ────────────────────────────────────────────────────────
PORT = int(os.environ.get('PORT', 8765))

# Load .env manually (no dotenv dependency)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

DB_STRING = os.environ.get('DB_STRING', '')

# ── Database Setup ────────────────────────────────────────────────

def get_db():
    """Get a new database connection."""
    conn = psycopg2.connect(DB_STRING)
    conn.autocommit = True
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            player_id TEXT PRIMARY KEY,
            state JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.close()
    conn.close()
    print("[DB] Tables ready.")


# ── Request Handler ───────────────────────────────────────────────

class GameHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files from CWD and handles /api/* routes."""

    def __init__(self, *args, **kwargs):
        # Serve from the project directory
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # GET /api/state?player=anas|pra
        if parsed.path == '/api/state':
            qs = urllib.parse.parse_qs(parsed.query)
            player = qs.get('player', [''])[0].lower()
            if player not in ('anas', 'pra'):
                self._json_response(400, {'error': 'Invalid player. Use anas or pra.'})
                return
            try:
                conn = get_db()
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT state FROM game_state WHERE player_id = %s", (player,))
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row:
                    self._json_response(200, row['state'])
                else:
                    # Return empty default state
                    self._json_response(200, self._default_state())
            except Exception as e:
                print(f"[DB ERROR] GET /api/state: {e}")
                self._json_response(500, {'error': str(e)})
            return

        # GET /api/auth?player=pra&password=xxx
        if parsed.path == '/api/auth':
            qs = urllib.parse.parse_qs(parsed.query)
            player = qs.get('player', [''])[0].lower()
            password = qs.get('password', [''])[0]
            if player == 'pra' and password == 'pranaylive':
                self._json_response(200, {'ok': True})
            elif player == 'anas':
                self._json_response(200, {'ok': True})
            else:
                self._json_response(403, {'ok': False, 'error': 'Wrong password'})
            return

        # Everything else: serve static files
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        # POST /api/state  body: {player, state}
        if parsed.path == '/api/state':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length))
                player = body.get('player', '').lower()
                state = body.get('state', {})
                if player not in ('anas', 'pra'):
                    self._json_response(400, {'error': 'Invalid player'})
                    return
                conn = get_db()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO game_state (player_id, state, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (player_id)
                    DO UPDATE SET state = %s, updated_at = NOW()
                """, (player, json.dumps(state), json.dumps(state)))
                cur.close()
                conn.close()
                self._json_response(200, {'ok': True})
            except Exception as e:
                print(f"[DB ERROR] POST /api/state: {e}")
                self._json_response(500, {'error': str(e)})
            return

        self._json_response(404, {'error': 'Not found'})

    def _json_response(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    @staticmethod
    def _default_state():
        return {
            'talkedTo': {},       # { 'harry_ron_hermione': True, ... }
            'fatLadyPassed': False,
            'praConvoComplete': False,
        }

    def log_message(self, format, *args):
        # Quieter logging — only log API calls
        if '/api/' in str(args[0] if args else ''):
            super().log_message(format, *args)


# ── Main ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"[Server] Initializing database...")
    init_db()
    print(f"[Server] Starting on http://localhost:{PORT}")
    server = http.server.HTTPServer(('', PORT), GameHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] Shutting down.")
        server.server_close()
