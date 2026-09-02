"""Регресс: мут не должен оставлять ДВА ограничения на участнике.

Нативный таймаут Discord глушит и чат, и голос одним состоянием; роль
войс-мута — только микрофон. Перед наложением любого мута противоположное
состояние снимается через services.mute_state.
"""
import asyncio
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MAIN_GUILD_ID", "777")
os.environ.setdefault("SECRET_KEY", "test")

_TMP = tempfile.mkdtemp()
os.chdir(_TMP)
os.makedirs("data", exist_ok=True)
with open("data/punish_roles.json", "w", encoding="utf-8") as _f:
    json.dump({"777": {"roles": {"mute": 101, "vmute": 102, "ban": 0}}}, _f)

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"PASS  {name}")
    else:
        _failed += 1
        print(f"FAIL  {name}")


class Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.members = []
        self.mention = f"<@&{rid}>"


class Voice:
    def __init__(self):
        self.channel = object()
        self.mute = True


class Member:
    def __init__(self, uid):
        self.id = uid
        self.name = f"u{uid}"
        self.display_name = f"User{uid}"
        self.global_name = f"User{uid}"
        self.roles = [Role(5, "@everyone")]
        self.bot = False
        self.voice = Voice()
        self.timed_out_until = None
        self.edits = []

    async def edit(self, **kw):
        self.edits.append(kw)
        if "mute" in kw:
            self.voice.mute = kw["mute"]

    async def timeout(self, until, reason=None):
        self.timed_out_until = until
        self.edits.append({"timeout": until})

    async def remove_roles(self, *roles, **kw):
        ids = {getattr(r, "id", r) for r in roles}
        self.roles = [r for r in self.roles if r.id not in ids]


class Guild:
    def __init__(self):
        self.id = 777
        self.name = "T"
        self.roles = [Role(101, "Мут"), Role(102, "ВойсМут")]

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)


async def main():
    from services import mute_state, punish_roles as PR

    check("роли наказаний читаются",
          PR.role_for(777, "mute") == 101 and PR.role_for(777, "vmute") == 102)

    g = Guild()

    # 1. Висит войс-мут (роль 102 + server-mute). Даём таймаут → чистим голос.
    u = Member(500)
    u.roles.append(g.get_role(102))
    await mute_state.clear_voice_mute(g, u)
    check("clear_voice_mute снял роль войс-мута",
          not any(r.id == 102 for r in u.roles))
    check("clear_voice_mute снял нативный server-mute",
          any(e.get("mute") is False for e in u.edits))

    # 2. Висит нативный таймаут (+чат-мут роль). Даём войс-мут → чистим чат.
    u2 = Member(501)
    u2.roles.append(g.get_role(101))
    u2.timed_out_until = datetime.datetime.now(datetime.timezone.utc)
    await mute_state.clear_chat_mute(g, u2)
    check("clear_chat_mute снял роль чат-мута",
          not any(r.id == 101 for r in u2.roles))
    check("clear_chat_mute сбросил нативный таймаут",
          any(e.get("timeout") is None for e in u2.edits))

    # 3. clear_all_mutes снимает оба состояния сразу.
    u3 = Member(502)
    u3.roles.append(g.get_role(101))
    u3.roles.append(g.get_role(102))
    u3.timed_out_until = datetime.datetime.now(datetime.timezone.utc)
    await mute_state.clear_all_mutes(g, u3)
    check("clear_all_mutes не оставил ни мут-ролей, ни таймаута",
          not any(r.id in (101, 102) for r in u3.roles)
          and any(e.get("timeout") is None for e in u3.edits)
          and any(e.get("mute") is False for e in u3.edits))

    # 4. У участника без мута вызовы безопасны (нет исключений).
    u4 = Member(503)
    u4.voice.mute = False
    try:
        await mute_state.clear_voice_mute(g, u4)
        await mute_state.clear_chat_mute(g, u4)
        await mute_state.clear_all_mutes(g, u4)
        check("хелперы безопасны без активного мута", True)
    except Exception as e:
        check(f"хелперы безопасны без активного мута ({e})", False)

    print(f"[helpers] PASS {_passed} / FAIL {_failed}")


asyncio.run(main())


# ═══ Регресс через панель: timeout глушит чат+войс нативно, mute_chat — ролью ═══
class PRole:
    def __init__(self, rid, name):
        self.id = rid; self.name = name; self.mention = f"<@&{rid}>"

class PMember:
    def __init__(self, uid):
        self.id = uid; self.name = "BadGuy"; self.display_name = "BadGuy"
        self.global_name = "BadGuy"; self.bot = False
        self.roles = [PRole(5, "@everyone")]
        _perms = type("P", (), {})
        for a in ("administrator","manage_guild","manage_messages","moderate_members",
                  "ban_members","kick_members","mute_members","deafen_members","manage_roles"):
            setattr(_perms, a, False)
        self.guild_permissions = _perms
        self.top_role = PRole(9, "x")
        self.voice = type("V", (), {"channel": None, "mute": False})()
        self.display_avatar = type("A", (), {"url": "http://x/a.png"})()
        self.timed_out_until = None
        self.added = []; self.edits = []
    def __str__(s): return "BadGuy"
    async def timeout(s, until, reason=None):
        s.timed_out_until = until
    async def edit(s, **kw): s.edits.append(kw)
    async def add_roles(s, *r, **k):
        for x in r: s.added.append(x.id)
    async def remove_roles(s, *r, **k):
        ids = {getattr(x, "id", x) for x in r}
        s.roles = [x for x in s.roles if x.id not in ids]
    async def send(s, embed=None, **k): pass

class PGuild:
    def __init__(s):
        s.id = 777; s.name = "T"; s.icon = None; s.owner_id = 1
        s.channels = []; s.text_channels = []; s.roles = []
        s.members = []
        me = PMember(999999)
        _bp = type("P", (), {})
        for a in ("administrator","manage_roles","moderate_members","mute_members"):
            setattr(_bp, a, True)
        me.guild_permissions = _bp
        me.top_role = PRole(999, "BotTop")
        s.me = me
    def get_role(s, rid): return next((r for r in s.roles if r.id == rid), None)
    def get_member(s, uid): return next((m for m in s.members if m.id == uid), None)

class PBot:
    def __init__(s, g): s.guilds = [g]
    def get_guild(s, gid): return s.guilds[0]
    def get_cog(s, n): return None
    def fetch_user(s, uid): return None


async def panel_checks():
    import cogs.moderation as M

    # A. Мут-роль НЕ выбрана: timeout должен быть нативным (чат+войс),
    #    а mute_chat — честный отказ (нельзя заглушить «только чат» без роли).
    g = PGuild()
    member = PMember(111000000000000900)
    member.guild = g
    g.members = [member]
    cog = M.Moderation.__new__(M.Moderation)
    cog.bot = PBot(g)
    ok, text = await cog.apply_panel_action(g, member, "timeout", reason="x", amount="2ч", actor="Ivan")
    check("A. timeout без роли → нативный member.timeout()",
          ok and member.timed_out_until is not None)
    check("A. timeout без роли НЕ вешает мут-роль (чат+войс одним состоянием)",
          member.added == [])

    ok2, text2 = await cog.apply_panel_action(g, member, "mute_chat", reason="x", amount="10", actor="Ivan")
    check("A. mute_chat без роли → внятный отказ (а не таймаут «типа только чат»)",
          (not ok2) and ("роль" in text2))

    # B. Роли ВЫБРАНЫ: timeout — нативный (глушит и голос) И, по заказу
    #    владельца, ДОПОЛНИТЕЛЬНО выдаёт сразу обе роли — мут чата (101)
    #    и мут войса (102). mute_chat выдаёт роль чата и НЕ трогает голос.
    g2 = PGuild()
    g2.roles = [PRole(101, "Мут"), PRole(102, "Войс-мут")]
    import services.punish_roles as PR2
    PR2.set_roles(777, mute=101, vmute=102)
    m2 = PMember(111000000000000901); m2.guild = g2
    g2.members = [m2]
    cog2 = M.Moderation.__new__(M.Moderation)
    cog2.bot = PBot(g2)
    ok3, _ = await cog2.apply_panel_action(g2, m2, "timeout", reason="x", amount="1ч", actor="Ivan")
    check("B. timeout нативный (глушит голос) И выдаёт обе роли — чат 101 + войс 102",
          ok3 and m2.timed_out_until is not None and 101 in m2.added and 102 in m2.added)

    m3 = PMember(111000000000000902); m3.guild = g2
    g2.members = [m3]
    cog3 = M.Moderation.__new__(M.Moderation)
    cog3.bot = PBot(g2)
    ok4, _ = await cog3.apply_panel_action(g2, m3, "mute_chat", reason="x", amount="10", actor="Ivan")
    check("B. mute_chat выдаёт мут-роль и НЕ ставит нативный таймаут (голос живёт)",
          ok4 and 101 in m3.added and m3.timed_out_until is None)


asyncio.run(panel_checks())

print(f"\n=== PASS {_passed} / FAIL {_failed} ===")
sys.exit(1 if _failed else 0)
