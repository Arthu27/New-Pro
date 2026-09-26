# -*- coding: utf-8 -*-
"""Форс-применение role_seed v6 + helper_acl v4 на боевой гильдии.

Запуск на VPS (из корня репо, с заполненным MAIN_GUILD_ID в .env):

  python3 scripts/apply_staff_seeds.py
  python3 scripts/apply_staff_seeds.py --force   # игнор маркеров
  python3 scripts/apply_staff_seeds.py --guild 793336829280780331

После мержа PR #62 достаточно рестарта бота (on_ready сам сеет).
Этот скрипт — если нужно применить без рестарта / поверх старых маркеров.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _load_dotenv():
    path = os.path.join(ROOT, '.env')
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def main():
    _load_dotenv()
    ap = argparse.ArgumentParser(description='Apply staff role/ACL seeds')
    ap.add_argument('--force', action='store_true',
                    help='Ignore version markers (re-apply)')
    ap.add_argument('--guild', type=int, default=0,
                    help='Guild id (default: MAIN_GUILD_ID from .env)')
    args = ap.parse_args()

    gid = int(args.guild or 0)
    if not gid:
        try:
            from config import Config
            gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
        except Exception:
            gid = 0
    if not gid:
        print('FAIL: нет MAIN_GUILD_ID / --guild')
        return 2

    from services.role_seed import apply_role_seed, ensure_known_helper_tier
    from services.helper_acl_seed import apply_helper_acl_seed, ensure_helper_acl

    print(f'guild={gid} force={args.force}')
    ensure_known_helper_tier()
    r1 = apply_role_seed(force=args.force, guild_id=gid)
    print('role_seed:', json.dumps(r1, ensure_ascii=False))
    r2 = apply_helper_acl_seed(force=args.force, guild_id=gid)
    print('helper_acl:', json.dumps(r2, ensure_ascii=False))
    if not args.force:
        r3 = ensure_helper_acl(guild_id=gid)
        print('ensure_acl:', json.dumps(r3, ensure_ascii=False))

    rm = {}
    try:
        with open('data/role_map.json', encoding='utf-8') as fh:
            rm = json.load(fh) or {}
    except (OSError, ValueError):
        pass
    hid = '948969471916249119'
    mid = '803553848396349510'
    print(f'role_map helper={rm.get(hid)!r} mod={rm.get(mid)!r}')

    from services.permission_acl import load_action_acl
    acl = load_action_acl(gid)
    for act in ('mute', 'purge', 'warn', 'ban', 'vmute', 'timeout'):
        roles = [str(x) for x in (acl.get(act) or [])]
        print(f'  acl {act}: helper={"Y" if hid in roles else "n"} '
              f'mod={"Y" if mid in roles else "n"}')

    from services.staff_limits import effective_limits, tier_for_roles
    for label, rid in (('helper', int(hid)), ('mod', int(mid)),
                       ('master', 1552637932907667466),
                       ('curator', 807030012301541377),
                       ('admin', 1189999426631122964)):
        lim = effective_limits(gid, [rid])[0]
        print(f'  lim {label}/{tier_for_roles([rid])}: '
              f'warn={lim.get("warn")} mute={lim.get("mute")} '
              f'unmute={lim.get("unmute")} ban={lim.get("ban")}')

    ok = rm.get(hid) == 'helper' and hid in [
        str(x) for x in (acl.get('mute') or [])] and hid not in [
        str(x) for x in (acl.get('ban') or [])]
    print('OK' if ok else 'CHECK FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
