from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"
HTML_PATH = STATIC_ROOT / "index.html"
CSS_PATH = STATIC_ROOT / "styles.css"
JS_PATH = STATIC_ROOT / "app.js"


class FrontendParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.tags: list[str] = []
        self.attributes: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        self.tags.append(tag)
        if element_id := values.get("id"):
            self.ids.append(element_id)
            self.attributes[element_id] = values


def frontend_sources() -> tuple[str, str, str]:
    return (
        HTML_PATH.read_text(encoding="utf-8"),
        CSS_PATH.read_text(encoding="utf-8"),
        JS_PATH.read_text(encoding="utf-8"),
    )


def test_frontend_dom_ids_are_unique_and_javascript_references_exist():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids))
    referenced_ids = set(re.findall(r'querySelector\("#([^" ]+)"\)', javascript))
    assert referenced_ids <= set(parser.ids)


def test_frontend_keeps_customer_view_media_free_and_self_contained():
    html, css, _ = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert not {"img", "picture", "source"}.intersection(parser.tags)
    assert not re.search(r'(?:src|href)=["\']https?://', html, re.IGNORECASE)
    assert not re.search(r'url\(["\']?https?://', css, re.IGNORECASE)
    assert "tool-trace" not in html


def test_frontend_preserves_dual_view_and_accessibility_contracts():
    html, _, _ = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert 'data-view="customer"' in html
    assert html.count('data-view-mode=') == 2
    assert parser.attributes["conversation"].get("aria-live") == "polite"
    assert parser.attributes["inspector-panel"].get("aria-hidden") == "true"
    assert parser.attributes["app-announcer"].get("role") == "status"
    assert parser.attributes["workspace"].get("tabindex") == "-1"
    assert parser.attributes["developer-view-button"].get("tabindex") == "-1"
    assert 'href="#workspace"' in html


def test_frontend_authentication_has_secure_fallback_and_explicit_states():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    login_form = parser.attributes["login-form"]
    assert login_form.get("method") == "post"
    assert login_form.get("action") == "/auth/login"
    assert "auth-checking" in parser.ids
    assert 'authStatus: storedAccessToken ? "checking" : "anonymous"' in javascript
    assert 'fetchJson("/auth/session"' in javascript
    assert "removeCredentialQueryParameters" in javascript
    assert "window.history.replaceState" in javascript
    assert '["username", "password", "access_token", "token"]' in javascript


def test_frontend_navigation_and_button_hierarchy_are_unambiguous():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert "对话视图" in html
    assert "调试视图" in html
    assert "客户模式" not in html
    assert "开发者模式" not in html
    assert html.index('id="account-title"') < html.index('id="quick-title"')
    assert html.index('id="account-title"') < html.index('id="new-chat-button"')
    assert html.index('id="new-chat-button"') < html.index('id="quick-title"')
    assert html.index('id="quick-title"') < html.index('id="system-status-title"')
    assert html.index('id="system-status-title"') < html.index('id="security-title"')
    assert parser.attributes["auth-expand-button"].get("aria-controls") == "login-form"
    assert parser.attributes["auth-expand-button"].get("aria-expanded") == "false"
    assert parser.attributes["login-button"].get("class") == "primary-button"
    assert parser.attributes["login-button"].get("data-button-level") == "primary"
    assert parser.attributes["send-button"].get("data-button-level") == "primary"
    assert parser.attributes["new-chat-button"].get("data-button-level") == "secondary"
    assert parser.attributes["fill-demo-button"].get("data-button-level") == "secondary"
    assert parser.attributes["logout-button"].get("data-button-level") == "text"
    assert ">退出登录</button>" in html
    assert 'cancel.dataset.buttonLevel = "danger"' in javascript
    assert 'action.dataset.buttonLevel = "danger"' in javascript
    assert 'sendButton.classList.toggle("is-loading", sending)' in javascript
    assert html.count('data-auth-required="true"') == 5
    assert 'requestLoginForAction(promptButton.dataset.prompt' in javascript
    assert 'chatForm.requestSubmit()' in javascript
    assert 'syncPendingActionUi()' in javascript
    assert 'button.dataset.locked = String(locked)' in javascript
    assert 'configureAuthRequiredButton(add, "加入个人购物车")' in javascript
    assert "state.pendingPrompt = null" in javascript
    assert "clear-button" not in parser.ids
    assert "startNewConversation" in javascript
    assert "clearButton" not in javascript


def test_frontend_styles_have_balanced_blocks_and_defined_tokens():
    _, css, _ = frontend_sources()
    definitions = set(re.findall(r'(--[\w-]+)\s*:', css))
    usages = set(re.findall(r'var\((--[\w-]+)', css))

    assert css.count("{") == css.count("}")
    assert usages <= definitions
    assert "prefers-reduced-motion: reduce" in css
    assert "forced-colors: active" in css


def test_frontend_static_assets_stay_within_demo_size_budget():
    assets = (HTML_PATH, CSS_PATH, JS_PATH)

    assert all(path.stat().st_size < 80 * 1024 for path in assets)
    assert sum(path.stat().st_size for path in assets) < 160 * 1024


def test_frontend_build_identity_and_initialization_fallback_are_visible():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    versions = re.findall(r'/static/(?:styles\.css|app\.js)\?v=([^"\']+)', html)
    assert versions == ["20260810.7", "20260810.7"]
    assert parser.attributes["ui-version"].get("data-ui-version") == "2"
    assert parser.attributes["app-init-error"].get("role") == "alert"
    assert "appReady" in html
    assert 'document.documentElement.dataset.appReady = "true"' in javascript


def test_acceptance_auth_lifecycle_is_explicit_and_mutually_exclusive():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert parser.attributes["login-form"].get("class") == "hidden"
    assert parser.attributes["signed-in"].get("class") == "signed-in hidden"
    assert parser.attributes["auth-checking"].get("class") == "auth-checking hidden"
    assert 'setAuthStatus("authenticating")' in javascript
    assert 'setAuthStatus("authenticated")' in javascript
    assert 'setAuthStatus("anonymous")' in javascript
    assert 'loginForm.classList.toggle("hidden", !showLoginForm)' in javascript
    assert 'signedIn.classList.toggle("hidden", !loggedIn)' in javascript
    assert 'loginHint.textContent = "登录已失效，请重新登录。"' in javascript
    assert 'sessionStorage.removeItem("ordermate_token")' in javascript
    assert 'sessionStorage.removeItem("ordermate_username")' in javascript


def test_acceptance_credentials_never_use_get_and_sensitive_query_is_removed():
    html, _, javascript = frontend_sources()
    parser = FrontendParser()
    parser.feed(html)

    assert parser.attributes["login-form"].get("method") == "post"
    assert 'event.preventDefault()' in javascript
    assert 'method: "POST"' in javascript
    assert 'JSON.stringify({ username, password })' in javascript
    assert 'window.history.replaceState' in javascript
    assert 'const sensitiveNames = ["username", "password", "access_token", "token"]' in javascript


def test_acceptance_views_are_auth_independent_and_inspector_redacts_secrets():
    html, _, javascript = frontend_sources()

    assert html.count('data-view-mode=') == 2
    view_function = javascript[javascript.index("function setViewMode"):javascript.index("function setSidebarOpen")]
    assert "authStatus" not in view_function
    assert "accessToken" not in view_function
    assert 'JSON.stringify(redactSensitive(event.data), null, 2)' in javascript
    assert re.search(r'pass\(word\)\?\|token\|secret\|authorization\|cookie', javascript)


def test_acceptance_anonymous_and_personal_capabilities_are_classified():
    html, _, javascript = frontend_sources()

    assert 'data-prompt="推荐 3000 元以内的手机"' in html
    assert 'data-prompt="我想了解取消订单的规则"' in html
    assert 'data-prompt="查看我的购物车" data-auth-required="true"' in html
    assert 'data-prompt="查询我的最近订单" data-auth-required="true"' in html
    assert 'requestLoginForAction(promptButton.dataset.prompt' in javascript
    assert 'pendingActionContinue.addEventListener("click"' in javascript
    assert "chatForm.requestSubmit()" in javascript
    assert 'clearPendingAction()' in javascript


def test_acceptance_duplicate_submissions_are_guarded():
    _, _, javascript = frontend_sources()

    assert "if (!message || state.sending) return;" in javascript
    assert 'sendButton.disabled = sending' in javascript
    assert 'chatForm.setAttribute("aria-busy", String(sending))' in javascript
    assert 'if (card.classList.contains("is-submitting") || state.confirming > 0) return;' in javascript
    assert 'buttons.forEach((button) => (button.disabled = true))' in javascript
    assert 'status.textContent = approved ? "正在安全提交，请勿重复操作…"' in javascript


def test_acceptance_responsive_layout_covers_desktop_tablet_and_phone():
    _, css, _ = frontend_sources()

    assert "min-width: 320px" in css
    assert "min-height: 100dvh" in css
    assert "height: 100dvh" in css
    assert "@media (max-width: 1100px)" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 680px)" in css
    assert ".app-shell.sidebar-open .sidebar" in css
    assert '.app-shell[data-view="developer"] .shell-backdrop' in css
