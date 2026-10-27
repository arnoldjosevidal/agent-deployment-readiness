from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse

from .service import ApprovalError, ApprovalService
from .workflow import ApprovalWorkflow


INDEX = Path(__file__).with_name("index.html")


class ApprovalHandler(BaseHTTPRequestHandler):
    server_version = "ADR-LocalApproval/1"

    def log_message(self, fmt, *args):
        # Requests may contain private action details; do not write request data to console.
        return

    def _send(self, code, value, *, cookie=None):
        body = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8" if isinstance(value, str) else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32_768:
                raise ValueError
            parsed = json.loads(self.rfile.read(length))
            if not isinstance(parsed, dict):
                raise ValueError
            return parsed
        except (ValueError, json.JSONDecodeError):
            raise ApprovalError("INVALID_REQUEST_BODY", 400)

    def _token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key == "adr_operator_session":
                return value
        return None

    def _operator(self, *, csrf=False):
        token = self._token()
        csrf_value = self.headers.get("X-ADR-CSRF") if csrf else None
        if csrf and not csrf_value:
            raise ApprovalError("CSRF_INVALID", 403)
        return self.server.service.authenticate(token, csrf_value)

    def _check_origin(self):
        origin = self.headers.get("Origin")
        allowed_host = f"127.0.0.1:{self.server.server_port}"
        expected = f"http://{allowed_host}"
        if self.headers.get("Host") != allowed_host or origin != expected:
            raise ApprovalError("ORIGIN_INVALID", 403)

    def _json_route(self, method, path, body):
        if method == "POST" and path == "/api/login":
            self._check_origin()
            token, csrf = self.server.service.login(body.get("password", ""))
            return 200, {"authenticated": True, "csrf": csrf}, f"adr_operator_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800"
        if method == "POST" and path == "/api/logout":
            self._check_origin(); self._operator(csrf=True)
            self.server.service.logout(self._token())
            return 200, {"authenticated": False}, "adr_operator_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
        if method == "GET" and path == "/api/state":
            self._operator()
            self.server.workflow.recover_decided()
            return 200, {"authenticated": True, "actions": self.server.service.list_actions(),
                         "workflows": self.server.workflow.list_runs(),
                         "model_mode": self.server.model_mode}, None
        if method == "POST" and path == "/api/propose":
            self._check_origin(); self._operator(csrf=True)
            return 201, self.server.service.propose_demo(body.get("scenario")), None
        if method == "POST" and path == "/api/workflows/start":
            self._check_origin(); self._operator(csrf=True)
            return 201, self.server.workflow.start(body.get("idempotency_key"), body.get("scenario", "integrated_adversarial")), None
        if method == "POST" and path.startswith("/api/actions/"):
            self._check_origin(); self._operator(csrf=True)
            tail = path.removeprefix("/api/actions/")
            action_id, sep, verb = tail.partition("/")
            if not sep or verb not in ("approve", "reject"):
                raise ApprovalError("ROUTE_NOT_FOUND", 404)
            csrf_token = self.headers.get("X-ADR-CSRF")
            result = self.server.service.decide(action_id, body.get("action_sha256", ""), self._token(), verb, csrf_token)
            workflow = self.server.workflow.resume_after_decision(action_id)
            if workflow is not None:
                result["workflow"] = workflow
            return 200, result, None
        raise ApprovalError("ROUTE_NOT_FOUND", 404)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, INDEX.read_text(encoding="utf-8"))
            return
        try:
            code, value, cookie = self._json_route("GET", path, {})
            self._send(code, value, cookie=cookie)
        except ApprovalError as exc:
            self._send(exc.status, {"error": exc.code})
        except Exception:
            self._send(500, {"error": "LOCAL_SERVER_ERROR"})

    def do_POST(self):
        try:
            body = self._body()
            code, value, cookie = self._json_route("POST", urlparse(self.path).path, body)
            self._send(code, value, cookie=cookie)
        except ApprovalError as exc:
            self._send(exc.status, {"error": exc.code})
        except Exception:
            self._send(500, {"error": "LOCAL_SERVER_ERROR"})


class ApprovalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, model=None):
        super().__init__(address, ApprovalHandler)
        self.service = service
        self.workflow = ApprovalWorkflow(service, model=model)
        self.model_mode = self.workflow.model.source_classification


def serve(db_path: str | Path, password: str, host="127.0.0.1", port=8765, model=None):
    if host != "127.0.0.1":
        raise ValueError("LOOPBACK_ONLY")
    service = ApprovalService(db_path, password)
    server = ApprovalHTTPServer((host, port), service, model=model)
    print(f"ADR approval demo listening at http://{host}:{server.server_port}/")
    print(f"Local operator authentication is active. Model mode: {server.model_mode}. Tool effects remain simulated.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

