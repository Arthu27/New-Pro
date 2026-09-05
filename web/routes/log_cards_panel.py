# -*- coding: utf-8 -*-
"""Настройки карточек логов: включение, тема, акцент + живой предпросмотр.

Карточка рисуется ботом при отправке лога (cogs/logs.py:_safe_send читает
data/log_cards_<gid>.json через services/log_card.get_log_cards_cfg).
Здесь — только панельная сторона: прочитать/сохранить настройки и отдать
PNG-пример, чтобы владелец видел результат до того, как «поедет» в канал.

Чтение — mod+, запись — admin+ (как канал апелляций и редактор правил).
"""
from web.routes._common import (
    _safe_json_obj,
    _log, render_template, session, request, jsonify, Response,
)

from services import log_card as LC

# Живой пример для предпросмотра: выглядит как настоящая mod-карточка.
# Заказ владельца 2026-08-25: ИМЕНА вместо сырых ID — и в демо тоже.
PREVIEW_ROWS = (
    ('Пользователь', 'GhostBlade'),
    ('Модератор', 'Sonya'),
    ('Причина', 'Повторные провокации после предупреждения в #флудилка'),
    ('Срок', 'предупреждение 2 из 3'),
)
PREVIEW_BY_CAT = {
    'mod': PREVIEW_ROWS,
    'automod': PREVIEW_ROWS,
    'punish': PREVIEW_ROWS,
    'message': (('Автор', 'GhostBlade'), ('Канал', '#флудилка'),
                ('Текст', 'удалённое сообщение')),
    'member': (('Участник', 'GhostBlade'), ('Аккаунт', '3 года'),
               ('Всего участников', '1247')),
    'welcome': (('Участник', 'GhostBlade'), ('Аккаунт', '3 года'),
                ('Всего участников', '1247')),
    'voice': (('Участник', 'GhostBlade'), ('Канал', 'Общий голос'),
              ('Действие', 'зашёл')),
    'nick': (('Участник', 'GhostBlade'), ('Было', 'кип'), ('Стало', 'Кипарис')),
    'role': (('Роль', '@Модератор'), ('Действие', 'выдана'),
             ('Кому', 'GhostBlade')),
    'channel': (('Канал', '#флудилка'), ('Действие', 'создан'),
                ('Тип', 'текстовый')),
    'invite': (('Код', 'discord.gg/hakumo'), ('Создал', 'GhostBlade'),
               ('Канал', '#правила')),
}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/guild/<gid>/log-cards/settings', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_log_cards_settings_get(gid):
        cfg = LC.get_log_cards_cfg(gid)
        return jsonify({'success': True, 'cfg': cfg,
                        'themes': [{'id': t, 'label': LC.LOG_CARD_THEMES[t]['label']}
                                   for t in LC.LOG_CARD_THEME_ORDER],
                        'cats': [{'id': k, 'label': v.get('tag', '').split('· ')[-1].title()}
                                 for k, v in LC.CATEGORY_STYLES.items()]})

    @app.route('/api/guild/<gid>/log-cards/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_log_cards_settings_post(gid):
        cfg = LC.save_log_cards_cfg(gid, _safe_json_obj())
        _log.info('log-cards: %s обновил оформление на %s: %s',
                  session.get('username', '?'), gid, cfg)
        theme_lbl = LC.LOG_CARD_THEMES.get(cfg['theme'], {}).get('label', cfg['theme'])
        per_cat = len(cfg.get('theme_by_cat') or {})
        return jsonify({'success': True, 'cfg': cfg,
                        'message': f'Оформление сохранено: {theme_lbl}' +
                                   (' · свой акцент' if cfg['accent'] else '') +
                                   (' · свой фон-фото' if cfg.get('bg_url') else '') +
                                   (f' · образов по категориям: {per_cat}' if per_cat else '')})

    @app.route('/api/guild/<gid>/log-cards/preview.png')
    @login_required
    @role_required('mod')
    def api_log_cards_preview(gid):
        theme = request.args.get('theme')
        accent = request.args.get('accent')
        cat = str(request.args.get('cat') or 'mod')
        if cat not in LC.CATEGORY_STYLES:
            cat = 'mod'
        cfg = LC.get_log_cards_cfg(gid)
        # Свой фон-фото: из строки превью (не сохранённая) или из конфига.
        # Качаем без кэша — что видишь в превью, то и уедет в лог-канал.
        bg_url = (request.args.get('bg') or '').strip()
        if not bg_url:
            bg_url = ((cfg.get('bg_url_by_cat') or {}).get(cat)
                      or cfg.get('bg_url') or '')
        bg_bytes = None
        if bg_url:
            try:
                bg_bytes = LC.fetch_bg_direct(bg_url)
            except Exception as _ex:
                _log.debug('log-cards preview: фон %s', _ex)
        # «Разными образами»: в превью показываем реальный образ категории —
        # из theme_by_cat, если владелец задал, иначе общая тема.
        if not theme:
            theme = (cfg.get('theme_by_cat') or {}).get(cat) or cfg.get('theme')
        rows = PREVIEW_BY_CAT.get(cat) or PREVIEW_ROWS
        try:
            png = LC.render_log_card(
                cat, 'Пример: выдано предупреждение', rows,
                color=0xE2455A, cat_name=cat,
                guild_name='Hakumo Demo', time_str='20:41 UTC',
                theme=theme, accent=accent, fmt='png', bg_bytes=bg_bytes)
        except Exception as _ex:
            _log.debug('log-cards preview: %s', _ex)
            png = None
        if not png:
            return jsonify({'success': False,
                            'error': 'Не удалось отрисовать пример'}), 500
        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp
