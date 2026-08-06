"""
AutoRole Join — применяет автоматические роли из настроек панели.

Роли, сохранённые из панели (страница /autorole) в data/autorole_{gid}.json,
теперь действительно выдаются:
  • member_roles → каждому новому участнику
  • bot_roles    → каждому боту, зашедшему на сервер

(girl_roles / boy_roles — пол автоматически определить нельзя,
поэтому к боту не привязаны; хранятся в панели для справки.)
"""
import json
from discord.ext import commands

from logger import get_logger

log = get_logger("autorole_join")


def _cfg_path(guild_id: int) -> str:
    return f'data/autorole_{guild_id}.json'


class AutoRoleJoin(commands.Cog):
    """Вступившим выдаёт роли из настроек панели (/autorole)."""

    def __init__(self, bot):
        self.bot = bot

    def _roles_for(self, guild_id: int, is_bot: bool) -> list:
        try:
            with open(_cfg_path(guild_id), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return []
        key = 'bot_roles' if is_bot else 'member_roles'
        return [str(x) for x in (data.get(key) or []) if str(x).isdigit()]

    @commands.Cog.listener()
    async def on_member_join(self, member):
        role_ids = self._roles_for(member.guild.id, member.bot)
        if not role_ids:
            return
        given, failed = [], []
        for rid in role_ids:
            role = member.guild.get_role(int(rid))
            if role is None:
                continue
            try:
                await member.add_roles(role, reason="[AutoRole] роль при входе (настройки панели)")
                given.append(role.name)
            except Exception as e:
                failed.append(role.name)
                log.warning(f"[AUTOROLE] {member.guild.name}: не выдал {role.name} → {member}: {e}")
        if given:
            log.info(f"[AUTOROLE] {member.guild.name}: {member} получил {', '.join(given)}"
                     + (f" | не удалось: {', '.join(failed)}" if failed else ""))


async def setup(bot):
    await bot.add_cog(AutoRoleJoin(bot))
    log.info("[AUTOROLE] Ког загружен")
