"""Extra panel routes - pages"""
from flask import render_template, session, redirect, url_for, request, jsonify
import os, json
import discord
from datetime import datetime


def _load_ai_tickets(guild_id: int) -> dict:
    """AI ticket verilerini yukle"""
    path = f"data/ai_tickets_{guild_id}.json"
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _process_action(answer: str, bot, guild_id: str, session_obj) -> str:
    """AI cevabındaki <action> bloğunu işler, sonuç messageı döner."""
    import re as _re, asyncio as _asyncio, os as _os
    from datetime import datetime as _dt, timedelta as _td

    action_match = _re.search(r'<action>(.*?)</action>', answer, _re.DOTALL)
    if not action_match:
        return ''
    try:
        raw = action_match.group(1).strip()
        # Bozuk JSON'u clear
        raw = _re.sub(r'[\x00-\x1f]', ' ', raw)  # kontrole karakterleri
        action_data = json.loads(raw)
    except Exception:
        # JSON parse неудачно — action'ı yoksay
        return ''

    action_type = action_data.get('action', '').lower()
    _aliases = {
        'dm_message': 'dm', 'send_dm': 'dm', 'direct_message': 'dm',
        'chat_message': 'send_message', 'channel_message': 'send_message',
        'send_channel_message': 'send_message', 'warning': 'warn', 'mute': 'timeout',
    }
    action_type = _aliases.get(action_type, action_type)
    uid = str(action_data.get('user_id', ''))
    gid = str(guild_id)
    guild = bot.get_guild(int(guild_id)) if bot else None

    try:
        if action_type == 'warn':
            reason = action_data.get('reason', 'AI asistan warn')
            if not uid:
                return '❌ Пользователь ID bulunamadı'
            # AI asistan hiçbir vakit otomatik warn atamaz — sadece предложение sunar
            return f'⚠️ AI warn предложениеsi: {uid} usersına "{reason}" sebebiyle warn. Подтвердитьmak için /moderate командаunu kullan.'

        elif action_type == 'ban':
            reason = action_data.get('reason', 'AI ban')
            if not (guild and uid):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            if not member:
                return '❌ Участник serverda bulunamadı'
            # AI ban предложениеsi — otomatik uygulamaz
            return f'⚠️ AI ban предложениеsi: {member.display_name} ({uid}) — Причина: "{reason}". Подтвердитьmak için /moderate ban командаunu kullan.'
            return f'✅ Бан uygulandı (user_id: {uid})'

        elif action_type == 'kick':
            reason = action_data.get('reason', 'AI kick')
            if not (guild and uid):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            if not member:
                return '❌ Участник serverda bulunamadı'
            # AI kick предложениеsi — otomatik uygulamaz
            return f'⚠️ AI kick предложениеsi: {member.display_name} ({uid}) — Причина: "{action_data.get("reason", "AI kick")}". Подтвердитьmak için /moderate kick командаunu kullan.'

        elif action_type == 'dm':
            message = action_data.get('message', '')
            if not (bot and uid and message):
                return '❌ Пользователь ID veya message eksik'
            async def _send_dm():
                user = await bot.fetch_user(int(uid))
                await user.send(message)
            _asyncio.run_coroutine_threadsafe(_send_dm(), bot.loop).result(timeout=10)
            return f'✅ DM отправитьildi (user_id: {uid})'

        elif action_type == 'timeout':
            minutes = int(action_data.get('minutes', 10))
            reason = action_data.get('reason', 'AI timeout')
            if not (guild and uid):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            if not member:
                return '❌ Участник serverda bulunamadı'
            # AI timeout предложениеsi — otomatik uygulamaz
            return f'⚠️ AI timeout предложениеsi: {member.display_name} ({uid}) — {minutes} minutes, Причина: "{reason}". Подтвердитьmak için /moderate timeout командаunu kullan.'

        elif action_type == 'add_role':
            role_id = str(action_data.get('role_id', ''))
            if not (guild and uid and role_id):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            role = guild.get_role(int(role_id))
            if not (member and role):
                return '❌ Участник veya role bulunamadı'
            _asyncio.run_coroutine_threadsafe(member.add_roles(role), bot.loop).result(timeout=10)
            return f'✅ Role addndi: {role.name}'

        elif action_type == 'remove_role':
            role_id = str(action_data.get('role_id', ''))
            if not (guild and uid and role_id):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            role = guild.get_role(int(role_id))
            if not (member and role):
                return '❌ Участник veya role bulunamadı'
            _asyncio.run_coroutine_threadsafe(member.remove_roles(role), bot.loop).result(timeout=10)
            return f'✅ Role alındı: {role.name}'

        elif action_type == 'send_message':
            channel_id = str(action_data.get('channel_id', ''))
            message = action_data.get('message', '')
            if not (bot and channel_id and message):
                return '❌ Канал ID veya message eksik'
            channel = bot.get_channel(int(channel_id))
            if not channel:
                return '❌ Канал bulunamadı'
            _asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop).result(timeout=10)
            return f'✅ Сообщение отправитьildi → #{channel.name}'

        elif action_type == 'delete_message':
            channel_id = str(action_data.get('channel_id', ''))
            message_id = str(action_data.get('message_id', ''))
            if not (bot and channel_id and message_id):
                return '❌ Канал ID veya message ID eksik'
            async def _del_msg():
                ch = bot.get_channel(int(channel_id))
                if not ch:
                    return '❌ Канал bulunamadı'
                msg = await ch.fetch_message(int(message_id))
                await msg.delete()
                return '✅ Сообщение удалено'
            return _asyncio.run_coroutine_threadsafe(_del_msg(), bot.loop).result(timeout=10)

        elif action_type == 'send_embed':
            channel_id = str(action_data.get('channel_id', ''))
            title = action_data.get('title', '')
            description = action_data.get('description', '')
            color = int(action_data.get('color', 0xc8922a))
            if not (bot and channel_id):
                return '❌ Канал ID eksik'
            channel = bot.get_channel(int(channel_id))
            if not channel:
                return '❌ Канал bulunamadı'
            import discord as _discord
            embed = _discord.Embed(title=title, description=description, color=color)
            _asyncio.run_coroutine_threadsafe(channel.send(embed=embed), bot.loop).result(timeout=10)
            return f'✅ Embed отправитьildi → #{channel.name}'

        elif action_type == 'bulk_dm':
            message = action_data.get('message', '')
            role_id = str(action_data.get('role_id', ''))
            if not (bot and guild and message):
                return '❌ Eksik parametre'
            members = guild.members if not role_id else [
                m for m in guild.members if any(str(r.id) == role_id for r in m.roles)
            ]
            async def _bulk():
                count = 0
                for m in members:
                    if not m.bot:
                        try:
                            await m.send(message)
                            count += 1
                        except Exception:
                            pass
                return count
            count = _asyncio.run_coroutine_threadsafe(_bulk(), bot.loop).result(timeout=60)
            return f'✅ {count} kişiye DM отправитьildi'

        elif action_type == 'create_channel':
            name = action_data.get('name', 'yeni-channel')
            category_id = action_data.get('category_id')
            if not (bot and guild):
                return '❌ Guild bulunamadı'
            async def _create_ch():
                cat = guild.get_channel(int(category_id)) if category_id else None
                return await guild.create_text_channel(name, category=cat)
            ch = _asyncio.run_coroutine_threadsafe(_create_ch(), bot.loop).result(timeout=10)
            return f'✅ Канал создано: #{ch.name} (ID: {ch.id})'

        elif action_type == 'delete_channel':
            channel_id = str(action_data.get('channel_id', ''))
            if not (bot and channel_id):
                return '❌ Канал ID eksik'
            channel = bot.get_channel(int(channel_id))
            if not channel:
                return '❌ Канал bulunamadı'
            _asyncio.run_coroutine_threadsafe(channel.delete(), bot.loop).result(timeout=10)
            return f'✅ Канал удалено: #{channel.name}'

        elif action_type == 'create_role':
            name = action_data.get('name', 'yeni-role')
            color_hex = action_data.get('color', '000000').lstrip('#')
            import discord as _discord
            color_obj = _discord.Color(int(color_hex, 16)) if color_hex else _discord.Color.default()
            if not (bot and guild):
                return '❌ Guild bulunamadı'
            role = _asyncio.run_coroutine_threadsafe(
                guild.create_role(name=name, color=color_obj), bot.loop
            ).result(timeout=10)
            return f'✅ Role создано: {role.name} (ID: {role.id})'

        elif action_type == 'delete_role':
            role_id = str(action_data.get('role_id', ''))
            if not (guild and role_id):
                return '❌ Role ID eksik'
            role = guild.get_role(int(role_id))
            if not role:
                return '❌ Role bulunamadı'
            _asyncio.run_coroutine_threadsafe(role.delete(), bot.loop).result(timeout=10)
            return f'✅ Role удалено: {role.name}'

        elif action_type == 'nick':
            nick = action_data.get('nick', '')
            if not (guild and uid):
                return '❌ Eksik parametre'
            member = guild.get_member(int(uid))
            if not member:
                return '❌ Участник bulunamadı'
            _asyncio.run_coroutine_threadsafe(member.edit(nick=nick or None), bot.loop).result(timeout=10)
            return f'✅ Nickname değiştirildi → {nick or "(sıfırlandı)"}'

        elif action_type == 'unban':
            if not (guild and uid):
                return '❌ Eksik parametre'
            async def _unban():
                user = await bot.fetch_user(int(uid))
                await guild.unban(user)
            _asyncio.run_coroutine_threadsafe(_unban(), bot.loop).result(timeout=10)
            return f'✅ Бан убратьıldı (user_id: {uid})'

        elif action_type == 'user_info':
            if not (guild and uid):
                return '❌ Пользователь ID eksik'
            member = guild.get_member(int(uid))
            if not member:
                return f'❌ Участник serverda bulunamadı (ID: {uid})'
            roles = [r.name for r in member.roles if r.name != '@everyone']
            warns_file = 'data/warnings.json'
            warn_count = 0
            if os.path.exists(warns_file):
                try:
                    w = json.load(open(warns_file, encoding='utf-8'))
                    warn_count = len(w.get(str(guild_id), {}).get(uid, []))
                except Exception:
                    pass
            return (f'👤 {member.display_name} ({member.name})\n'
                    f'📅 Katılım: {member.joined_at.strftime("%d.%m.%Y") if member.joined_at else "?"}\n'
                    f'⚠️ Warning: {warn_count}\n'
                    f'🎭 Роли: {", ".join(roles) or "Нет"}')

        return f'⚠️ Bilinmeyen action: {action_type}'
    except Exception as e:
        return f'⚠️ Action Ошибкаsı: {e}'


def register_extra_routes(app, ROLES, login_required, role_required, MAIN_GUILD_ID='1384282749317152878'):

    # ── PAGE ROUTES ──────────────────────────────────────────────────────────

    @app.route('/ai_ticket_stats')
    @login_required
    @role_required('mod')
    def ai_ticket_stats():
        """AI ticket istatistikleri sayfası"""
        guild_id = session.get('selected_guild')
        if not guild_id:
            return redirect(url_for('select_guild'))
        
        stats = calculate_ai_ticket_stats(int(guild_id))
        
        return render_template(
            'ai_ticket_stats.html',
            role=session.get('role'),
            username=session.get('username'),
            stats=stats
        )

    @app.route('/бот-stats')
    @login_required
    @role_required('mod')
    def bot_stats_page():
        return render_template('bot_stats.html', role=session.get('role'), username=session.get('username'))

    @app.route('/analytics')
    @login_required
    @role_required('mod')
    def analytics_page():
        return render_template('analytics.html', role=session.get('role'), username=session.get('username'))

    @app.route('/server-health')
    @login_required
    @role_required('mod')
    def server_health_page():
        return render_template('server_health.html', role=session.get('role'), username=session.get('username'))

    @app.route('/roles')
    @login_required
    @role_required('admin')
    def roles_page():
        return render_template('roles.html', role=session.get('role'), username=session.get('username'))

    @app.route('/channels')
    @login_required
    @role_required('admin')
    def channels_page():
        return render_template('channels.html', role=session.get('role'), username=session.get('username'))

    @app.route('/mod-history')
    @login_required
    @role_required('mod')
    def modhistory_page():
        return render_template('modhistory.html', role=session.get('role'), username=session.get('username'))

    @app.route('/welcome-editor')
    @login_required
    @role_required('admin')
    def welcome_editor_page():
        return render_template('welcome_editor.html', role=session.get('role'), username=session.get('username'))

    @app.route('/reaction-roles')
    @login_required
    @role_required('admin')
    def reaction_roles_page():
        return render_template('reaction_roles.html', role=session.get('role'), username=session.get('username'))

    @app.route('/giveaway')
    @login_required
    @role_required('admin')
    def giveaway_page():
        return render_template('giveaway.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/polls')
    @login_required
    @role_required('mod')
    def polls_page():
        return render_template('polls.html', role=session.get('role'), username=session.get('username'))

    @app.route('/autorole')
    @login_required
    @role_required('admin')
    def autorole_page():
        return render_template('autorole.html', role=session.get('role'), username=session.get('username'))

    @app.route('/leveling')
    @login_required
    @role_required('owner')
    def leveling_page():
        return render_template('leveling.html', role=session.get('role'), username=session.get('username'))
    
    @app.route('/ai-tickets')
    @login_required
    @role_required('mod')
    def ai_tickets_page():
        """AI ticket konusmalarini goster"""
        guild_id = session.get('guild_id', MAIN_GUILD_ID)
        tickets_data = _load_ai_tickets(int(guild_id))
        
        # Бот instance'dan channel bilgilerini al
        import web.app as _app; bot = _app.bot_instance
        tickets_list = []
        
        for channel_id, ticket in tickets_data.items():
            try:
                guild = bot.get_guild(int(guild_id))
                channel = guild.get_channel(int(channel_id)) if guild else None
                user = guild.get_member(ticket['user_id']) if guild and ticket.get('user_id') else None
                
                tickets_list.append({
                    'channel_id': channel_id,
                    'channel_name': channel.name if channel else f"ticket-{channel_id}",
                    'user_name': user.display_name if user else 'Bilinmiyor',
                    'user_id': ticket.get('user_id'),
                    'status': ticket.get('status', 'unknown'),
                    'category': ticket.get('category', 'genel'),
                    'ai_message_count': ticket.get('ai_message_count', 0),
                    'history': ticket.get('history', []),
                    'escalated_at': ticket.get('escalated_at'),
                    'staff_notified': ticket.get('staff_notified', False)
                })
            except:
                pass
        
        return render_template(
            'ai_tickets.html',
            role=session.get('role'),
            username=session.get('username'),
            tickets=tickets_list
        )

    @app.route('/economy')
    @login_required
    @role_required('admin')
    def economy_page():
        return render_template('economy.html', role=session.get('role'), username=session.get('username'))

    @app.route('/scheduled-messages')
    @login_required
    @role_required('owner')
    def scheduled_messages_page():
        return render_template('scheduled_messages.html', role=session.get('role'), username=session.get('username'))

    @app.route('/custom-commands')
    @login_required
    @role_required('owner')
    def custom_commands_page():
        return render_template('custom_commands.html', role=session.get('role'), username=session.get('username'))

    @app.route('/member-notes')
    @login_required
    @role_required('mod')
    def member_notes_page():
        return render_template('member_notes.html', role=session.get('role'), username=session.get('username'))

    @app.route('/bulk-actions')
    @login_required
    @role_required('admin')
    def bulk_actions_page():
        return render_template('bulk_actions.html', role=session.get('role'), username=session.get('username'))

    @app.route('/invite-tracker')
    @login_required
    @role_required('mod')
    def invite_tracker_page():
        return render_template('invite_tracker.html', role=session.get('role'), username=session.get('username'))

    @app.route('/suggestions')
    @login_required
    @role_required('mod')
    def suggestions_page():
        return render_template('suggestions.html', role=session.get('role'), username=session.get('username'))

    @app.route('/starboard')
    @login_required
    @role_required('mod')
    def starboard_page():
        return render_template('starboard.html', role=session.get('role'), username=session.get('username'))

    @app.route('/yardim')
    @login_required
    @role_required('uye')
    def yardim_page():
        return render_template('yardim.html', role=session.get('role'), username=session.get('username'))

    # ── YENİ SAYFALAR ────────────────────────────────────────────────────────

    @app.route('/chat')
    @login_required
    @role_required('owner')
    def chat_page():
        return render_template('chat.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/бот-settings')
    @login_required
    @role_required('owner')
    def bot_settings_page():
        return render_template('bot_settings.html', role=session.get('role'), username=session.get('username'))

    @app.route('/cog-manager')
    @login_required
    @role_required('owner')
    def cog_manager_page():
        return render_template('cog_manager.html', role=session.get('role'), username=session.get('username'))

    @app.route('/warn-config')
    @login_required
    @role_required('admin')
    def warn_config_page():
        return render_template('warn_config.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/duty-panel-web')
    @login_required
    @role_required('admin')
    def duty_panel_web_page():
        return render_template('duty_panel.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/member-search')
    @login_required
    @role_required('admin')
    def member_search_page():
        return render_template('member_search.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/afk-list')
    @login_required
    @role_required('mod')
    def afk_list_page():
        return render_template('afk_list.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/watchlist-panel')
    @login_required
    @role_required('mod')
    def watchlist_panel_page():
        return render_template('watchlist.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/my-profile')
    @login_required
    @role_required('uye')
    def my_profile_page():
        return render_template('member_profile.html', role=session.get('role'), username=session.get('username'))

    @app.route('/change-password')
    @login_required
    @role_required('uye')
    def change_password_page():
        return render_template('change_password.html', role=session.get('role'), username=session.get('username'))

    @app.route('/api/user/change-password', methods=['POST'])
    @login_required
    @role_required('uye')
    def api_user_change_password():
        from web.app import USERS
        import json as _json
        data = request.get_json() or {}
        old_pass = data.get('old_password', '').strip()
        new_pass = data.get('new_password', '').strip()

        if not old_pass or not new_pass or len(new_pass) < 6:
            return jsonify({'error': 'Geçersiz veri'})

        # Owner kontroleü (USERS dict'inden)
        username = session.get('username')
        if username in USERS:
            if USERS[username]['password'] != old_pass:
                return jsonify({'error': 'Mevcut паrole yanlış'})
            USERS[username]['password'] = new_pass
            return jsonify({'success': True})

        # Normal участник — По Discord ID ara
        discord_id = session.get('discord_id') or username
        members_file = 'data/members.json'
        if not os.path.exists(members_file):
            return jsonify({'error': 'Пользователь bulunamadı'})

        with open(members_file, 'r', encoding='utf-8') as f:
            members = _json.load(f)

        # discord_id ile найти, yoksa display_name ile dene
        member_key = None
        if discord_id and discord_id in members:
            member_key = discord_id
        else:
            for k, v in members.items():
                if v.get('display_name') == username or v.get('name') == username:
                    member_key = k
                    break

        if not member_key:
            return jsonify({'error': 'Пользователь bulunamadı'})
        if members[member_key].get('password') != old_pass:
            return jsonify({'error': 'Mevcut паrole yanlış'})

        members[member_key]['password'] = new_pass
        with open(members_file, 'w', encoding='utf-8') as f:
            _json.dump(members, f, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/birthday-register')
    @login_required
    @role_required('uye')
    def birthday_register_page():
        return render_template('birthday_register.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/ai-chat')
    @login_required
    @role_required('uye')
    def ai_chat_page():
        return render_template('ai_chat_panel.html', role=session.get('role'), username=session.get('username'), guild_id=MAIN_GUILD_ID)

    @app.route('/api/ai-chat', methods=['POST'])
    @login_required
    @role_required('uye')
    def api_ai_chat():
        """Панель AI — tam server erişimi + eylem yapabilme"""
        from web.ai_helper import _call
        import web.app as _app; bot = _app.bot_instance
        import datetime as _dt, asyncio as _asyncio, discord as _discord
        d = request.json or {}
        question = d.get('message', '').strip()
        if not question:
            return jsonify({'error': 'Сообщение boş'}), 400

        history_key = f'ai_history_{session.get("username", "anon")}'
        history = session.get(history_key, [])
        user_role = session.get('role', 'uye')
        now = _dt.datetime.now()

        # ── SUNUCU VERİSİ TOPLA ──────────────────────────────────────────────
        guild_data = []
        if bot:
            for g in bot.guilds:
                online = [m for m in g.members if not m.bot and m.status != _discord.Status.offline]
                in_voice = []
                for vc in g.voice_channels:
                    mems = [m.display_name for m in vc.members if not m.bot]
                    if mems: in_voice.append(f"{vc.name}: {', '.join(mems)}")
                channels = [f"#{c.name}(id={c.id})" for c in g.text_channels[:20]]
                roles = [r.name for r in g.roles if not r.is_default()][:15]
                # Участник listesi (eylemler için имя→ID eşleştirmesi)
                members_list = [f"{m.display_name}(id={m.id})" for m in g.members if not m.bot][:50]

                # Серверya ait tüm data dosyalarını oku
                server_configs = []
                config_files = {
                    f'data/automod_{g.id}.json':   'Automod настройкиı',
                    f'data/antiraid_{g.id}.json':  'Anti-raid настройкиı',
                    f'data/health_{g.id}.json':    'Сервер sağlığı',
                    f'data/badges_{g.id}.json':    'Rozetler',
                    f'data/warn_config_{g.id}.json': 'Warning limitleri',
                }
                for fpath, flabel in config_files.items():
                    if os.path.exists(fpath):
                        try:
                            with open(fpath, 'r', encoding='utf-8') as fp:
                                fdata = json.load(fp)
                            # Sadece özet info отправить (token tasarrufu)
                            if flabel == 'Сервер sağlığı':
                                score = fdata.get('score', fdata.get('health_score', '?'))
                                label = fdata.get('label', fdata.get('status', '?'))
                                server_configs.append(f"{flabel}: {score}/100 ({label})")
                            elif flabel == 'Automod настройкиı':
                                enabled = [k for k, v in fdata.items() if isinstance(v, dict) and v.get('enabled')]
                                server_configs.append(f"{flabel}: {', '.join(enabled) or 'Нет'}")
                            elif flabel == 'Warning limitleri':
                                thresholds = fdata.get('thresholds', [])
                                server_configs.append(f"{flabel}: {thresholds}")
                            else:
                                server_configs.append(f"{flabel}: mevcut")
                        except: pass

                # Warning sayıları
                warn_summary = ''
                warns_f = 'data/warnings.json'
                if os.path.exists(warns_f):
                    try:
                        with open(warns_f, 'r', encoding='utf-8') as fp:
                            wd = json.load(fp)
                        gw = wd.get(str(g.id), {})
                        total_warns = sum(len(v) for v in gw.values())
                        top_warned = sorted(gw.items(), key=lambda x: len(x[1]), reverse=True)[:3]
                        top_names = []
                        for uid, ws in top_warned:
                            m = g.get_member(int(uid)) if uid.isdigit() else None
                            name = m.display_name if m else uid
                            top_names.append(f"{name}({len(ws)})")
                        warn_summary = f"Всего предупреждений: {total_warns}, En çok: {', '.join(top_names)}"
                    except: pass

                guild_data.append(
                    f"Сервер: {g.name} (id={g.id})\n"
                    f"  Всего участник: {g.member_count}, Online: {len(online)}\n"
                    f"  Голос channelları: {', '.join(in_voice) or 'Boş'}\n"
                    f"  Каналlar: {', '.join(channels)}\n"
                    f"  Роли: {', '.join(roles)}\n"
                    f"  Участникler: {', '.join(members_list)}\n"
                    + (f"  Warninglar: {warn_summary}\n" if warn_summary else '')
                    + ('\n'.join(f'  {c}' for c in server_configs))
                )

        # ── KULLANICI ID TESPİT ET VE BİLGİ ÇEK ─────────────────────────────
        import re as _re2
        user_info_block = ''
        id_matches = _re2.findall(r'\b(\d{17,20})\b', question)
        # Имя araması — sadece tırnak içindeki veya belirgin имяler
        name_matches = _re2.findall(r'"([^"]+)"', question)  # Tırnak içindeki имяler
        if not id_matches and bot and name_matches:
            for name_q in name_matches[:2]:
                for g in bot.guilds:
                    m = discord.utils.find(
                        lambda mem: mem.display_name.lower() == name_q.lower() or mem.name.lower() == name_q.lower(),
                        g.members
                    )
                    if m:
                        id_matches.append(str(m.id))
                        break
        if id_matches and bot:
            for uid_str in id_matches[:3]:  # max 3 ID
                uid = int(uid_str)
                for g in bot.guilds:
                    member = g.get_member(uid)
                    if not member:
                        continue
                    # Роли
                    member_roles = [r.name for r in member.roles if r.name != '@everyone']
                    # Warninglar
                    warn_count = 0
                    warns_file = 'data/warnings.json'
                    warn_list = []
                    if os.path.exists(warns_file):
                        try:
                            with open(warns_file, 'r', encoding='utf-8') as fp:
                                wd = json.load(fp)
                            warn_list = wd.get(str(g.id), {}).get(uid_str, [])
                            warn_count = len(warn_list)
                        except: pass
                    # Mod geçmişi — hem mod_data.json hem discord_audit_cache'den
                    mod_history = []
                    mod_file = 'data/mod_data.json'
                    if os.path.exists(mod_file):
                        try:
                            with open(mod_file, 'r', encoding='utf-8') as fp:
                                md = json.load(fp)
                            case = md.get('case', {}).get(str(g.id), [])
                            for c in case:
                                if str(c.get('user_id','')) == uid_str:
                                    mod_history.append(
                                        f"{c.get('timestamp','')[:10]} {c.get('action','?').upper()} — "
                                        f"Mod: {c.get('mod_id','?')} — {c.get('reason','?')}"
                                    )
                        except: pass
                    # Discord audit cache'den de çek
                    cache_f = 'data/discord_audit_cache.json'
                    if os.path.exists(cache_f):
                        try:
                            with open(cache_f, 'r', encoding='utf-8') as fp:
                                cdata = json.load(fp)
                            for gid_c, evs in cdata.items():
                                for ev in evs:
                                    if str(ev.get('target_id','')) == uid_str:
                                        ts = ev.get('timestamp','')[:16].replace('T',' ')
                                        mod_history.append(
                                            f"{ts} {ev.get('action','?')} — "
                                            f"Mod: {ev.get('mod_name','?')} — {ev.get('reason','') or 'Причина yok'}"
                                        )
                        except: pass
                    # Role geçmişi — audit cache'den kim role verdi/aldı
                    role_gecmisi = []
                    if os.path.exists(cache_f):
                        try:
                            with open(cache_f, 'r', encoding='utf-8') as fp:
                                cdata2 = json.load(fp)
                            for gid_c, evs in cdata2.items():
                                for ev in evs:
                                    if str(ev.get('target_id','')) == uid_str and ev.get('action') == 'Role Değişikliği':
                                        ts = ev.get('timestamp','')[:16].replace('T',' ')
                                        role_gecmisi.append(
                                            f"{ts} Role Değişikliği — Mod: {ev.get('mod_name','?')} — {ev.get('reason','') or ev.get('before','') or ''}"
                                        )
                        except: pass
                    role_gecmisi.sort()
                    # Davet eden
                    inviter = '?'
                    invite_file = f'data/invite_joins_{g.id}.json'
                    if os.path.exists(invite_file):
                        try:
                            with open(invite_file, 'r', encoding='utf-8') as fp:
                                inv = json.load(fp)
                            inviter = inv.get(uid_str, {}).get('inviter_name', '?')
                        except: pass
                    # Katılma датаi
                    joined = member.joined_at.strftime('%d.%m.%Y %H:%M') if member.joined_at else '?'
                    created = member.created_at.strftime('%d.%m.%Y') if member.created_at else '?'
                    # Мут statusu
                    timed_out = 'Да' if member.is_timed_out() else 'Нет'

                    user_info_block += (
                        f"\n=== KULLANICI BİLGİSİ: {member.display_name} (ID: {uid_str}) ===\n"
                        f"  Сервер: {g.name}\n"
                        f"  Пользователь adı: {member.name}\n"
                        f"  Статус: {str(member.status)}\n"
                        f"  Мут: {timed_out}\n"
                        f"  Katılma: {joined}\n"
                        f"  Hesap создатьma: {created}\n"
                        f"  Роли: {', '.join(member_roles) or 'Нет'}\n"
                        f"  Warning sayısı: {warn_count}\n"
                        f"  Warninglar: {'; '.join([w.get('reason','?') for w in warn_list[-5:]]) or 'Нет'}\n"
                        f"  Mod geçmişi ({len(mod_history)} регистрация):\n"
                    )
                    user_info_block += ('\n'.join(f'    {h}' for h in mod_history) if mod_history else '    Temiz') + '\n'
                    user_info_block += (f"  Role geçmişi ({len(role_gecmisi)} регистрация):\n" + '\n'.join(f'    {r}' for r in role_gecmisi) + '\n') if role_gecmisi else '  Role geçmişi: Регистрация yok\n'
                    user_info_block += f"  Davet eden: {inviter}\n"
                    break

        # ── KANAL MESAJ GEÇMİŞİ (soruda channel adı geçiyorsa) ────────────────
        channel_messages_block = ''
        import re as _re3
        channel_mentions = _re3.findall(r'#([\w\-]+)', question)
        channel_keywords = ['channel', 'yazıyor', 'yazılan', 'messagelar', 'son message']
        if bot and (channel_mentions or any(k in question.lower() for k in channel_keywords)):
            async def fetch_channel_msgs():
                lines = []
                for g in bot.guilds:
                    for ch in g.text_channels:
                        # Канал adı soruda geçiyor mu?
                        if channel_mentions and not any(m.lower() in ch.name.lower() for m in channel_mentions):
                            continue
                        if not channel_mentions:
                            break  # Genel soru — sadece ilk channelı al
                        try:
                            msgs = [m async for m in ch.history(limit=10)]
                            for m in reversed(msgs):
                                lines.append(f"  [{ch.name}] {m.author.display_name}: {m.content[:100]}")
                        except: pass
                return lines

            try:
                import asyncio as _asyncio3
                ch_lines = _asyncio3.run_coroutine_threadsafe(
                    fetch_channel_msgs(), bot.loop
                ).result(timeout=8)
                if ch_lines:
                    channel_messages_block = f"\n=== KANAL MESAJLARI ===\n" + '\n'.join(ch_lines[:30])
            except: pass
        recent_logs = []
        cache_file_logs = 'data/discord_audit_cache.json'
        if os.path.exists(cache_file_logs):
            try:
                with open(cache_file_logs, 'r', encoding='utf-8') as fp:
                    ald = json.load(fp)
                for gid, evs in ald.items():
                    for ev in evs[-5:]:
                        recent_logs.append(
                            f"[{ev.get('timestamp','')[:16]}] {ev.get('action','?')}: "
                            f"{ev.get('target_name', ev.get('user_name','?'))} — "
                            f"Mod: {ev.get('mod_name','?')} — {ev.get('reason','')}"
                        )
            except: pass

        # Mod istatistikleri — cache'den oku (bot 30sn'de bir günceller)
        mod_stats = ''
        today = _dt.datetime.utcnow().date()
        yesterday = today - _dt.timedelta(days=1)
        today_actions = []
        yesterday_actions = []

        cache_file_mod = 'data/discord_audit_cache.json'
        if os.path.exists(cache_file_mod):
            try:
                with open(cache_file_mod, 'r', encoding='utf-8') as fp:
                    cache_data = json.load(fp)
                mod_action_types = {'Бан', 'Кик', 'Мут', 'Unban', 'Бан Снят', 'Мут Снят'}
                for gid, evs in cache_data.items():
                    for ev in evs:
                        ts = ev.get('timestamp', '')
                        if ev.get('action') not in mod_action_types:
                            continue
                        ev_date = ts[:10]
                        entry = {
                            'action': ev.get('action', '?'),
                            'target': ev.get('target_name', '?'),
                            'mod': ev.get('mod_name', '?'),
                            'reason': ev.get('reason', ''),
                            'time': ts[11:16],
                        }
                        if ev_date == str(today):
                            today_actions.append(entry)
                        elif ev_date == str(yesterday):
                            yesterday_actions.append(entry)
            except Exception as _fe:
                print(f'[AI] Cache okuma Ошибкаsı: {_fe}')

        def fmt_actions(actions):
            if not actions:
                return '  Нет'
            return '\n'.join(
                f"  {a['time']} {a['action']} — Hedef: {a['target']} — Mod: {a['mod']}"
                + (f" — Причина: {a['reason']}" if a['reason'] else '')
                for a in actions
            )

        t_ban  = sum(1 for c in today_actions if c['action'] == 'Бан')
        t_kick = sum(1 for c in today_actions if c['action'] == 'Кик')
        t_to   = sum(1 for c in today_actions if c['action'] == 'Мут')

        # Buденьkü предупрежденийları warnings.json'dan oku
        today_warns = []
        warns_f2 = 'data/warnings.json'
        if os.path.exists(warns_f2):
            try:
                with open(warns_f2, 'r', encoding='utf-8') as fp:
                    wd2 = json.load(fp)
                for gid2, guild_warns2 in wd2.items():
                    for uid2, warn_list2 in guild_warns2.items():
                        for w in warn_list2:
                            ts2 = w.get('timestamp', '')
                            if ts2[:10] == str(today):
                                today_warns.append({
                                    'action': 'Warning',
                                    'target': uid2,
                                    'mod': w.get('moderator', w.get('mod', '?')),
                                    'reason': w.get('reason', ''),
                                    'time': ts2[11:16],
                                })
            except: pass

        mod_stats = (
            f"Buдень ({today}) — Бан: {t_ban}, Кик: {t_kick}, Мут: {t_to}, Warning: {len(today_warns)}\n"
            f"Buденьkü mod действиеleri:\n{fmt_actions(today_actions)}\n"
            f"Buденьkü предупрежденийlar:\n{fmt_actions(today_warns) if today_warns else '  Нет'}\n\n"
            f"Dün ({yesterday}) действиеler:\n{fmt_actions(yesterday_actions)}"
        )

        # Sağlık skoru — tüm guild'lerin health dosyalarından çek
        health_info = ''
        health_lines = []
        if bot:
            for g in bot.guilds:
                hf = f'data/health_{g.id}.json'
                if os.path.exists(hf):
                    try:
                        with open(hf, 'r', encoding='utf-8') as fp:
                            hd = json.load(fp)
                        score = hd.get('score', hd.get('health_score', '?'))
                        label = hd.get('label', hd.get('status', '?'))
                        health_lines.append(f"{g.name}: {score}/100 ({label})")
                    except: pass
        if health_lines:
            health_info = 'Сервер sağlık skorları:\n' + '\n'.join(f'  {l}' for l in health_lines)
        else:
            # Fallback: API'den hesapla
            try:
                import requests as _req2
                for g in (bot.guilds if bot else []):
                    r = _req2.get(
                        f'http://localhost:5001/api/guild/{g.id}/health',
                        cookies=request.cookies, timeout=3
                    )
                    if r.status_code == 200:
                        hd = r.json()
                        health_info = f"{g.name} sağlık skoru: {hd.get('score','?')}/100 ({hd.get('label','?')})"
                        break
            except: pass

        # ── SİSTEM PROMPT ────────────────────────────────────────────────────
        is_owner = user_role == 'owner'

        if is_owner:
            eylem_prompt = (
                "=== J.A.R.V.I.S. MODU (OWNER) ===\n"
                "Sen Arthur'un kişisel asistanısın.\n\n"
                "EYLEM KURALI — SADECE şu tam ifadeler geçtiğinde [EYLEM:...] kullan:\n"
                "  'kilitle' → [EYLEM:KANAL_KILITLE:channel_id]\n"
                "  'kilidi aç' veya 'channelı aç' → [EYLEM:KANAL_AC:channel_id]\n"
                "  'ban at' → [EYLEM:BAN:user_id:причина]\n"
                "  'kick at' → [EYLEM:KICK:user_id:причина]\n"
                "  'timeout ver' veya 'mute at' → [EYLEM:TIMEOUT:user_id:minutes:причина]\n"
                "  'şunu yaz' veya 'message отправить' + channel adı + message içeriği → [EYLEM:MESAJ:channel_id:metin]\n"
                "  'yavaş mod' → [EYLEM:KANAL_YAVAŞ:channel_id:saniye]\n"
                "  'role ver' → [EYLEM:ROL_VER:user_id:role_id]\n"
                "  'role al' → [EYLEM:ROL_AL:user_id:role_id]\n"
                "  'dm отправить' veya 'özelden yaz' → [EYLEM:DM:user_adı_veya_id:message]\n"
                "  'голосten at' → [EYLEM:SESTEN_AT:user_id]\n"
                "  'voice move' → [EYLEM:SESE_TAS:user_id:channel_adı]\n"
                "  'üst voice move' → [EYLEM:UST_SESE:user_id:step_count] (undo :geri add)\n"
                "  'alt voice move' → [EYLEM:ALT_SESE:user_id:step_count] (undo :geri add)\n"
                "  Örnek: 1 üst voice move sonra geri al → [EYLEM:UST_SESE:user_id:1:geri]\n"
                "  NOT: 'üst voice', 'bir üst', '1 üst' gibi ifadelerde MUTLAKA UST_SESE kullan, SESE_TAS kullanma!\n"
                "  'sustur' → [EYLEM:SUSTUR:user_id]\n"
                "  'susturmayı убрать' → [EYLEM:SUSTUR_KALDIR:user_id]\n"
                "  'kulaklığını закрыть' → [EYLEM:KULAKLIK_KAPAT:user_id]\n"
                "  'kulaklığını aç' → [EYLEM:KULAKLIK_AC:user_id]\n"
                "  'timeout убрать' → [EYLEM:TIMEOUT_KALDIR:user_id]\n"
                "  'unban' → [EYLEM:UNBAN:user_id]\n"
                "  'uyar' → [EYLEM:UYARI:user_id:причина]\n"
                "  'предупрежденийları clear' → [EYLEM:UYARI_TEMIZLE:user_id]\n"
                "  'message удалить' → [EYLEM:MESAJ_SIL:channel:sayi]\n"
                "  'channel создать' → [EYLEM:KANAL_OLUSTUR:channel-adı]\n"
                "  'голос channelı создать' → [EYLEM:SES_KANAL_OLUSTUR:channel adı]\n"
                "  'role создать' → [EYLEM:ROL_OLUSTUR:role adı]\n"
                "  'announce yap' → [EYLEM:DUYURU:channel:metin]\n"
                "  'nick değiştir' veya 'isminin yanına X yaz' → [EYLEM:NICK:user_id:yeni_nick]\n\n"
                "YASAK: 'удалить', 'ne', 'kim', 'kaç', 'göster', 'var mı', 'statusu', 'sağlık', 'listele', 'oku', 'bak', 'atacağım', 'atıcam', 'gidiyorum', 'yokum' gibi kelimelerde KESİNLİKLE eylem üretme!\n"
                "NOT: Канал adı kullanırken ID yerine channel adını yaz, sistem otomatik çevirir. Örnek: [EYLEM:MESAJ:genel:merhaba]\n"
                "Kısa ve net cevap ver. 'Efendim' diye hitap et.\n"
            )
        else:
            eylem_prompt = (
                "=== BİLGİ MODU ===\n"
                "Bu user sadece info sorgulayabilir, eylem yapamaz.\n"
                "Eylem isterlerse 'Bu действие için owner правоsi gerekiyor' de.\n"
            )

        system = (
            f"Sen Aether, Aether Discord serversunun panel asistanısın.\n"
            f"Пользователь: {session.get('username')}, Роль: {user_role}\n"
            f"Время: {now.strftime('%H:%M')}, Дата: {now.strftime('%d %B %Y, %A')}\n\n"
            f"=== SUNUCU DURUMU ===\n"
            f"{chr(10).join(guild_data) if guild_data else 'Бот offline'}\n\n"
            f"=== MOD İSTATİSTİKLERİ ===\n{mod_stats}\n\n"
            f"{f'=== SAĞLIK ==={chr(10)}{health_info}{chr(10)}{chr(10)}' if health_info else ''}"
            f"=== SON LOGLAR (son 10) ===\n{chr(10).join(recent_logs[-10:]) if recent_logs else 'Лог yok'}\n\n"
            f"{user_info_block}"
            f"{channel_messages_block}\n"
            f"{eylem_prompt}\n"
            "Türkçe konuş. Сервер verisi sorulursa SADECE yukarıdaki gerçek verileri kullan, asla tahmin etme. "
            "Listede olmayan bir имя veya eylem sorulursa 'Bu kişi/eylem регистрацияlarda yok' de, uydurma. "
            "Eylem yaparken участник adı yerine ID kullan — участникler listesinde her участникnin ID'si var."
        )

        messages = [{'role': 'system', 'content': system}]
        messages.extend(history[-20:])
        messages.append({'role': 'user', 'content': question})

        try:
            answer, model_name, _ = _call(messages, max_tokens=1024)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        # ── EYLEM İŞLE (sadece owner) ─────────────────────────────────────────
        action_result = None
        import re as _re
        action_match = _re.search(r'\[EYLEM:([^\]]+)\]', answer)
        if action_match and bot and user_role == 'owner':
            parts = action_match.group(1).split(':')
            tip = parts[0] if parts else ''
            # "channel_id=123" veya "user_id=123" gibi prefix'leri clear
            import re as _re3
            clean_parts = [parts[0]]
            for p in parts[1:]:
                clean_parts.append(_re3.sub(r'^[a-z_]+=', '', p))
            parts = clean_parts
            try:
                async def do_action():
                    guild = bot.get_guild(int(MAIN_GUILD_ID))
                    if not guild: return '❌ Сервер bulunamadı'
                    _owner_id = int(os.getenv('OWNER_ID', '987430047889637426'))

                    def resolve_channel(val):
                        """Канал adı veya ID'den channel nesnesini döndür"""
                        val = val.lstrip('#').strip()
                        if val.isdigit():
                            return guild.get_channel(int(val))
                        # Имяle ara
                        return discord.utils.find(
                            lambda c: c.name.lower() == val.lower() or val.lower() in c.name.lower(),
                            guild.text_channels
                        )

                    def resolve_member(val):
                        """ID veya имяden участник döndür — kısmi eşleşme destekli"""
                        if val.isdigit():
                            return guild.get_member(int(val))
                        val_lower = val.lower()
                        # Önce tam eşleşme
                        exact = discord.utils.find(
                            lambda m: m.display_name.lower() == val_lower or m.name.lower() == val_lower,
                            guild.members
                        )
                        if exact: return exact
                        # Последнийra kısmi eşleşme
                        return discord.utils.find(
                            lambda m: val_lower in m.display_name.lower() or val_lower in m.name.lower(),
                            guild.members
                        )

                    def resolve_role(val):
                        """ID veya имяden role döndür"""
                        if val.isdigit():
                            return guild.get_role(int(val))
                        return discord.utils.find(
                            lambda r: r.name.lower() == val.lower(),
                            guild.roles
                        )
                    if tip == 'KANAL_KILITLE' and len(parts) > 1:
                        ch = resolve_channel(parts[1])
                        if ch:
                            await ch.set_permissions(guild.default_role, send_messages=False)
                            return f'✅ #{ch.name} kilitlendi'
                    elif tip == 'KANAL_AC' and len(parts) > 1:
                        ch = resolve_channel(parts[1])
                        if ch:
                            await ch.set_permissions(guild.default_role, send_messages=None)
                            return f'✅ #{ch.name} açıldı'
                    elif tip == 'BAN' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            reason = ':'.join(parts[2:]) or 'Панель AI'
                            await m.ban(reason=reason)
                            return f'✅ {m.display_name} banlandı'
                    elif tip == 'KICK' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            reason = ':'.join(parts[2:]) or 'Панель AI'
                            await m.kick(reason=reason)
                            return f'✅ {m.display_name} atıldı'
                    elif tip == 'TIMEOUT' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        if m and m.id != _owner_id:
                            mins = int(parts[2]) if parts[2].isdigit() else 10
                            until = _discord.utils.utcnow() + _dt.timedelta(minutes=mins)
                            await m.timeout(until)
                            return f'✅ {m.display_name} {mins} dk timeout'
                    elif tip == 'MESAJ' and len(parts) > 2:
                        ch = resolve_channel(parts[1])
                        if ch:
                            metin = ':'.join(parts[2:])
                            if metin:
                                await ch.send(metin)
                                return f'✅ #{ch.name} channelına message отправитьildi'
                            return '❌ Сообщение içeriği boş'
                    elif tip == 'KANAL_YAVAŞ' and len(parts) > 2:
                        ch = resolve_channel(parts[1])
                        if ch:
                            secs = int(parts[2]) if parts[2].isdigit() else 5
                            await ch.edit(slowmode_delay=secs)
                            return f'✅ #{ch.name} yavaş mod: {secs}s'
                    elif tip == 'DM' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        if m:
                            metin = ':'.join(parts[2:])
                            if metin:
                                try:
                                    await m.send(metin)
                                    return f'✅ {m.display_name} usersına DM отправитьildi'
                                except discord.Forbidden:
                                    return f'❌ {m.display_name} DM\'lere kapalı'
                        return '❌ Участник bulunamadı'
                    elif tip == 'SESTEN_AT' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m and m.voice:
                            await m.move_to(None)
                            return f'✅ {m.display_name} голосten atıldı'
                        return f'❌ Участник голосte değil veya bulunamadı'
                    elif tip == 'SESE_TAS' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        ch = discord.utils.find(lambda c: parts[2].lower() in c.name.lower(), guild.voice_channels)
                        if m and ch:
                            await m.move_to(ch)
                            return f'✅ {m.display_name} → {ch.name} movendı'
                        return '❌ Участник veya channel bulunamadı'
                    elif tip == 'UST_SESE' and len(parts) > 1:
                        # Üst голос channelına move
                        m = resolve_member(parts[1])
                        adim = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                        geri = parts[3].lower() == 'geri' if len(parts) > 3 else False
                        if not m or not m.voice:
                            return '❌ Участник голосte değil'
                        vcs = sorted(guild.voice_channels, key=lambda c: c.position)
                        idx = next((i for i, c in enumerate(vcs) if c.id == m.voice.channel.id), None)
                        if idx is None: return '❌ Канал bulunamadı'
                        orijinal = m.voice.channel
                        hedef_idx = max(0, idx - adim)
                        hedef = vcs[hedef_idx]
                        await m.move_to(hedef)
                        if geri:
                            import asyncio as _as2
                            await _as2.sleep(3)
                            fresh = guild.get_member(m.id)
                            if fresh and fresh.voice:
                                await fresh.move_to(orijinal)
                            return f'✅ {m.display_name} → {hedef.name} movendı, 3sn sonra {orijinal.name} geri getirildi'
                        return f'✅ {m.display_name} → {hedef.name} movendı'
                    elif tip == 'ALT_SESE' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        adim = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                        geri = parts[3].lower() == 'geri' if len(parts) > 3 else False
                        if not m or not m.voice:
                            return '❌ Участник голосte değil'
                        vcs = sorted(guild.voice_channels, key=lambda c: c.position)
                        idx = next((i for i, c in enumerate(vcs) if c.id == m.voice.channel.id), None)
                        if idx is None: return '❌ Канал bulunamadı'
                        orijinal = m.voice.channel
                        hedef_idx = min(len(vcs) - 1, idx + adim)
                        hedef = vcs[hedef_idx]
                        await m.move_to(hedef)
                        if geri:
                            import asyncio as _as2
                            await _as2.sleep(3)
                            fresh = guild.get_member(m.id)
                            if fresh and fresh.voice:
                                await fresh.move_to(orijinal)
                            return f'✅ {m.display_name} → {hedef.name} movendı, 3sn sonra {orijinal.name} geri getirildi'
                        return f'✅ {m.display_name} → {hedef.name} movendı'
                    elif tip == 'SUSTUR' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            if not m.voice:
                                return f'❌ {m.display_name} şu an голос channelında değil, susturulamaz'
                            await m.edit(mute=True)
                            return f'✅ {m.display_name} susturuldu'
                        return '❌ Участник bulunamadı'
                    elif tip == 'SUSTUR_KALDIR' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            if not m.voice:
                                return f'❌ {m.display_name} şu an голос channelında değil'
                            await m.edit(mute=False)
                            return f'✅ {m.display_name} susturma убратьıldı'
                        return '❌ Участник bulunamadı'
                    elif tip == 'KULAKLIK_KAPAT' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            await m.edit(deafen=True)
                            return f'✅ {m.display_name} kulaklığı закрытьıldı'
                    elif tip == 'KULAKLIK_AC' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            await m.edit(deafen=False)
                            return f'✅ {m.display_name} kulaklığı açıldı'
                    elif tip == 'TIMEOUT_KALDIR' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            await m.timeout(None)
                            return f'✅ {m.display_name} timeout убратьıldı'
                    elif tip == 'UNBAN' and len(parts) > 1:
                        try:
                            u = await bot.fetch_user(int(parts[1]))
                            await guild.unban(u)
                            return f'✅ {u.name} unban edildi'
                        except: return '❌ Пользователь bulunamadı'
                    elif tip == 'UYARI' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            import json as _j2
                            wf = 'data/warnings.json'
                            wd = _j2.load(open(wf, encoding='utf-8')) if os.path.exists(wf) else {}
                            gid = str(guild.id)
                            uid = str(m.id)
                            wd.setdefault(gid, {}).setdefault(uid, [])
                            reason = ':'.join(parts[2:]) or 'Панель AI'
                            import datetime as _dt2
                            wd[gid][uid].append({'reason': reason, 'mod': 'Arthur', 'timestamp': _dt2.datetime.utcnow().isoformat()})
                            with open(wf, 'w', encoding='utf-8') as fp: _j2.dump(wd, fp, ensure_ascii=False, indent=2)
                            return f'✅ {m.display_name} предупрежденийldı: {reason}'
                    elif tip == 'UYARI_TEMIZLE' and len(parts) > 1:
                        m = resolve_member(parts[1])
                        if m:
                            import json as _j2
                            wf = 'data/warnings.json'
                            wd = _j2.load(open(wf, encoding='utf-8')) if os.path.exists(wf) else {}
                            wd.setdefault(str(guild.id), {})[str(m.id)] = []
                            with open(wf, 'w', encoding='utf-8') as fp: _j2.dump(wd, fp, ensure_ascii=False, indent=2)
                            return f'✅ {m.display_name} предупрежденийları clearndi'
                    elif tip == 'MESAJ_SIL' and len(parts) > 1:
                        ch = resolve_channel(parts[1])
                        sayi = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
                        if ch:
                            deleted = await ch.purge(limit=sayi)
                            return f'✅ #{ch.name} channelından {len(deleted)} message удалено'
                    elif tip == 'KANAL_OLUSTUR' and len(parts) > 1:
                        channel_name = '-'.join(parts[1:]).lower().replace(' ', '-')
                        ch = await guild.create_text_channel(имя)
                        return f'✅ #{ch.name} channelı создано'
                    elif tip == 'SES_KANAL_OLUSTUR' and len(parts) > 1:
                        channel_name = ' '.join(parts[1:])
                        ch = await guild.create_voice_channel(имя)
                        return f'✅ 🔊 {ch.name} голос channelı создано'
                    elif tip == 'ROL_OLUSTUR' and len(parts) > 1:
                        channel_name = ' '.join(parts[1:])
                        r = await guild.create_role(name=имя)
                        return f'✅ @{r.name} roleü создано'
                    elif tip == 'DUYURU' and len(parts) > 2:
                        ch = resolve_channel(parts[1])
                        metin = ':'.join(parts[2:])
                        if ch and metin:
                            await ch.send(f'📢 **DUYURU**\n\n{metin}')
                            return f'✅ #{ch.name} channelına announce отправитьildi'
                    elif tip == 'ROL_VER' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        r = resolve_role(parts[2])
                        if m and r:
                            await m.add_roles(r)
                            return f'✅ {m.display_name} → {r.name} roleü verildi'
                    elif tip == 'ROL_AL' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        r = resolve_role(parts[2])
                        if m and r:
                            await m.remove_roles(r)
                            return f'✅ {m.display_name} → {r.name} roleü alındı'
                    elif tip == 'NICK' and len(parts) > 2:
                        m = resolve_member(parts[1])
                        if m:
                            yeni_nick = ':'.join(parts[2:])
                            await m.edit(nick=yeni_nick)
                            return f'✅ {m.name} nicki → {yeni_nick}'
                    return '⚠️ Eylem tamamlanamadı — channel/участник bulunamadı'
                action_result = _asyncio.run_coroutine_threadsafe(do_action(), bot.loop).result(timeout=10)
            except Exception as ae:
                action_result = f'❌ Eylem Ошибкаsı: {ae}'

            # Eylem tag'ini cevaptan clear
            answer = _re.sub(r'\[EYLEM:[^\]]+\]', '', answer).strip()
            if action_result:
                answer = f"{answer}\n\n`{action_result}`" if answer else f"`{action_result}`"

        new_history = history + [
            {'role': 'user', 'content': question},
            {'role': 'assistant', 'content': answer}
        ]
        session[history_key] = new_history[-30:]
        session.modified = True
        return jsonify({'answer': answer, 'model': model_name})

    @app.route('/api/ai-chat/clear', methods=['POST'])
    @login_required
    @role_required('uye')
    def api_ai_chat_clear():
        """AI sohbet geçmişini clear"""
        history_key = f'ai_history_{session.get("username", "anon")}'
        session.pop(history_key, None)
        session.modified = True
        return jsonify({'ok': True})

    # ── API ROUTES ────────────────────────────────────────────────────────────

    # ── YENİ API ENDPOINT'LERİ ────────────────────────────────────────────────

    @app.route('/api/бот/status', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_бот_status():
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        d = request.json or {}
        status_map = {'online': discord.Status.online, 'idle': discord.Status.idle, 'dnd': discord.Status.dnd, 'invisible': discord.Status.invisible}
        type_map = {'listening': discord.ActivityType.listening, 'playing': discord.ActivityType.playing, 'watching': discord.ActivityType.watching, 'competing': discord.ActivityType.competing}
        status = status_map.get(d.get('status', 'online'), discord.Status.online)
        atype  = type_map.get(d.get('activity_type', 'listening'), discord.ActivityType.listening)
        atext  = d.get('activity_text', '.gg/Aether')
        async def _set():
            await bot.change_presence(status=status, activity=discord.Activity(type=atype, name=atext))
        asyncio.run_coroutine_threadsafe(_set(), bot.loop).result(timeout=5)
        # Config'e сохранить — bot yeniden başlayınca da hatırlasın
        os.makedirs('data', exist_ok=True)
        cfg = {}
        cfg_file = 'data/бот_config.json'
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, encoding='utf-8') as f: cfg = json.load(f)
            except Exception: pass
        cfg['status'] = d.get('status', 'online')
        cfg['activity_type'] = d.get('activity_type', 'listening')
        cfg['activity_text'] = atext
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return jsonify({'ok': True})

    @app.route('/api/бот/prefix', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_бот_prefix():
        d = request.json or {}
        prefix = d.get('prefix', '!').strip()
        if not prefix: return jsonify({'error': 'Boş prefix'}), 400
        os.makedirs('data', exist_ok=True)
        with open('data/бот_config.json', 'w', encoding='utf-8') as f:
            json.dump({'prefix': prefix}, f)
        return jsonify({'ok': True})

    @app.route('/api/cogs', methods=['GET'])
    @login_required
    @role_required('owner')
    def api_cogs_list():
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify([])
        loaded = set(bot.extensions.keys())
        all_files = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py') and f != 'embed_utils.py']
        result = []
        for name in sorted(all_files):
            ext = 'cogs.' + name
            result.append({'name': name, 'loaded': ext in loaded})
        return jsonify(result)

    @app.route('/api/cogs/load', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_cog_load():
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        name = (request.json or {}).get('name', '')
        try:
            asyncio.run_coroutine_threadsafe(bot.load_extension(name), bot.loop).result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/cogs/unload', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_cog_unload():
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        name = (request.json or {}).get('name', '')
        try:
            asyncio.run_coroutine_threadsafe(bot.unload_extension(name), bot.loop).result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/cogs/reload', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_cog_reload():
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        name = (request.json or {}).get('name', '')
        try:
            asyncio.run_coroutine_threadsafe(bot.reload_extension(name), bot.loop).result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/cogs/reload-all', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_cog_reload_all():
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        results = []
        for ext in list(bot.extensions.keys()):
            try:
                asyncio.run_coroutine_threadsafe(bot.reload_extension(ext), bot.loop).result(timeout=10)
                results.append({'name': ext, 'ok': True})
            except Exception as e:
                results.append({'name': ext, 'ok': False, 'error': str(e)})
        return jsonify({'ok': True, 'results': results})

    @app.route('/api/warn-config/<guild_id>', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_warn_config_get(guild_id):
        f = f'data/warn_config_{guild_id}.json'
        if not os.path.exists(f):
            return jsonify({'thresholds': [{'count':3,'action':'timeout','duration':10},{'count':5,'action':'ban','duration':0}]})
        with open(f, encoding='utf-8') as fp:
            return jsonify(json.load(fp))

    @app.route('/api/warn-config/<guild_id>', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_warn_config_save(guild_id):
        d = request.json or {}
        os.makedirs('data', exist_ok=True)
        with open(f'data/warn_config_{guild_id}.json', 'w', encoding='utf-8') as fp:
            json.dump(d, fp, indent=2, ensure_ascii=False)
        return jsonify({'ok': True})

    @app.route('/api/duty/<guild_id>', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_duty_data(guild_id):
        duty_f  = 'data/duty_log.json'
        pts_f   = f'data/duty_points.json'
        duty = {}
        pts  = {}
        if os.path.exists(duty_f):
            with open(duty_f, encoding='utf-8') as f: duty = json.load(f).get(guild_id, {})
        if os.path.exists(pts_f):
            with open(pts_f, encoding='utf-8') as f: pts = json.load(f).get(guild_id, {})
        return jsonify({'duty': duty, 'points': pts})

    @app.route('/api/afk/<guild_id>', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_afk_list(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify([])
        afk_cog = bot.get_cog('AFK')
        if not afk_cog: return jsonify([])
        guild_afk = afk_cog._afk.get(str(guild_id), {})
        result = []
        guild = bot.get_guild(int(guild_id))
        for uid, data in guild_afk.items():
            member = guild.get_member(int(uid)) if guild else None
            result.append({
                'id': uid,
                'name': member.display_name if member else uid,
                'avatar': str(member.display_avatar.url) if member else None,
                'reason': data.get('reason', 'AFK'),
                'since': data.get('since', '')
            })
        return jsonify(result)

    @app.route('/api/watchlist/<guild_id>', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_watchlist(guild_id):
        f = 'data/mod_data.json'
        if not os.path.exists(f): return jsonify([])
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
        wl = data.get('watchlist', {}).get(guild_id, {})
        result = []
        for uid, info in wl.items():
            result.append({'id': uid, 'name': info.get('added_by', uid), 'reason': info.get('reason',''), 'added_by': info.get('added_by',''), 'timestamp': info.get('timestamp','')})
        return jsonify(result)

    @app.route('/api/member-search/<guild_id>', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_member_search(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify([])
        q = request.args.get('q', '').lower().strip()
        if not q: return jsonify([])
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify([])
        results = []
        for m in guild.members:
            if q in m.name.lower() or q in m.display_name.lower() or q == str(m.id):
                results.append({'id': str(m.id), 'name': m.name, 'display_name': m.display_name, 'avatar': str(m.display_avatar.url)})
            if len(results) >= 20: break
        return jsonify(results)

    @app.route('/api/member-profile/<guild_id>/<user_id>', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_member_profile(guild_id, user_id):
        import web.app as _app; bot = _app.bot_instance
        result = {'id': user_id}
        if bot:
            guild = bot.get_guild(int(guild_id))
            if guild:
                m = guild.get_member(int(user_id))
                if m:
                    result.update({'name': m.name, 'display_name': m.display_name, 'avatar': str(m.display_avatar.url), 'joined_at': m.joined_at.isoformat() if m.joined_at else None, 'created_at': m.created_at.isoformat(), 'roles': [r.name for r in m.roles[1:]]})
        # Warninglar
        wf = 'data/warnings.json'
        if os.path.exists(wf):
            with open(wf, encoding='utf-8') as f: wdata = json.load(f)
            warns = wdata.get(guild_id, {}).get(user_id, [])
            result['warnings'] = warns
            result['warn_count'] = len(warns)
        # Mod geçmişi
        mf = 'data/mod_data.json'
        if os.path.exists(mf):
            with open(mf, encoding='utf-8') as f: mdata = json.load(f)
            case = [c for c in mdata.get('case', {}).get(guild_id, []) if str(c.get('user_id')) == str(user_id)]
            result['case'] = case
            result['case_count'] = len(case)
        return jsonify(result)

    @app.route('/api/my-profile', methods=['GET'])
    @login_required
    def api_my_profile():
        import web.app as _app; bot = _app.bot_instance
        username = session.get('username')
        result = {'username': username, 'display_name': username}
        # Участник verisi
        mf = 'data/members.json'
        if os.path.exists(mf):
            with open(mf, encoding='utf-8') as f: members = json.load(f)
            for uid, m in members.items():
                if m.get('username') == username:
                    result['discord_id'] = uid
                    result['avatar'] = m.get('avatar')
                    result['display_name'] = m.get('display_name', username)
                    break
        # Warninglar (tüm serverlardan)
        wf = 'data/warnings.json'
        all_warns = []
        if os.path.exists(wf) and result.get('discord_id'):
            with open(wf, encoding='utf-8') as f: wdata = json.load(f)
            for gid, users in wdata.items():
                all_warns.extend(users.get(result['discord_id'], []))
        result['warnings'] = all_warns
        # Bakiye (ilk server)
        if bot and result.get('discord_id'):
            for guild in bot.guilds:
                bf = f'data/balance_{guild.id}.json'
                if os.path.exists(bf):
                    with open(bf, encoding='utf-8') as f: bdata = json.load(f)
                    result['balance'] = bdata.get(result['discord_id'], {}).get('balance', 0)
                    break
        # Голос süresi
        if bot and result.get('discord_id'):
            for guild in bot.guilds:
                vf = f'data/voice_stats_{guild.id}.json'
                if os.path.exists(vf):
                    with open(vf, encoding='utf-8') as f: vdata = json.load(f)
                    result['voice_seconds'] = vdata.get('users', {}).get(result['discord_id'], {}).get('total_seconds', 0)
                    break
        # Davet sayısı
        if bot and result.get('discord_id'):
            for guild in bot.guilds:
                inf = f'data/invite_counts_{guild.id}.json'
                if os.path.exists(inf):
                    with open(inf, encoding='utf-8') as f: idata = json.load(f)
                    result['invites'] = idata.get(result['discord_id'], {}).get('total', 0)
                    break
        return jsonify(result)

    @app.route('/api/my-birthday/<guild_id>', methods=['GET'])
    @login_required
    def api_my_birthday_get(guild_id):
        username = session.get('username')
        mf = 'data/members.json'
        discord_id = None
        if os.path.exists(mf):
            with open(mf, encoding='utf-8') as f: members = json.load(f)
            for uid, m in members.items():
                if m.get('username') == username:
                    discord_id = uid; break
        if not discord_id: return jsonify({})
        bf = f'data/birthdays_{guild_id}.json'
        if not os.path.exists(bf): return jsonify({})
        with open(bf, encoding='utf-8') as f: bdata = json.load(f)
        return jsonify(bdata.get(discord_id, {}))

    @app.route('/api/my-birthday/<guild_id>', methods=['POST'])
    @login_required
    def api_my_birthday_save(guild_id):
        username = session.get('username')
        mf = 'data/members.json'
        discord_id = None
        if os.path.exists(mf):
            with open(mf, encoding='utf-8') as f: members = json.load(f)
            for uid, m in members.items():
                if m.get('username') == username:
                    discord_id = uid; break
        if not discord_id: return jsonify({'error': 'Пользователь bulunamadı'}), 404
        d = request.json or {}
        day, month, year = d.get('day'), d.get('month'), d.get('year')
        if not day or not month: return jsonify({'error': 'Gün ve ay zorunlu'}), 400
        os.makedirs('data', exist_ok=True)
        bf = f'data/birthdays_{guild_id}.json'
        bdata = {}
        if os.path.exists(bf):
            with open(bf, encoding='utf-8') as f: bdata = json.load(f)
        entry = {'date': f'{int(month):02d}-{int(day):02d}', 'name': username}
        if year: entry['year'] = int(year)
        bdata[discord_id] = entry
        with open(bf, 'w', encoding='utf-8') as f: json.dump(bdata, f, indent=2, ensure_ascii=False)
        return jsonify({'ok': True})

    @app.route('/api/birthdays/<guild_id>', methods=['GET'])
    @login_required
    def api_birthdays_list(guild_id):
        import web.app as _app; bot = _app.bot_instance
        bf = f'data/birthdays_{guild_id}.json'
        if not os.path.exists(bf): return jsonify([])
        with open(bf, encoding='utf-8') as f: bdata = json.load(f)
        from datetime import datetime as _dt
        now = _dt.utcnow()
        today_num = now.month * 100 + now.day
        result = []
        for uid, info in bdata.items():
            try:
                m, d = map(int, info['date'].split('-'))
                num = m * 100 + d
                diff = num - today_num
                if diff < 0: diff += 1200
                name = info.get('name', uid)
                if bot:
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        member = guild.get_member(int(uid))
                        if member: name = member.display_name
                result.append({'name': name, 'date': info['date'], 'diff': diff})
            except: pass
        result.sort(key=lambda x: x['diff'])
        return jsonify(result)

    @app.route('/api/giveaway/<guild_id>', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_giveaway_list(guild_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f):
            return jsonify([])
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
        result = []
        for gw_id, gw in data.items():
            result.append({
                'id': gw_id,
                'prize': gw.get('prize', '?'),
                'winners': gw.get('winners', 1),
                'status': gw.get('status', 'unknown'),
                'ends_at': gw.get('ends_at', ''),
                'participants': len(gw.get('participants', [])),
                'channel_id': gw.get('channel_id', ''),
            })
        result.sort(key=lambda x: x['ends_at'], reverse=True)
        return jsonify(result)

    @app.route('/api/giveaway/<guild_id>/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_giveaway_create(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, random
        from datetime import timedelta
        data_req = request.json or {}
        prize    = data_req.get('prize', '').strip()
        winners  = int(data_req.get('winners', 1))
        minutes  = int(data_req.get('minutes', 60))
        channel_id = data_req.get('channel_id', '')
        if not prize or not channel_id:
            return jsonify({'error': 'Eksik alan'}), 400

        if not bot:
            return jsonify({'error': 'Бот offline'}), 503

        guild = bot.get_guild(int(guild_id))
        if not guild:
            return jsonify({'error': 'Сервер bulunamadı'}), 404

        channel = guild.get_channel(int(channel_id))
        if not channel:
            return jsonify({'error': 'Канал bulunamadı'}), 404

        ends_at = datetime.utcnow() + timedelta(minutes=minutes)
        gw_id   = str(int(ends_at.timestamp()))

        async def _send():
            embed = discord.Embed(
                title="🎉  ÇEKİLİŞ BAŞLADI!",
                color=0x2ECC71,
                timestamp=ends_at
            )
            embed.description = (
                f"**🏆 Ödül:** `{prize}`\n\n"
                f"Katılmak için **🎉 Katıl** butonuna bas!\n"
                f"Giveaway <t:{int(ends_at.timestamp())}:R> sona eriyor."
            )
            embed.add_field(name="👥 Katılımcı", value=f"0/{winners}", inline=True)
            embed.add_field(name="🏆 Kazanan",   value=str(winners),   inline=True)
            embed.add_field(name="⏰ Bitiş",      value=f"<t:{int(ends_at.timestamp())}:F>", inline=True)
            embed.set_footer(text=f"{guild.name} • Giveaway Sistemi")

            from cogs.giveaway import GiveawayView
            view = GiveawayView(gw_id, guild_id)
            msg  = await channel.send(embed=embed, view=view)

            os.makedirs('data', exist_ok=True)
            f = f'data/giveaways_{guild_id}.json'
            gws = {}
            if os.path.exists(f):
                with open(f, encoding='utf-8') as fp:
                    gws = json.load(fp)
            gws[gw_id] = {
                'prize': prize, 'winners': winners,
                'ends_at': ends_at.isoformat(),
                'channel_id': str(channel.id),
                'message_id': str(msg.id),
                'status': 'active',
                'participants': [],
                'user_info': {},
            }
            with open(f, 'w', encoding='utf-8') as fp:
                json.dump(gws, fp, indent=2, ensure_ascii=False)

        asyncio.run_coroutine_threadsafe(_send(), bot.loop).result(timeout=10)
        return jsonify({'ok': True, 'id': gw_id})

    @app.route('/api/giveaway/<guild_id>/<gw_id>/end', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_giveaway_end(guild_id, gw_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f):
            return jsonify({'error': 'Не найдено'}), 404
        with open(f, encoding='utf-8') as fp:
            gws = json.load(fp)
        if gw_id not in gws:
            return jsonify({'error': 'Giveaway yok'}), 404
        gws[gw_id]['status'] = 'ended'
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(gws, fp, indent=2, ensure_ascii=False)
        return jsonify({'ok': True})

    @app.route('/api/giveaway/<guild_id>/<gw_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_giveaway_delete(guild_id, gw_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f):
            return jsonify({'ok': True})
        with open(f, encoding='utf-8') as fp:
            gws = json.load(fp)
        gws.pop(gw_id, None)
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(gws, fp, indent=2, ensure_ascii=False)
        return jsonify({'ok': True})

    @app.route('/api/guild/<guild_id>/info')
    @login_required
    def api_guild_info(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot:
            return jsonify({'error': 'Бот offline'})
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return jsonify({'error': 'Guild not found'})
        return jsonify({
            'id': str(guild.id),
            'name': guild.name,
            'description': guild.description or '',
            'icon': str(guild.icon.url) if guild.icon else None,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'banner': str(guild.banner.url) if guild.banner else None,
            'member_count': guild.member_count,
            'online_count': sum(1 for m in guild.members if m.status != discord.Status.offline),
            'бот_count': sum(1 for m in guild.members if m.bot),
            'channel_count': len(guild.channels),
            'role_count': len(guild.roles),
            'emoji_count': len(guild.emojis),
            'boost_level': guild.premium_tier,
            'boost_count': guild.premium_subscription_count,
            'created_at': guild.created_at.isoformat(),
            'owner_id': str(guild.owner_id),
            'verification_level': str(guild.verification_level),
            'features': list(guild.features),
        })

    @app.route('/api/бот-stats')
    @login_required
    def api_bot_stats():
        import time
        import web.app as _app; bot = _app.bot_instance
        if not bot:
            return jsonify({'error': 'Бот offline'})
        try:
            import psutil
            proc = psutil.Process()
            cpu = psutil.cpu_percent(interval=0.1)
            ram = round(proc.memory_info().rss / 1024 / 1024, 1)
            uptime_sec = int(time.time() - proc.create_time())
        except ImportError:
            cpu = 0
            ram = 0
            uptime_sec = 0
        h, m = divmod(uptime_sec // 60, 60)
        uptime = f"{h}sa {m}dk"
        history_file = 'data/sys_history.json'
        os.makedirs('data', exist_ok=True)
        history = []
        if os.path.exists(history_file):
            with open(history_file) as f:
                history = json.load(f)
        now = datetime.utcnow().strftime('%H:%M')
        history.append({'time': now, 'cpu': cpu, 'ram': ram})
        history = history[-20:]
        with open(history_file, 'w') as f:
            json.dump(history, f)
        return jsonify({
            'guilds': len(bot.guilds),
            'users': sum(g.member_count for g in bot.guilds),
            'latency': round(bot.latency * 1000),
            'uptime': uptime,
            'cpu': cpu,
            'ram': ram,
            'history': history,
            'guild_list': [{'name': g.name, 'members': g.member_count} for g in bot.guilds]
        })

    @app.route('/api/mod-history')
    @login_required
    @role_required('mod')
    def api_mod_history():
        import web.app as _app; bot = _app.bot_instance
        guild_id = request.args.get('guild_id')
        all_events = []

        # ── 1. mod_data.json — бот'un сохранитьtiği case'ler ────────────────────
        mod_file = 'data/mod_data.json'
        if os.path.exists(mod_file):
            try:
                with open(mod_file, 'r', encoding='utf-8') as fp:
                    md = json.load(fp)
                case = md.get('case', {})
                for gid, case_list in case.items():
                    if guild_id and gid != guild_id:
                        continue
                    if not isinstance(case_list, list):
                        continue
                    for case in case_list:
                        uid = str(case.get('user_id', ''))
                        mid = str(case.get('mod_id', ''))
                        all_events.append({
                            'guild_id':    gid,
                            'category':    'mod',
                            'action':      case.get('action', 'warn'),
                            'target_name': uid,
                            'target_id':   uid,
                            'mod_name':    mid,
                            'reason':      case.get('reason', 'Не указана'),
                            'created_at':  case.get('timestamp', ''),
                            'source':      'bot',
                        })
            except Exception as _e:
                print(f'[MOD-HISTORY] mod_data Ошибкаsı: {_e}')

        # ── 2. Discord Audit Cache ────────────────────────────────────────────
        cache_file = 'data/discord_audit_cache.json'
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as fp:
                    cache = json.load(fp)
                mod_cats = {'Бан', 'Бан Снят', 'Кик', 'Мут', 'Мут Снят',
                            'ban', 'kick', 'timeout', 'unban', 'warn', 'mute'}
                for gid, events in cache.items():
                    if guild_id and gid != guild_id:
                        continue
                    for ev in events:
                        if ev.get('action') in mod_cats:
                            ev['guild_id'] = gid
                            ev['created_at'] = ev.get('timestamp', '')
                            all_events.append(ev)
            except Exception as _e:
                print(f'[MOD-HISTORY] Cache okuma Ошибкаsı: {_e}')

        # ── 3. warnings.json ─────────────────────────────────────────────────
        warns_file = 'data/warnings.json'
        if os.path.exists(warns_file):
            try:
                with open(warns_file, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                for gid, guild_warns in data.items():
                    if guild_id and gid != guild_id:
                        continue
                    for uid, warns in guild_warns.items():
                        if not isinstance(warns, list):
                            continue
                        name = uid
                        if bot:
                            for g in bot.guilds:
                                m = g.get_member(int(uid)) if uid.isdigit() else None
                                if m:
                                    name = m.display_name
                                    break
                        for w in warns:
                            all_events.append({
                                'guild_id':    gid,
                                'category':    'mod',
                                'action':      'warn',
                                'target_name': name,
                                'target_id':   uid,
                                'mod_name':    w.get('mod', w.get('moderator', '?')),
                                'reason':      w.get('reason', ''),
                                'created_at':  w.get('timestamp', ''),
                                'source':      'bot',
                            })
            except Exception as _e:
                print(f'[MOD-HISTORY] Warnings Ошибкаsı: {_e}')

        all_events.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return jsonify(all_events[:500])

    @app.route('/api/guild/<guild_id>/roles')
    @login_required
    def api_guild_roles(guild_id):
        import web.app as _app
        bot = _app.bot_instance
        if not bot: return jsonify([])
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify([])
        roles = [{'id': str(r.id), 'name': r.name, 'color': str(r.color), 'members': len(r.members)}
                 for r in guild.roles if r.name != '@everyone']
        return jsonify(sorted(roles, key=lambda x: -x['members']))

    @app.route('/api/guild/<guild_id>/roles/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_create_role(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        async def do():
            guild = bot.get_guild(int(guild_id))
            color_hex = data.get('color', '#dc143c').lstrip('#')
            color = discord.Color(int(color_hex, 16))
            await guild.create_role(name=data['name'], color=color)
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/roles/<role_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_delete_role(guild_id, role_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'})
        async def do():
            guild = bot.get_guild(int(guild_id))
            role = guild.get_role(int(role_id))
            if role: await role.delete()
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/channels')
    @login_required
    def api_guild_channels(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import discord as _discord
        if not bot:
            print(f'[WEB][WARN] /channels: bot_instance is None')
            return jsonify({'error': 'Бот offline', 'channels': []})

        guild = bot.get_guild(int(guild_id))
        if not guild:
            for g in bot.guilds:
                if str(g.id) == str(guild_id):
                    guild = g
                    break
        if not guild:
            print(f'[WEB][WARN] /channels: guild {guild_id} not found. Бот guilds: {[str(g.id) for g in bot.guilds]}')
            return jsonify({'error': f'Guild {guild_id} not found', 'channels': []})

        type_map = {
            _discord.ChannelType.text: 'text',
            _discord.ChannelType.voice: 'voice',
            _discord.ChannelType.category: 'category',
            _discord.ChannelType.news: 'text',
            _discord.ChannelType.stage_voice: 'voice',
            _discord.ChannelType.forum: 'text',
        }

        channels_data = []
        try:
            for c in guild.channels:
                ch_type = type_map.get(c.type, str(c.type).split('.')[-1])
                channels_data.append({
                    'id': str(c.id),
                    'name': c.name,
                    'type': ch_type,
                    'position': getattr(c, 'position', 0),
                    'category': c.category.name if hasattr(c, 'category') and c.category else None,
                    'category_pos': c.category.position if hasattr(c, 'category') and c.category else -1
                })
        except Exception as e:
            print(f'[WEB][ERR] channels error: {e}')
            return jsonify({'error': str(e), 'channels': []})

        sorted_channels = sorted(channels_data, key=lambda x: (x['category_pos'], x['position']))
        print(f'[WEB] /channels guild={guild_id} returned {len(sorted_channels)} channels')
        return jsonify(sorted_channels)

    # ── AI API ───────────────────────────────────────────────────────────────

    @app.route('/api/ai/stream', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ai_stream():
        return jsonify({'error': 'AI sistemi devre dışı'}), 503

    @app.route('/api/ai/assistant', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ai_assistant():
        return jsonify({'error': 'AI sistemi devre dışı'}), 503

    @app.route('/api/ai/clear', methods=['POST'])
    @login_required
    def api_ai_clear():
        session.pop('ai_history', None)
        return jsonify({'ok': True})

    @app.route('/api/ai/announcement', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ai_announcement():
        return jsonify({'error': 'AI sistemi devre dışı'}), 503

    @app.route('/api/ai/mod-report', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_ai_mod_report():
        return jsonify({'error': 'AI sistemi devre dışı'}), 503

    @app.route('/api/ai/embed', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ai_embed():
        return jsonify({'error': 'AI sistemi devre dışı'}), 503

    # ── CHAT API ─────────────────────────────────────────────────────────────

    @app.route('/api/chat/<guild_id>/<channel_id>/messages')
    @login_required
    @role_required('owner')
    def api_chat_messages(guild_id, channel_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        channel = bot.get_channel(int(channel_id))
        if not channel: return jsonify({'error': 'Канал bulunamadı'}), 404
        async def _fetch():
            msgs = []
            async for m in channel.history(limit=50, oldest_first=False):
                msgs.append({
                    'id': str(m.id),
                    'content': m.content,
                    'author': m.author.display_name,
                    'author_id': str(m.author.id),
                    'avatar': str(m.author.display_avatar.url),
                    'bot': m.author.bot,
                    'timestamp': m.created_at.isoformat(),
                    'edited': m.edited_at.isoformat() if m.edited_at else None,
                    'attachments': [a.url for a in m.attachments],
                    'embeds': len(m.embeds) > 0,
                })
            return list(reversed(msgs))
        try:
            msgs = asyncio.run_coroutine_threadsafe(_fetch(), bot.loop).result(timeout=10)
            return jsonify(msgs)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/chat/<guild_id>/<channel_id>/send', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_chat_send(guild_id, channel_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        channel = bot.get_channel(int(channel_id))
        if not channel: return jsonify({'error': 'Канал bulunamadı'}), 404
        d = request.json or {}
        content = d.get('content', '').strip()
        if not content: return jsonify({'error': 'Сообщение boş'}), 400
        async def _send():
            await channel.send(content)
        try:
            asyncio.run_coroutine_threadsafe(_send(), bot.loop).result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/chat/<guild_id>/<channel_id>/delete/<message_id>', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_chat_delete(guild_id, channel_id, message_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        channel = bot.get_channel(int(channel_id))
        if not channel: return jsonify({'error': 'Канал bulunamadı'}), 404
        async def _delete():
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
        try:
            asyncio.run_coroutine_threadsafe(_delete(), bot.loop).result(timeout=10)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/chat/<guild_id>/members')
    @login_required
    @role_required('owner')
    def api_chat_members(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify([])
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify([])
        return jsonify([{
            'id': str(m.id),
            'name': m.display_name,
            'display_name': m.display_name,
            'avatar': str(m.display_avatar.url) if m.display_avatar else '',
            'mention': f'<@{m.id}>'
        } for m in guild.members if not m.bot][:200])

    # ── DM API ───────────────────────────────────────────────────────────────
    DM_LOG_FILE = 'data/dm_log.json'

    def _load_dm_log():
        if os.path.exists(DM_LOG_FILE):
            try:
                with open(DM_LOG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def _save_dm_log(data):
        os.makedirs('data', exist_ok=True)
        with open(DM_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @app.route('/api/dm/<guild_id>/recent')
    @login_required
    @role_required('mod')
    def api_dm_recent(guild_id):
        """Последний DM разговоры listele"""
        import web.app as _app; bot = _app.bot_instance
        log = _load_dm_log()
        result = []
        for uid, msgs in log.items():
            if not msgs: continue
            last = msgs[-1]
            name = uid
            if bot:
                for g in bot.guilds:
                    try:
                        m = g.get_member(int(uid))
                        if m: name = m.display_name; break
                    except: pass
            result.append({
                'id': uid,
                'name': name,
                'last_msg': last.get('content', '')[:50],
                'timestamp': last.get('timestamp', ''),
                'unread': 0,
            })
        result.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(result[:20])

    @app.route('/api/dm/<guild_id>/<user_id>/messages')
    @login_required
    @role_required('mod')
    def api_dm_messages(guild_id, user_id):
        log = _load_dm_log()
        msgs = log.get(user_id, [])
        return jsonify(msgs)

    @app.route('/api/dm/<guild_id>/<user_id>/send', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_dm_send(guild_id, user_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio as _asyncio, datetime as _dt2
        if not bot: return jsonify({'error': 'Бот offline'}), 503
        data = request.get_json() or {}
        content = data.get('content', '').strip()
        if not content: return jsonify({'error': 'Сообщение boş'}), 400

        async def do():
            user = await bot.fetch_user(int(user_id))
            await user.send(content)
            return str(user)

        try:
            username = _asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
            # Loğa сохранить
            log = _load_dm_log()
            if user_id not in log: log[user_id] = []
            log[user_id].append({
                'author': session.get('username', 'Панель'),
                'content': content,
                'timestamp': _dt2.datetime.utcnow().isoformat(),
                'from_бот': True,
            })
            _save_dm_log(log)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/guild/<guild_id>/channels/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_create_channel(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        async def do():
            guild = bot.get_guild(int(guild_id))
            t = data.get('type', 'text')
            if t == 'text': await guild.create_text_channel(data['name'])
            elif t == 'voice': await guild.create_voice_channel(data['name'])
            elif t == 'category': await guild.create_category(data['name'])
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/channels/<channel_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_delete_channel(guild_id, channel_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'})
        async def do():
            ch = bot.get_channel(int(channel_id))
            if ch: await ch.delete()
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/welcome-settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_welcome_settings(guild_id):
        f = f'data/welcome_{guild_id}.json'
        os.makedirs('data', exist_ok=True)  # Ensure data directory exists
        
        if request.method == 'GET':
            if not os.path.exists(f): 
                return jsonify({})
            try:
                with open(f, 'r', encoding='utf-8') as fp: 
                    return jsonify(json.load(fp))
            except Exception as e:
                print(f'[WEB][ERR] welcome-settings GET error: {e}')
                return jsonify({'error': str(e)})
                
        # POST request
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'})
                
            settings = {}
            if os.path.exists(f):
                with open(f, 'r', encoding='utf-8') as fp: 
                    settings = json.load(fp)
                    
            t = data.pop('type', None)
            if not t:
                return jsonify({'error': 'Type not specified'})
                
            settings[t] = data
            with open(f, 'w', encoding='utf-8') as fp: 
                json.dump(settings, fp, indent=2, ensure_ascii=False)
            print(f'[WEB] welcome-settings saved for guild {guild_id}, type {t}')
            return jsonify({'success': True})
        except Exception as e:
            print(f'[WEB][ERR] welcome-settings POST error: {e}')
            return jsonify({'error': str(e)})

    @app.route('/api/guild/<guild_id>/autorole', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_autorole(guild_id):
        f = f'data/autorole_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f):
                return jsonify({'member_roles': [], 'girl_roles': [], 'boy_roles': [], 'бот_roles': []})
            with open(f) as fp:
                data = json.load(fp)
            # Старый format uyumluluğu
            data.setdefault('girl_roles', [])
            data.setdefault('boy_roles', [])
            return jsonify(data)
        data = request.get_json()
        settings = {}
        if os.path.exists(f):
            with open(f, encoding='utf-8') as fp: settings = json.load(fp)
        # type -> key mapping
        key_map = {'member': 'member_roles', 'girl': 'girl_roles', 'boy': 'boy_roles', 'bot': 'бот_roles'}
        key = key_map.get(data.get('type'), data.get('type')+'_roles')
        settings[key] = data['roles']
        os.makedirs('data', exist_ok=True)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(settings, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/leveling', methods=['GET', 'POST'])
    @login_required
    @role_required('mod')
    def api_leveling(guild_id):
        f = f'data/leveling_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({'enabled': False, 'xp_min': 15, 'xp_max': 25})
            with open(f) as fp: return jsonify(json.load(fp))
        data = request.get_json()
        with open(f, 'w') as fp: json.dump(data, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/leaderboard')
    @login_required
    def api_leaderboard(guild_id):
        f = f'data/xp_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: data = json.load(fp)
        lb = sorted(data.values(), key=lambda x: x.get('xp', 0), reverse=True)
        return jsonify(lb[:20])

    @app.route('/api/guild/<guild_id>/economy', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_economy(guild_id):
        f = f'data/economy_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({'currency_name': 'Coin', 'currency_emoji': '💰', 'start_balance': 100, 'daily_reward': 50})
            with open(f) as fp: return jsonify(json.load(fp))
        data = request.get_json()
        with open(f, 'w') as fp: json.dump(data, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/economy/shop')
    @login_required
    def api_economy_shop(guild_id):
        f = f'data/shop_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(json.load(fp))

    @app.route('/api/guild/<guild_id>/economy/shop/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_economy_shop_add(guild_id):
        f = f'data/shop_{guild_id}.json'
        items = []
        if os.path.exists(f):
            with open(f) as fp: items = json.load(fp)
        data = request.get_json()
        data['id'] = str(int(datetime.utcnow().timestamp()))
        items.append(data)
        with open(f, 'w') as fp: json.dump(items, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/economy/shop/<item_id>/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_economy_shop_remove(guild_id, item_id):
        f = f'data/shop_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: items = json.load(fp)
        items = [i for i in items if i.get('id') != item_id]
        with open(f, 'w') as fp: json.dump(items, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/economy/rich')
    @login_required
    def api_economy_rich(guild_id):
        f = f'data/balance_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: data = json.load(fp)
        return jsonify(sorted(data.values(), key=lambda x: x.get('balance', 0), reverse=True)[:10])

    @app.route('/api/guild/<guild_id>/giveaways')
    @login_required
    def api_giveaways(guild_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/giveaways/create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_create_giveaway(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        gw_id = str(int(datetime.utcnow().timestamp()))
        from datetime import timedelta
        ends_at = (datetime.utcnow() + timedelta(minutes=data['duration'])).isoformat()
        f = f'data/giveaways_{guild_id}.json'
        gws = {}
        if os.path.exists(f):
            with open(f) as fp: gws = json.load(fp)
        gws[gw_id] = {
            'id': gw_id,
            'prize': data['prize'],
            'winners': data['winners'],
            'ends_at': ends_at,
            'status': 'active',
            'channel_id': data['channel_id'],
            'participants': [],
            'message_id': None
        }
        with open(f, 'w', encoding='utf-8') as fp: json.dump(gws, fp, indent=2, ensure_ascii=False)
        async def send():
            from cogs.giveaway import GiveawayView
            ch = bot.get_channel(int(data['channel_id']))
            if ch:
                end_ts = int(datetime.utcnow().timestamp()) + int(data['duration']) * 60
                embed = discord.Embed(
                    title='🎉 ✨ HARIKA BİR ÇEKİLİŞ BAŞLADI! ✨ 🎉',
                    description=(
                        f"\n🏆 **ÖDÜL:** `{data['prize']}`\n"
                        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎟️ **Katılmak İçin:** aşağıdaki 🎉 **`Katıl`** Butonuna Tıkla\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"\n⏳ **Bitiş Времяı:** <t:{end_ts}:R>\n"
                        f"📅 **Tam Время:** <t:{end_ts}:f>\n"
                        f"\n✅ Katılmak ОКen **ÜCRETSİZ** ve **AÇIK**!\n"
                        f"🍀 Şanslı ol ve **KAZAN**! 🍀\n"
                    ),
                    color=0xFFD700
                )
                embed.add_field(name='🏅 Kazanan Sayısı', value=f'**{data["winners"]} KİŞİ KAZANACAK!** 👑', inline=False)
                embed.add_field(name='👥 Şimdiki Katılımcı', value=f'**0/{data["winners"]}** 🔥', inline=True)
                embed.add_field(name='📊 Oranı', value='Открытьılıyor...', inline=True)
                embed.set_thumbnail(url='https://media.discordapp.net/attachments/1107038411895881788/1110305847399120916/gifty.gif')
                embed.set_image(url='https://media.discordapp.net/attachments/1107038411895881788/1110305847399120916/gifty.gif')
                embed.set_footer(text=f'🎯 Giveaway ID: {gw_id} | Sistem: Бот Giveaway v2')
                view = GiveawayView(gw_id, guild_id)
                msg = await ch.send(embed=embed, view=view)
                gws[gw_id]['message_id'] = str(msg.id)
                with open(f, 'w', encoding='utf-8') as fp:
                    json.dump(gws, fp, indent=2, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(send(), bot.loop)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/giveaways/<gw_id>/end', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_end_giveaway(guild_id, gw_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'error': 'Не найдено'})
        with open(f) as fp: gws = json.load(fp)
        if gw_id in gws:
            gws[gw_id]['status'] = 'ended'
            with open(f, 'w') as fp: json.dump(gws, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/giveaways/<gw_id>/join', methods=['POST'])
    @login_required
    def api_join_giveaway(guild_id, gw_id):
        f = f'data/giveaways_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'error': 'Giveaway bulunamadı'})
        with open(f) as fp: gws = json.load(fp)
        if gw_id not in gws: return jsonify({'error': 'Giveaway bulunamadı'})
        gw = gws[gw_id]
        if gw.get('status') != 'active': return jsonify({'error': 'Giveaway активен değil'})
        participants = gw.setdefault('participants', [])
        username = session.get('username', '')
        if username in participants: return jsonify({'error': 'Zaten katıldın!'})
        participants.append(username)
        with open(f, 'w') as fp: json.dump(gws, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/polls')
    @login_required
    def api_polls(guild_id):
        f = f'data/polls_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/polls/<poll_id>/vote', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_vote_poll(guild_id, poll_id):
        f = f'data/polls_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'error': 'Опрос bulunamadı'})
        with open(f, encoding='utf-8') as fp: polls = json.load(fp)
        if poll_id not in polls: return jsonify({'error': 'Опрос bulunamadı'})
        data = request.get_json()
        option_index = data.get('option_index', 0)
        poll = polls[poll_id]
        voters = poll.setdefault('voters', [])
        username = session.get('username', '')
        if username in voters: return jsonify({'error': 'Zaten oy verdin!'})
        if 0 <= option_index < len(poll['options']):
            poll['options'][option_index]['votes'] = poll['options'][option_index].get('votes', 0) + 1
            voters.append(username)
            with open(f, 'w', encoding='utf-8') as fp: json.dump(polls, fp, indent=2, ensure_ascii=False)
            return jsonify({'success': True})
        return jsonify({'error': 'Geçersiz выбратьenek'})

    @app.route('/api/guild/<guild_id>/polls/create', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_create_poll(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        poll_id = str(int(datetime.utcnow().timestamp()))
        f = f'data/polls_{guild_id}.json'
        polls = {}
        if os.path.exists(f):
            with open(f) as fp: polls = json.load(fp)
        entry = {'id': poll_id, 'question': data['question'], 'created_at': datetime.utcnow().isoformat(),
                 'options': [{'emoji': o['emoji'], 'text': o['text'], 'votes': 0} for o in data['options']]}
        polls[poll_id] = entry
        with open(f, 'w') as fp: json.dump(polls, fp, indent=2)
        async def send():
            ch = bot.get_channel(int(data['channel_id']))
            if ch:
                desc = '\n'.join([f"{o['emoji']} **{o['text']}**" for o in data['options']])
                embed = discord.Embed(title=f"📊 {data['question']}", description=desc, color=0xdc143c)
                embed.set_footer(text=f"Опрос ID: {poll_id}")
                msg = await ch.send(embed=embed)
                for o in data['options']:
                    try: await msg.add_reaction(o['emoji'])
                    except: pass
        asyncio.run_coroutine_threadsafe(send(), bot.loop)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/custom-commands')
    @login_required
    def api_custom_commands(guild_id):
        f = f'data/custom_cmds_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/custom-commands/create', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_create_custom_command(guild_id):
        data = request.get_json()
        f = f'data/custom_cmds_{guild_id}.json'
        cmds = {}
        if os.path.exists(f):
            with open(f) as fp: cmds = json.load(fp)
        cmd_id = str(int(datetime.utcnow().timestamp()))
        cmds[cmd_id] = {'id': cmd_id, 'trigger': data['trigger'], 'response': data['response'],
                        'type': data.get('type', 'text'), 'uses': 0, 'created_at': datetime.utcnow().isoformat()}
        with open(f, 'w') as fp: json.dump(cmds, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/custom-commands/<cmd_id>/delete', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_delete_custom_command(guild_id, cmd_id):
        f = f'data/custom_cmds_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: cmds = json.load(fp)
        cmds.pop(cmd_id, None)
        with open(f, 'w') as fp: json.dump(cmds, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/scheduled-messages')
    @login_required
    def api_scheduled_messages(guild_id):
        f = f'data/scheduled_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/scheduled-messages/create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_create_scheduled_message(guild_id):
        data = request.get_json()
        f = f'data/scheduled_{guild_id}.json'
        msgs = {}
        if os.path.exists(f):
            with open(f) as fp: msgs = json.load(fp)
        msg_id = str(int(datetime.utcnow().timestamp()))
        msgs[msg_id] = {'id': msg_id, 'channel_id': data['channel_id'], 'channel_name': '',
                        'content': data['content'], 'interval': data['interval'],
                        'next_run': data.get('start_time', datetime.utcnow().isoformat()),
                        'active': True, 'created_at': datetime.utcnow().isoformat()}
        with open(f, 'w') as fp: json.dump(msgs, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/scheduled-messages/<msg_id>/delete', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_delete_scheduled_message(guild_id, msg_id):
        f = f'data/scheduled_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: msgs = json.load(fp)
        msgs.pop(msg_id, None)
        with open(f, 'w') as fp: json.dump(msgs, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/member-notes')
    @login_required
    @role_required('mod')
    def api_all_member_notes():
        f = 'data/member_notes.json'
        if not os.path.exists(f): return jsonify([])
        try:
            with open(f, encoding='utf-8') as fp: data = json.load(fp)
        except (json.JSONDecodeError, ValueError):
            return jsonify([])
        return jsonify([{'id': k, 'name': v.get('name', k), 'avatar': v.get('avatar', ''), 'notes': v.get('notes', [])} for k, v in data.items() if v.get('notes')])

    @app.route('/api/member-notes/<member_id>')
    @login_required
    @role_required('mod')
    def api_member_notes(member_id):
        f = 'data/member_notes.json'
        if not os.path.exists(f): return jsonify([])
        try:
            with open(f, encoding='utf-8') as fp: data = json.load(fp)
        except (json.JSONDecodeError, ValueError):
            return jsonify([])
        return jsonify(data.get(member_id, {}).get('notes', []))

    @app.route('/api/member-notes/<member_id>/add', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_add_member_note(member_id):
        import web.app as _app; bot = _app.bot_instance
        f = 'data/member_notes.json'
        data = {}
        if os.path.exists(f):
            try:
                with open(f, encoding='utf-8') as fp: data = json.load(fp)
            except (json.JSONDecodeError, ValueError):
                data = {}
        if member_id not in data:
            name = member_id
            avatar = ''
            if bot:
                for g in bot.guilds:
                    m = g.get_member(int(member_id))
                    if m:
                        name = m.display_name
                        avatar = str(m.display_avatar.url)
                        break
            data[member_id] = {'name': name, 'avatar': avatar, 'notes': []}
        note = {'id': str(int(datetime.utcnow().timestamp())), 'text': request.get_json().get('text', ''),
                'author': session.get('username'), 'created_at': datetime.utcnow().isoformat()}
        data[member_id]['notes'].append(note)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(data, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/member-notes/<member_id>/<note_id>/delete', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_delete_member_note(member_id, note_id):
        f = 'data/member_notes.json'
        if not os.path.exists(f): return jsonify({'success': True})
        try:
            with open(f, encoding='utf-8') as fp: data = json.load(fp)
        except (json.JSONDecodeError, ValueError):
            return jsonify({'success': True})
        if member_id in data:
            data[member_id]['notes'] = [n for n in data[member_id]['notes'] if n['id'] != note_id]
        with open(f, 'w', encoding='utf-8') as fp: json.dump(data, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/purge', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_purge(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        result = {'count': 0}
        async def do():
            ch = bot.get_channel(int(data['channel_id']))
            if ch:
                deleted = await ch.purge(limit=int(data.get('count', 10)))
                result['count'] = len(deleted)
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=30)
        return jsonify({'success': True, 'count': result['count']})

    @app.route('/api/guild/<guild_id>/bulk-role', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_bulk_role(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        result = {'count': 0}
        async def do():
            guild = bot.get_guild(int(guild_id))
            target_role = guild.get_role(int(data['target_role']))
            action_role = guild.get_role(int(data['action_role']))
            if not target_role or not action_role: return
            for member in target_role.members:
                try:
                    if data['action'] == 'add': await member.add_roles(action_role)
                    else: await member.remove_roles(action_role)
                    result['count'] += 1
                except: pass
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=60)
        return jsonify({'success': True, 'count': result['count']})

    @app.route('/api/guild/<guild_id>/bulk-dm', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_bulk_dm(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        result = {'count': 0}
        async def do():
            guild = bot.get_guild(int(guild_id))
            role = guild.get_role(int(data['role_id']))
            if not role: return
            embed = discord.Embed(title="📢 Объявление", description=data['message'], color=0xdc143c)
            embed.set_footer(text="Aether Панель", icon_url=bot.user.display_avatar.url)
            for member in role.members:
                try: await member.send(embed=embed); result['count'] += 1
                except: pass
        asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=120)
        return jsonify({'success': True, 'count': result['count']})

    # ── WARN CONFIG API ───────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/warn-config', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_warn_config(guild_id):
        f = f'data/warn_config_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f):
                return jsonify({'steps': []})
            with open(f, 'r', encoding='utf-8') as fp:
                return jsonify(json.load(fp))
        data = request.get_json()
        os.makedirs('data', exist_ok=True)
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    # ── WARN DM AYARI ─────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/warn-dm', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_warn_dm(guild_id):
        f = f'data/warn_dm_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f):
                return jsonify({'message': ''})
            with open(f, 'r', encoding='utf-8') as fp:
                return jsonify(json.load(fp))
        data = request.get_json()
        os.makedirs('data', exist_ok=True)
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump({'message': data.get('message', '')}, fp, ensure_ascii=False)
        return jsonify({'success': True})

    # ── ANALYTICS API ─────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/analytics')
    @login_required
    def api_guild_analytics(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import collections, datetime as dt

        result = {
            'top_members': [], 'top_channels': [],
            'daily_labels': [], 'daily_messages': [],
            'member_labels': [], 'member_counts': []
        }

        # audit_log.json'dan message istatistikleri çek
        audit_file = 'data/audit_log.json'
        member_msg_counts = collections.Counter()
        channel_msg_counts = collections.Counter()
        daily_counts = collections.Counter()

        if os.path.exists(audit_file):
            try:
                with open(audit_file, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
            except Exception:
                data = {}
            events = data.get(guild_id, [])
            for ev in events:
                action = (ev.get('action') or '').lower()
                category = (ev.get('category') or '').lower()
                if category == 'message' and action == 'message yazıldı':
                    name = ev.get('user_name') or ev.get('user_id', '?')
                    member_msg_counts[name] += 1
                    ch = ev.get('channel') or ev.get('channel_name', '?')
                    channel_msg_counts[ch] += 1
                    ts = ev.get('timestamp', '')
                    if ts:
                        try:
                            day = ts[:10]
                            daily_counts[day] += 1
                        except Exception:
                            pass

        # Eğer audit_log'da message yoksa, message_logs dosyasına bak
        msg_log_file = f'data/message_logs_{guild_id}.json'
        if not member_msg_counts and os.path.exists(msg_log_file):
            with open(msg_log_file, 'r', encoding='utf-8') as fp:
                msgs = json.load(fp)
            for m in msgs:
                name = m.get('author') or m.get('user_name', '?')
                member_msg_counts[name] += 1
                ch = m.get('channel', '?')
                channel_msg_counts[ch] += 1
                ts = m.get('timestamp', '')
                if ts:
                    try:
                        daily_counts[ts[:10]] += 1
                    except Exception:
                        pass

        # Бот'tan gerçek vakitlı участник sayısı geçmişi
        if bot:
            guild = bot.get_guild(int(guild_id))
            if guild:
                # Eğer hiç message verisi yoksa, en azından участник listesini göster
                if not member_msg_counts:
                    # Участникleri role sayısına göre sırala (proxy olarak)
                    for m in list(guild.members)[:10]:
                        if not m.bot:
                            member_msg_counts[m.display_name] = len(m.roles)

        # Последний 7 день etiketleri
        today = dt.date.today()
        labels = [(today - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        result['daily_labels'] = [l[5:] for l in labels]  # MM-DD formatı
        result['daily_messages'] = [daily_counts.get(l, 0) for l in labels]

        # Top участникler
        result['top_members'] = [
            {'name': name, 'messages': count}
            for name, count in member_msg_counts.most_common(10)
        ]

        # Top channellar
        result['top_channels'] = [
            {'name': ch, 'messages': count}
            for ch, count in channel_msg_counts.most_common(10)
        ]

        # Участник büyümesi (son 7 день — statik veri, gerçek vakitlı değil)
        result['member_labels'] = result['daily_labels']
        if bot:
            guild = bot.get_guild(int(guild_id))
            mc = guild.member_count if guild else 0
        else:
            mc = 0
        result['member_counts'] = [max(0, mc - (6 - i) * 2) for i in range(7)]

        return jsonify(result)

    # ── HEALTH API ────────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/health')
    @login_required
    def api_guild_health(guild_id):
        import web.app as _app; bot = _app.bot_instance

        ban_count = 0
        kick_count = 0
        warn_count = 0
        spam_count = 0

        # mod_data.json
        mod_file = 'data/mod_data.json'
        if os.path.exists(mod_file):
            with open(mod_file, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            case = data.get('case', {}).get(guild_id, [])
            for c in case:
                a = (c.get('action') or '').lower()
                if 'ban' in a: ban_count += 1
                elif 'kick' in a: kick_count += 1
                elif 'warn' in a: warn_count += 1

        # warnings.json
        warns_file = 'data/warnings.json'
        if os.path.exists(warns_file):
            with open(warns_file, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            guild_warns = data.get(guild_id, {})
            for uid, ws in guild_warns.items():
                warn_count += len(ws)

        # audit_log'dan spam tespiti
        audit_file = 'data/audit_log.json'
        if os.path.exists(audit_file):
            try:
                with open(audit_file, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
            except Exception:
                data = {}
            for ev in data.get(guild_id, []):
                a = (ev.get('action') or '').lower()
                if 'spam' in a or 'automod' in a:
                    spam_count += 1

        # Оценка hesapla (100'den düş)
        score = 100
        score -= min(ban_count * 3, 30)
        score -= min(kick_count * 2, 20)
        score -= min(warn_count, 20)
        score -= min(spam_count, 15)
        score = max(0, score)

        if score >= 80:
            label = 'Mükemmel'
        elif score >= 60:
            label = 'İyi'
        elif score >= 40:
            label = 'Orta'
        else:
            label = 'Kötü'

        return jsonify({
            'score': score,
            'label': label,
            'ban_count': ban_count,
            'kick_count': kick_count,
            'warn_count': warn_count,
            'spam_count': spam_count
        })

    # ── VOICE STATS API ───────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/voice-stats')
    @login_required
    def api_voice_stats(guild_id):
        import web.app as _app; bot = _app.bot_instance

        leaderboard = []
        total_seconds = 0

        # voice_stats_<guild_id>.json dosyasını oku
        vs_file = f'data/voice_stats_{guild_id}.json'
        if os.path.exists(vs_file):
            with open(vs_file, 'r', encoding='utf-8') as fp:
                data = json.load(fp)

            users_dict = data.get('users', data) if isinstance(data, dict) else {}
            today_data = data.get('today', {}) if isinstance(data, dict) else {}

            for uid, entry in users_dict.items():
                if not isinstance(entry, dict):
                    continue
                secs = entry.get('total_seconds', entry.get('seconds', 0))
                if not secs:
                    # Старый format: minutes
                    secs = entry.get('minutes', 0) * 60
                total_seconds += secs

                # Имя ve avatar al
                name = entry.get('name', uid)
                avatar = entry.get('avatar', 'https://cdn.discordapp.com/embed/avatars/0.png')
                if bot:
                    for g in bot.guilds:
                        try:
                            m = g.get_member(int(uid))
                            if m:
                                name = m.display_name
                                avatar = str(m.display_avatar.url)
                                break
                        except Exception:
                            pass

                h, rem = divmod(int(secs), 3600)
                m_val, s_val = divmod(rem, 60)
                if h > 0:
                    time_str = f'{h}s {m_val}dk'
                elif m_val > 0:
                    time_str = f'{m_val}dk {s_val}sn'
                else:
                    time_str = f'{s_val}sn'

                leaderboard.append({
                    'name': name,
                    'avatar': avatar,
                    'seconds': secs,
                    'time': time_str
                })

        leaderboard.sort(key=lambda x: x['seconds'], reverse=True)

        # Всего süre formatla
        th, trem = divmod(total_seconds, 3600)
        tm, _ = divmod(trem, 60)
        total_str = f'{th}s {tm}dk' if th > 0 else f'{tm}dk'

        # Buдень VC kullanan (basit tahmin)
        today_users = len(today_data) if isinstance(today_data, dict) else sum(1 for u in leaderboard if u['seconds'] > 0)

        avg_secs = (total_seconds // len(leaderboard)) if leaderboard else 0
        ah, arem = divmod(avg_secs, 3600)
        am, _ = divmod(arem, 60)
        avg_str = f'{ah}s {am}dk' if ah > 0 else f'{am}dk'

        return jsonify({
            'leaderboard': leaderboard[:20],
            'total_time': total_str,
            'today_users': today_users,
            'avg_time': avg_str
        })

    # ── PANEL LOGS API ────────────────────────────────────────────────────────

    @app.route('/api/panel-logs')
    @login_required
    @role_required('admin')
    def api_panel_logs():
        f = 'data/panel_logs.json'
        if not os.path.exists(f):
            return jsonify([])
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                logs = json.load(fp)
            # En yeni önce
            return jsonify(list(reversed(logs)))
        except (json.JSONDecodeError, ValueError):
            return jsonify([])

    @app.route('/api/panel-logs/clear', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_clear_panel_logs():
        f = 'data/panel_logs.json'
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump([], fp)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/invite-tracker-full')
    @login_required
    @role_required('mod')
    def api_invite_tracker_full(guild_id):
        import web.app as _app; bot = _app.bot_instance
        result = {
            'total_invites': 0, 'total_joins': 0, 'total_leaves': 0,
            'active_invites': 0, 'leaderboard': [], 'recent_joins': [], 'invite_list': []
        }
        # Бот'tan canlı davet verisi çek
        if bot:
            import asyncio
            guild = bot.get_guild(int(guild_id))
            if guild:
                try:
                    invites_future = asyncio.run_coroutine_threadsafe(guild.invites(), bot.loop)
                    invites = invites_future.result(timeout=5)
                    result['active_invites'] = len(invites)
                    result['total_invites'] = sum(inv.uses or 0 for inv in invites)
                    # Davet listesi
                    result['invite_list'] = [{
                        'code': inv.code,
                        'inviter': inv.inviter.display_name if inv.inviter else '?',
                        'uses': inv.uses or 0,
                        'channel': inv.channel.name if inv.channel else '?'
                    } for inv in sorted(invites, key=lambda x: x.uses or 0, reverse=True)]
                    # Liderboard - kim kaç kişi davet etti
                    lb_map = {}
                    for inv in invites:
                        if inv.inviter:
                            uid = str(inv.inviter.id)
                            if uid not in lb_map:
                                lb_map[uid] = {
                                    'name': inv.inviter.display_name,
                                    'avatar': str(inv.inviter.display_avatar.url),
                                    'total': 0, 'joins': 0, 'leaves': 0, 'fake': 0
                                }
                            lb_map[uid]['total'] += inv.uses or 0
                            lb_map[uid]['joins'] += inv.uses or 0
                    result['leaderboard'] = sorted(lb_map.values(), key=lambda x: x['total'], reverse=True)[:20]
                except Exception:
                    pass
        # JSON dosyasından katılım geçmişi oku
        joins_file = f'data/invite_joins_{guild_id}.json'
        if os.path.exists(joins_file):
            with open(joins_file, 'r', encoding='utf-8') as fp:
                joins_data = json.load(fp)
            result['total_joins'] = len(joins_data)
            result['recent_joins'] = list(reversed(joins_data[-50:]))
            # Ayrılmaları da say
            leaves_file = f'data/invite_leaves_{guild_id}.json'
            if os.path.exists(leaves_file):
                with open(leaves_file, 'r', encoding='utf-8') as fp:
                    leaves_data = json.load(fp)
                result['total_leaves'] = len(leaves_data)
                # Liderboard'a ayrılmaları add
                for leave in leaves_data:
                    inviter = leave.get('inviter', '')
                    for lb in result['leaderboard']:
                        if lb['name'] == inviter:
                            lb['leaves'] += 1
                            break
        # Старый format uyumluluğu
        old_file = f'data/invites_{guild_id}.json'
        if os.path.exists(old_file) and not result['leaderboard']:
            with open(old_file) as fp:
                old = json.load(fp)
            result['leaderboard'] = old.get('leaderboard', [])
            result['total_joins'] = result['total_joins'] or old.get('total_joins', 0)
            result['total_leaves'] = result['total_leaves'] or old.get('total_leaves', 0)
        return jsonify(result)

    @app.route('/api/guild/<guild_id>/invite-tracker')
    @login_required
    @role_required('mod')
    def api_invite_tracker(guild_id):
        f = f'data/invites_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'total_invites': 0, 'total_joins': 0, 'total_leaves': 0, 'fake_invites': 0, 'leaderboard': []})
        with open(f) as fp: return jsonify(json.load(fp))

    @app.route('/api/guild/<guild_id>/suggestions')
    @login_required
    @role_required('mod')
    def api_suggestions(guild_id):
        f = f'data/suggestions_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/suggestions/<sug_id>/review', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_review_suggestion(guild_id, sug_id):
        f = f'data/suggestions_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'error': 'Не найдено'})
        with open(f) as fp: data = json.load(fp)
        if sug_id in data:
            data[sug_id]['status'] = 'approved' if request.get_json().get('action') == 'approve' else 'rejected'
            with open(f, 'w') as fp: json.dump(data, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/suggestions/channel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_suggestions_channel(guild_id):
        f = f'data/sug_settings_{guild_id}.json'
        with open(f, 'w') as fp: json.dump(request.get_json(), fp)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/starboard')
    @login_required
    @role_required('mod')
    def api_starboard(guild_id):
        import web.app as _app; bot = _app.bot_instance
        f = f'data/starboard_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
        
        # Бот'tan message detaylarını çek
        result = []
        if bot:
            guild = bot.get_guild(int(guild_id))
            if guild:
                import asyncio
                for msg_id, entry in data.items():
                    try:
                        # Сообщениеı найти
                        for channel in guild.text_channels:
                            try:
                                msg_future = asyncio.run_coroutine_threadsafe(
                                    channel.fetch_message(int(msg_id)), 
                                    bot.loop
                                )
                                msg = msg_future.result(timeout=2)
                                result.append({
                                    'id': msg_id,
                                    'count': entry.get('stars', 0),
                                    'content': msg.content[:200] if msg.content else '',
                                    'author': msg.author.display_name,
                                    'channel': channel.name,
                                    'jump_url': msg.jump_url,
                                    'created_at': entry.get('created_at', '')
                                })
                                break
                            except:
                                continue
                    except:
                        # Сообщение bulunamadı, sadece регистрацияlı veriyi göster
                        result.append({
                            'id': msg_id,
                            'count': entry.get('stars', 0),
                            'content': '',
                            'author': '?',
                            'channel': '?',
                            'jump_url': '',
                            'created_at': entry.get('created_at', '')
                        })
        
        # Yıldız sayısına göre sırala
        result.sort(key=lambda x: x['count'], reverse=True)
        return jsonify(result)

    @app.route('/api/guild/<guild_id>/starboard/settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_starboard_settings(guild_id):
        f = f'data/starboard_settings_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({'min_stars': 3})
            with open(f) as fp: return jsonify(json.load(fp))
        with open(f, 'w') as fp: json.dump(request.get_json(), fp)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/reaction-roles')
    @login_required
    def api_reaction_roles(guild_id):
        f = f'data/rr_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/reaction-roles/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_create_reaction_role(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        rr_id = str(int(datetime.utcnow().timestamp()))
        f = f'data/rr_{guild_id}.json'
        rrs = {}
        if os.path.exists(f):
            with open(f) as fp: rrs = json.load(fp)
        guild = bot.get_guild(int(guild_id))
        entries_with_names = []
        for e in data.get('entries', []):
            role = guild.get_role(int(e['role_id'])) if guild else None
            entries_with_names.append({'emoji': e['emoji'], 'role_id': e['role_id'], 'role_name': role.name if role else e['role_id']})
        rrs[rr_id] = {'id': rr_id, 'title': data['title'], 'channel_id': data['channel_id'], 'entries': entries_with_names}
        with open(f, 'w') as fp: json.dump(rrs, fp, indent=2)
        async def send():
            ch = bot.get_channel(int(data['channel_id']))
            if ch:
                desc = '\n'.join([f"{e['emoji']} → **{e['role_name']}**" for e in entries_with_names])
                embed = discord.Embed(title=data['title'], description=desc, color=0xdc143c)
                msg = await ch.send(embed=embed)
                for e in entries_with_names:
                    try: await msg.add_reaction(e['emoji'])
                    except: pass
                rrs[rr_id]['message_id'] = str(msg.id)
                with open(f, 'w') as fp2: json.dump(rrs, fp2, indent=2)
        asyncio.run_coroutine_threadsafe(send(), bot.loop)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/reaction-roles/<rr_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_delete_reaction_role(guild_id, rr_id):
        f = f'data/rr_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: rrs = json.load(fp)
        rrs.pop(rr_id, None)
        with open(f, 'w') as fp: json.dump(rrs, fp, indent=2)
        return jsonify({'success': True})

    # ── YENİ SAYFALAR ─────────────────────────────────────────────────────────

    @app.route('/ticket-settings')
    @login_required
    @role_required('admin')
    def ticket_settings_page():
        return render_template('ticket_settings.html', role=session.get('role'), username=session.get('username'))

    @app.route('/automod-settings')
    @login_required
    @role_required('admin')
    def automod_settings_page():
        return render_template('automod_settings.html', role=session.get('role'), username=session.get('username'))

    @app.route('/antiraid')
    @login_required
    @role_required('owner')
    def antiraid_page():
        return render_template('antiraid.html', role=session.get('role'), username=session.get('username'))

    @app.route('/backup')
    @login_required
    @role_required('owner')
    def backup_page():
        return render_template('backup.html', role=session.get('role'), username=session.get('username'))

    @app.route('/panel-logs')
    @login_required
    @role_required('admin')
    def panel_logs_page():
        return render_template('panel_logs.html', role=session.get('role'), username=session.get('username'))

    @app.route('/message-logs')
    @login_required
    @role_required('mod')
    def message_logs_page():
        return render_template('message_logs.html', role=session.get('role'), username=session.get('username'))

    @app.route('/voice-stats')
    @login_required
    @role_required('mod')
    def voice_stats_page():
        return render_template('voice_stats.html', role=session.get('role'), username=session.get('username'))

    @app.route('/todo')
    @login_required
    @role_required('owner')
    def todo_page():
        return render_template('todo.html', role=session.get('role'), username=session.get('username'))

    @app.route('/color-roles')
    @login_required
    @role_required('owner')
    def color_roles_page():
        return render_template('color_roles.html', role=session.get('role'), username=session.get('username'))

    @app.route('/rules-editor')
    @login_required
    @role_required('admin')
    def rules_editor_page():
        return render_template('rules_editor.html', role=session.get('role'), username=session.get('username'))
        
    # ── API ROUTES ───────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/ticket-settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_ticket_settings(guild_id):
        f = f'data/ticket_settings_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({})
            with open(f) as fp: return jsonify(json.load(fp))
        data = request.get_json()
        with open(f, 'w') as fp: json.dump(data, fp, indent=2)
        # Панель messageı отправить
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        from cogs.ticket import TicketView
        panel_sent = False
        panel_error = None
        if bot and data.get('ticket_channel_id'):
            async def send_panel():
                ch = bot.get_channel(int(data['ticket_channel_id']))
                if not ch:
                    raise ValueError(f"Канал bulunamadı: {data['ticket_channel_id']}")
                embed = discord.Embed(
                    title=data.get('title', '🎫  DESTEK SİSTEMİ'),
                    description=(
                        data.get('description',
                            "Серверmuzda bir sorunla mı karşılaştın?\n"
                            "Bir şey mi sormak istiyorsun?\n\n"
                            "**Нажмите кнопку нижеyarak** özel bir destek channelı создатьabilirsin.\n"
                            "🤖 **AI Asistan** ilk olarak sana yardımcı olacak!\n"
                            "Gerekirse ekibimiz devralacak. 💙\n\n"
                            "```yaml\n🤖 AI Destek  •  ⚡ Hızlı yanıt  •  🔒 Секретный channel\n```"
                        )
                    ),
                    color=0x5865F2
                )
                embed.set_footer(
                    text=f"{ch.guild.name} • Destek Sistemi",
                    icon_url=ch.guild.icon.url if ch.guild.icon else None
                )
                await ch.send(embed=embed, view=TicketView())
            try:
                future = asyncio.run_coroutine_threadsafe(send_panel(), bot.loop)
                future.result(timeout=10)  # 10 saniye badd, Ошибка varsa yakala
                panel_sent = True
            except Exception as ex:
                panel_error = str(ex)
        return jsonify({'success': True, 'panel_sent': panel_sent, 'error': panel_error})

    @app.route('/api/guild/<guild_id>/tickets')
    @login_required
    @role_required('mod')
    def api_tickets(guild_id):
        f = f'data/tickets_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/tickets/<ticket_id>/close', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_close_ticket(guild_id, ticket_id):
        f = f'data/tickets_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: tickets = json.load(fp)
        if ticket_id in tickets:
            tickets[ticket_id]['status'] = 'closed'
            with open(f, 'w') as fp: json.dump(tickets, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/automod', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_automod_settings(guild_id):
        f = f'data/automod_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({'banned_words': []})
            with open(f) as fp: return jsonify(json.load(fp))
        data = request.get_json()
        # Mevcut config'i oku ve merge et (hiçbir alan kaybolmasın)
        existing = {}
        if os.path.exists(f):
            try:
                with open(f, encoding='utf-8') as fp: existing = json.load(fp)
            except Exception: pass
        existing.update(data)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(existing, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/backup', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_create_backup(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify({'error': 'Бот offline'})
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify({'error': 'Сервер bulunamadı'})
        data = request.get_json()
        backup = {'guild_name': guild.name, 'guild_id': str(guild.id),
                  'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'), 'size': '0 KB'}
        if data.get('roles'):
            backup['roles'] = [{'name': r.name, 'color': str(r.color), 'permissions': r.permissions.value,
                                 'hoist': r.hoist, 'mentionable': r.mentionable} for r in guild.roles if r.name != '@everyone']
        if data.get('channels'):
            backup['channels'] = [{'name': c.name, 'type': str(c.type), 'position': c.position,
                                    'topic': getattr(c, 'topic', None)} for c in guild.channels]
        if data.get('settings'):
            backup['settings'] = {'name': guild.name, 'description': guild.description,
                                   'verification_level': str(guild.verification_level)}
        backup_id = str(int(datetime.utcnow().timestamp()))
        backup['id'] = backup_id
        import sys
        backup['size'] = f"{round(sys.getsizeof(json.dumps(backup)) / 1024, 1)} KB"
        f = 'data/backups.json'
        os.makedirs('data', exist_ok=True)
        backups = []
        if os.path.exists(f):
            try:
                with open(f, encoding='utf-8') as fp: backups = json.load(fp)
            except (json.JSONDecodeError, ValueError):
                backups = []
        backups.append(backup)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(backups, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True, 'id': backup_id})

    @app.route('/api/backups')
    @login_required
    @role_required('admin')
    def api_list_backups():
        f = 'data/backups.json'
        if not os.path.exists(f): return jsonify([])
        try:
            with open(f, encoding='utf-8') as fp: return jsonify(json.load(fp))
        except (json.JSONDecodeError, ValueError):
            return jsonify([])

    @app.route('/api/backups/<backup_id>/download')
    @login_required
    @role_required('admin')
    def api_download_backup(backup_id):
        from flask import send_file
        import io
        f = 'data/backups.json'
        if not os.path.exists(f): return jsonify({'error': 'Не найдено'})
        try:
            with open(f, encoding='utf-8') as fp: backups = json.load(fp)
        except (json.JSONDecodeError, ValueError):
            return jsonify({'error': 'Backup dosyası bozuk'})
        backup = next((b for b in backups if b.get('id') == backup_id), None)
        if not backup: return jsonify({'error': 'Не найдено'})
        buf = io.BytesIO(json.dumps(backup, indent=2, ensure_ascii=False).encode())
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"backup_{backup_id}.json", mimetype='application/json')

    @app.route('/api/backups/<backup_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_delete_backup(backup_id):
        f = 'data/backups.json'
        if not os.path.exists(f): return jsonify({'success': True})
        try:
            with open(f, encoding='utf-8') as fp: backups = json.load(fp)
        except (json.JSONDecodeError, ValueError):
            return jsonify({'success': True})
        backups = [b for b in backups if b.get('id') != backup_id]
        with open(f, 'w', encoding='utf-8') as fp: json.dump(backups, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/restore', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_restore_backup(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify({'error': 'Hedef server bulunamadı'})

        # JSON dosyası upload mu yoksa backup_id mi?
        backup_data = None
        if request.content_type and 'multipart' in request.content_type:
            f = request.files.get('file')
            if not f: return jsonify({'error': 'Dosya bulunamadı'})
            try:
                backup_data = json.loads(f.read().decode('utf-8'))
            except Exception:
                return jsonify({'error': 'Geçersiz JSON dosyası'})
        else:
            data = request.get_json()
            backup_id = data.get('backup_id')
            bf = 'data/backups.json'
            if not os.path.exists(bf): return jsonify({'error': 'Yedek bulunamadı'})
            try:
                with open(bf, encoding='utf-8') as fp: backups = json.load(fp)
            except Exception:
                return jsonify({'error': 'Yedek dosyası bozuk'})
            backup_data = next((b for b in backups if b.get('id') == backup_id), None)
            if not backup_data: return jsonify({'error': 'Yedek bulunamadı'})

        result = {'roles_created': 0, 'channels_created': 0, 'errors': []}

        async def do_restore():
            # Ролиi uygula
            if 'roles' in backup_data:
                existing_role_names = [r.name.lower() for r in guild.roles]
                for role_data in backup_data['roles']:
                    if role_data['name'].lower() in existing_role_names:
                        continue
                    try:
                        color_str = role_data.get('color', '#000000').lstrip('#')
                        color = discord.Color(int(color_str, 16)) if color_str and color_str != '000000' else discord.Color.default()
                        await guild.create_role(
                            name=role_data['name'],
                            color=color,
                            hoist=role_data.get('hoist', False),
                            mentionable=role_data.get('mentionable', False),
                            permissions=discord.Permissions(role_data.get('permissions', 0))
                        )
                        result['roles_created'] += 1
                        await asyncio.sleep(0.5)  # rate limit
                    except Exception as e:
                        result['errors'].append(f"Role '{role_data['name']}': {str(e)}")

            # Каналları uygula
            if 'channels' in backup_data:
                existing_ch_names = [c.name.lower() for c in guild.channels]
                for ch_data in backup_data['channels']:
                    if ch_data['name'].lower() in existing_ch_names:
                        continue
                    try:
                        ch_type = ch_data.get('type', 'text')
                        if 'text' in ch_type:
                            await guild.create_text_channel(
                                name=ch_data['name'],
                                topic=ch_data.get('topic')
                            )
                        elif 'voice' in ch_type:
                            await guild.create_voice_channel(name=ch_data['name'])
                        elif 'category' in ch_type:
                            await guild.create_category(name=ch_data['name'])
                        result['channels_created'] += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        result['errors'].append(f"Канал '{ch_data['name']}': {str(e)}")

        asyncio.run_coroutine_threadsafe(do_restore(), bot.loop).result(timeout=120)
        return jsonify({'success': True, 'result': result})

    @app.route('/api/guild/<guild_id>/message-logs')
    @login_required
    @role_required('mod')
    def api_message_logs(guild_id):
        audit_file = 'data/audit_log.json'
        if not os.path.exists(audit_file):
            return jsonify([])
        try:
            with open(audit_file, 'r', encoding='utf-8') as fp:
                all_data = json.load(fp)
        except Exception:
            return jsonify([])
        events = all_data.get(str(guild_id), [])
        # Sadece message kategorisi
        msg_type = request.args.get('type')  # 'deleted' veya 'edited'
        result = []
        for ev in events:
            if ev.get('category') != 'message':
                continue
            action = ev.get('action', '').lower()
            if msg_type == 'deleted' and 'удалить' not in action and 'delete' not in action:
                continue
            if msg_type == 'edited' and 'düzenl' not in action and 'edit' not in action:
                continue
            result.append(ev)
        result.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(result[:300])

    @app.route('/api/restore-upload', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_restore_upload():
        """Upload edilen JSON'dan backup_data döndür (önizleme için)"""
        f = request.files.get('file')
        if not f: return jsonify({'error': 'Dosya yok'})
        try:
            data = json.loads(f.read().decode('utf-8'))
            return jsonify({
                'guild_name': data.get('guild_name', '?'),
                'created_at': data.get('created_at', '?'),
                'roles_count': len(data.get('roles', [])),
                'channels_count': len(data.get('channels', [])),
                'has_settings': 'settings' in data,
                'raw': data
            })
        except Exception as e:
            return jsonify({'error': f'Geçersiz dosya: {str(e)}'})

    @app.route('/api/tasks')
    @login_required
    @role_required('mod')
    def api_get_tasks():
        f = 'data/tasks.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/tasks', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_create_task():
        data = request.get_json()
        f = 'data/tasks.json'
        os.makedirs('data', exist_ok=True)
        tasks = {}
        if os.path.exists(f):
            with open(f) as fp: tasks = json.load(fp)
        task_id = str(int(datetime.utcnow().timestamp()))
        tasks[task_id] = {'id': task_id, 'title': data['title'], 'assigned_to': data.get('assigned_to', ''),
                          'priority': data.get('priority', 'medium'), 'status': 'pending',
                          'created_by': session.get('username'), 'created_at': datetime.utcnow().isoformat()}
        with open(f, 'w') as fp: json.dump(tasks, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/tasks/<task_id>', methods=['PATCH'])
    @login_required
    @role_required('mod')
    def api_update_task(task_id):
        f = 'data/tasks.json'
        if not os.path.exists(f): return jsonify({'error': 'Не найдено'})
        with open(f) as fp: tasks = json.load(fp)
        if task_id in tasks:
            tasks[task_id].update(request.get_json())
            with open(f, 'w') as fp: json.dump(tasks, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/tasks/<task_id>/delete', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_delete_task(task_id):
        f = 'data/tasks.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f) as fp: tasks = json.load(fp)
        tasks.pop(task_id, None)
        with open(f, 'w') as fp: json.dump(tasks, fp, indent=2)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/rules', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_rules(guild_id):
        f = f'data/rules_{guild_id}.json'
        os.makedirs('data', exist_ok=True)
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify([])
            with open(f, encoding='utf-8') as fp: return jsonify(json.load(fp))
        rules = request.get_json(force=True, удалитьent=True)
        if rules is None: rules = []
        with open(f, 'w', encoding='utf-8') as fp: json.dump(rules, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/rules/publish', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_publish_rules(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        async def send():
            ch = bot.get_channel(int(data['channel_id']))
            if ch:
                desc = '\n'.join([f"**{i+1}.** {r}" for i, r in enumerate(data['rules'])])
                embed = discord.Embed(title="📜 Сервер Kuralları", description=desc, color=0xdc143c)
                embed.set_footer(text="Kuralları ihlal edenler cezalandırılır.")
                await ch.send(embed=embed)
        asyncio.run_coroutine_threadsafe(send(), bot.loop).result(timeout=10)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/color-roles', methods=['GET'])
    @login_required
    def api_color_roles(guild_id):
        f = f'data/color_roles_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f) as fp: return jsonify(json.load(fp))

    @app.route('/api/guild/<guild_id>/color-roles/publish', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_publish_color_roles(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        f = f'data/color_roles_{guild_id}.json'
        with open(f, 'w') as fp: json.dump(data.get('colors', []), fp, indent=2)
        async def send():
            guild = bot.get_guild(int(guild_id))
            ch = bot.get_channel(int(data['channel_id']))
            if not guild or not ch: return
            for c in data.get('colors', []):
                role = discord.utils.get(guild.roles, name=f"🎨 {c['name']}")
                if not role:
                    color_hex = c['hex'].lstrip('#')
                    role = await guild.create_role(name=f"🎨 {c['name']}", color=discord.Color(int(color_hex, 16)))
            desc = '\n'.join([f"{c.get('emoji','🎨')} **{c['name']}** — `{c['hex']}`" for c in data.get('colors', [])])
            embed = discord.Embed(title="🎨 Цвет Ролиi", description=desc + "\n\nİstediğin rengi almak için `/color` командаunu kullan!", color=0xdc143c)
            await ch.send(embed=embed)
        asyncio.run_coroutine_threadsafe(send(), bot.loop)
        return jsonify({'success': True})

    @app.route('/api/guild/<guild_id>/antiraid', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_antiraid_settings(guild_id):
        f = f'data/antiraid_{guild_id}.json'
        if request.method == 'GET':
            if not os.path.exists(f): return jsonify({'whitelist': [], 'recent_events': []})
            with open(f) as fp: return jsonify(json.load(fp))
        data = request.get_json()
        existing = {}
        if os.path.exists(f):
            with open(f) as fp: existing = json.load(fp)
        data['recent_events'] = existing.get('recent_events', [])
        with open(f, 'w') as fp: json.dump(data, fp, indent=2)
        return jsonify({'success': True})

    # ── ROZET API ────────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/badges')
    @login_required
    @role_required('mod')
    def api_guild_badges(guild_id):
        f = f'data/badges_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        result = []
        for uid, u in data.items():
            if u.get('badges'):
                result.append({'user_id': uid, 'name': u.get('name', uid), 'badges': u['badges'], 'messages': u.get('messages', 0)})
        result.sort(key=lambda x: len(x['badges']), reverse=True)
        return jsonify(result[:50])

    # ── COG YÖNETİMİ API ─────────────────────────────────────────────────────

    @app.route('/api/cogs')
    @login_required
    @role_required('owner')
    def api_cogs():
        import web.app as _app; bot = _app.bot_instance
        import os
        all_cogs = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
        loaded = [ext.split('.')[-1] for ext in (bot.extensions if bot else [])]
        return jsonify([{
            'name': c,
            'loaded': c in loaded
        } for c in sorted(all_cogs)])

    @app.route('/api/cogs/<cog_name>/reload', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_reload_cog(cog_name):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'})
        async def do():
            if f'cogs.{cog_name}' in бот.extensions:
                await бот.reload_extension(f'cogs.{cog_name}')
            else:
                await bot.load_extension(f'cogs.{cog_name}')
        try:
            asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)})

    @app.route('/api/cogs/<cog_name>/unload', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_unload_cog(cog_name):
        import web.app as _app; bot = _app.bot_instance
        import asyncio
        if not bot: return jsonify({'error': 'Бот offline'})
        if cog_name == 'cog_manager':
            return jsonify({'error': 'Bu cog убратьılamaz!'})
        async def do():
            await бот.unload_extension(f'cogs.{cog_name}')
        try:
            asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)})

    # ── SUNUCU BİLGİSİ API ───────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/info2')
    @login_required
    @role_required('mod')
    def api_guild_info2(guild_id):
        import web.app as _app; bot = _app.bot_instance
        if not bot: return jsonify({'error': 'Бот offline'})
        guild = bot.get_guild(int(guild_id))
        if not guild: return jsonify({'error': 'Сервер bulunamadı'})
        return jsonify({
            'id': str(guild.id),
            'name': guild.name,
            'description': guild.description or '',
            'icon': str(guild.icon.url) if guild.icon else None,
            'banner': str(guild.banner.url) if guild.banner else None,
            'splash': str(guild.splash.url) if guild.splash else None,
            'member_count': guild.member_count,
            'online_count': sum(1 for m in guild.members if m.status != discord.Status.offline),
            'бот_count': sum(1 for m in guild.members if m.bot),
            'channel_count': len(guild.channels),
            'role_count': len(guild.roles),
            'emoji_count': len(guild.emojis),
            'boost_level': guild.premium_tier,
            'boost_count': guild.premium_subscription_count,
            'created_at': guild.created_at.isoformat(),
            'owner_id': str(guild.owner_id),
            'verification_level': str(guild.verification_level),
            'features': list(guild.features),
        })

    # ── ETKİNLİKLER API ──────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/events')
    @login_required
    @role_required('mod')
    def api_guild_events(guild_id):
        f = f'data/events_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        events = list(data.values())
        events.sort(key=lambda x: x.get('time', ''))
        return jsonify(events)

    @app.route('/api/guild/<guild_id>/events/<event_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_delete_event(guild_id, event_id):
        f = f'data/events_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'success': True})
        with open(f, 'r', encoding='utf-8') as fp: data = json.load(fp)
        data.pop(event_id, None)
        with open(f, 'w', encoding='utf-8') as fp: json.dump(data, fp, indent=2, ensure_ascii=False)
        return jsonify({'success': True})

    # ── DOĞUM GÜNÜ API ───────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/birthdays')
    @login_required
    @role_required('mod')
    def api_birthdays(guild_id):
        f = f'data/birthdays_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f, 'r', encoding='utf-8') as fp: data = json.load(fp)
        return jsonify([{'user_id': k, **v} for k, v in data.items()])

    # ── WEBHOOK API ──────────────────────────────────────────────────────────

    @app.route('/api/guild/<guild_id>/webhooks')
    @login_required
    @role_required('admin')
    def api_guild_webhooks(guild_id):
        f = f'data/webhooks_{guild_id}.json'
        if not os.path.exists(f): return jsonify([])
        with open(f, 'r', encoding='utf-8') as fp: return jsonify(list(json.load(fp).values()))

    @app.route('/api/guild/<guild_id>/webhooks/send', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_send_webhook_v2(guild_id):
        import web.app as _app; bot = _app.bot_instance
        import asyncio, discord as _discord
        if not bot: return jsonify({'error': 'Бот offline'})
        data = request.get_json()
        wh_id = data.get('webhook_id')
        message = data.get('message', '')
        username = data.get('username', 'Aether')
        f = f'data/webhooks_{guild_id}.json'
        if not os.path.exists(f): return jsonify({'error': 'Webhook bulunamadı'})
        with open(f, 'r', encoding='utf-8') as fp: whs = json.load(fp)
        if wh_id not in whs: return jsonify({'error': 'Webhook bulunamadı'})
        wh_data = whs[wh_id]
        async def do():
            channel = bot.get_channel(int(wh_data['channel_id']))
            if channel:
                webhooks = await channel.webhooks()
                wh = _discord.utils.get(webhooks, id=int(wh_id))
                if wh:
                    await wh.send(content=message, username=username)
        try:
            asyncio.run_coroutine_threadsafe(do(), bot.loop).result(timeout=10)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)})

    # ── CUSTOM EMBED API ─────────────────────────────────────────────────────
    # api_send_embed and custom_embeds_page are defined in app.py directly


def calculate_ai_ticket_stats(guild_id: int) -> dict:
    """AI ticket istatistiklerini hesapla"""
    import json, os
    from datetime import datetime
    from collections import Counter
    
    # Penalty dosyasını загрузить
    penalty_file = 'data/ticket_penalties.json'
    penalties = {}
    if os.path.exists(penalty_file):
        try:
            with open(penalty_file, 'r', encoding='utf-8') as f:
                penalties = json.load(f)
        except:
            pass
    
    guild_penalties = penalties.get(str(guild_id), {})
    
    # Temel istatistikler
    total_penalties = sum(len(p) if isinstance(p, list) else 1 for p in guild_penalties.values())
    
    # Наказание причинаlerini say
    reasons = []
    for user_penalties in guild_penalties.values():
        if isinstance(user_penalties, list):
            for p in user_penalties:
                reasons.append(p.get('reason', 'bilinmiyor'))
        else:
            reasons.append(user_penalties.get('reason', 'bilinmiyor'))
    
    reason_counter = Counter(reasons)
    
    # Karşılıklı ihlal, sahte şikayet sayıları
    mutual_violations = reason_counter.get('karşılıklı küfür/hakaret', 0)
    fake_complaints = reason_counter.get('sahte şikayet + kural ihlali', 0)
    single_violations = total_penalties - mutual_violations - fake_complaints
    
    # Oranlar
    total = total_penalties if total_penalties > 0 else 1
    mutual_rate = round((mutual_violations / total) * 100, 1)
    fake_rate = round((fake_complaints / total) * 100, 1)
    single_rate = round((single_violations / total) * 100, 1)
    no_violation_rate = max(0, 100 - mutual_rate - fake_rate - single_rate)
    
    # En çok ceza alan userlar
    top_offenders = []
    for user_id, user_penalties in guild_penalties.items():
        if isinstance(user_penalties, list):
            count = len(user_penalties)
            total_duration = sum(p.get('duration', 0) for p in user_penalties)
            last_penalty = user_penalties[-1].get('date', 'bilinmiyor') if user_penalties else 'bilinmiyor'
            name = user_penalties[-1].get('name', user_id) if user_penalties else user_id
        else:
            count = 1
            total_duration = user_penalties.get('duration', 0)
            last_penalty = user_penalties.get('date', 'bilinmiyor')
            name = user_penalties.get('name', user_id)
        
        top_offenders.append({
            'name': name,
            'count': count,
            'total_duration': total_duration,
            'last_penalty': last_penalty[:10] if isinstance(last_penalty, str) else 'bilinmiyor'
        })
    
    top_offenders.sort(key=lambda x: x['count'], reverse=True)
    top_offenders = top_offenders[:10]
    
    # Наказание причинаleri
    penalty_reasons = []
    for reason, count in reason_counter.most_common():
        penalty_reasons.append({
            'name': reason,
            'count': count,
            'percentage': round((count / total) * 100, 1)
        })
    
    # AI ticket verilerini загрузить
    ai_tickets = _load_ai_tickets(guild_id)
    total_tickets = len(ai_tickets)
    
    return {
        'total_tickets': total_tickets,
        'total_penalties': total_penalties,
        'mutual_violations': mutual_violations,
        'fake_complaints': fake_complaints,
        'single_violation_rate': single_rate,
        'mutual_rate': mutual_rate,
        'fake_rate': fake_rate,
        'no_violation_rate': no_violation_rate,
        'avg_confidence': 75,  # Placeholder - gerçek hesaplama için AI response'ları saklamak gerek
        'high_confidence_count': int(total_penalties * 0.8),  # Tahmini
        'low_confidence_count': int(total_penalties * 0.2),  # Tahmini
        'appeal_rate': 5,  # Placeholder
        'appeal_success_rate': 30,  # Placeholder
        'top_offenders': top_offenders,
        'penalty_reasons': penalty_reasons
    }

