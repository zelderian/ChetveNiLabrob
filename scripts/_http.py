"""Tiny stdlib-only HTTP helper, so the scripts run without installing anything."""
import json
import urllib.error
import urllib.request


class Resp:
    def __init__(self, status: int, headers, body: bytes):
        self.status = status
        self.headers = headers
        self.text = body.decode() if body else ""

    def json(self):
        return json.loads(self.text) if self.text else None

    @property
    def instance(self) -> str:
        return self.headers.get("X-Instance-ID", "-")


def request(method: str, url: str, body=None, headers=None, timeout: float = 10) -> Resp:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Resp(r.status, r.headers, r.read())
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.headers, e.read())
