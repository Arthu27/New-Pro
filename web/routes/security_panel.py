# -*- coding: utf-8 -*-
"""Центр безопасности (идеи #131-135): настройки антискама и песочница.

Хранилище одно на двоих с ботом: data/security_<gid>.json, его пишут
_load_cfg/_save_cfg из cogs/security.py — панель зовёт их же (дефолты
_CFG_DEFAULT не дублируем).

Настройки 1:1 с /security, /security-toggle, /security-newaccount:
три флага (ai_spam/fake_account/link_scanner), порог возраста и действие
для новых аккаунтов (warn|kick|ban).

Инструменты-песочницы зовут настоящие сканеры кога (передаём None вместо
self — методы его не трогают):
- _scan_links/_extract_domains + MALICIOUS_DOMAINS — проверка текста;
- _fake_account_score на синтетическом профиле — разбор, за что флагают;
- _ai_spam_score на живом shim с msg_history — симуляция очереди спама.

Чтение и инструменты — mod+ (scan-link у бота для moderate_members),
изменение настроек — admin+ (команды под administrator).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from cogs import security as SC

UTC = timezone.utc


def _gid_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


FEATURES = (
    ('ai_spam', 'AI-детект спама'),
    ('fake_account', 'Детект фейковых аккаунтов'),
    ('link_scanner', 'Сканер ссылок'),
)
ACTIONS = ('warn', 'kick', 'ban')
DAYS_MIN, DAYS_MAX = 1, 365



def protection_reset_all(gid):
    """Выключить ВСЮ защиту сервера (заказ владельца: всё opt-in, «включать будем сами»).
    Тушим только флаги — пороги, белые списки и история наказаний сохраняются.
    Работает и без бота: сторы защиты файловые (json/GuildData)."""
    import json as _json
    import os as _os

    flipped = []
    gid_i = int(gid)

    def _write_atomic(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            _json.dump(data, fh, ensure_ascii=False, indent=2)
        _os.replace(tmp, path)

    # 1) Центр безопасности (cogs/security.py): три флага
    try:
        cfg = SC._load_cfg(gid_i)
        for key, _t in FEATURES:
            cfg[key] = False
        SC._save_cfg(gid_i, cfg)
        flipped.append('security')
    except Exception as _ex:
        _log.debug('protection_reset_all(): security пропущен: %s', _ex)

    # 2) Анти-фейк/имперсонация (data/antifake.json {gid: cfg})
    try:
        path = 'data/antifake.json'
        data = {}
        if _os.path.exists(path):
            with open(path, encoding='utf-8') as fh:
                data = _json.load(fh)
            if not isinstance(data, dict):
                data = {}
        cur = data.get(str(gid_i)) or {}
        cur['enabled'] = False
        data[str(gid_i)] = cur
        _write_atomic(path, data)
        flipped.append('antifake')
    except Exception as _ex:
        _log.debug('protection_reset_all(): antifake пропущен: %s', _ex)

    # 3) Автофильтр (data/autofilter_<gid>.json): корень + все секции
    try:
        from cogs import auto_filter as AF
        cfg = AF.load_config(gid_i)
        cfg['enabled'] = False
        for sect in ('words', 'links', 'caps', 'flood'):
            if isinstance(cfg.get(sect), dict):
                cfg[sect]['enabled'] = False
        AF.save_config(gid_i, cfg)
        flipped.append('auto_filter')
    except Exception as _ex:
        _log.debug('protection_reset_all(): auto_filter пропущен: %s', _ex)

    # 4) Анти-альт (GuildData('anti_alt'), ключ settings)
    try:
        from db import GuildData as _GD
        from cogs import anti_alt as AA
        store = _GD('anti_alt')
        cfg = AA.merge_settings(store.get(gid_i, 'settings', {}) or {})
        cfg['enabled'] = False
        store.set(gid_i, 'settings', cfg)
        flipped.append('anti_alt')
    except Exception as _ex:
        _log.debug('protection_reset_all(): anti_alt пропущен: %s', _ex)

    # 5) Щит от нюка — data/guardian_<gid>.json (глобальный enabled)
    try:
        path = f'data/guardian_{gid_i}.json'
        if _os.path.exists(path):
            with open(path, encoding='utf-8') as fh:
                cfg = _json.load(fh)
        else:
            from cogs import guardian as GR
            cfg = GR.guardian_default()
        if isinstance(cfg, dict):
            cfg['enabled'] = False
            _write_atomic(path, cfg)
            flipped.append('guardian')
    except Exception as _ex:
        _log.debug('protection_reset_all(): guardian пропущен: %s', _ex)

    # 6) AI-модерация — data/ai_mod_config_<gid>.json (если уже писался)
    try:
        path = f'data/ai_mod_config_{gid_i}.json'
        if _os.path.exists(path):
            with open(path, encoding='utf-8') as fh:
                cfg = _json.load(fh)
            if isinstance(cfg, dict):
                cfg['enabled'] = False
                _write_atomic(path, cfg)
                flipped.append('ai_moderation')
    except Exception as _ex:
        _log.debug('protection_reset_all(): ai_moderation пропущен: %s', _ex)

    return flipped


# ── Контур защиты: соседние системы — статус и быстрый тумблер ───────────
def shield_statuses(gid):
    """Состояние всех систем щита одним списком (для карточек страницы)."""
    gid_i = _gid_int(gid)
    out = []

    # Анти-альт: свежие аккаунты при входе (настройки в GuildData)
    on = False  # opt-in: без сохранённой настройки щит на паузе
    try:
        from cogs import anti_alt as _aa
        from db import GuildData as _GD
        st = _GD('anti_alt').get(gid_i, 'settings', {}) or {}
        on = bool(_aa.merge_settings(st).get('enabled'))
    except Exception as _ex:
        _log.debug('shield anti_alt: %s', _ex)
    out.append({'key': 'anti_alt', 'label': 'Анти-альт', 'enabled': on,
                'href': '/automation', 'hint': 'ловит свежие аккаунты на входе'})

    # Антифейк: маски под администрацию (impersonation)
    on = False  # opt-in
    try:
        from cogs import impersonation as _im
        cfg = dict(_im.DEFAULT_CFG)
        raw = _im._load_json(_im.CFG_PATH, {})
        if isinstance(raw, dict):
            cfg.update(raw.get(str(gid_i), {}) or {})
        on = bool(cfg.get('enabled'))
    except Exception as _ex:
        _log.debug('shield antifake: %s', _ex)
    out.append({'key': 'antifake', 'label': 'Антифейк: маски под админов',
                'enabled': on, 'href': '/antifake',
                'hint': 'подделки ников и аватаров стаффа'})

    # ИИ-модерация чата (файл конфига на гильдию)
    on = False  # opt-in
    try:
        import json as _json
        import os as _os
        _p = f'data/ai_mod_config_{gid_i}.json'
        if _os.path.exists(_p):
            with open(_p, encoding='utf-8') as _f:
                on = bool((_json.load(_f) or {}).get('enabled', False))
    except Exception as _ex:
        _log.debug('shield ai_mod: %s', _ex)
    out.append({'key': 'ai_moderation', 'label': 'ИИ-модерация чата',
                'enabled': on, 'href': '/ai-moderation',
                'hint': 'токсичность и оскорбления в чате'})

    # Автофильтр: флуд/слова/ссылки/капс (модульные функции кога)
    on = False  # opt-in
    try:
        from cogs import auto_filter as _af
        on = bool(_af.load_config(gid_i).get('enabled'))
    except Exception as _ex:
        _log.debug('shield auto_filter: %s', _ex)
    out.append({'key': 'auto_filter', 'label': 'Автофильтр: спам и флуд',
                'enabled': on, 'href': '/autofilter',
                'hint': 'флуд, слова, ссылки, капс'})
    return out


def toggle_shield(gid, key, enabled):
    """Тумблер соседней системы щита. Возвращает (ок, ошибка)."""
    gid_i = _gid_int(gid)
    val = bool(enabled)
    try:
        if key == 'anti_alt':
            from cogs import anti_alt as _aa
            from db import GuildData as _GD
            db = _GD('anti_alt')
            st = _aa.merge_settings(db.get(gid_i, 'settings', {}) or {})
            st['enabled'] = val
            db.set(gid_i, 'settings', st)
            return True, ''
        if key == 'antifake':
            # Живой ког держит конфиг в памяти — пишем через него, если он
            # загружен; иначе правим файл (ког подхватит при старте).
            try:
                import web.app as _app
                cog = _app.bot_instance.get_cog('AntiFake') if _app.bot_instance else None
            except Exception as _ex:
                _log.debug('shield antifake bot: %s', _ex)
                cog = None
            if cog is not None:
                cog.set_cfg(gid_i, 'enabled', val)
            else:
                from cogs import impersonation as _im
                data = _im._load_json(_im.CFG_PATH, {})
                if not isinstance(data, dict):
                    data = {}
                data.setdefault(str(gid_i), {})['enabled'] = val
                _im._save_json(_im.CFG_PATH, data)
            return True, ''
        if key == 'ai_moderation':
            import json as _json
            import os as _os
            _p = f'data/ai_mod_config_{gid_i}.json'
            cfg = {}
            if _os.path.exists(_p):
                with open(_p, encoding='utf-8') as _f:
                    cfg = _json.load(_f) or {}
            cfg['enabled'] = val
            _os.makedirs('data', exist_ok=True)
            tmp = _p + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as _f:
                _json.dump(cfg, _f, ensure_ascii=False, indent=2)
            _os.replace(tmp, _p)
            return True, ''
        if key == 'auto_filter':
            from cogs import auto_filter as _af
            cfg = _af.load_config(gid_i)
            cfg['enabled'] = val
            _af.save_config(gid_i, cfg)
            return True, ''
    except Exception as _ex:
        return False, str(_ex)
    return False, 'Неизвестная система щита'


# ─────────────────────────────────────────────────────────────────────
# #131: настройки 1:1 с /security
# ─────────────────────────────────────────────────────────────────────
def _load(gid):
    return SC._load_cfg(str(gid))


def _save(gid, cfg):
    SC._save_cfg(str(gid), cfg)


def cfg_view(cfg):
    """Карточки состояния — поля и выкл/вкл как в эмбеде /security."""
    feats = []
    for key, label in FEATURES:
        on = bool(cfg.get(key))
        feats.append({'key': key, 'label': label, 'enabled': on,
                      'status': ' Активен' if on else ' Закрыт'})
    return {
        'features': feats,
        'new_account_days': cfg.get('new_account_days', 7),
        'new_account_action': cfg.get('new_account_action', 'warn'),
        'log_channel': cfg.get('log_channel'),
    }


# ─────────────────────────────────────────────────────────────────────
# #131-132: изменения 1:1 с toggle/newaccount
# ─────────────────────────────────────────────────────────────────────
def toggle_feature(gid, feature, enabled):
    """Переключатель: только те три ключа, что у команды в choices."""
    if feature not in {k for k, _ in FEATURES}:
        return False, 'Неизвестная функция безопасности', None
    cfg = _load(gid)
    cfg[feature] = bool(enabled)
    _save(gid, cfg)
    return True, '', {'feature': feature, 'enabled': bool(enabled),
                      'status': ' Активен' if enabled else ' Закрыт'}


def set_newaccount(gid, days, action):
    """Порог и действие, как /security-newaccount (действия — из choices)."""
    try:
        days_i = int(str(days).strip())
    except (TypeError, ValueError):
        return False, 'Порог — число дней', None
    if not DAYS_MIN <= days_i <= DAYS_MAX:
        return False, f'Порог: от {DAYS_MIN} до {DAYS_MAX} дней', None
    if action not in ACTIONS:
        return False, 'Действие: warn, kick или ban', None
    cfg = _load(gid)
    cfg['new_account_days'] = days_i
    cfg['new_account_action'] = action
    _save(gid, cfg)
    return True, '', {'message': f'Порог: {days_i} дн., действие: {action}'}


# ─────────────────────────────────────────────────────────────────────
# #133: сканер ссылок — /scan-link
# ─────────────────────────────────────────────────────────────────────
def scan_text(text):
    """Та же проверка доменов, что у /scan-link (метод кога, self не нужен)."""
    text = str(text or '')
    has_bad, bad_domains = SC.Security._scan_links(None, text)
    return {'malicious': has_bad, 'domains': bad_domains,
            'extracted': SC._extract_domains(text)}


# ─────────────────────────────────────────────────────────────────────
# #134: антискам-песочница
# ─────────────────────────────────────────────────────────────────────
class _FakeAvatar:
    def __init__(self, default=True):
        self._default = default
        self.url = ('https://cdn.discordapp.com/embed/avatars/0.png' if default
                    else 'https://cdn.discordapp.com/avatars/1/x.png')

    def is_animated(self):
        return not self._default


def fake_account_preview(age_days, name, cfg, avatar_default=True):
    """Разбор синтетического профиля настоящим _fake_account_score кога."""
    try:
        age = int(str(age_days).strip())
    except (TypeError, ValueError):
        return False, 'Возраст — число дней', None
    if not 0 <= age <= 3650:
        return False, 'Возраст: от 0 до 3650 дней', None
    member = SimpleNamespace(
        created_at=datetime.now(UTC) - timedelta(days=age),
        display_avatar=_FakeAvatar(default=avatar_default),
        name=str(name or ''),
        display_name=str(name or ''),
        discriminator='0001',
    )
    score, warnings = SC.Security._fake_account_score(None, member, cfg)
    return True, '', {'score': round(score, 2), 'warnings': warnings,
                      'suspicious_name': SC._is_suspicious_name(str(name or ''))}


class _SpamShim:
    """Минимальный self для _ai_spam_score: ему нужен только msg_history."""

    def __init__(self):
        self.msg_history = defaultdict(list)


def spam_simulate(content, times):
    """Очередь одинаковых отправок через настоящий _ai_spam_score.

    Каждый вызов = сообщение сейчас: ког сам растит скорость/повторы.
    """
    content = str(content or '')
    try:
        n = int(str(times).strip())
    except (TypeError, ValueError):
        return False, 'Сколько раз — число', None
    if not 1 <= n <= 12:
        return False, 'От 1 до 12 сообщений в симуляции', None
    shim = _SpamShim()
    trail = []
    for _ in range(n):
        score, reason = SC.Security._ai_spam_score(shim, 424242, content)
        trail.append({'score': round(score, 3), 'reason': reason})
    return True, '', {'trail': trail, 'final': trail[-1]}


# ─────────────────────────────────────────────────────────────────────
# #135: справочник правил и выгрузка
# ─────────────────────────────────────────────────────────────────────
def rules_reference():
    """Списки правил кога как есть — что именно ловит сканер."""
    return {
        'domains': sorted(SC.MALICIOUS_DOMAINS),
        'domains_total': len(SC.MALICIOUS_DOMAINS),
        'name_patterns': list(SC.SUSPICIOUS_NAME_PATTERNS),
        'patterns_total': len(SC.SUSPICIOUS_NAME_PATTERNS),
    }


def csv_rows(cfg):
    view = cfg_view(cfg)
    rows = [('section', 'key', 'value')]
    for feat in view['features']:
        rows.append(('feature', feat['key'], feat['status'].strip()))
    rows.append(('new_account', 'days', str(view['new_account_days'])))
    rows.append(('new_account', 'action', str(view['new_account_action'])))
    rows.append(('log_channel', 'channel_id', str(view['log_channel'] or '')))
    for domain in sorted(SC.MALICIOUS_DOMAINS):
        rows.append(('malicious_domain', 'domain', domain))
    for pattern in SC.SUSPICIOUS_NAME_PATTERNS:
        rows.append(('name_pattern', 'regex', pattern))
    return rows


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'mod_action', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('security: уведомление не ушло: %s', _ex)

    @app.route('/security')
    @login_required
    @role_required('mod')
    def security_page():
        return render_template('security.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/security-center/overview')
    @login_required
    @role_required('mod')
    def api_sec_overview(gid):
        # Сводка Щита (анти-нюк) — обзор виден всем модераторам;
        # сама настройка — только админам на странице /guardian.
        try:
            from web.routes.guardian import guardian_summary
            shield = guardian_summary(_gid_int(gid))
        except Exception as _ex:
            _log.debug('security: сводка Щита не собрана: %s', _ex)
            shield = None
        return jsonify({'success': True,
                        'cfg': cfg_view(_load(gid)),
                        'rules': rules_reference(),
                        'guardian': shield,
                        'shields': shield_statuses(gid),
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/security-center/toggle', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sec_toggle(gid):
        data = request.get_json(silent=True) or {}
        feat = data.get('feature')
        keys = {k for k, _ in FEATURES}
        if feat in keys:
            ok, err, payload = toggle_feature(gid, feat, data.get('enabled'))
        else:
            ok, err = toggle_shield(gid, feat, data.get('enabled'))
            payload = {'feature': feat, 'enabled': bool(data.get('enabled')),
                       'status': ' Активен' if data.get('enabled') else ' Закрыт'} if ok else None
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _notify(f"Безопасность: {payload['feature']} → {payload['status']}")
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/security-center/protection-reset', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sec_protection_reset(gid):
        # «Выключи все настройки — включать будем сами» (заказ владельца).
        flipped = protection_reset_all(_gid_int(gid))
        _notify('Безопасность: вся защита выключена (сброс до opt-in)')
        return jsonify({'success': True, 'flipped': flipped, 'count': len(flipped)})

    @app.route('/api/guild/<gid>/security-center/newaccount', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_sec_newaccount(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = set_newaccount(gid, data.get('days'), data.get('action'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _notify('Безопасность: порог новых аккаунтов обновлён')
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/security-center/scan', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_sec_scan(gid):
        data = request.get_json(silent=True) or {}
        text = str(data.get('text') or '').strip()
        if not text:
            return jsonify({'success': False, 'error': 'Пустой текст — нечего сканировать'}), 400
        return jsonify({'success': True, **scan_text(text)})

    @app.route('/api/guild/<gid>/security-center/fake-score', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_sec_fake(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = fake_account_preview(
            data.get('age_days'), data.get('name'), _load(gid),
            avatar_default=bool(data.get('avatar_default', True)))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/security-center/spam-sim', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_sec_spam(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = spam_simulate(data.get('content'), data.get('times'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/security-center/export.csv')
    @login_required
    @role_required('mod')
    def api_sec_export(gid):
        rows = csv_rows(_load(gid))
        body = '\ufeff' + '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=security_{gid}.csv')
        return resp
