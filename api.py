from __future__ import annotations

import os
import random
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from server import db
from server.discord_rest import DiscordRestClient, DiscordRestError

load_dotenv()

GUILD_ID = os.getenv("GUILD_ID", "1524635551804686486")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")
ALLOW_LIVE = os.getenv("ALLOW_LIVE_DISCORD_ACTIONS", "false").lower() == "true"
DEV_USE_SNAPSHOT = os.getenv("DEV_USE_SNAPSHOT", "false").lower() == "true"

app = FastAPI(title="ProBotum API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def require_token(request: Request, authorization: Optional[str] = Header(default=None)) -> None:
    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost"}:
        return
    if not DASHBOARD_TOKEN:
        return
    if authorization != f"Bearer {DASHBOARD_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid dashboard token")


def guild_id_from_param(guild_id: str) -> str:
    return GUILD_ID if guild_id == "current" else guild_id


def _auth_token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    return authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else authorization.strip()


def _resolve_portal(member: Dict[str, Any]) -> str:
    try:
        if int(str(member.get("permissions", "0"))) & 0x8:
            return "admin"
    except ValueError:
        pass
    return "member"


def _display_name(member: Dict[str, Any]) -> str:
    user = member.get("user", {})
    return user.get("global_name") or user.get("username") or str(user.get("id", "unknown"))


def _snapshot_to_discord(member: Dict[str, Any]) -> Dict[str, Any]:
    return {"user": {"id": str(member.get("id")), "username": member.get("username") or str(member.get("id")), "global_name": member.get("global_name") or member.get("display_name"), "bot": bool(member.get("bot", False))}, "nick": member.get("display_name"), "roles": member.get("roles", [])}


def _find_snapshot_member(guild_id: str, identifier: str) -> Optional[Dict[str, Any]]:
    snapshot = db.get_guild_snapshot(guild_id)
    raw = identifier.strip().lstrip("@").lower()
    if not raw:
        return None
    for member in snapshot.get("members", []):
        values = [str(member.get("id", "")).lower(), str(member.get("username", "")).lower(), str(member.get("global_name", "")).lower(), str(member.get("display_name", "")).lower()]
        if raw in values or any(v and raw in v for v in values):
            return _snapshot_to_discord(member)
    return None


def _find_member(rest: DiscordRestClient, guild_id: str, identifier: str) -> Dict[str, Any]:
    raw = identifier.strip()
    normalized = raw[1:] if raw.startswith("@") else raw
    if normalized.isdigit() and 15 <= len(normalized) <= 22:
        return rest.get_guild_member(guild_id, normalized)
    results = rest.search_guild_members(guild_id, normalized, limit=10)
    if not results:
        raise HTTPException(status_code=404, detail="Member not found in guild")
    low = normalized.lower()
    for m in results:
        u = m.get("user", {})
        if str(u.get("username", "")).lower() == low or str(u.get("global_name", "")).lower() == low:
            return m
    return results[0]


@app.on_event("startup")
async def startup() -> None:
    db.init_db()


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "mode": "python-api", "guildId": GUILD_ID, "liveDiscordActions": ALLOW_LIVE}


@app.get("/api/auth/search-members")
async def search_members(query: str, guildId: str = "current") -> Dict[str, Any]:
    gid = guild_id_from_param(guildId)
    q = query.strip().lstrip("@")
    if not q:
        return {"ok": True, "guildId": gid, "members": []}

    def fmt(members: list) -> list:
        return [{"id": str(m.get("user", {}).get("id")), "username": m.get("user", {}).get("username"), "globalName": m.get("user", {}).get("global_name"), "displayName": m.get("nick") or m.get("user", {}).get("global_name") or m.get("user", {}).get("username") or str(m.get("user", {}).get("id")), "avatar": m.get("user", {}).get("avatar")} for m in members]

    if DEV_USE_SNAPSHOT:
        snapshot = db.get_guild_snapshot(gid)
        found = [_snapshot_to_discord(m) for m in snapshot.get("members", []) if q.lower() in str(m.get("username", "")).lower() or q.lower() in str(m.get("global_name", "")).lower() or q.lower() in str(m.get("display_name", "")).lower()]
        return {"ok": True, "guildId": gid, "members": fmt(found[:8]), "source": "snapshot"}

    try:
        rest = DiscordRestClient()
        members = [rest.get_guild_member(gid, q)] if q.isdigit() and 15 <= len(q) <= 22 else rest.search_guild_members(gid, q, limit=8)
        return {"ok": True, "guildId": gid, "members": fmt(members)}
    except DiscordRestError as exc:
        sm = _find_snapshot_member(gid, q)
        return {"ok": bool(sm), "guildId": gid, "members": fmt([sm] if sm else []), "warning": str(exc), "source": "snapshot"}


@app.post("/api/auth/request-code")
async def request_login_code(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    identifier = str(payload.get("identifier", "")).strip()
    gid = guild_id_from_param(str(payload.get("guildId", "current")))
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")

    member = _find_snapshot_member(gid, identifier) if DEV_USE_SNAPSHOT else _find_member(DiscordRestClient(), gid, identifier)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    user = member.get("user", {})
    user_id = str(user.get("id"))
    if not user_id or user_id == "None":
        raise HTTPException(status_code=404, detail="Member user id not found")
    if user.get("bot"):
        raise HTTPException(status_code=403, detail="Bot accounts cannot log in")

    portal = _resolve_portal(member)
    code = f"{random.randint(100000, 999999)}"
    username = _display_name(member)
    db.create_login_code(gid, user_id, username, code, db.now() + 5 * 60)

    dm_sent, dm_warning = True, None
    if DEV_USE_SNAPSHOT:
        dm_sent, dm_warning = False, "DEV_USE_SNAPSHOT=true"
    else:
        try:
            DiscordRestClient().send_dm(user_id, f"Your ProBotum code: {code}\nExpires in 5 minutes.")
        except DiscordRestError as exc:
            dm_sent, dm_warning = False, str(exc)

    resp: Dict[str, Any] = {"ok": True, "guildId": gid, "userId": user_id, "username": username, "portal": portal, "dmSent": dm_sent}
    if dm_warning:
        resp["warning"] = dm_warning
    if not dm_sent:
        resp["devCode"] = code
    return resp


@app.post("/api/auth/verify-code")
async def verify_login_code(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    gid = guild_id_from_param(str(payload.get("guildId", "current")))
    user_id = str(payload.get("userId", "")).strip()
    code = str(payload.get("code", "")).strip()
    username = str(payload.get("username", user_id)).strip() or user_id
    if not user_id or not code:
        raise HTTPException(status_code=400, detail="userId and code are required")
    if not db.verify_login_code(gid, user_id, code):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    portal = "member"
    try:
        member = DiscordRestClient().get_guild_member(gid, user_id)
        portal = _resolve_portal(member)
        username = _display_name(member)
    except Exception:
        pass

    token = db.create_auth_session(gid, user_id, username, portal)
    db.add_audit_log(gid, "dashboard_login", {"userId": user_id, "portal": portal}, user_id)
    return {"ok": True, "token": token, "user": {"id": user_id, "username": username, "portal": portal}}


@app.get("/api/auth/me")
async def auth_me(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _auth_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    session = db.get_auth_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {"ok": True, "user": {"id": session["user_id"], "username": session["username"], "portal": session["portal"]}, "guildId": session["guild_id"]}


@app.get("/api/guilds/{guild_id}/overview")
async def overview(guild_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    modules = db.get_all_modules(gid)
    logs = db.get_audit_logs(gid, limit=50)
    snapshot = db.get_guild_snapshot(gid)
    guild: Dict[str, Any] = {}
    channels_list = snapshot.get("channels", [])
    roles_list = snapshot.get("roles", [])
    warning = None

    if not DEV_USE_SNAPSHOT:
        try:
            rest = DiscordRestClient()
            guild = rest.get_guild(gid, with_counts=True)
            try: channels_list = rest.get_guild_channels(gid) or channels_list
            except: pass
            try: roles_list = [r for r in rest.get_guild_roles(gid) if r.get("name") != "@everyone"] or roles_list
            except: pass
        except DiscordRestError as exc:
            warning = str(exc)

    return {
        "guildId": gid, "mock": False,
        "guildName": guild.get("name") or snapshot.get("name"),
        "members": guild.get("approximate_member_count") or guild.get("member_count") or snapshot.get("member_count"),
        "online": guild.get("approximate_presence_count"),
        "channels": len(channels_list), "roles": len(roles_list),
        "channelsList": channels_list, "rolesList": roles_list,
        "modulesConfigured": len(modules), "auditEvents": len(logs),
        "backend": "online", "liveDiscordActions": ALLOW_LIVE,
        "snapshotUpdatedAt": snapshot.get("snapshotUpdatedAt"),
        "recentAudit": logs[:5], "warning": warning,
    }


@app.get("/api/guilds/{guild_id}/channels")
async def channels(guild_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    snapshot = db.get_guild_snapshot(gid)
    try:
        return {"guildId": gid, "channels": DiscordRestClient().get_guild_channels(gid)}
    except DiscordRestError as exc:
        return {"guildId": gid, "channels": snapshot.get("channels", []), "warning": str(exc), "source": "snapshot"}


@app.get("/api/guilds/{guild_id}/roles")
async def roles(guild_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    snapshot = db.get_guild_snapshot(gid)
    try:
        return {"guildId": gid, "roles": DiscordRestClient().get_guild_roles(gid)}
    except DiscordRestError as exc:
        return {"guildId": gid, "roles": snapshot.get("roles", []), "warning": str(exc), "source": "snapshot"}


@app.get("/api/guilds/{guild_id}/modules")
async def modules(guild_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    return {"guildId": guild_id_from_param(guild_id), "modules": db.get_all_modules(guild_id_from_param(guild_id))}


@app.get("/api/guilds/{guild_id}/modules/{module_id}")
async def module_config(guild_id: str, module_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    return {"guildId": gid, "moduleId": module_id, "config": db.get_module_config(gid, module_id)}


@app.put("/api/guilds/{guild_id}/modules/{module_id}")
async def save_module(guild_id: str, module_id: str, request: Request, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    payload = await request.json()
    db.set_module_config(gid, module_id, payload)
    db.add_audit_log(gid, "module_config_saved", {"moduleId": module_id, "config": payload})
    return {"ok": True, "guildId": gid, "moduleId": module_id}


@app.get("/api/guilds/{guild_id}/access-portals")
async def get_access_portals(guild_id: str, _: None = Depends(require_token)) -> Dict[str, Any]:
    return {"guildId": guild_id_from_param(guild_id), "config": db.get_access_portals(guild_id_from_param(guild_id))}


@app.put("/api/guilds/{guild_id}/access-portals")
async def put_access_portals(guild_id: str, request: Request, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    payload = await request.json()
    db.save_access_portals(gid, payload)
    db.add_audit_log(gid, "access_portals_saved", {"keys": list(payload.keys())})
    return {"ok": True, "guildId": gid, "config": payload}


@app.get("/api/guilds/{guild_id}/permissions")
async def get_permissions(guild_id: str, command: Optional[str] = None, _: None = Depends(require_token)) -> Dict[str, Any]:
    return {"guildId": guild_id_from_param(guild_id), "rules": db.get_permission_rules(guild_id_from_param(guild_id), command)}


@app.put("/api/guilds/{guild_id}/permissions")
async def put_permissions(guild_id: str, request: Request, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    payload = await request.json()
    for rule in payload.get("rules", []):
        db.set_permission_rule(gid, str(rule["command"]), str(rule["targetType"]), str(rule["targetId"]), str(rule.get("effect", "allow")), str(rule.get("visibility", "use")))
    db.add_audit_log(gid, "permissions_saved", {"count": len(payload.get("rules", []))})
    return {"ok": True, "saved": len(payload.get("rules", []))}


@app.get("/api/guilds/{guild_id}/logs")
async def audit_logs(guild_id: str, limit: int = 50, _: None = Depends(require_token)) -> Dict[str, Any]:
    return {"guildId": guild_id_from_param(guild_id), "logs": db.get_audit_logs(guild_id_from_param(guild_id), limit=limit)}


@app.post("/api/guilds/{guild_id}/actions/apply")
async def apply_action(guild_id: str, request: Request, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    payload = await request.json()
    db.add_audit_log(gid, "apply_action", payload)
    return {"ok": True, "guildId": gid, "mode": "live" if ALLOW_LIVE else "dry-run", "received": payload}


@app.post("/api/guilds/{guild_id}/actions/create-log-channels")
async def create_log_channels(guild_id: str, request: Request, _: None = Depends(require_token)) -> Dict[str, Any]:
    gid = guild_id_from_param(guild_id)
    payload = await request.json()
    category_name = payload.get("category", "📁 Logs")
    selected = [name for name, enabled in payload.get("channels", {}).items() if enabled]
    plan = {"category": category_name, "channels": selected, "roles": payload.get("roles", []), "mode": "live" if ALLOW_LIVE and payload.get("live") else "dry-run"}

    created: Dict[str, Any] = {}
    if plan["mode"] == "live":
        rest = DiscordRestClient()
        category = rest.create_category(gid, category_name)
        created["category"] = category
        created["channels"] = {}
        for key in selected:
            created["channels"][key] = rest.create_text_channel(gid, key if key.endswith("-logs") else f"{key}-logs", category.get("id"))
    else:
        created = {"dryRun": True, "plan": plan}

    db.save_log_channels(gid, {"plan": plan, "created": created})
    db.add_audit_log(gid, "create_log_channels", {"plan": plan, "created": created})
    return {"ok": True, "guildId": gid, "plan": plan, "created": created}
