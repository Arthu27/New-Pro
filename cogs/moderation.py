
from logger import get_logger

_log = get_logger("moderation")

import discord 
from discord .ext import commands 
from discord import app_commands 
from datetime import datetime ,timedelta ,timezone 
import json 
import os 
import time 
from cogs .embed_utils import gif ,now_ts ,mod_dm_embed ,mod_log_embed ,success_embed ,error_embed 

from logger import get_logger 
log =get_logger ("moderation")


DIVIDER ="✦ ───────────────────── ✦"


async def _respond (interaction ,**kw ):
    """Ответить на interaction максимально надёжно.

    Первый ответ — response.send_message; если уже был defer/ответ —
    followup. Ошибки самой отправки глушим с записью в журнал: модератор
    НИКОГДА не должен видеть «Приложение не отвечает» при выполненном
    наказании.
    """
    try :
        if interaction .response .is_done ():
            await interaction .followup .send (**kw )
        else :
            await interaction .response .send_message (**kw )
    except Exception as _e :
        log .info (f'[MODPANEL] Ответ не доставлен: {_e}')
        try :
            await interaction .followup .send (**kw )
        except Exception as _e2 :
            log .warning (f'[MODPANEL] Ответ не доставлен и через followup: {_e2}')


class Moderation (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    def save_case (self ,guild_id ,action ,user_id ,mod_id ,reason ):
        os .makedirs ('data',exist_ok =True )
        filepath ='data/mod_data.json'
        try :
            data ={'cases':{}}
            if os .path .exists (filepath ):
                with open (filepath ,'r',encoding ='utf-8')as f :
                    loaded =json .load (f )
                # Устойчивость: файл могли записать другие коги с другой схемой
                # (например, {'case': ..., 'notes': ...}). Не теряем их записи,
                # а лишь гарантируем ключ 'cases'.
                if isinstance (loaded ,dict ):
                    data =loaded
                data .setdefault ('cases',{})
            gid =str (guild_id )
            if gid not in data ['cases']:
                data ['cases'][gid ]=[]
            case_id =len (data ['cases'][gid ])+1 
            data ['cases'][gid ].append ({
            'id':case_id ,'action':action ,
            'user_id':str (user_id ),'mod_id':str (mod_id ),
            'reason':reason or 'Не указана',
            'timestamp':datetime .now (timezone .utc ).isoformat ()
            })
            with open (filepath ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,indent =2 ,ensure_ascii =False )
            return case_id 
        except Exception as e :
            log .info (f"[MOD] Ошибка сохранения дел: {e}")
            return 0 

    async def send_log (self ,guild ,embed ):
        # Общий резолвер: -модерация → legacy (mod-log, moderasyon) → server-log …
        ch =None
        try :
            from cogs .logs import find_log_channel
            ch =find_log_channel (guild ,'модерация')
        except Exception :
            ch =None
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="mod-log")
        if not ch :
            ch =discord .utils .get (guild .text_channels ,name ="moderasyon")
        if ch :
            try :
                await ch .send (embed =embed )
            except Exception as _ex:
                _log.debug("send_log(): подавлено: %s", _ex)

    async def _notify_owner (self ,action ,user ,mod ,reason =None ):
        from config import clean_number
        owner_id = clean_number(os.getenv('OWNER_ID')) or 0
        if not owner_id or not mod or mod .id ==owner_id :
            return 
        flag_file ='data/mod_notify.json'
        try :
            enabled =json .load (open (flag_file ,encoding ='utf-8')).get ('enabled',False )if os .path .exists (flag_file )else False 
        except Exception :
            enabled =False 
        if not enabled :
            return 
        try :
            owner =await self .bot .fetch_user (owner_id )
            name =user .display_name if hasattr (user ,'display_name')else str (user )
            msg =f"**{action.upper()}** — {name} | Mod: {mod.display_name}"
            if reason :
                msg +=f" | Причина: {reason}"
            await owner .send (msg )
        except Exception as _ex:
            _log.debug("_notify_owner(): подавлено: %s", _ex)

    async def send_dm (self ,user ,embed ):
        # DM — шаг best-effort: закрытые ЛС/сетевые сбои НЕ должны
        # отменять наказание или превращать его в «ошибку» для модератора
        try :
            await user .send (embed =embed )
        except Exception as _ex:
            _log.debug("send_dm(): подавлено: %s", _ex)

    def _confirm_embed (self ,action ,user ,guild ,reason ,case_id ,extra ="" ,moderator =None ):
        """Embed подтверждения для модератора — чистый стиль без эмодзи:
        заголовок-результат, карточка участника, поля, однострочный футер."""
        moderator =moderator or (guild .me if guild else None )
        configs ={
        "ban":("Бан выполнен",0xE74C3C ,"забанен"),
        "kick":("Кик выполнен",0xE67E22 ,"кикнут с сервера"),
        "timeout":("Мут выполнен",0xF39C12 ,"временно замьючен"),
        "untimeout":("Мут снят",0x2ECC71 ,"мут снят"),
        "unban":("Бан снят",0x2ECC71 ,"разбанен"),
        }
        title ,color ,action_text =configs .get (action ,("Действие выполнено",0x2ECC71 ,"применено"))

        e =discord .Embed (title =title ,
        description =f"**{user.display_name}** — {action_text}\nID: `{user.id}`",
        color =color ,timestamp =datetime .now (timezone .utc ))

        e .add_field (name ="Причина",value =(reason or "Не указана")[:1000],inline =True )
        e .add_field (name ="Модератор",value =(moderator .mention if moderator else "—"),inline =True )
        if extra :
            e .add_field (name ="Детали",value =str (extra )[:1000],inline =False )

        e .set_thumbnail (url =user .display_avatar .url )

        if guild .icon :
            e .set_footer (text =f"{guild.name} · дело #{case_id} · ЛС отправлено",
            icon_url =guild .icon .url )
        else :
            e .set_footer (text =f"{guild.name} · дело #{case_id} · ЛС отправлено")

        return e 


            # /роли 


        # /leaveguild 

    # ═══════════════════════════════════════════════════════════════════
    #  /modpanel — панель модерации через select-меню
    # ═══════════════════════════════════════════════════════════════════
    @app_commands .command (name ="modpanel",description ="Панель модерации (выпадающее меню)")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def modpanel (self ,interaction ):
        embed =discord .Embed (
        title ="🛡 Модерация",
        description =(
        "Выберите действие в выпадающем меню ниже.\n"
        "После выбора откроется окно для ввода цели и причины."
        ),
        color =0x3498DB ,
        timestamp =datetime .now (timezone .utc )
        )
        if interaction .guild .icon :
            embed .set_footer (text =f"{interaction.guild.name} · Модерация · видите только вы",icon_url =interaction .guild .icon .url )
        else :
            embed .set_footer (text =f"{interaction.guild.name} · Модерация · видите только вы")
        await _respond (interaction ,embed =embed ,view =ModPanelView (self ),ephemeral =True )

    # ═══════════════════════════════════════════════════════════════════
    #  !moderate — та же панель, но префиксной командой (без slash-синхронизации)
    # ═══════════════════════════════════════════════════════════════════

    def _parse_target_id (self ,target :str ):
        """Из '@упоминание' или '123456789' вернуть int ID (или None)."""
        if not target :
            return None
        import re as _re
        m =_re .search (r'(\d{15,22})',target )
        if m :
            return int (m .group (1 ))
        return None

    def _resolve_member (self ,guild ,target ):
        """Найти участника по строке из модалки: @упоминание, ID или ТОЧНЫЙ ник.

        Возвращает (user, uid). uid может быть найден без user (оффлайн/ушёл —
        добираем через fetch_user выше по стеку), user без uid не бывает.
        Точный ник: совпадение с username / отображаемым / ником на сервере
        (без учёта регистра); неоднозначность → (None, None), мод уточнит.
        """
        uid =self ._parse_target_id (target )
        if uid :
            return discord .utils .get (guild .members ,id =uid ),uid
        name =(target or '').strip ().lstrip ('@').strip ().casefold ()
        if len (name )<2 :
            return None ,None
        cands =[u for u in guild .members
        if name in (str (getattr (u ,'name','')).casefold (),
        str (getattr (u ,'global_name','')or '').casefold (),
        str (getattr (u ,'display_name','')).casefold ())]
        if len (cands )==1 :
            return cands [0 ],cands [0 ].id
        return None ,None

    # ── Апелляция («бан») ─────────────────────────────────────────────
    # «Бан» больше НЕ выгоняет с сервера: у участника закрываются все каналы,
    # открытым остаётся только один — канал апелляции, где он обжалует бан.
    _ISO_NAMES =('апелляция','апелляции','appeal','appeals')

    async def _isolation_channel (self ,guild ,reason ):
        """Найти или создать канал апелляции (виден только изолированным)."""
        ch =None
        for _nm in self ._ISO_NAMES :
            ch =discord .utils .get (guild .text_channels ,name =_nm )
            if ch is not None :
                break
        if ch is None :
            try :
                overwrites ={
                guild .default_role :discord .PermissionOverwrite (view_channel =False ),
                guild .me :discord .PermissionOverwrite (view_channel =True ,send_messages =True ),
                }
                ch =await guild .create_text_channel ('апелляция',overwrites =overwrites ,
                reason =reason or 'Канал апелляции')
            except Exception as _ex :
                log .warning (f'[MODPANEL] создание канала апелляции: {_ex}')
                ch =None
        return ch

    async def _isolate_member (self ,guild ,user ,reason ):
        """Закрыть все каналы для участника, оставить открытым канал апелляции."""
        iso =await self ._isolation_channel (guild ,reason )
        deny =discord .PermissionOverwrite (view_channel =False ,send_messages =False ,
        connect =False ,speak =False )
        allow =discord .PermissionOverwrite (view_channel =True ,send_messages =True )
        closed =0
        for ch in guild .channels :
            if ch ==iso :
                continue
            try :
                await ch .set_permissions (user ,overwrite =deny )
                closed +=1
            except Exception as _ex :
                log .debug (f'_isolate_member(): {ch}: {_ex}')
        if iso is not None :
            try :
                await iso .set_permissions (user ,overwrite =allow )
            except Exception as _ex :
                log .debug (f'_isolate_member(): iso: {_ex}')
        return iso ,closed

    async def _unisolate_member (self ,guild ,user ):
        """Снять апелляцию: вернуть участнику обычный доступ ко всем каналам."""
        for ch in guild .channels :
            try :
                await ch .set_permissions (user ,overwrite =None )
            except Exception as _ex :
                log .debug (f'_unisolate_member(): {ch}: {_ex}')

    # ── Почему Forbidden: иерархия ролей / владелец сервера / право бота ──
    _NEED_PERMS = {
        'ban': ('ban_members', 'Бан участников'),
        'kick': ('kick_members', 'Выгонять участников'),
        'timeout': ('moderate_members', 'Модерация участников (таймаут)'),
        'mute_chat': ('manage_roles', 'Управление ролями (мут-роль)'),
        'vmute': ('manage_roles', 'Управление ролями (мут-роль)'),
    }

    async def preflight_reason(self, guild, user, action):
        """Проверить ЗАРАНЕЕ, хватит ли боту прав (до попытки и до записи
        дела в базу). None — всё ок, иначе — причина для модератора."""
        try:
            me = guild.me
            if not me:
                return None
            # снять наказание можно и без иерархии; выдать — нет
            if (action not in ('unban', 'untimeout', 'vunmute', 'clear')
                    and user and getattr(user, 'id', None) == guild.owner_id):
                return 'Это владелец сервера — применить к нему наказание нельзя в принципе.'
            if (action in self._NEED_PERMS and user
                    and getattr(user, 'top_role', None) is not None
                    and user.top_role >= me.top_role):
                return (f'Роль бота ({me.top_role.name}) стоит не выше роли '
                        f'«{user.top_role.name}» нарушителя — Discord не позволит '
                        'действие. Поднимите роль бота: Настройки сервера → Роли.')
            perm, label = self._NEED_PERMS.get(action, (None, None))
            if perm and not getattr(me.guild_permissions, perm, False):
                return (f'Боту не выдано право «{label}». '
                        'Настройки сервера → Роли → роль бота.')
        except Exception:
            return None
        return None

    async def _forbidden_reason(self, guild, user, action):
        """Человеческое объяснение discord.Forbidden — что именно проверить."""
        try:
            me = guild.me
            if user and getattr(user, 'id', None) == guild.owner_id:
                return 'Это владелец сервера — применить наказание к нему нельзя.'
            if user and me and user.top_role >= me.top_role:
                return (f'Роль бота ({me.top_role.name}) стоит не выше роли '
                        f'«{user.top_role.name}». Поднимите роль бота: '
                        'Настройки сервера → Роли → перетащите роль бота выше.')
            perm, label = self._NEED_PERMS.get(action, (None, None))
            if perm and me and not getattr(me.guild_permissions, perm, False):
                return f'Боту не выдано право «{label}». Настройки сервера → Роли → роль бота.'
        except Exception as _fre:
            log.debug('forbidden_reason: подавлено: %s', _fre)
        return ('Проверьте: роль бота выше роли нарушителя и у бота есть нужное '
                'право (Настройки сервера → Роли).')

    async def _execute_mod_action (self ,interaction ,action ,target ,reason ,amount ,proof_link =None ):
        """Выполнить выбранное действие модерации."""
        guild =interaction .guild

        # Лимиты стаффа — защита от «плохих» модераторов (владельца не трогаем).
        # С 2026-08 лимитируется ВСЁ: варны, муты, баны, чистка — и действует
        # САМЫЙ СТРОГИЙ лимит среди ролей модератора (пер-рольные лимиты).
        try :
            _sl_key ={'warn':'warn','timeout':'mute','mute_chat':'mute','vmute':'mute',
            'untimeout':'unmute','vunmute':'unmute','unban':'unban',
            'ban':'ban','clear':'clear','kick':'kick'}.get (action )
            if _sl_key and guild and getattr (interaction .user ,'id',0 )!=getattr (guild ,'owner_id',0 ):
                from services .staff_limits import check_limit as _sl_check ,ACTION_TITLES 
                if action =='clear':
                    try :
                        _sl_amt =max (1 ,min (int (amount )or 10 ,200 ))
                    except Exception :
                        _sl_amt =10
                else :
                    _sl_amt =1
                _sl_roles =[]
                try :
                    _sl_roles =[r .id for r in (getattr (interaction .user ,'roles',None )or [])
                    if getattr (r ,'id',None )!=getattr (guild ,'id',None )]
                except Exception :
                    _sl_roles =[]
                _sl_ok ,_sl_used ,_sl_lim =_sl_check (guild .id ,interaction .user .id ,_sl_key ,_sl_amt ,role_ids =_sl_roles )
                if not _sl_ok :
                    _what =ACTION_TITLES .get (_sl_key ,'действий' )
                    await _respond (interaction ,
                    embed =error_embed (f'🛡 Лимит исчерпан: {_sl_lim} {_what} (уже {_sl_used}). Период настраивается в «Лимитах команды».'),
                    ephemeral =True )
                    return
        except Exception as _le :
            log .debug (f'[STAFF_LIMIT] {_le}')

        # Наказания — только с доказательством (ссылкой на скрин/видео):
        # модальные окна Discord не принимают вложения, поэтому через панель
        # доказательство передаётся ссылкой.
        _punish_actions =("ban","timeout","mute_chat","vmute")
        if action in _punish_actions :
            from cogs .proof_cog import require_proof
            _action_ru ={'ban':'апелляция','kick':'кик','timeout':'мут','mute_chat':'мут чата','vmute':'войс-мут'}[action ]
            if not await require_proof (interaction ,action_ru =_action_ru ,link =proof_link ):
                return

        if action in ("ban","kick","timeout","mute_chat","untimeout","vmute","vunmute"):
            user ,uid =self ._resolve_member (guild ,target )
            if not user and uid :
                try :
                    user =await self .bot .fetch_user (uid )
                except Exception :
                    user =None
            if not user :
                await _respond (interaction ,
                embed =error_embed ("Пользователь не найден. Укажите @упоминание, точный ник или ID — ровно как на сервере."),
                ephemeral =True )
                return

            # Предпроверка прав бота: знаем ЗАРАНЕЕ, получится ли действие,
            # и дело в базу не пишется зря
            _pre =await self .preflight_reason (guild ,user ,action )
            if _pre :
                await _respond (interaction ,
                embed =error_embed (_pre ,"У бота не хватит прав"),ephemeral =True )
                return

            try :
                if action =="ban":
                    # Апелляция: закрыть все каналы, оставить канал апелляции.
                    _iso ,_closed =await self ._isolate_member (guild ,user ,reason )
                    msg =f"🚫 апелляция: закрыто каналов {_closed}, открыт {_iso .mention if _iso else 'канал апелляции'}"
                    try :
                        from services .staff_limits import record_hit as _sl_rec
                        _sl_rec (guild .id ,interaction .user .id ,'ban',1 )
                    except Exception as _re :
                        log .debug (f'[STAFF_LIMIT] ban rec: {_re}')
                elif action =="kick":
                    # Система kick полностью отключена решением владельца (2026-08):
                    # опция убрана из меню, ручные вызовы — вежливый отказ.
                    if interaction .response .is_done ():
                        await interaction .followup .send ("🛡 Кик отключён на этом сервере — используй мут или апелляцию.",ephemeral =True )
                    else :
                        await interaction .response .send_message ("🛡 Кик отключён на этом сервере — используй мут или апелляцию.",ephemeral =True )
                    return 
                elif action in ("timeout","mute_chat"):
                    try :
                        minutes =max (1 ,int (amount )if str (amount ).strip () else 5 )
                    except (TypeError ,ValueError ):
                        minutes =5
                    until =datetime.now(timezone.utc)+timedelta (minutes =minutes )
                    await user .timeout (until ,reason =reason )
                    if action =="mute_chat":
                        msg =f"🔇 чат закрыт на {minutes} мин"
                    else :
                        msg =f"🔇 чат и голос закрыты на {minutes} мин"
                    # 2 mute → 1 неделя в watchlist
                    await self._maybe_watchlist_after_mute (interaction ,user ,reason )
                elif action =="vmute":
                    if not user .voice or not user .voice .channel :
                        await _respond (interaction ,
                        embed =error_embed ("Участник не в голосовом канале. Голосовой мьют невозможен."),
                        ephemeral =True )
                        return
                    await user .edit (mute =True )
                    msg ="🎙️ микрофон заглушён (войс-мут)"
                elif action =="vunmute":
                    await user .edit (mute =False )
                    msg ="🎙️ микрофон включён"
                else :  # untimeout
                    await user .timeout (None )
                    msg ="🔊 мут снят (чат и голос открыты)"

                # Вспомогательные шаги: дело, DM, лог, уведомление панели.
                # Каждый — в своём try: сбой побочного шага НЕ должен превращать
                # выполненное наказание в «ошибку» для модератора.
                aux_errors =[]
                # Лимиты: фиксируем успешные муты в дневном счётчике
                # (бан и чистка пишутся в своих ветках)
                try :
                    _sl_rec_key ={'timeout':'mute','mute_chat':'mute','vmute':'mute',
                    'untimeout':'unmute','vunmute':'unmute','kick':'kick'}.get (action )
                    if _sl_rec_key and guild :
                        from services .staff_limits import record_hit as _sl_rec 
                        _sl_rec (guild .id ,interaction .user .id ,_sl_rec_key ,1 )
                except Exception as _slr :
                    log .debug (f'[STAFF_LIMIT] rec: {_slr}')
                try :
                    case_id =self .save_case (guild .id ,action ,user .id ,interaction .user .id ,reason )
                except Exception as _case_e :
                    case_id =0
                    aux_errors .append ("дело не записано")
                    log .warning (f'[MODPANEL] save_case: {_case_e}')
                try :
                    dm =mod_dm_embed (action ,guild ,interaction .user ,reason )
                    await self .send_dm (user ,dm )
                except Exception as _dm_e :
                    aux_errors .append ("DM не доставлен")
                    log .info (f'[MODPANEL] DM: {_dm_e}')
                try :
                    log_ch_embed =mod_log_embed (action ,{"ban":"🚫 Апелляция","kick":"👢 Кик","timeout":"🔇 Мут","mute_chat":"🔇 Мут чата","vmute":"🎙️ Войс-мут","vunmute":"🎙️ Войс-мут снят","untimeout":"🔊 Мут снят"}.get (action ,action ),0x3498DB ,user ,interaction .user ,guild ,reason ,case_id )
                    await self .send_log (guild ,log_ch_embed )
                except Exception as _log_e :
                    aux_errors .append ("лог-канал недоступен")
                    log .warning (f'[MODPANEL] send_log: {_log_e}')

                # Уведомление панели о действии модерации (веб/Discord/email — в фоне)
                try :
                    from cogs .ticket import _notify_panel_ticket_event as _np
                    _label ={"ban":"Апелляция","kick":"Кик","timeout":"Таймаут","mute_chat":"Мут чата","vmute":"Войс-мут","vunmute":"Войс-мут снят","untimeout":"Мут снят"}.get (action ,action )
                    _np (interaction ,'mod_action',
                    f"{_label }: {user .display_name }",
                    f"Модератор: {interaction .user .display_name } · Причина: {reason } · Дело #{case_id}")
                except Exception as _ex:
                    _log.debug("_execute_mod_action(): подавлено: %s", _ex)

                # Доказательство (ссылка) — в канал доказательств.
                proof_note =None
                try :
                    if action in _punish_actions and (proof_link or '').strip ():
                        from cogs .proof_cog import try_deliver_proof
                        _p_ru ={'ban':'апелляция','kick':'кик','timeout':'мут','mute_chat':'мут чата','vmute':'войс-мут'}.get (action ,action )
                        proof_note =await try_deliver_proof (self .bot ,guild ,interaction .user ,user ,_p_ru ,reason ,link =proof_link )
                except Exception as _pe :
                    log .warning (f'[MODPANEL] демка: {_pe}')

                confirm =success_embed (
                "Действие выполнено",
                f"**{user.display_name}** · `{user.id}`\n{msg}\n**Причина:** {reason}\n**Дело:** #{case_id}",
                guild =guild )
                if aux_errors :
                    confirm .description +=f"\n\n⚠️ {' · '.join (aux_errors )}"
                if proof_note :
                    confirm .description +=f"\n{proof_note }"
                await _respond (interaction ,embed =confirm ,ephemeral =True )
            except discord .Forbidden :
                await _respond (interaction ,
                embed =error_embed (await _forbidden_reason (guild ,user ,action ),"Не хватило прав у бота"),ephemeral =True )
            except Exception as ex :
                import traceback as _tb
                log .warning (f"[MODPANEL] Сбой действия: {_tb.format_exc()}")
                await _respond (interaction ,embed =error_embed (str (ex )),ephemeral =True )

        elif action =="unban":
            uid =self ._parse_target_id (target )
            if not uid :
                await _respond (interaction ,
                embed =error_embed ("Укажите ID пользователя для разбана (15-22 цифры, можно с @упоминанием)."),ephemeral =True )
                return
            try :
                member =guild .get_member (uid )
                # Снятие апелляции (участник остаётся на сервере)
                if member is not None :
                    await self ._unisolate_member (guild ,member )
                # Настоящий разбан (для легаси-банов, если пользователь вне сервера)
                unban_done =False
                try :
                    fetched =await self .bot .fetch_user (uid )
                    await guild .unban (fetched )
                    unban_done =True
                except Exception as _ub_ex :
                    log .debug (f'unban: {_ub_ex}')
                case_id =self .save_case (guild .id ,"unban",uid ,interaction .user .id ,reason )
                try :
                    from services .staff_limits import record_hit as _sl_rec
                    _sl_rec (guild .id ,interaction .user .id ,'unban',1 )
                except Exception as _re :
                    log .debug (f'[STAFF_LIMIT] unban rec: {_re}')
                _who =member .display_name if member else (getattr (fetched ,'name','') if unban_done else str (uid ))
                _desc =f"**{_who}** · `{uid}`\n"
                _desc +="Снята апелляция и разбан." if (member is not None and unban_done) else \
                        ("Апелляция снята." if member is not None else \
                         ("Разбан выполнен." if unban_done else "Ничего не изменилось (не изолирован и не забанен)."))
                _desc +=f"\n**Дело:** #{case_id}"
                confirm =success_embed ("Снятие апелляции / разбан",_desc ,guild =guild )
                await self .send_log (guild ,confirm )
                # Уведомление панели (веб/Discord/email — в фоне)
                try :
                    from cogs .ticket import _notify_panel_ticket_event as _np
                    _np (interaction ,'mod_action',
                    f"Разбан/снятие апелляции: {_who }",
                    f"Модератор: {interaction .user .display_name } · Дело #{case_id}")
                except Exception as _ex:
                    _log.debug("_execute_mod_action(): подавлено: %s", _ex)
                await _respond (interaction ,embed =confirm ,ephemeral =True )
            except Exception as ex :
                await _respond (interaction ,embed =error_embed (str (ex )),ephemeral =True )

        elif action =="clear":
            try :
                count =max (1 ,min (int (amount )or 10 ,200 ))
            except Exception :
                count =10
            deleted =await interaction .channel .purge (limit =count )
            try :
                from services .staff_limits import record_hit as _sl_rec
                _sl_rec (guild .id ,interaction .user .id ,'clear',len (deleted ))
            except Exception as _re :
                log .debug (f'[STAFF_LIMIT] clear rec: {_re}')
            confirm =success_embed (
            "Сообщения удалены",
            f"Удалено **{len(deleted)}** сообщений в {interaction.channel.mention}",
            guild =guild )
            await _respond (interaction ,embed =confirm ,ephemeral =True )

    async def _maybe_watchlist_after_mute (self ,interaction ,user ,reason ):
        """Если пользователь получил 2+ мьюта — добавить в watchlist на 1 неделю.

        Считаем мьюты (timeout) из mod_data.json. При достижении 2-го мьюта
        добавляем в mod_advanced_data.json (watchlist) с меткой until (+7 дней).
        """
        try :
            import datetime as _dt
            # 1) Считаем мьюты пользователя
            os .makedirs ('data',exist_ok =True )
            mod_file ='data/mod_data.json'
            mute_count =0
            if os .path .exists (mod_file ):
                with open (mod_file ,'r',encoding ='utf-8')as f :
                    data =json .load (f )
                cases =data .get ('cases',{}).get (str (interaction .guild .id ),[])
                for c in cases :
                    if str (c .get ('user_id',''))==str (user .id )and c .get ('action')in ('timeout','mute_chat','vmute'):
                        mute_count +=1
            # 2) Добавляем в watchlist (advanced_mod) на 1 неделю
            adv_file ='data/mod_advanced_data.json'
            adv ={}
            if os .path .exists (adv_file ):
                with open (adv_file ,'r',encoding ='utf-8')as f :
                    adv =json .load (f )
            adv .setdefault ('watchlist',{})
            gid =str (interaction .guild .id )
            adv ['watchlist'].setdefault (gid ,{})
            until =int (time .time ())+7 *86400  # +7 дней
            adv ['watchlist'][gid ][str (user .id )]={
                "reason":f"Автоматически: {mute_count}-й мьют. {reason or ''}",
                "added_by":str (interaction .user ),
                "timestamp":datetime .now (timezone .utc ).isoformat (),
                "until":until ,
                "auto":True ,
            }
            with open (adv_file ,'w',encoding ='utf-8')as f :
                json .dump (adv ,f ,indent =2 ,ensure_ascii =False )
        except Exception as ex :
            log .warning (f"[watchlist auto] {ex}")


# ═══════════════════════════════════════════════════════════════════
#  SELECT-МЕНЮ МОДЕРАЦИИ (без кнопок/эмодзи — только выпадающие меню)
# ═══════════════════════════════════════════════════════════════════
class ModActionSelect(discord.ui.Select):
    """Выбор действия модерации."""

    def __init__(self, cog):
        options = [
            discord.SelectOption(label="Бан (апелляция)", value="ban", description="Закрыть все каналы, оставить канал апелляции"),
            discord.SelectOption(label="Мут (чат + войс)", value="timeout", description="Таймаут — закрыть и чат, и голос"),
            discord.SelectOption(label="Мут (только чат)", value="mute_chat", description="Закрыть только чат (таймаут)"),
            discord.SelectOption(label="Мут (только войс)", value="vmute", description="Заглушить микрофон (чат не трогает)"),
            discord.SelectOption(label="Снять апелляцию / разбан", value="unban", description="Вернуть доступ к каналам (по ID)"),
            discord.SelectOption(label="Очистить сообщения", value="clear", description="Удалить N сообщений"),
            discord.SelectOption(label="Размут (чат + войс)", value="untimeout", description="Снять таймаут с участника"),
            discord.SelectOption(label="Размут (войс)", value="vunmute", description="Включить микрофон участника"),
        ]
        super().__init__(
            placeholder="Выберите действие модерации...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        modal = ModActionModal(self.cog, action, guild=interaction.guild)
        await interaction.response.send_modal(modal)


# Действия-наказания в мод-панели: к ним обязательна демка (пока включено
# требование в панели: «Доказательства» → тумблер).
_PUNISH_MODPANEL = ("ban", "timeout", "mute_chat", "vmute")


class ModActionModal(discord.ui.Modal):
    """Модальное окно ввода — поля строго под выбранное действие.

    «Очистка» спрашивает только количество и причину (никакой демки),
    разбан/размут — цель и причину, наказания — демку, НО только если
    требование включено в панели.
    """

    def __init__(self, cog, action, guild=None):
        self.cog = cog
        self.action = action
        titles = {
            "ban": "Бан (апелляция)",
            "timeout": "Мут (чат + войс)",
            "mute_chat": "Мут чата",
            "vmute": "Войс-мут",
            "unban": "Снять апелляцию / разбан",
            "clear": "Очистка сообщений",
            "untimeout": "Снять мут",
            "vunmute": "Снять войс-мут",
        }
        super().__init__(title=titles.get(action, "Модерация"))

        if action != "clear":
            self.target = discord.ui.TextInput(
                label="Цель (@ник, точное имя или ID)", required=True,
                placeholder="@упоминание, ник или 15-22 цифры ID",
            )
            self.add_item(self.target)
        if action in ("timeout", "mute_chat", "vmute", "clear"):
            if action == "clear":
                _lbl, _ph, _d = "Сколько сообщений удалить?", "например: 25", "10"
            else:
                _lbl, _ph, _d = "На сколько минут?", "например: 60", "5"
            self.amount = discord.ui.TextInput(
                label=_lbl, required=False, placeholder=_ph, default=_d,
            )
            self.add_item(self.amount)
        self.reason = discord.ui.TextInput(
            label="Причина", required=False, placeholder="За что? (необязательно)",
            style=discord.TextStyle.short,
        )
        self.add_item(self.reason)
        _need_proof = False
        if action in _PUNISH_MODPANEL:
            try:
                from cogs.proof_cog import proof_is_required
                _need_proof = proof_is_required(getattr(guild, 'id', 0) or 0)
            except Exception:
                _need_proof = True
        if _need_proof:
            self.proof = discord.ui.TextInput(
                label="Доказательство (ссылка на скрин/видео)", required=True,
                placeholder="https://… — без этого наказание не выдаётся",
                max_length=500,
            )
            self.add_item(self.proof)

    async def on_submit(self, interaction: discord.Interaction):
        # Быстрый ack — дальше цепочка (таймаут → дело → DM → лог) может
        # занять больше 3 секунд, без defer токен умирал и Discord рисовал
        # «Приложение не отвечает», хотя наказание уже применено.
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as _ex:
            _log.debug("on_submit(): подавлено: %s", _ex)
        _t = getattr(self, 'target', None)
        _a = getattr(self, 'amount', None)
        _p = getattr(self, 'proof', None)
        _reason = (self.reason.value or "").strip() or "Не указана"
        await self.cog._execute_mod_action(
            interaction,
            self.action,
            (_t.value or "").strip() if _t else "",
            _reason,
            (_a.value or "").strip() if _a else "5",
            proof_link=(_p.value or "").strip() if _p else "",
        )


class ModPanelView(discord.ui.View):
    """View панели: только выпадающее меню, без кнопок."""

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.add_item(ModActionSelect(cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Панель модерации — только для модераторов (сообщение публичное)."""
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                embed=error_embed("Недостаточно прав: нужно право «Модерация участников»."),
                ephemeral=True)
            return False
        return True


async def setup (bot ):
    await bot .add_cog (Moderation (bot ))
