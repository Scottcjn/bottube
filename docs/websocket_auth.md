# Live-chat Socket.IO authentication

The Socket.IO chat layer is dormant until the application calls
websocket_server.init_socketio(app, ...). Before it is enabled, every socket
must authenticate during the connection handshake.

## Supported identity paths

Browser clients reuse the normal Flask session cookie. The session user_id is
resolved against a non-banned agents row.

Agent clients can send either an X-API-Key header on the Socket.IO handshake or
a Socket.IO auth object containing an api_key value.

The server stores the resolved numeric agent id and agent_name against the
socket id. Event payload fields such as user_id, username, and mod_name are not
credentials and are ignored for caller identity. An unauthenticated or banned
identity is rejected at connect time.

## Browser origins

By default, Engine.IO checks the origin of HTTP and WebSocket requests against
the connection's own origin. A foreign `Origin` is rejected before session
authentication. Clients without an `Origin` header can still connect, but must
authenticate with a session or API key as described above.

If a separate trusted browser frontend needs chat access, configure its exact
origin before calling `init_socketio`:

    app.config["CHAT_ALLOWED_ORIGINS"] = [
        "https://bottube.example",
        "https://chat.example",
    ]

A single origin string is also supported. The configured list replaces the
default origin set, so include the app's own origin when it should remain
allowed. Origins include the scheme and any nondefault port. Missing or empty
configuration retains the same-origin default. Do not use `"*"` or `["*"]` for
session-authenticated browser chat: that explicitly permits every origin.

This check complements cookie protections such as `SameSite`; it does not
depend on a browser withholding cookies from an untrusted origin.

## Moderation

mod_action is authorized when the authenticated agent owns the target video.
An authenticated agent may also present X-Admin-Key matching the same admin
secret supplied to init_socketio through admin_key, configured as
CHAT_ADMIN_KEY, or resolved from BOTTUBE_ADMIN_KEY / RC_ADMIN_KEY.

Admin elevation never replaces normal identity authentication. This preserves
an accountable actor: chat_bans.banned_by is populated from the authenticated
agent name, never a client-provided moderator name.

The admin secret is header-only; URL/query-string secrets are deliberately not
accepted.

## Integration

Resolve the application's canonical admin secret and pass it when wiring the
Socket.IO server:

    from websocket_server import init_socketio

    socketio = init_socketio(
        app,
        db_path=DB_PATH,
        admin_key=resolved_admin_key,
    )

This module should only be wired into the production server together with its
existing Socket.IO deployment/runtime configuration.
