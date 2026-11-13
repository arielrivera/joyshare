"""Things that belong to the signed-in person: their connected accounts (cookie files).

Passkey sign-in only, never access tokens. Nothing here ever returns a cookie file's contents.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, cookies, db, platforms, settings

router = APIRouter(prefix="/api/account")


class CookieBody(BaseModel):
    text: str


def _platform(conn, name: str) -> str:
    if name not in platforms.PLATFORMS or name not in settings.get(conn, "platforms"):
        raise HTTPException(404, "Unknown platform.")
    return name


@router.get("/cookies")
def list_connected(who: auth.Auth = Depends(auth.session_auth), conn=Depends(db.get_conn)):
    return cookies.status_list(conn, who.user_id, settings.get(conn, "platforms"))


@router.put("/cookies/{platform}")
def connect(platform: str, body: CookieBody, who: auth.Auth = Depends(auth.session_auth), conn=Depends(db.get_conn)):
    platform = _platform(conn, platform)
    try:
        count = cookies.save(conn, who.user_id, platform, body.text)
    except cookies.CookieError as exc:
        raise HTTPException(422, exc.args[0]) from exc
    return {"ok": True, "cookie_count": count}


@router.delete("/cookies/{platform}")
def disconnect(platform: str, who: auth.Auth = Depends(auth.session_auth), conn=Depends(db.get_conn)):
    if not cookies.remove(conn, who.user_id, _platform(conn, platform)):
        raise HTTPException(404, "That account isn't connected.")
    return {"ok": True}
