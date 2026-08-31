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

    print(f"\n=== PASS {_passed} / FAIL {_failed} ===")
    sys.exit(1 if _failed else 0)


asyncio.run(main())
