"""TODO 245 — PC 레지스트리가 .js 를 text/plain 으로 적어 둔 곳에서도 화면 묶음은 자바스크립트로 나간다."""

import mimetypes

import pytest

from app import mimefix
from app.main import FRONTEND_DIST


@pytest.fixture()
def broken_registry():
    """윈도우 파이썬이 레지스트리를 읽어 .js 를 text/plain 으로 덮어쓴 상태를 흉내 낸다."""
    mimetypes.add_type("text/plain", ".js")
    mimetypes.add_type("text/plain", ".css")
    yield
    mimefix.ensure()


def test_ensure_reports_and_fixes_wrong_js_type(broken_registry):
    wrong = mimefix.ensure()
    assert (".js", "text/plain", "text/javascript") in wrong
    assert mimetypes.guess_type("a.js")[0] == "text/javascript"
    assert mimetypes.guess_type("a.css")[0] == "text/css"
    # 한 번 바로잡으면 조용하다 — 켤 때마다 알리지 않는다
    assert mimefix.ensure() == []


def test_application_javascript_is_not_reported():
    mimetypes.add_type("application/javascript", ".js")
    try:
        assert all(ext != ".js" for ext, _, _ in mimefix.ensure())
    finally:
        mimefix.ensure()


def test_assets_are_served_as_javascript_even_if_registry_is_wrong(client, broken_registry):
    js = next((FRONTEND_DIST / "assets").glob("*.js"))
    for encoding in ("gzip", "identity"):
        res = client.get(f"/assets/{js.name}", headers={"Accept-Encoding": encoding})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/javascript")
    css = next((FRONTEND_DIST / "assets").glob("*.css"), None)
    if css is not None:
        assert client.get(f"/assets/{css.name}").headers["content-type"].startswith("text/css")
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
    page = client.get("/")
    assert page.headers["content-type"].startswith("text/html")


def test_index_has_plain_script_fallback_instead_of_white_screen():
    html = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
    assert "boot-fail" in html and "화면을 그리지 못했습니다" in html
    # 모듈이 아닌 옛 문법의 스크립트여야 IE 모드에서도 돈다
    fallback = html.split("boot-fail")[0].rsplit("<script", 1)[1]
    assert 'type="module"' not in fallback.split(">", 1)[0]
