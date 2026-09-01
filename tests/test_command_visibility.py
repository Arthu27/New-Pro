# -*- coding: utf-8 -*-
"""Видимость боевых слеш-команд в Discord (заказ владельца 2026-09-01).

Правила:
• /verify-setup — настройка системы верификации: обычные участники НЕ
  видят команду в подсказке «/» (default_member_permissions=administrator),
  в рантайме тоже только админ.
• /report-setup, /report-settings — админская настройка репортов: то же.
• /modpanel — панель модерации: по умолчанию Discord прячет её от обычных
  участников (default_member_permissions=moderate_members); видят только
  роли с правом «Модерация участников». Владелец открывает команду нужным
  ролям БЕЗ выдачи полного права: Настройки сервера → Интеграции → Hakumo
  → /modpanel. Второй уровень — панель (Доступ → Права команд): ролевой
  ACL решает, кто из видящих реально вызывает команду и какие действия
  (бан/мут/варн) ему доступны. Жёсткого рантайм checks.has_permissions на
  команде НЕТ — его нельзя переопределить ни панелью, ни Интеграциями.
• /update — только владелец и только в ЛС бота (DM context + administrator).
• /апелляция — подаётся в ЛС боту: на сервере команда в подсказке НЕ
  показывается (allowed_contexts guilds=False).

Проверяем ДЕКОРАТОРЫ реально зарегистрированных функций (то, что увидит
Discord при синке), а не исходный текст.
"""
import importlib
import inspect
import os
import shutil
import sys
import types
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _AnyMod(types.ModuleType):
    """Заглушка опциональных зависимостей — интроспекция когов без сети/диска."""
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        cls = type(name, (), {'__init__': lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


for _m in ['flask_session', 'gunicorn', 'nacl', 'psutil', 'duckduckgo_search',
           'edge_tts', 'faster_whisper', 'voice_recv', 'deep_translator',
           'colorama', 'requests', 'websockets', 'PIL', 'pyotp', 'qrcode']:
    try:
        if importlib.util.find_spec(_m) is None:
            sys.modules[_m] = _AnyMod(_m)
    except Exception:
        sys.modules[_m] = _AnyMod(_m)


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


def find_cog_callback(module_name, method_name):
    """Декорированная слеш-команда внутри класса-кога.

    После @app_commands.command атрибут класса — объект Command (не callable);
    атрибуты видимости (default_permissions, allowed_contexts) лежат прямо на
    нём, а исполняющая функция — в .callback.
    """
    mod = importlib.import_module(module_name)
    for attr in dir(mod):
        cls = getattr(mod, attr)
        if inspect.isclass(cls) and getattr(cls, '__cog_name__', None):
            obj = getattr(cls, method_name, None)
            if obj is not None and hasattr(obj, 'name'):
                return obj
    return None


def perms_of(fn):
    p = getattr(fn, 'default_permissions', None)
    v = getattr(p, 'value', p)
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def contexts_of(fn):
    ctx = getattr(fn, 'allowed_contexts', None)
    if ctx is None:
        return None
    return {'guild': bool(getattr(ctx, 'guild', False)),
            'dm': bool(getattr(ctx, 'dm_channel', False))}


ADMINISTRATOR = 1 << 3                   # бит administrator в Discord
MODERATE_MEMBERS = 1 << 40               # бит moderate_members

# ── Сетап-команды удалены из Discord: настройка — только через панель ──
print('== Сетап-команды убраны из Discord (настройка в панели) ==')
for modname, meth, label in (
    ('cogs.age_verification', 'verify_setup', '/verify-setup'),
    ('cogs.reports', 'report_setup_slash', '/report-setup'),
    ('cogs.reports', 'report_settings_slash', '/report-settings'),
    ('cogs.afk', 'afk_remove', '/afk-remove'),
):
    fn = find_cog_callback(modname, meth)
    check(fn is None, f'{label}: слеш-команда не регистрируется (настройка в панели / AFK авто)')
try:
    import slash_budget
    for gone in ('verify-setup', 'report-setup', 'report-settings', 'afk-remove'):
        check(gone not in slash_budget.KEEP_SLASH,
              f'{gone} нет в белом списке меню')
except Exception as ex:
    check(False, f'KEEP_SLASH: {ex}')

# ── /modpanel: модерация, карточки по ACL ──────────────────────────────
print('== /modpanel: видимость и карточки ==')
fn = find_cog_callback('cogs.moderation', 'modpanel')
check(fn is not None, '/modpanel определён')
if fn:
    # Жёсткий дефолт Discord: /modpanel скрыта от обычных участников (видна
    # ролям с «Модерация участников»); владелец открывает её ролям через
    # Настройки сервера → Интеграции. Это настраиваемый уровень видимости.
    check(bool(perms_of(fn) & MODERATE_MEMBERS),
          '/modpanel: по умолчанию скрыта Discord (moderate_members) — открывается через Интеграции')
    # Рантайм checks.has_permissions запрещён намеренно: его не переопределить
    # ни панелью, ни Интеграциями (именно он ломал выданные роли).
    cb = getattr(fn, 'callback', fn)
    check(not any('has_permissions' in (getattr(d, '__qualname__', '') or '')
                  for d in getattr(cb, '__commands_checks__', [])),
          '/modpanel: без жёсткой checks.has_permissions (доступ рулит панель/Интеграции)')

# actions_for_member реально режет карточки по Action ACL (войс-мут без прав)
try:
    import config
    _tmp_db = os.path.abspath(os.path.join(
        os.environ.get('TMPDIR', '/tmp'), f'hakumo_vis_acl_{os.getpid()}.db'))
    config.Config.DB_PATH = _tmp_db
    from services.permission_acl import set_action_rule
    from cogs.moderation import actions_for_member, MODPANEL_ACTIONS

    class _Role:
        def __init__(self, rid):
            self.id = rid

    class _Perms:
        administrator = False

    class _Member:
        def __init__(self, uid, roles=()):
            self.id = uid
            self.roles = [_Role(r) for r in roles]
            self.guild_permissions = _Perms()
            self.bot = False

    class _Guild:
        id = 999001
        owner_id = 1  # не наш участник

    GID = _Guild.id
    member = _Member(4242, roles=[501])
    # Правило «Мут разрешён только роли 999» → у роли 501 права на мут нет.
    set_action_rule(GID, 'mute', [999])
    allowed = actions_for_member(_Guild(), member)
    actions = {a[0] for a in allowed}   # имена пунктов меню (value)
    check('mute_chat' not in actions and 'vmute' not in actions
          and 'vunmute' not in actions,
          '/modpanel: без права «Мут» карточки мута (чат/войс) и снятия не видны')
    check('ban' in actions and 'warn' in actions and 'clear' in actions,
          '/modpanel: невыданные действия не трогают остальные карточки')
    set_action_rule(GID, 'mute', [])   # вернуть как было
except Exception as ex:
    check(False, f'ACL карточек /modpanel: {ex}')

# ── /update: владелец + только ЛС ──────────────────────────────────────
print('== /update и /апелляция: контекст ЛС ==')
fn = find_cog_callback('cogs.diagnostics', 'update_cmd')
check(fn is not None, '/update определён')
if fn:
    ctx = contexts_of(fn)
    check(ctx is not None and not ctx['guild'] and ctx['dm'],
          '/update: вызывается только в ЛС (в меню сервера не показывается)')
    check(bool(perms_of(fn) & ADMINISTRATOR),
          '/update: по умолчанию скрыт от не-админов')

fn = find_cog_callback('cogs.appeals', 'cmd_appeal')
check(fn is not None, '/апелляция определена')
if fn:
    ctx = contexts_of(fn)
    check(ctx is not None and not ctx['guild'] and ctx['dm'],
          '/апелляция: на сервере в подсказке не видна, работает только в ЛС')

shutil_ok = True
try:
    import shutil
    os.remove(_tmp_db) if os.path.exists(_tmp_db) else None
except Exception:
    pass

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
