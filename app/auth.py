"""Sign-in: passkeys, sessions, invite codes and access tokens.

How people get in:
  - The very first device registers with a one-time setup code printed in the server log.
  - After that, a signed-in device creates a short-lived invite code (shown as a QR code)
    to add another device, or (admins only) another person.
  - Scripts such as the iOS Shortcut use an access token instead of a passkey.
"""
import hashlib
import ipaddress
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.parse import urlsplit

import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import config, db, notify
from .i18n import LANGS, T

log = logging.getLogger("joyshare.auth")

SESSION_COOKIE = "joyshare_session"
SESSION_SECONDS = 30 * 86400
FRESH_SECONDS = 10 * 60          # sensitive actions need a passkey check this recent
CHALLENGE_SECONDS = 5 * 60
SETUP_CODE_SECONDS = 24 * 3600
INVITE_SECONDS = 10 * 60
RECOVERY_SECONDS = 30 * 60
TOKEN_PREFIX = "js_"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no look-alikes such as O/0 or I/1
MAX_FAILURES, FAILURE_WINDOW = 10, 600

router = APIRouter(prefix="/api/auth")
admin_router = APIRouter(prefix="/api/admin")


def site(request: Request | None = None) -> str:
    """The address this request came in on, if it is one of ours. Otherwise the main address."""
    if request is not None:
        origin = (request.headers.get("origin") or "").rstrip("/")
        if origin in config.ORIGINS:
            return origin
        host = request.headers.get("host", "")
        for known in config.ORIGINS:
            if urlsplit(known).netloc == host:
                return known
    return config.PUBLIC_URL


def rp_id(request: Request | None = None) -> str:
    """Passkeys are tied to this name: the host part of the address the person is using."""
    return urlsplit(site(request)).hostname or "localhost"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ---------- slowing down guessing ----------

_failures: dict[str, deque] = defaultdict(deque)


def _ip(request: Request) -> str:
    """The visitor's address. Behind the Cloudflare Tunnel (or the Caddy web server) every request arrives
    from that container, so the real address is in a header, which is only believed when it comes from a
    private network. Caddy writes X-Forwarded-For itself and puts the visitor last."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[-1]
    if forwarded.strip():
        try:
            if ipaddress.ip_address(peer).is_private:
                return forwarded.strip()[:64]
        except ValueError:
            pass
    return peer


def check_rate(request: Request) -> None:
    recent = _failures[_ip(request)]
    while recent and recent[0] < time.time() - FAILURE_WINDOW:
        recent.popleft()
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Too many failed attempts. Wait a few minutes and try again.")


def note_failure(request: Request, conn, what: str) -> None:
    _failures[_ip(request)].append(time.time())
    if len(_failures[_ip(request)]) == MAX_FAILURES:  # just hit the limit: tell the admin once
        notify.send(conn, "failed_signins", "Repeated failed sign-ins",
                    T("{count} failed attempts from {ip}. That address now has to wait.", count=MAX_FAILURES, ip=_ip(request)))
    db.audit(conn, None, "auth.failure", json.dumps({"what": what, "ip": _ip(request)}))


# ---------- who is asking ----------

@dataclass
class Auth:
    user_id: int
    name: str
    role: str
    via: str                      # "session" or "token"
    session_hash: str | None = None
    credential_pk: int | None = None
    authenticated_at: int = 0


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in config.ORIGINS
    return request.headers.get("sec-fetch-site") == "same-origin"


def authenticate(request: Request, conn) -> Auth | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        row = conn.execute(
            "SELECT t.id, u.id AS user_id, u.name, u.role FROM api_tokens t JOIN users u ON u.id=t.user_id "
            "WHERE t.token_hash=? AND t.revoked_at IS NULL AND u.disabled=0",
            (sha(header[7:].strip()),),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (db.now(), row["id"]))
        return Auth(row["user_id"], row["name"], row["role"], "token")

    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    token_hash = sha(cookie)
    row = conn.execute(
        "SELECT s.*, u.name, u.role FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0",
        (token_hash, db.now()),
    ).fetchone()
    if not row:
        return None
    # Cookies travel automatically, so changes must come from our own pages.
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        raise HTTPException(403, "This request didn't come from this app.")
    if db.now() - row["last_seen_at"] > 300:
        conn.execute(
            "UPDATE sessions SET last_seen_at=?, expires_at=? WHERE token_hash=?",
            (db.now(), db.now() + SESSION_SECONDS, token_hash),
        )
    return Auth(row["user_id"], row["name"], row["role"], "session", token_hash,
                row["credential_pk"], row["authenticated_at"])


def current_auth(request: Request, conn=Depends(db.get_conn)) -> Auth:
    auth = authenticate(request, conn)
    if not auth:
        raise HTTPException(401, "Sign in to continue.")
    return auth


def current_user(auth: Auth = Depends(current_auth)) -> int:
    return auth.user_id


def session_auth(auth: Auth = Depends(current_auth)) -> Auth:
    """Account management is for people signed in with a passkey, not for access tokens."""
    if auth.via != "session":
        raise HTTPException(403, "Access tokens can't manage devices or people.")
    return auth


def fresh_auth(auth: Auth = Depends(session_auth)) -> Auth:
    """Sensitive actions need a passkey check in the last few minutes."""
    if db.now() - auth.authenticated_at > FRESH_SECONDS:
        raise HTTPException(401, "Confirm it's you to continue.", headers={"X-Joyshare-Reauth": "1"})
    return auth


def admin_auth(auth: Auth = Depends(session_auth)) -> Auth:
    if auth.role != "admin":
        raise HTTPException(403, "Only an admin can do that.")
    return auth


# ---------- sessions ----------

def create_session(conn, user_id: int, credential_pk: int | None = None, user_agent: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    moment = db.now()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, credential_pk, created_at, authenticated_at, "
        "last_seen_at, expires_at, user_agent) VALUES (?,?,?,?,?,?,?,?)",
        (sha(token), user_id, credential_pk, moment, moment, moment, moment + SESSION_SECONDS,
         (user_agent or "")[:200]),
    )
    return token


def _start_session(conn, request: Request, response: Response, user_id: int, credential_pk: int) -> None:
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (sha(old),))
    token = create_session(conn, user_id, credential_pk, request.headers.get("user-agent"))
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax",
        secure=site(request).startswith("https://"), path="/",
    )


# ---------- invite codes ----------

def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def create_invite(conn, *, kind: str, ttl: int, user_id: int | None = None, role: str | None = None,
                  name: str | None = None, created_by: int | None = None) -> tuple[str, int]:
    code = new_code()
    expires_at = db.now() + ttl
    conn.execute(
        "INSERT INTO invites (code_hash, kind, user_id, role, name, created_by, created_at, expires_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (sha(normalize_code(code)), kind, user_id, role, name, created_by, db.now(), expires_at),
    )
    return code, expires_at


def live_invite(conn, code: str):
    return conn.execute(
        "SELECT * FROM invites WHERE code_hash=? AND used_at IS NULL AND expires_at>?",
        (sha(normalize_code(code)), db.now()),
    ).fetchone()


def has_any_passkey(conn) -> bool:
    return conn.execute("SELECT 1 FROM credentials LIMIT 1").fetchone() is not None


def first_admin(conn):
    return conn.execute("SELECT * FROM users WHERE role='admin' AND disabled=0 ORDER BY id LIMIT 1").fetchone()


def ensure_setup_code(conn) -> str | None:
    """While nobody has registered a device, keep one setup code alive and print it in the log."""
    if has_any_passkey(conn):
        return None
    conn.execute("DELETE FROM invites WHERE kind='setup'")
    code, _ = create_invite(conn, kind="setup", ttl=SETUP_CODE_SECONDS, user_id=first_admin(conn)["id"])
    banner = "=" * 62
    log.warning("\n%s\n  Setup code:  %s\n  Open %s and enter it to register your first device.\n"
                "  It works once and expires in 24 hours.\n%s", banner, code, config.PUBLIC_URL, banner)
    return code


def recovery_code(conn) -> str:
    """For the server owner who lost every passkey. Used by: python -m app.cli setup-code"""
    admin = first_admin(conn)
    if not admin:
        raise RuntimeError("No active admin exists.")
    code, _ = create_invite(conn, kind="device", ttl=RECOVERY_SECONDS, user_id=admin["id"])
    db.audit(conn, admin["id"], "auth.recovery_code", None)
    return code


def user_handle(conn, user_id: int) -> bytes:
    row = conn.execute("SELECT handle FROM users WHERE id=?", (user_id,)).fetchone()
    if row["handle"]:
        return bytes(row["handle"])
    handle = secrets.token_bytes(16)
    conn.execute("UPDATE users SET handle=? WHERE id=?", (handle, user_id))
    return handle


def _save_challenge(conn, kind: str, challenge: bytes, **extra) -> str:
    challenge_id = secrets.token_urlsafe(16)
    conn.execute(
        "INSERT INTO challenges (id, kind, challenge, invite_hash, user_handle, device_name, expires_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (challenge_id, kind, challenge, extra.get("invite_hash"), extra.get("user_handle"),
         extra.get("device_name"), db.now() + CHALLENGE_SECONDS),
    )
    return challenge_id


def _take_challenge(conn, challenge_id: str, kind: str):
    row = conn.execute(
        "DELETE FROM challenges WHERE id=? AND kind=? AND expires_at>? RETURNING *",
        (challenge_id, kind, db.now()),
    ).fetchone()
    if not row:
        raise HTTPException(400, "That took too long. Try again.")
    return row


# ---------- each person's own look ----------

FONTS = ("unbounded", "syne", "glitch", "warp", "mono", "fredoka", "bangers", "win",
         "playfair", "intertight", "cormorant", "manrope", "dmserif", "plex")
THEMES = ("zine", "acid", "clay", "win95", "comic", "editorial", "swiss", "midnight", "nordic", "library", "studio")


DEFAULT_THEME, DEFAULT_FONT = "zine", "mono"   # the look a new person starts with
SCENES = ("random", "demolition", "compressor", "voyage", "rocket", "blackhole", "dominoes", "ufo", "none")
MOTION = ("auto", "full")
SIZES = ("auto", "ask")   # "auto": a pasted link is made straight away at a sensible size; "ask": show the size step first


def get_prefs(conn, user_id: int) -> dict:
    """Name shown at the top, font, theme and language. Missing choices fall back to the defaults."""
    row = conn.execute("SELECT prefs FROM users WHERE id=?", (user_id,)).fetchone()
    saved = json.loads(row["prefs"]) if row and row["prefs"] else {}
    return {
        "name": saved.get("name") or config.APP_NAME,
        "font": saved.get("font") if saved.get("font") in FONTS else DEFAULT_FONT,
        "theme": saved.get("theme") if saved.get("theme") in THEMES else DEFAULT_THEME,
        "lang": saved.get("lang") if saved.get("lang") in LANGS else None,
        "scene": saved.get("scene") if saved.get("scene") in SCENES else SCENES[0],
        "motion": saved.get("motion") if saved.get("motion") in MOTION else MOTION[0],
        "sizes": saved.get("sizes") if saved.get("sizes") in SIZES else SIZES[0],
    }


# ---------- request bodies ----------

class PrefsBody(BaseModel):
    name: str | None = None
    font: str | None = None
    theme: str | None = None
    lang: str | None = None
    scene: str | None = None
    motion: str | None = None
    sizes: str | None = None


class RegisterOptionsBody(BaseModel):
    code: str
    device_name: str = ""


class VerifyBody(BaseModel):
    challenge_id: str
    credential: dict


class InviteBody(BaseModel):
    kind: str = "device"      # "device" (another device for me) or "user" (a new person, admin only)
    name: str = ""
    role: str = "member"      # for a new person: "member" or "admin"


class RoleBody(BaseModel):
    role: str


class TokenBody(BaseModel):
    name: str


# ---------- registering a device ----------

@router.get("/status")
def status(request: Request, conn=Depends(db.get_conn)):
    try:
        auth = authenticate(request, conn)
    except HTTPException:
        auth = None
    return {
        "signed_in": bool(auth),
        "user": {"id": auth.user_id, "name": auth.name, "role": auth.role} if auth else None,
        "first_run": not has_any_passkey(conn),
        "prefs": get_prefs(conn, auth.user_id) if auth else None,
        "app_name": config.APP_NAME,
    }


@router.put("/prefs")
def save_prefs(body: PrefsBody, auth: Auth = Depends(session_auth), conn=Depends(db.get_conn)):
    """Saved on the account, so the look follows the person to every device."""
    row = conn.execute("SELECT prefs FROM users WHERE id=?", (auth.user_id,)).fetchone()
    saved = json.loads(row["prefs"]) if row["prefs"] else {}
    if body.name is not None:
        name = " ".join("".join(ch for ch in body.name if ch.isprintable()).split())
        if len(name) > 24:
            raise HTTPException(422, "That name is too long.")
        saved["name"] = name  # empty means: back to the default name
    for field, allowed in (("font", FONTS), ("theme", THEMES), ("lang", LANGS), ("scene", SCENES), ("motion", MOTION),
                           ("sizes", SIZES)):
        value = getattr(body, field)
        if value is not None:
            if value not in allowed:
                raise HTTPException(422, "Unknown choice.")
            saved[field] = value
    conn.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps(saved), auth.user_id))
    return get_prefs(conn, auth.user_id)


@router.post("/register/options")
def register_options(body: RegisterOptionsBody, request: Request, conn=Depends(db.get_conn)):
    check_rate(request)
    invite = live_invite(conn, body.code)
    if not invite:
        note_failure(request, conn, "invite_code")
        raise HTTPException(400, "That code isn't valid. Codes work once and expire quickly.")
    exclude = []
    if invite["kind"] == "user":
        handle, name = secrets.token_bytes(16), invite["name"] or "member"
    else:
        user = conn.execute("SELECT * FROM users WHERE id=? AND disabled=0", (invite["user_id"],)).fetchone()
        if not user:
            raise HTTPException(400, "That code isn't valid. Codes work once and expire quickly.")
        handle, name = user_handle(conn, user["id"]), user["name"]
        exclude = [
            PublicKeyCredentialDescriptor(id=bytes(row["credential_id"]))
            for row in conn.execute("SELECT credential_id FROM credentials WHERE user_id=?", (user["id"],))
        ]
    options = generate_registration_options(
        rp_id=rp_id(request), rp_name=config.APP_NAME, user_id=handle, user_name=name, user_display_name=name,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    challenge_id = _save_challenge(
        conn, "register", options.challenge, invite_hash=invite["code_hash"], user_handle=handle,
        device_name=(body.device_name or "").strip()[:60] or "My device",
    )
    return {"challenge_id": challenge_id, "publicKey": json.loads(options_to_json(options))}


@router.post("/register/verify")
def register_verify(body: VerifyBody, request: Request, response: Response, conn=Depends(db.get_conn)):
    check_rate(request)
    challenge = _take_challenge(conn, body.challenge_id, "register")
    try:
        verified = verify_registration_response(
            credential=body.credential, expected_challenge=bytes(challenge["challenge"]),
            expected_rp_id=rp_id(request), expected_origin=site(request), require_user_verification=True,
        )
    except Exception as exc:
        note_failure(request, conn, "register_verify")
        log.info("Passkey registration rejected: %s", exc)
        raise HTTPException(400, "That passkey couldn't be verified. Try again.") from exc

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Claim the invite first, so one code can never register two devices.
        invite = conn.execute(
            "UPDATE invites SET used_at=? WHERE code_hash=? AND used_at IS NULL AND expires_at>? RETURNING *",
            (db.now(), challenge["invite_hash"], db.now()),
        ).fetchone()
        if not invite:
            raise HTTPException(400, "That code was already used or has expired.")
        if invite["kind"] == "user":
            user_id = conn.execute(
                "INSERT INTO users (name, role, handle, created_at) VALUES (?,?,?,?)",
                (invite["name"] or "member", invite["role"] or "member", bytes(challenge["user_handle"]), db.now()),
            ).lastrowid
        else:
            user_id = invite["user_id"]
        transports = (body.credential.get("response") or {}).get("transports") or []
        credential_pk = conn.execute(
            "INSERT INTO credentials (user_id, credential_id, public_key, sign_count, name, transports, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, verified.credential_id, verified.credential_public_key, verified.sign_count,
             challenge["device_name"], json.dumps(transports), db.now()),
        ).lastrowid
        db.audit(conn, user_id, "device.add", json.dumps({"name": challenge["device_name"], "via": invite["kind"]}))
        _start_session(conn, request, response, user_id, credential_pk)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    user = conn.execute("SELECT id, name, role FROM users WHERE id=?", (user_id,)).fetchone()
    notify.send(conn, "new_device", "New device added",
                T("{device} was registered for {person}.", device=challenge["device_name"], person=user["name"]))
    return {"user": dict(user)}


# ---------- signing in ----------

@router.post("/login/options")
def login_options(request: Request, conn=Depends(db.get_conn)):
    check_rate(request)
    options = generate_authentication_options(
        rp_id=rp_id(request), user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = _save_challenge(conn, "login", options.challenge)
    return {"challenge_id": challenge_id, "publicKey": json.loads(options_to_json(options))}


@router.post("/login/verify")
def login_verify(body: VerifyBody, request: Request, response: Response, conn=Depends(db.get_conn)):
    check_rate(request)
    challenge = _take_challenge(conn, body.challenge_id, "login")
    failed = HTTPException(401, "That passkey isn't registered here.")
    try:
        raw_id = base64url_to_bytes(body.credential.get("id") or "")
    except Exception:
        raise failed from None
    row = conn.execute(
        "SELECT c.*, u.name AS user_name, u.role, u.disabled FROM credentials c JOIN users u ON u.id=c.user_id "
        "WHERE c.credential_id=?", (raw_id,),
    ).fetchone()
    if not row or row["disabled"]:
        note_failure(request, conn, "unknown_passkey")
        raise failed
    try:
        verified = verify_authentication_response(
            credential=body.credential, expected_challenge=bytes(challenge["challenge"]),
            expected_rp_id=rp_id(request), expected_origin=site(request),
            credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=row["sign_count"], require_user_verification=True,
        )
    except Exception as exc:
        note_failure(request, conn, "login_verify")
        log.info("Passkey sign-in rejected: %s", exc)
        raise failed from exc
    conn.execute("UPDATE credentials SET sign_count=?, last_used_at=? WHERE id=?",
                 (verified.new_sign_count, db.now(), row["id"]))
    _start_session(conn, request, response, row["user_id"], row["id"])
    return {"user": {"id": row["user_id"], "name": row["user_name"], "role": row["role"]}}


@router.post("/logout")
def logout(response: Response, auth: Auth = Depends(session_auth), conn=Depends(db.get_conn)):
    conn.execute("DELETE FROM sessions WHERE token_hash=?", (auth.session_hash,))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, auth: Auth = Depends(session_auth), conn=Depends(db.get_conn)):
    conn.execute("DELETE FROM sessions WHERE user_id=?", (auth.user_id,))
    response.delete_cookie(SESSION_COOKIE, path="/")
    db.audit(conn, auth.user_id, "auth.logout_all", None)
    return {"ok": True}


# ---------- my devices and tokens ----------

@router.get("/devices")
def devices(auth: Auth = Depends(session_auth), conn=Depends(db.get_conn)):
    passkeys = [
        {"id": r["id"], "name": r["name"], "created_at": r["created_at"], "last_used_at": r["last_used_at"],
         "current": r["id"] == auth.credential_pk}
        for r in conn.execute("SELECT * FROM credentials WHERE user_id=? ORDER BY id", (auth.user_id,))
    ]
    tokens = [
        {"id": r["id"], "name": r["name"], "created_at": r["created_at"], "last_used_at": r["last_used_at"]}
        for r in conn.execute(
            "SELECT * FROM api_tokens WHERE user_id=? AND revoked_at IS NULL ORDER BY id", (auth.user_id,))
    ]
    return {"passkeys": passkeys, "tokens": tokens}


@router.delete("/devices/{credential_pk}")
def remove_device(credential_pk: int, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    row = conn.execute("SELECT * FROM credentials WHERE id=? AND user_id=?",
                       (credential_pk, auth.user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Device not found.")
    count = conn.execute("SELECT COUNT(*) FROM credentials WHERE user_id=?", (auth.user_id,)).fetchone()[0]
    if count <= 1:
        raise HTTPException(409, "This is your only device. Add another one before removing it.")
    conn.execute("DELETE FROM sessions WHERE credential_pk=?", (credential_pk,))
    conn.execute("DELETE FROM credentials WHERE id=?", (credential_pk,))
    db.audit(conn, auth.user_id, "device.remove", json.dumps({"name": row["name"]}))
    return {"ok": True}


@router.post("/invites")
def invite(body: InviteBody, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    if body.kind == "device":
        code, expires_at = create_invite(conn, kind="device", ttl=INVITE_SECONDS,
                                         user_id=auth.user_id, created_by=auth.user_id)
    elif body.kind == "user":
        if auth.role != "admin":
            raise HTTPException(403, "Only an admin can invite people.")
        name = body.name.strip()[:40]
        if not name:
            raise HTTPException(422, "Give the person a name.")
        if body.role not in ("member", "admin"):
            raise HTTPException(422, "Unknown choice.")
        code, expires_at = create_invite(conn, kind="user", ttl=INVITE_SECONDS, role=body.role,
                                         name=name, created_by=auth.user_id)
    else:
        raise HTTPException(422, "Unknown invite type.")
    db.audit(conn, auth.user_id, "invite.create", json.dumps(
        {"kind": body.kind, **({"role": body.role, "name": name} if body.kind == "user" else {})}))
    url = f"{config.PUBLIC_URL}/#join={code}"
    qr = segno.make(url, error="m").svg_data_uri(scale=5, border=2, dark="#000000", light="#ffffff")
    return {"code": code, "url": url, "qr": qr, "expires_at": expires_at}


@router.post("/tokens")
def create_token(body: TokenBody, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    name = body.name.strip()[:60]
    if not name:
        raise HTTPException(422, "Give the token a name, such as iPhone Shortcut.")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    conn.execute("INSERT INTO api_tokens (user_id, name, token_hash, created_at) VALUES (?,?,?,?)",
                 (auth.user_id, name, sha(token), db.now()))
    db.audit(conn, auth.user_id, "token.create", json.dumps({"name": name}))
    return {"token": token, "name": name}


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, auth: Auth = Depends(session_auth), conn=Depends(db.get_conn)):
    done = conn.execute(
        "UPDATE api_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
        (db.now(), token_id, auth.user_id),
    ).rowcount
    if not done:
        raise HTTPException(404, "Token not found.")
    db.audit(conn, auth.user_id, "token.revoke", None)
    return {"ok": True}


# ---------- people (admin) ----------

@admin_router.get("/users")
def list_users(auth: Auth = Depends(admin_auth), conn=Depends(db.get_conn)):
    rows = conn.execute(
        "SELECT u.id, u.name, u.role, u.disabled, u.created_at, "
        "(SELECT COUNT(*) FROM credentials c WHERE c.user_id=u.id) AS devices, "
        "(SELECT COUNT(*) FROM jobs j WHERE j.user_id=u.id) AS jobs "
        "FROM users u ORDER BY u.id"
    ).fetchall()
    return [{**dict(r), "disabled": bool(r["disabled"]), "me": r["id"] == auth.user_id} for r in rows]


@admin_router.post("/users/{user_id}/role")
def change_role(user_id: int, body: RoleBody, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    """Make a member an admin, or an admin a member. There is always at least one admin."""
    if auth.role != "admin":
        raise HTTPException(403, "Only an admin can do that.")
    if body.role not in ("member", "admin"):
        raise HTTPException(422, "Unknown choice.")
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, "Person not found.")
    if user["role"] == "admin" and body.role == "member":
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
        if admins <= 1:
            raise HTTPException(409, "There has to be at least one admin.")
    conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
    db.audit(conn, auth.user_id, "user.role", json.dumps({"user_id": user_id, "name": user["name"], "role": body.role}))
    return {"ok": True}


def _set_disabled(conn, auth: Auth, user_id: int, disabled: bool) -> dict:
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, "Person not found.")
    if disabled:
        if user["id"] == auth.user_id:
            raise HTTPException(409, "You can't turn off your own account.")
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
        if user["role"] == "admin" and admins <= 1:
            raise HTTPException(409, "The last admin can't be turned off.")
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.execute("UPDATE users SET disabled=? WHERE id=?", (int(disabled), user_id))
    db.audit(conn, auth.user_id, "user.disable" if disabled else "user.enable", json.dumps({"user_id": user_id}))
    return {"ok": True}


@admin_router.post("/users/{user_id}/disable")
def disable_user(user_id: int, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    if auth.role != "admin":
        raise HTTPException(403, "Only an admin can do that.")
    return _set_disabled(conn, auth, user_id, True)


@admin_router.post("/users/{user_id}/enable")
def enable_user(user_id: int, auth: Auth = Depends(fresh_auth), conn=Depends(db.get_conn)):
    if auth.role != "admin":
        raise HTTPException(403, "Only an admin can do that.")
    return _set_disabled(conn, auth, user_id, False)
