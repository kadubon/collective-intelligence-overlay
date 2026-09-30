"""Installer failure boundaries; native execution is verified in service CI separately."""

import io
from types import SimpleNamespace
from urllib.request import Request

import pytest

from collective_intelligence_overlay import opa_install


@pytest.mark.parametrize(
    "machine,expected",
    [("AMD64", "amd64"), ("x86_64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")],
)
def test_cpu_aliases_and_explicit_unsupported(machine, expected):
    assert opa_install.architecture(machine) == expected
    with pytest.raises(ValueError, match="unsupported CPU"):
        opa_install.architecture("riscv64")


@pytest.mark.parametrize("failure", ["hash", "length", "read"])
def test_failed_download_keeps_old_binary_and_removes_temporary(tmp_path, monkeypatch, failure):
    target = tmp_path / "空白 path" / "opa.exe"
    target.parent.mkdir()
    target.write_bytes(b"previous binary")
    response = io.BytesIO(b"untrusted incomplete download")
    response.headers = {
        "Content-Length": str(opa_install.MAX_BYTES + 1 if failure == "length" else 1)
    }
    if failure == "read":

        def read(size):
            raise TimeoutError("controlled interrupted download")

        response.read = read
    monkeypatch.setattr(opa_install.platform, "system", lambda: "Windows")
    monkeypatch.setattr(opa_install.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(
        opa_install.urllib.request,
        "build_opener",
        lambda *handlers: SimpleNamespace(open=lambda *args, **kw: response),
    )
    with pytest.raises((ValueError, TimeoutError)):
        opa_install.install_opa(target)
    assert target.read_bytes() == b"previous binary"
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("url", ["http://github.com/a", "https://untrusted.example/b"])
def test_redirect_cannot_leave_official_https_assets(url):
    with pytest.raises(ValueError, match="official HTTPS"):
        opa_install._HTTPSRedirect().redirect_request(
            Request("https://github.com/a"), None, 302, "Found", {}, url
        )


def test_unsupported_os_is_clear_and_does_not_create_target(tmp_path, monkeypatch):
    monkeypatch.setattr(opa_install.platform, "system", lambda: "Unknown")
    monkeypatch.setattr(opa_install.platform, "machine", lambda: "arm64")
    with pytest.raises(ValueError, match="unsupported OPA platform"):
        opa_install.install_opa(tmp_path / "new" / "opa")
    assert not (tmp_path / "new").exists()
