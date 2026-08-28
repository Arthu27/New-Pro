# -*- coding: utf-8 -*-
"""Инфо-база сервера (идеи #176-180): /server-info в браузере.

Хранилище и функции — те самые из cogs/server_info.py: _load_info/_save_info
(значит и json_store-кэш общий) и get_sunucu_context (текст для AI-чата).
Ключи файла не трогаем: 'о', 'правила', 'yetkili_olmak', 'приватные_данные'.

- Витрина 1:1 кнопке «Текущая информация»: поля срезаны [:500], приватные
  пары показаны первыми пятью и [:200] — ровно как эмбед бота; для
  редактора рядом лежат полные значения.
- Поля 1:1 модалкам ServerModal: strip + max_length 1000 (кламп как у
  TextInput), успех словами модалки без эмодзи/маркдауна («… сохранено!»);
  пустой текст панель снимает поле — модалка требует непустое, у панели
  стёртое поле просто исчезает из файла.
- Пары 1:1 OzelBilgiModal: заголовок [:50], содержимое [:500], успех
  «{заголовок} сохранено!»; удаление одиночной пары — панельное дополнение
  (в боте лишь общая очистка), файл тот же.
- «Очистить» 1:1 danger-кнопке: весь dict -> {}, текст словами кнопки.
- Превью контекста 1:1 get_sunucu_context — что реально уходит в AI-чат;
  пустая база отвечает словами бота «Информация еще не введена.».

Чтение — mod+ (кнопка просмотра в боте доступна всем); правки и очистка —
admin+ (кнопки бота требуют administrator).
"""
from web.routes._common import (
    render_template, session, request, jsonify,
)

from cogs.server_info import _load_info, _save_info, get_sunucu_context

FIELDS = {'about': ('о', 'Информация о сервере'),
          'rules': ('правила', 'Правила сервера'),
          'mod': ('yetkili_olmak', 'Как стать модератором')}
ERR_FIELD = 'Неизвестное поле'
ERR_KEY = 'Заголовок пустой'
ERR_VALUE = 'Содержимое пустое'
NOTE_EMPTY = 'Информация еще не введена.'  # слова бота, с «еще»
CARD_FIELD_LEN = 500   # срез поля в эмбеде «Текущая информация»
CARD_PAIR_LEN = 200    # срез значения пары в эмбеде
CARD_PAIRS_MAX = 5     # сколько пар показывает эмбед
FIELD_LEN = 1000       # max_length TextInput модалки поля
KEY_LEN = 50           # max_length заголовка пары
VALUE_LEN = 500        # max_length содержимого пары


def view(gid):
    """Витрина + редактор: карточные срезы как в эмбеде, полные — для форм."""
    info = _load_info(int(gid))
    fields = []
    for key, (store_key, title) in FIELDS.items():
        value = str(info.get(store_key, '') or '')
        fields.append({'key': key, 'title': title, 'value': value,
                       'card': value[:CARD_FIELD_LEN]})
    pairs = info.get('приватные_данные') or {}
    pair_list = [{'key': str(k), 'value': str(v),
                  'card': str(v)[:CARD_PAIR_LEN]}
                 for k, v in pairs.items()]
    context = get_sunucu_context(int(gid))
    return {'fields': fields,
            'pairs': pair_list,
            'card_pairs': pair_list[:CARD_PAIRS_MAX],
            'context': context,
            'empty': not info,
            'note': NOTE_EMPTY}


def save_field_flow(gid, field, text):
    """ServerModal 1:1: strip и потолок 1000; пусто — снять поле."""
    meta = FIELDS.get(str(field or ''))
    if not meta:
        return False, ERR_FIELD, None
    store_key, title = meta
    value = str(text or '').strip()[:FIELD_LEN]
    info = _load_info(int(gid))
    if value:
        info[store_key] = value
        message = f'{title} сохранено!'
    else:
        info.pop(store_key, None)
        message = f'{title} очищено.'
    _save_info(int(gid), info)
    return True, '', {'message': message, 'view': view(gid)}


def set_pair_flow(gid, key, value):
    """OzelBilgiModal 1:1: заголовок [:50], текст [:500], оба strip."""
    key = str(key or '').strip()[:KEY_LEN]
    if not key:
        return False, ERR_KEY, None
    value = str(value or '').strip()[:VALUE_LEN]
    if not value:
        return False, ERR_VALUE, None
    info = _load_info(int(gid))
    pairs = info.setdefault('приватные_данные', {})
    pairs[key] = value
    _save_info(int(gid), info)
    return True, '', {'message': f'{key} сохранено!', 'view': view(gid)}


def del_pair_flow(gid, key):
    """Панельное дополнение: убрать одну пару (в боте есть лишь «Очистить»)."""
    key = str(key or '').strip()
    info = _load_info(int(gid))
    pairs = info.get('приватные_данные') or {}
    if key not in pairs:
        return False, f'Пара «{key}» не найдена.', None
    del pairs[key]
    if not pairs:
        info.pop('приватные_данные', None)
    _save_info(int(gid), info)
    rest = len(pairs)
    return True, '', {'message': f'Пара «{key}» удалена. Осталось: {rest}.',
                      'view': view(gid)}


def clear_flow(gid):
    """Кнопка «Очистить» 1:1: весь dict -> {}."""
    _save_info(int(gid), {})
    return True, '', {'message': 'Вся информация о сервере очищена.',
                      'view': view(gid)}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/server-info')
    @login_required
    @role_required('mod')
    def server_info_page():
        return render_template('server_info.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/server-info/view')
    @login_required
    @role_required('mod')
    def api_si_view(gid):
        return jsonify({'success': True, 'view': view(gid),
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/server-info/field', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_si_field(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = save_field_flow(gid, data.get('field'),
                                           data.get('text'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/server-info/pair', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_si_pair(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = set_pair_flow(gid, data.get('key'),
                                         data.get('value'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/server-info/pair-delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_si_pair_delete(gid):
        ok, err, payload = del_pair_flow(
            gid, (request.get_json(silent=True) or {}).get('key'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/server-info/clear', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_si_clear(gid):
        ok, err, payload = clear_flow(gid)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})
