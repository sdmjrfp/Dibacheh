"""تست آفلاین: کل برنامه بدون هیچ اتصال شبکه کار می‌کند.

در این تست هر تلاش برای اتصال شبکه (حتی به proxy محلی) خطا می‌دهد.
بعد همهٔ کارهای اصلی انجام می‌شود: افزودن درس، صف، تیک، جابه‌جایی، تنظیمات و خروجی.
"""

import socket

import pytest

from test_api import add, item_named
from test_exporter import make_pdf


@pytest.fixture
def no_network(monkeypatch):
    attempts = []

    def blocked_connect(self, address):
        attempts.append(address)
        raise OSError("شبکه در این تست بسته است")

    def blocked_lookup(host, *args, **kwargs):
        attempts.append(host)
        raise OSError("شبکه در این تست بسته است")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", blocked_lookup)
    return attempts


def test_whole_app_works_without_network(client, tmp_path, no_network):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# فصل ۱\nمتن\n", encoding="utf-8")
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, 20)
    client.patch("/api/settings", json={"vault_path": str(vault), "export_folder": str(tmp_path / "out")})

    assert client.get("/").status_code == 200
    add(client, "کتاب", count=4, section_unit="page", range_start="1", range_end="20",
        source_type="file", source_path_or_url=str(pdf))
    state = add(client, "نوت", count=1, source_type="vault", source_path_or_url="n.md")
    ids = [i["id"] for i in state["items"]]
    client.post("/api/items/reorder", json={"ids": ids[::-1]})
    s = item_named(state, "کتاب")["sessions"][0]["id"]
    client.post("/api/tasks/done", json={"session_id": s, "kind": "read", "result": "done"})
    client.post("/api/tasks/move", json={"session_id": item_named(state, "کتاب")["sessions"][1]["id"],
                                          "kind": "read", "date": state["today"]})
    client.patch("/api/settings", json={"review_intervals": [1, 4, 10]})
    for scope in ("day", "week", "month"):
        response = client.post("/api/export", json={"scope": scope, "with_content": True})
        assert response.status_code == 200
    client.post("/api/undo", json={})

    assert no_network == []   # هیچ تلاشی برای اتصال به شبکه نشد
