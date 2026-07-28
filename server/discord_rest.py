from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

DISCORD_API = "https://discord.com/api/v10"


class DiscordRestError(RuntimeError):
    pass


class DiscordRestClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("DISCORD_TOKEN")
        if not self.token:
            raise DiscordRestError("DISCORD_TOKEN is not configured")

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_API + path, data=data, method=method,
            headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json", "User-Agent": "ProBotumDashboard/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise DiscordRestError(f"Discord API {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise DiscordRestError(f"Discord API unreachable: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            raise DiscordRestError(f"Discord API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DiscordRestError(f"Discord API returned invalid JSON: {exc}") from exc

    def get_guild(self, guild_id: str, with_counts: bool = True) -> Dict[str, Any]:
        return self._request("GET", f"/guilds/{guild_id}{'?with_counts=true' if with_counts else ''}")

    def get_guild_channels(self, guild_id: str) -> List[Dict[str, Any]]:
        return self._request("GET", f"/guilds/{guild_id}/channels")

    def get_guild_roles(self, guild_id: str) -> List[Dict[str, Any]]:
        return self._request("GET", f"/guilds/{guild_id}/roles")

    def get_guild_member(self, guild_id: str, user_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/guilds/{guild_id}/members/{user_id}")

    def search_guild_members(self, guild_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self._request("GET", f"/guilds/{guild_id}/members/search?query={urllib.parse.quote(query)}&limit={limit}")

    def create_dm_channel(self, user_id: str) -> Dict[str, Any]:
        return self._request("POST", "/users/@me/channels", {"recipient_id": user_id})

    def send_dm(self, user_id: str, content: str) -> Dict[str, Any]:
        channel = self.create_dm_channel(user_id)
        return self._request("POST", f"/channels/{channel['id']}/messages", {"content": content})

    def create_category(self, guild_id: str, name: str) -> Dict[str, Any]:
        return self._request("POST", f"/guilds/{guild_id}/channels", {"name": name, "type": 4})

    def create_text_channel(self, guild_id: str, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name, "type": 0}
        if parent_id:
            payload["parent_id"] = parent_id
        return self._request("POST", f"/guilds/{guild_id}/channels", payload)
