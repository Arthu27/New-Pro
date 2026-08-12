# -*- coding: utf-8 -*-
"""Экономика (economy_cog) + левелинг (autorole_level + ОЖИВЛЁННЫЙ level_cog).

Запуск: python3 tests/test_economy_leveling.py
"""
import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_ecolevel_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


import discord  # noqa: E402,F401
from PIL import Image  # noqa: E402

import cogs.economy_cog as E  # noqa: E402
import cogs.autorole_level as A  # noqa: E402
import cogs.level_cog as L  # noqa: E402
from json_store import save_json  # noqa: E402

# ═══ 1. Экономика: инварианты каталога ══════════════════════════════════
print('== economy: каталог и дефолты ==')
check(len(E.ITEM_DETAILS) == 18, f'в каталоге 18 предметов ({len(E.ITEM_DETAILS)})')
bad_price = [k for k, d in E.ITEM_DETAILS.items()
             if not (isinstance(d.get('price'), int) and d['price'] > 0)]
check(not bad_price, f'у всех предметов цена — целое положительное ({bad_price or "ок"})')
bad_sell = [k for k, d in E.ITEM_DETAILS.items()
            if d.get('sell', 0) > d.get('price', 0)]
check(not bad_sell, f'продажа не дороже покупки ни у одного ({bad_sell or "ок"})')
bad_rarity = [k for k, d in E.ITEM_DETAILS.items()
              if d.get('rarity') not in E.RARITY_ORDER]
check(not bad_rarity, f'редкость каждого из RARITY_ORDER ({bad_rarity or "ок"})')
check(set(E.RARITY_ORDER) == set(E.RARITY_COLORS), 'RARITY_COLORS покрывает все редкости')
check(E._rarity_color('божественный') == 0x8E44AD, '_rarity_color: божественный = фиолет')
check(E._rarity_color('несуществующая') == 0x95A5A6, '_rarity_color: неизвестная = серый дефолт')
pets = {k: d for k, d in E.ITEM_DETAILS.items() if d.get('category') == 'питомцы'}
check(pets and all(d.get('pet_bonus', 0) > 0 for d in pets.values()),
      f'питомцев {len(pets)}, у всех pet_bonus > 0')
check(E.DEFAULT_DATA['balance'] == 100 and E.DEFAULT_DATA['vault'] == 0
      and E.DEFAULT_DATA['history'] == [], 'DEFAULT_DATA: старт 100 коинов, история пуста')

# ═══ 2. Экономика: миграция и история операций ══════════════════════════
print('== economy: миграция + _log_tx ==')


class _FakeEco:
    def __init__(self):
        self.saved = []

    def _save(self, uid, data):
        self.saved.append((uid, [x.copy() if isinstance(x, dict) else x
                                 for x in data.get('history', [])]))


old = {'balance': 5000, 'custom': 'keep'}
mig = E._EconomyExtra._migrate(_FakeEco(), 1, dict(old))
check(all(k in mig for k in E.DEFAULT_DATA), 'миграция дополняет все поля DEFAULT_DATA')
check(mig['balance'] == 5000 and mig['custom'] == 'keep', 'миграция не трогает существующие')

f = _FakeEco()
data = dict(E.DEFAULT_DATA)
for i in range(60):
    E._EconomyExtra._log_tx(f, 7, data, f'оп{i}', i)
check(len(data['history']) == 50, 'лог операций обрезается до 50 записей')
check(data['history'][-1]['label'] == 'оп59', 'последняя запись — самая свежая')
check(f.saved and f.saved[-1][0] == 7, 'log_tx сохраняет через _save верного юзера')

# ═══ 3. Экономика: карточки (headless PIL) ═══════════════════════════════
print('== economy: карточки ==')


class _FakeCogForCard:
    def _get(self, uid):
        return dict(E.DEFAULT_DATA, balance=77777, inventory=['fishing_rod'] if
                    'fishing_rod' in E.ITEM_DETAILS else [])


class _FakeMember:
    id = 42
    display_name = 'Тестер'


img = E.generate_economy_card(_FakeCogForCard(), _FakeMember(), 'shop')
check(isinstance(img, Image.Image) and img.width == 920, f'карточка магазина {img.size}')
img2 = E.generate_economy_card(_FakeCogForCard(), _FakeMember(), 'inventory')
check(isinstance(img2, Image.Image) and img2.height >= 520, 'карточка инвентаря собирается')
raw = E.generate_economy_bytes(_FakeCogForCard(), _FakeMember(), 'shop').getvalue()
check(raw[:4] == b'\x89PNG', 'economy bytes — валидный PNG')
img3 = E.generate_eco_card('Т', 'С', [('Поле', 'Значение')])
check(isinstance(img3, Image.Image), 'generate_eco_card: универсальная карточка')

# ═══ 4. Левелинг: формула ════════════════════════════════════════════════
print('== leveling: формула и её зеркало ==')
lvl_of = A.AutoRoleLevel._level_from_xp
check(lvl_of(0) == 0 and lvl_of(99) == 0, '0..99 XP → уровень 0')
check(lvl_of(100) == 1, '100 XP → уровень 1')
check(lvl_of(100 + 115) == 2, '215 XP → уровень 2 (×1.15)')
check(lvl_of(100 + 115 + 132) == 3, '347 XP → уровень 3')
consistent = all(lvl_of(L._xp_total_for_level(l)) == l for l in range(0, 61))
check(consistent, 'зеркало: _xp_total_for_level обратна _level_from_xp (ур. 0..60)')
l10 = L._progress_from_xp(L._xp_total_for_level(10))
check(l10[0] == 10 and l10[1] == 0 and l10[2] > 0, 'progress на границе: (10, 0, need>0)')
cur = L._progress_from_xp(L._xp_total_for_level(10) + 5)
check(cur[0] == 10 and cur[1] == 5, 'progress внутри уровня: (10, 5, need)')

# ═══ 5. level_cog — живые команды (была заглушка!) ══════════════════════
print('== level_cog: команды на живых данных ==')

GUILD_ID = 31337
save_json(f'data/xp_{GUILD_ID}.json', {
    '10': {'xp': L._xp_total_for_level(12) + 3, 'level': 12},   # герой теста
    '11': {'xp': L._xp_total_for_level(30), 'level': 30},
    '12': {'xp': 50, 'level': 0},
})
save_json(f'data/level_roles_{GUILD_ID}.json', {'5': '501', '20': '502'})


class _Member:
    def __init__(self, uid, name):
        self.id = uid
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.display_avatar = type('A', (), {'url': 'http://x/a.png'})()


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Guild:
    id = GUILD_ID
    name = 'Тест-ленд'

    def __init__(self):
        self._members = {10: _Member(10, 'Герой'), 11: _Member(11, 'Легенда'),
                         12: _Member(12, 'Новичок')}
        self._roles = {501: _Role(501, 'Гуляка'), 502: _Role(502, 'Старейшина')}

    def get_member(self, uid):
        return self._members.get(uid)

    def get_role(self, rid):
        return self._roles.get(rid)


class _Ctx:
    def __init__(self):
        self.guild = _Guild()
        self.author = self.guild.get_member(10)
        self.sent = []

    async def send(self, content=None, embed=None, **kw):
        self.sent.append((content, embed))


cog = L.LevelCog(bot=None)
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def run(coro):
    return _loop.run_until_complete(coro)


ctx = _Ctx()
run(L.LevelCog.rank.callback(cog, ctx, None))
emb = ctx.sent[-1][1]
check(emb is not None and 'Герой' in emb.title, 'rank: карточка с именем участника')
fields = {f.name: f.value for f in emb.fields}
check(fields.get('Уровень') == '**12**', 'rank: уровень 12 из xp')
check(fields.get('Рейтинг') == '#2 из 3', 'rank: место #2 из 3 по xp')
check('Прогресс' in fields and '%' in fields['Прогресс'], 'rank: прогресс-бар присутствует')

ctx = _Ctx()
run(L.LevelCog.leaderboard.callback(cog, ctx))
emb = ctx.sent[-1][1]
lines = (emb.description or '').split('\n')
check(len(lines) == 3, 'leaderboard: все 3 участника в топе')
check('Легенда' in lines[0] and '🥇' in lines[0], 'leaderboard: 30-й уровень первый с 🥇')
check('ур. **30**' in lines[0], 'leaderboard: уровень из xp, не константа')
check('участников в рейтинге: 3' in (emb.footer.text or ''), 'leaderboard: футер со счётчиком')

save_json(f'data/xp_{GUILD_ID}.json', {})  # пустой рейтинг
ctx = _Ctx()
run(L.LevelCog.leaderboard.callback(cog, ctx))
check('Пока пусто' in (ctx.sent[-1][1].description or ''), 'leaderboard: честное «пусто»')
save_json(f'data/xp_{GUILD_ID}.json', {'11': {'xp': L._xp_total_for_level(30), 'level': 30}})

ctx = _Ctx()
run(L.LevelCog.rewards.callback(cog, ctx))
desc = ctx.sent[-1][1].description or ''
check('Гуляка' in desc and 'Старейшина' in desc, 'rewards: настоящие роли из файла')
check(desc.index('Уровень **5**') < desc.index('Уровень **20**'), 'rewards: сорт по уровню')

save_json(f'data/level_roles_{GUILD_ID}.json', {})
ctx = _Ctx()
run(L.LevelCog.rewards.callback(cog, ctx))
check('не настроены' in (ctx.sent[-1][1].description or ''), 'rewards: честное «не настроены»')
save_json(f'data/level_roles_{GUILD_ID}.json', {'5': '501', '20': '502'})

ctx = _Ctx()
run(L.LevelCog.setlevel.callback(cog, ctx, ctx.guild.get_member(12), 7))
from json_store import load_json as _jsl  # noqa: E402
rec = _jsl(f'data/xp_{GUILD_ID}.json', {})['12']
check(rec['level'] == 7 and rec['xp'] == L._xp_total_for_level(7),
      'setlevel: пишет суммарный XP по формуле (ур.7)')
check(lvl_of(rec['xp']) == 7, 'setlevel: записанный XP согласован с _level_from_xp')
ctx = _Ctx()
run(L.LevelCog.setlevel.callback(cog, ctx, ctx.guild.get_member(12), 5000))
check(ctx.sent[-1][0] and '0 до 1000' in ctx.sent[-1][0], 'setlevel: кап уровня 1000')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
