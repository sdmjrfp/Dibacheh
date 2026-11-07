"""دستورهای مخصوص هر سیستم‌عامل، بدون نیاز به خود آن سیستم."""

from pathlib import Path

import pytest

import platform_tools


def as_system(monkeypatch, name):
    monkeypatch.setattr(platform_tools, "system", lambda: name)


def test_open_and_reveal_commands(monkeypatch):
    as_system(monkeypatch, "mac")
    assert platform_tools.open_args("x") == ["open", "x"]
    assert platform_tools.reveal_args("/a/b.html") == ["open", "-R", "/a/b.html"]
    as_system(monkeypatch, "windows")
    assert platform_tools.open_args("x") == ["rundll32", "url.dll,FileProtocolHandler", "x"]
    assert platform_tools.reveal_args("C:\\a\\b.html") == ["explorer", "/select,C:\\a\\b.html"]
    as_system(monkeypatch, "linux")
    assert platform_tools.open_args("x") == ["xdg-open", "x"]
    assert platform_tools.reveal_args("/a/b.html") == ["xdg-open", str(Path("/a"))]


def test_data_folder_of_installed_app(monkeypatch, tmp_path):
    monkeypatch.delenv("DIBACHEH_HOME", raising=False)
    monkeypatch.setattr(platform_tools, "is_frozen", lambda: True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    as_system(monkeypatch, "mac")
    assert platform_tools.app_home() == tmp_path / "Library" / "Application Support" / "Dibacheh"
    as_system(monkeypatch, "windows")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert platform_tools.app_home() == tmp_path / "Roaming" / "Dibacheh"
    as_system(monkeypatch, "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert platform_tools.app_home() == tmp_path / ".local" / "share" / "dibacheh"


def test_data_folder_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DIBACHEH_HOME", str(tmp_path))
    assert platform_tools.app_home() == tmp_path


def test_browse_commands(monkeypatch):
    as_system(monkeypatch, "mac")
    assert "choose folder" in platform_tools.browse_command("folder", 'x"y')[-1]
    as_system(monkeypatch, "windows")
    assert "OpenFileDialog" in platform_tools.browse_command("file", "x")[-1]
    assert "FolderBrowserDialog" in platform_tools.browse_command("folder", "x")[-1]
    as_system(monkeypatch, "linux")
    monkeypatch.setattr(platform_tools.shutil, "which", lambda name: name == "zenity")
    assert platform_tools.browse_command("folder", "x") == ["zenity", "--file-selection", "--title", "x", "--directory"]
    monkeypatch.setattr(platform_tools.shutil, "which", lambda name: name == "kdialog")
    assert platform_tools.browse_command("file", "x")[0] == "kdialog"


def test_linux_without_dialog_tool(monkeypatch):
    as_system(monkeypatch, "linux")
    monkeypatch.setattr(platform_tools.shutil, "which", lambda name: None)
    with pytest.raises(platform_tools.BrowseUnavailable):
        platform_tools.choose("file", "x")


def test_browse_error_reaches_the_page(client, monkeypatch):
    as_system(monkeypatch, "linux")
    monkeypatch.setattr(platform_tools.shutil, "which", lambda name: None)
    response = client.post("/api/browse", json={"kind": "file"})
    assert response.status_code == 400 and "zenity" in response.get_json()["error"]


def test_linux_child_programs_get_original_library_path(monkeypatch):
    as_system(monkeypatch, "linux")
    monkeypatch.setattr(platform_tools, "is_frozen", lambda: True)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")
    assert platform_tools.run_env()["LD_LIBRARY_PATH"] == "/usr/lib"
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in platform_tools.run_env()


def test_quit_only_in_installed_windows_linux_app(client):
    assert client.post("/api/quit", json={}).status_code == 404
