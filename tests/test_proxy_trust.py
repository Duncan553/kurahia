"""
The login rate limit is keyed on the client IP (flask-limiter's
get_remote_address), which reads the socket peer address. DEPLOY.md puts Nginx
in front of the app for TLS, so in production that peer is ALWAYS 127.0.0.1 —
every member of staff would share one "5 per minute" login bucket and a shift
change would lock people out.

The fix is ProxyFix, but it must be opt-in: trusting X-Forwarded-For when
nothing is actually in front lets any client forge the header and rotate past
the brute-force protection. So TRUSTED_PROXY_COUNT defaults to 0 and production
sets it to 1.
"""
from app import create_app


def _client_ip_app(hops):
    """An app that just reports what it believes the client IP is."""
    app = create_app("testing")
    app.config["TRUSTED_PROXY_COUNT"] = hops
    # ProxyFix is applied in create_app from config, so rebuild through it.
    if hops > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    @app.route("/__whoami")
    def whoami():
        from flask import request, jsonify
        return jsonify({"ip": request.remote_addr})

    return app


def test_forwarded_header_is_ignored_when_no_proxy_is_trusted():
    """Default posture: a forged X-Forwarded-For must NOT change the client IP."""
    app = _client_ip_app(hops=0)
    with app.test_client() as c:
        rv = c.get("/__whoami", headers={"X-Forwarded-For": "9.9.9.9"})
        assert rv.get_json()["ip"] != "9.9.9.9", (
            "trusting X-Forwarded-For with no proxy in front would let anyone "
            "forge a new IP per request and walk straight past the login rate limit"
        )


def test_forwarded_header_is_honoured_when_one_proxy_is_trusted():
    """Behind Nginx, the real client IP must come from the forwarded header."""
    app = _client_ip_app(hops=1)
    with app.test_client() as c:
        rv = c.get("/__whoami", headers={"X-Forwarded-For": "9.9.9.9"})
        assert rv.get_json()["ip"] == "9.9.9.9", (
            "without this every request looks like it came from 127.0.0.1, so the "
            "whole resort shares a single login rate-limit bucket"
        )


def test_production_config_trusts_exactly_one_hop_by_default():
    """DEPLOY.md documents exactly one proxy (Nginx). Trust that many, no more."""
    from config import ProductionConfig, TestingConfig, DevelopmentConfig

    assert ProductionConfig.TRUSTED_PROXY_COUNT == 1
    # Everywhere else must stay closed unless explicitly opened.
    assert TestingConfig.TRUSTED_PROXY_COUNT == 0
    assert DevelopmentConfig.TRUSTED_PROXY_COUNT == 0


def test_only_the_rightmost_trusted_hop_is_used():
    """
    With one trusted hop, a client that forges a chain must not be able to pick
    its own IP: ProxyFix takes the entry the trusted proxy appended, which is
    the LAST one, not the first.
    """
    app = _client_ip_app(hops=1)
    with app.test_client() as c:
        # Attacker sends "1.1.1.1"; Nginx appends the real peer after it.
        rv = c.get("/__whoami", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
        assert rv.get_json()["ip"] == "203.0.113.7", (
            "the forged left-hand entry must be ignored in favour of what the "
            "trusted proxy actually observed"
        )
