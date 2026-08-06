import discord 
from discord .ext import commands ,tasks 
from discord import app_commands 
import datetime 
from datetime import timedelta 
import io 
import json 
import os 
import logging 
import asyncio 
from cogs .embed_utils import gif ,now_ts ,_divider 
from services .rate_limiter import get_rate_limiter 
from services .feedback_service import get_feedback_service 
from services .custom_menu import CustomMenu ,TicketMenu ,StatsMenu ,HelpMenu 

from logger import get_logger 
log =get_logger ("ticket")


logger =logging .getLogger ('ticket')

TICKET_CATEGORY_NAME ="Тикеты"
SUPPORT_ROLE_NAME ="Поддержка"

GIF_TICKET_OPEN ="https://media.tenor.com/3Ky6UNqMFpkAAAAC/talking-speak.gif"
GIF_TICKET_CLOSE ="https://media.tenor.com/x8v1oNUOmg4AAAAC/ban-hammer.gif"
GIF_PANEL ="https://media.tenor.com/ZBDpMFBMFpkAAAAC/celebration-party.gif"

from PIL import Image ,ImageDraw ,ImageFont 
from cogs ._menu_bg import load_menu_bg 

ROOT =os .path .join (os .path .dirname (__file__ ),'..')
FONTS =os .path .join (ROOT ,'assets','fonts')
BG_PATH =os .path .join (ROOT ,'assets','profile_bg_pro.jpg')
FONT_B =os .path .join (FONTS ,'Bold.ttf')
FONT_R =os .path .join (FONTS ,'Regular.ttf')

WHITE =(255 ,255 ,255 )
BLACK =(20 ,20 ,25 )
TEAL =(13 ,148 ,136 )
MUTED =(110 ,115 ,125 )
SS =4 

def _f (bold =False ,sz =20 ):
    try :
        return ImageFont .truetype (FONT_B if bold else FONT_R ,sz )
    except Exception :
        return ImageFont .load_default ()

def _ss_render (w ,h ,draw_fn ,scale =SS ):
    big =Image .new ('RGBA',(w *scale ,h *scale ),(0 ,0 ,0 ,0 ))
    d =ImageDraw .Draw (big )
    draw_fn (d ,scale )
    return big .resize ((w ,h ),Image .Resampling .LANCZOS )

def _load_bg (w ,h ):
    try :
        bg =Image .open (BG_PATH ).convert ('RGBA')
        bw ,bh =bg .size 
        target_ratio =w /h 
        src_ratio =bw /bh 
        if src_ratio >target_ratio :
            new_w =int (bh *target_ratio )
            x0 =(bw -new_w )//2 
            bg =bg .crop ((x0 ,0 ,x0 +new_w ,bh ))
        else :
            new_h =int (bw /target_ratio )
            y0 =(bh -new_h )//2 
            bg =bg .crop ((0 ,y0 ,bw ,y0 +new_h ))
        return bg .resize ((w ,h ),Image .Resampling .LANCZOS )
    except Exception :
        return Image .new ('RGBA',(w ,h ),(255 ,255 ,255 ,255 ))

def _icon_ticket (d ,cx ,cy ,s ,w ,color ):
    w_t ,h_t =s *0.44 ,s *0.30 
    x0 ,y0 =cx -w_t ,cy -h_t 
    x1 ,y1 =cx +w_t ,cy +h_t 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =h_t *0.25 ,outline =color ,width =w )
    r =s *0.1 
    d .arc ((x0 -r ,cy -r ,x0 +r ,cy +r ),-90 ,90 ,fill =WHITE ,width =w *2 )
    d .arc ((x0 -r ,cy -r ,x0 +r ,cy +r ),-90 ,90 ,fill =color ,width =w )
    d .arc ((x1 -r ,cy -r ,x1 +r ,cy +r ),90 ,270 ,fill =WHITE ,width =w *2 )
    d .arc ((x1 -r ,cy -r ,x1 +r ,cy +r ),90 ,270 ,fill =color ,width =w )

def _icon_badge (diameter ,glyph_fn ,ring_color =BLACK ,ring_w =None ,icon_color =TEAL ):
    ring_w =ring_w if ring_w is not None else max (2 ,diameter //22 )
    def draw (d ,scale ):
        size =diameter *scale 
        rw =ring_w *scale 
        r =size *0.22 
        d .rounded_rectangle ((rw /2 ,rw /2 ,size -rw /2 -1 ,size -rw /2 -1 ),
        radius =r ,fill =WHITE ,outline =ring_color ,width =rw )
        glyph_fn (d ,size /2 ,size /2 ,size *0.60 ,max (2 ,int (size *0.032 )),icon_color )
    return _ss_render (diameter ,diameter ,draw )

def _corner_bracket (size ,thickness ,length_ratio =0.35 ,color =TEAL ):
    def draw (d ,scale ):
        t =thickness *scale 
        L =size *scale *length_ratio 
        d .line ([(0 ,t /2 ),(L ,t /2 )],fill =color ,width =t )
        d .line ([(t /2 ,0 ),(t /2 ,L )],fill =color ,width =t )
    return _ss_render (size ,size ,draw )

def _rounded_panel (w ,h ,radius ,fill =WHITE ,outline =BLACK ,ow =3 ):
    def draw (d ,scale ):
        r =radius *scale 
        o =ow *scale 
        d .rounded_rectangle ((o /2 ,o /2 ,w *scale -o /2 -1 ,h *scale -o /2 -1 ),
        radius =r ,fill =fill ,outline =outline ,width =o )
    return _ss_render (w ,h ,draw )

def generate_ticket_panel_card ()->Image .Image :
    W ,H =920 ,520 
    bg =load_menu_bg (W ,H ,"teal")
    d =ImageDraw .Draw (bg )

    # Header
    header_box =_rounded_panel (872 ,72 ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
    bg .alpha_composite (header_box ,(24 ,20 ))

    badge =_icon_badge (52 ,_icon_ticket ,ring_color =BLACK ,ring_w =2 ,icon_color =TEAL )
    bg .alpha_composite (badge ,(36 ,30 ))

    d .text ((100 ,26 ),"СЛУЖБА ПОДДЕРЖКИ СЕРВЕРА",fill =BLACK ,font =_f (True ,24 ))
    d .text ((100 ,56 ),"ВЫБЕРИТЕ КАТЕГОРИЮ ОБРАЩЕНИЯ В МЕНЮ НИЖЕ",fill =MUTED ,font =_f (False ,15 ))

    pill =_rounded_panel (160 ,36 ,radius =10 ,fill =WHITE ,outline =TEAL ,ow =2 )
    bg .alpha_composite (pill ,(720 ,38 ))
    d .text ((738 ,46 ),"SUPPORT v4.0",fill =TEAL ,font =_f (True ,14 ))

    # 4 Category cards
    items =[
    ("ОБЩИЕ ВОПРОСЫ","Консультации и помощь","Ответ до 24ч"),
    ("ТЕХ. ПОДДЕРЖКА","Проблемы с ботом/сервером","Высокий приоритет"),
    ("ЖАЛОБЫ","Нарушения правил","Конфиденциально"),
    ("ЗАЯВКИ В СТАФФ","Набор модераторов","Отбор кандидатов")
    ]
    box_w ,box_h =426 ,110 
    gap_x ,gap_y =20 ,14 
    start_x ,start_y =24 ,106 

    for idx ,(title ,sub ,note )in enumerate (items ):
        c =idx %2 
        r =idx //2 
        bx =start_x +c *(box_w +gap_x )
        by =start_y +r *(box_h +gap_y )

        box =_rounded_panel (box_w ,box_h ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
        bg .alpha_composite (box ,(bx ,by ))

        ibadge =_icon_badge (64 ,_icon_ticket ,ring_color =BLACK ,ring_w =2 ,icon_color =TEAL )
        bg .alpha_composite (ibadge ,(bx +16 ,by +23 ))

        d .text ((bx +94 ,by +18 ),title ,fill =BLACK ,font =_f (True ,23 ))
        d .text ((bx +94 ,by +50 ),sub ,fill =TEAL ,font =_f (True ,17 ))
        d .text ((bx +94 ,by +78 ),note ,fill =MUTED ,font =_f (False ,15 ))

    br =_corner_bracket (40 ,4 ,color =TEAL )
    bg .alpha_composite (br ,(6 ,6 ))
    bg .alpha_composite (br .rotate (270 ),(W -46 ,6 ))
    bg .alpha_composite (br .rotate (90 ),(6 ,H -46 ))
    bg .alpha_composite (br .rotate (180 ),(W -46 ,H -46 ))

    return bg 

def generate_ticket_panel_bytes ()->io .BytesIO :
    card =generate_ticket_panel_card ().convert ('RGB')
    buf =io .BytesIO ()
    card .save (buf ,format ='PNG',optimize =True )
    buf .seek (0 )
    return buf 


    # AI Ticket Settings
AI_ENABLED =True # AI-система поддержки активна
MAX_AI_MESSAGES =10 

# AI по серверам (guild) — глобально включено, можно отключить для конкретного сервера
AI_DISABLED_GUILDS :set =set ()

# На этом сервере система тикетов отключена
TICKET_DISABLED_GUILDS :set =set ()


def _get_punishment_for_quote (quote :str )->dict :
    q =quote .lower ()

    # 1. Critical Insults or Threats -> BAN or KICK (Requires Admin Confirmation)
    critical_keywords =[
    'убью','убить','зарежу','прирежу','прибью','пристрелю','закопаю','ёldюreceгim','ёldюr','gebert','vuracaгыm','keseceгim','kill you','will kill','murder',
    'yosma','fahiшe','orospu','pezevenk','piч','шerefsiz','namussuz','ублюдок','мраз','блядина','пидор','faggot','nigger'
    ]
    if any (w in q for w in critical_keywords ):
        return {
        'action':'BAN',
        'duration':None ,
        'reason':f"Тяжелое оскорбление / Угрозы в логах: «{quote[:60]}»"
        }

        # 2. Medium Insults -> MUTE (1 hour)
    medium_keywords =[
    'amk','amq','aq','siktir','yarrak','yarak','gёt','got','amcыk','amcik','ibne','kahpe',
    'хуй','хуя','хую','ебал','рот','пидорас','сука','блядь','блять','мудак','гондон','bitch','asshole'
    ]
    if any (w in q for w in medium_keywords ):
        return {
        'action':'MUTE',
        'duration':60 ,# 1 hour
        'reason':f"Оскорбление средней тяжести в логах: «{quote[:60]}»"
        }

        # 3. Mild Insults / Disrespect -> WARN (No punishment, just warning)
    mild_keywords =[
    'salak','aptal','gerizekalы','it','kёpek','terbiyesiz','saygыsыz','saygisiz','lan',
    'дурак','дура','идиот','тупой','тупица','дебил','кретин','придурок','урод','чмо','лох'
    ]
    if any (w in q for w in mild_keywords ):
        return {
        'action':'WARN',
        'duration':0 ,
        'reason':f"Неуважительное отношение / Легкое оскорбление: «{quote[:60]}»"
        }

        # Default fallback
    return {
    'action':'WARN',
    'duration':0 ,
    'reason':f"Нарушение правил общения в логах: «{quote[:60]}»"
    }


class AdminApprovalView (discord .ui .View ):
    def __init__ (self ,target_id :int ,action_type :str ,reason :str ,guild_id :int =0 ,quote :str =''):
        super ().__init__ (timeout =None )
        self .target_id =target_id 
        self .action_type =action_type .upper ()
        self .reason =reason 
        self .guild_id =guild_id 
        self .quote =quote 

    @discord .ui .button (
    label ="✅ Одобрить наказание",
    style =discord .ButtonStyle .green ,
    custom_id ="admin_approve_punishment"
    )
    async def approve (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        is_admin =interaction .user .guild_permissions .administrator or interaction .user .guild_permissions .manage_guild 
        if not is_admin :
            await interaction .response .send_message ("❌ Только администратор может одобрять наказания!",ephemeral =True )
            return 

        await interaction .response .defer ()
        guild =interaction .guild 
        target =guild .get_member (self .target_id )
        if not target :
            try :
                target =await guild .fetch_member (self .target_id )
            except Exception :
                pass 

        if not target :
            await interaction .channel .send ("❌ Нарушитель не найден на сервере.")
            return 

        try :
            if self .action_type =='BAN':
                await target .ban (reason =f"AI Рекомендация (одобрено {interaction.user}): {self.reason}")
                await interaction .channel .send (f"✅ **[СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]**: Участник **{target.display_name}** забанен администратором {interaction.user.mention}.\n**Причина:** {self.reason}")
            elif self .action_type =='KICK':
                await target .kick (reason =f"AI Рекомендация (одобрено {interaction.user}): {self.reason}")
                await interaction .channel .send (f"✅ **[СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]**: Участник **{target.display_name}** кикнут администратором {interaction.user.mention}.\n**Причина:** {self.reason}")

                # ЗАЩИТА ОТ ДВОЙНОГО НАКАЗАНИЯ: сохраняем одобренное наказание, чтобы не наказывать повторно.
            try :
                cog =interaction .client .get_cog ('Ticket')
                if cog and self .guild_id :
                    cog ._record_penalty (
                    int (self .guild_id ),int (self .target_id ),target .name ,
                    self .reason ,0 ,self .quote
                    )
            except Exception :
                pass 

                # Disable buttons
            for child in self .children :
                child .disabled =True 
            await interaction .message .edit (view =self )
        except Exception as e :
            await interaction .channel .send (f"❌ Не удалось применить наказание: {e}")

    @discord .ui .button (
    label ="❌ Отклонить",
    style =discord .ButtonStyle .red ,
    custom_id ="admin_reject_punishment"
    )
    async def reject (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        is_admin =interaction .user .guild_permissions .administrator or interaction .user .guild_permissions .manage_guild 
        if not is_admin :
            await interaction .response .send_message ("❌ Только администратор может отклонять наказания!",ephemeral =True )
            return 

        await interaction .response .defer ()
        guild =interaction .guild 
        target =guild .get_member (self .target_id )
        target_name =target .display_name if target else f"ID {self.target_id}"

        await interaction .channel .send (f"❌ **[РЕШЕНИЕ ОТКЛОНЕНО]**: Администратор {interaction.user.mention} отклонил рекомендацию AI на {self.action_type} для **{target_name}**.")

        # Disable buttons
        for child in self .children :
            child .disabled =True 
        await interaction .message .edit (view =self )


class TicketCategorySelect (discord .ui .Select ):
    """Select menu для выбора категории тикета"""
    def __init__ (self ,channel_id :int ,guild_id :int ):
        self .channel_id =channel_id 
        self .guild_id =guild_id 

        options =[
        discord .SelectOption (
        label ="Жалоба",
        description ="Нарушение правил, оскорбления, угрозы",
        value ="sikayet"
        ),
        discord .SelectOption (
        label ="Вопрос / Помощь",
        description ="Общие вопросы, помощь с ботом",
        value ="soru"
        ),
        discord .SelectOption (
        label ="Техническая проблема",
        description ="Баги, ошибки, технические вопросы",
        value ="teknik"
        ),
        ]

        super ().__init__ (
        placeholder ="Выберите категорию...",
        min_values =1 ,
        max_values =1 ,
        options =options ,
        custom_id ="ticket_category_select"
        )

    async def callback (self ,interaction :discord .Interaction ):
        category =self .values [0 ]
        cog =interaction .client .get_cog ('Ticket')
        if cog :
            state =cog ._get_ticket_state (self .guild_id ,self .channel_id )
            state ['category']=category 

            # В категории жалобы сразу запускать поток жалобы
            if category =='sikayet':
                state ['complaint']={
                'active':True ,
                'step':'ask_description',
                'type':None ,
                'accused_id':None ,
                'channel_id':None ,
                'messages':[],
                'description':None ,
                }

            cog ._save_ticket_state (self .guild_id ,self .channel_id ,state )

        category_hints ={
        'sikayet':(
        '**Выбрана категория: Жалоба.**\n\n'
        'Кратко опишите, что произошло:'
        ),
        'soru':(
        '**Выбрана категория: Вопрос/Помощь.**\n\n'
        'Чем я могу помочь? Какую информацию вы хотите получить?\n'
        '> Панель, регистрация, команды, роли, экономика, уровни...'
        ),
        'teknik':(
        '**Выбрана категория: Техническая проблема.**\n\n'
        'Чем я могу помочь? С какой проблемой вы столкнулись?\n'
        '> Бот, музыка, команда не работает, текст ошибки...'
        ),
        }

        hint =category_hints .get (category ,'Чем я могу помочь?')
        e =discord .Embed (description =hint ,color =0x00D9FF )
        await interaction .response .send_message (embed =e )

        # Отключить select menu после выбора
        self .disabled =True 
        await interaction .message .edit (view =self .view )


class TicketCategoryView (discord .ui .View ):
    """View с select menu для выбора категории"""
    def __init__ (self ,channel_id :int ,guild_id :int ):
        super ().__init__ (timeout =300 )
        self .add_item (TicketCategorySelect (channel_id ,guild_id ))


class TicketView (discord .ui .View ):
    def __init__ (self ):
        super ().__init__ (timeout =None )

    @discord .ui .select (
    placeholder ="Выберите категорию обращения",
    custom_id ="ticket_category_select",
    options =[
    discord .SelectOption (label ="Общий вопрос",value ="general",description ="Общие вопросы и консультации"),
    discord .SelectOption (label ="Техническая поддержка",value ="technical",description ="Проблемы с ботом или сервером"),
    discord .SelectOption (label ="Жалоба",value ="complaint",description ="Жалоба на участника или нарушение"),
    discord .SelectOption (label ="Предложение",value ="suggestion",description ="Предложения по улучшению сервера"),
    discord .SelectOption (label ="Заявка в команду",value ="staff_apply",description ="Заявка на роль модератора/хелпера"),
    ]
    )
    async def category_select (self ,interaction :discord .Interaction ,select :discord .ui .Select ):
        guild =interaction .guild 
        category =select .values [0 ]

        # На этом сервере система тикетов отключена
        if guild .id in TICKET_DISABLED_GUILDS :
            await interaction .response .send_message (
            'На этом сервере система тикетов отключена.',ephemeral =True 
            )
            return 

        existing =discord .utils .get (guild .text_channels ,name =f"ticket-{interaction.user.name.lower()}")
        if existing :
            await interaction .response .send_message (
            f"У вас уже есть открытый тикет: {existing.mention}\nПожалуйста, сначала закройте его.",
            ephemeral =True 
            )
            return 

            #  RATE LIMIT CHECK 
        rate_limiter =get_rate_limiter ()
        rate_check =await rate_limiter .check_ticket_limit (guild .id ,interaction .user .id )
        if not rate_check .allowed :
            logger .warning (
            f"[RateLimit] Отказано в создании тикета: user={interaction.user} "
            f"({interaction.user.id}) reason={rate_check.reason}"
            )
            rl_embed =discord .Embed (
            color =0xE74C3C ,
            timestamp =datetime .datetime .utcnow ()
            )
            rl_embed .description =(
            "## Ограничение на создание тикетов\n"
            "\n\n"
            f"**Причина:** {rate_check.reason}\n\n"
            )
            if rate_check .wait_seconds >0 :
                if rate_check .wait_seconds >=3600 :
                    wait_str =f"{rate_check.wait_seconds // 3600} ч. {(rate_check.wait_seconds % 3600) // 60} мин."
                elif rate_check .wait_seconds >=60 :
                    wait_str =f"{rate_check.wait_seconds // 60} мин. {rate_check.wait_seconds % 60} сек."
                else :
                    wait_str =f"{rate_check.wait_seconds} сек."
                rl_embed .description +=f"**Подождите:** {wait_str}\n"

            rl_embed .description +=(
            f"**Осталось тикетов:** {rate_check.remaining}/{rate_check.limit} (за 24 часа)\n\n"
            )
            rl_embed .set_footer (text ="Защита от спама")
            await interaction .response .send_message (embed =rl_embed ,ephemeral =True )
            return 

        await interaction .response .send_message (
        "Канал тикета создаётся...",
        ephemeral =True 
        )

        category_group =discord .utils .get (guild .categories ,name =TICKET_CATEGORY_NAME )
        if not category_group :
            category_group =await guild .create_category (TICKET_CATEGORY_NAME )

        support_role =discord .utils .get (guild .roles ,name =SUPPORT_ROLE_NAME )
        overwrites ={
        guild .default_role :discord .PermissionOverwrite (read_messages =False ),
        interaction .user :discord .PermissionOverwrite (read_messages =True ,send_messages =True ),
        }
        if support_role :
            overwrites [support_role ]=discord .PermissionOverwrite (read_messages =True ,send_messages =True )

        channel =await guild .create_text_channel (
        f"ticket-{interaction.user.name.lower()}",
        category =category_group ,
        overwrites =overwrites ,
        topic =f"Ticket sahibi: {interaction.user.id}"
        )

        ts =int (datetime .datetime .utcnow ().timestamp ())

        # Встроенное приветствие в канале — стиль карточки (Custom Menu)
        e =TicketMenu .welcome (
        user =interaction .user ,
        guild =guild ,
        channel =channel 
        )

        await channel .send (
        content =f"{interaction.user.mention}"+(f" | {support_role.mention}"if support_role else ""),
        embed =e ,
        view =CloseTicketView ()
        )

        # Отправить приветственное сообщение от AI
        if self ._ai_enabled (channel .guild .id ):
            try :
                from web .ai_helper import ai_ticket_greeting 

                state ={
                'user_id':interaction .user .id ,
                'category':category ,
                'history':[],
                'status':'ai_handling',
                'ai_message_count':0 ,
                'escalated_at':None ,
                'staff_notified':False 
                }

                cog =interaction .client .get_cog ('Ticket')
                if cog :
                # If they chose complaint, set up the complaint flow right away
                    if category =='complaint':
                        state ['complaint']={
                        'active':True ,
                        'step':'ask_description',
                        'type':None ,
                        'accused_id':None ,
                        'channel_id':None ,
                        'messages':[],
                        'description':None ,
                        }
                    cog ._save_ticket_state (guild .id ,channel .id ,state )

                greeting =ai_ticket_greeting ()
                ai_embed =discord .Embed (
                color =0x00D9FF ,
                timestamp =datetime .datetime .utcnow ()
                )
                ai_embed .description =greeting 
                ai_embed .set_author (
                name ="Поддержка Aether AI",
                icon_url =interaction .client .user .display_avatar .url 
                )
                ai_embed .set_footer (text ="Если я не смогу помочь — передам модератору.")

                if category =='complaint':
                    ai_embed .description +="\n\n**Выбрана категория: Жалоба.**\nКратко опишите, что произошло:"

                await channel .send (embed =ai_embed )
            except Exception as _ae :
                log .info (f"AI ticket setup error: {_ae}")

                # Отправить DM пользователю
        try :
            dm_e =discord .Embed (color =0x5865F2 ,timestamp =datetime .datetime .utcnow ())
            dm_e .description =(
            "## Тикет создан\n"
            "### Ваш запрос принят\n"
            "\n\n"
            f"**Сервер:** {guild.name}\n"
            f"**Канал:** {channel.mention}\n"
            f"**Создан:** <t:{ts}:R>\n\n"
            "Опишите проблему как можно подробнее для быстрого решения.\n\n"
            )
            dm_e .set_thumbnail (url =guild .icon .url if guild .icon else None )
            if guild .icon :
                dm_e .set_footer (text =f"{guild.name} · Поддержка",icon_url =guild .icon .url )
            else :
                dm_e .set_footer (text =f"{guild.name} · Поддержка")
            await interaction .user .send (embed =dm_e )
        except discord .Forbidden :
            pass 

            # RATE LIMIT: Записать создание тикета 
        try :
            await rate_limiter .record_ticket_creation (guild .id ,interaction .user .id )
            logger .info (
            f"[RateLimit] Тикет создан: user={interaction.user} ({interaction.user.id}) "
            f"remaining={rate_check.remaining}/{rate_check.limit}"
            )
        except Exception as _rl_err :
            logger .error (f"[RateLimit] Ошибка записи: {_rl_err}")

            # Отправить followup сообщение
        await interaction .followup .send (
        f"Канал тикета создан: {channel.mention}",
        ephemeral =True 
        )




class FeedbackModal (discord .ui .Modal ,title ="Обратная связь"):
    """Модальное окно для ввода отзыва"""
    feedback_text =discord .ui .TextInput (
    label ="Ваш отзыв (необязательно)",
    style =discord .TextStyle .paragraph ,
    placeholder ="Расскажите, что можно улучшить...",
    required =False ,
    max_length =500 
    )

    def __init__ (self ,ticket_channel :str ,rating :str ):
        super ().__init__ ()
        self .ticket_channel =ticket_channel 
        self .rating =rating 

    async def on_submit (self ,interaction :discord .Interaction ):
        """Обработка отправки формы"""
        feedback_service =get_feedback_service ()
        feedback_service .add_feedback (
        guild_id =interaction .guild .id ,
        user_id =interaction .user .id ,
        ticket_channel =self .ticket_channel ,
        rating =self .rating ,
        comment =self .feedback_text .value if self .feedback_text .value else None 
        )

        embed =discord .Embed (
        title ="Спасибо за отзыв!",
        description ="Ваше мнение очень важно для нас и поможет улучшить качество поддержки.",
        color =0x2ECC71 
        )
        await interaction .response .send_message (embed =embed ,ephemeral =True )


class FeedbackView (discord .ui .View ):
    """Представление для сбора обратной связи"""
    def __init__ (self ,ticket_channel :str ):
        super ().__init__ (timeout =300 )# 5 минут
        self .ticket_channel =ticket_channel 

    @discord .ui .button (label =" Хорошо",style =discord .ButtonStyle .success ,custom_id ="feedback_positive")
    async def positive_feedback (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        """Положительный отзыв"""
        feedback_service =get_feedback_service ()
        feedback_service .add_feedback (
        guild_id =interaction .guild .id ,
        user_id =interaction .user .id ,
        ticket_channel =self .ticket_channel ,
        rating ='positive'
        )

        embed =discord .Embed (
        title ="Спасибо за отзыв!",
        description ="Рады, что вам понравилось! Если есть предложения — нажмите кнопку ниже.",
        color =0x2ECC71 
        )

        # Предлагаем оставить комментарий
        comment_view =discord .ui .View (timeout =60 )
        comment_button =discord .ui .Button (
        label =" Оставить комментарий",
        style =discord .ButtonStyle .primary ,
        custom_id ="add_comment"
        )

        async def comment_callback (btn_interaction :discord .Interaction ):
            modal =FeedbackModal (self .ticket_channel ,'positive')
            await btn_interaction .response .send_modal (modal )

        comment_button .callback =comment_callback 
        comment_view .add_item (comment_button )

        await interaction .response .send_message (embed =embed ,view =comment_view ,ephemeral =True )

        # Отключить кнопки
        for item in self .children :
            item .disabled =True 
        await interaction .message .edit (view =self )

    @discord .ui .button (label =" Плохо",style =discord .ButtonStyle .danger ,custom_id ="feedback_negative")
    async def negative_feedback (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        """Отрицательный отзыв"""
        # Сразу показать модальное окно для комментария
        modal =FeedbackModal (self .ticket_channel ,'negative')
        await interaction .response .send_modal (modal )

        # Отключить кнопки
        for item in self .children :
            item .disabled =True 
        await interaction .message .edit (view =self )


class AILearnModal (discord .ui .Modal ,title ="🧠 Обучение ИИ Аэйтера"):
    err_input =discord .ui .TextInput (
    label ="В чем ошибся ИИ?",
    placeholder ="Например: ИИ не заметил провокацию со стороны заявителя...",
    style =discord .TextStyle .paragraph ,
    required =True 
    )
    corr_input =discord .ui .TextInput (
    label ="Каким должно быть правильное решение?",
    placeholder ="Например: выдать обоюдный мут или отклонить жалобу...",
    style =discord .TextStyle .paragraph ,
    required =True 
    )

    async def on_submit (self ,interaction :discord .Interaction ):
        await interaction .response .defer ()
        try :
            import cogs .ai_chat as ai_mod 
            guild_key =str (interaction .guild_id )
            if guild_key not in ai_mod ._knowledge_base :
                ai_mod ._knowledge_base [guild_key ]=[]
            ai_mod ._knowledge_base [guild_key ].append ({
            'type':'admin_correction',
            'question':f"Ошибка модерации: {self.err_input.value}",
            'info':f"Правильное правило от админа: {self.corr_input.value}",
            'confidence':'high',
            'source':'admin_correction'
            })
            ai_mod ._save_knowledge_base (ai_mod ._knowledge_base )
            from cogs ._ai_card import generate_ai_dialogue_bytes 
            img_buf =await interaction .client .loop .run_in_executor (
            None ,
            generate_ai_dialogue_bytes ,
            "Спасибо, Администратор! Я сохранил ваше исправление в базу знаний. Мои алгоритмы прокачаны и больше не допустят эту ошибку!",
            self .err_input .value ,
            "solution"
            )
            file =discord .File (img_buf ,filename ="gojo_dialogue.png")
            await interaction .channel .send (file =file )
        except Exception as e :
            await interaction .followup .send (f"Ошибка сохранения обучения ИИ: {e}",ephemeral =True )


class InteractiveFeedbackView (discord .ui .View ):
    def __init__ (self ,channel :discord .TextChannel =None ):
        super ().__init__ (timeout =30 )
        self .channel =channel 
        self .clicked =False 

    async def on_timeout (self ):
        if not self .clicked and self .channel :
            try :
                await self .channel .delete ()
            except Exception :
                pass 

    @discord .ui .button (label ="Да (Yes)",style =discord .ButtonStyle .green ,custom_id ="feedback_yes")
    async def positive_feedback (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if self .clicked :
            return 
        self .clicked =True 
        await interaction .response .defer ()

        # Disable buttons
        for child in self .children :
            child .disabled =True 
        await interaction .message .edit (view =self )

        cog =interaction .client .get_cog ('Ticket')
        if cog and self .channel :
            state =cog ._get_ticket_state (interaction .guild .id ,self .channel .id )
            state ['waiting_for_feedback_text']=True 
            state ['feedback_rating']='positive'
            cog ._save_ticket_state (interaction .guild .id ,self .channel .id ,state )

        await interaction .channel .send (
        "🧠 **Большое спасибо!** Пожалуйста, напишите в чат краткую причину (что именно вам понравилось или как мы можем стать еще лучше?).\n"
        "Я лично просканирую и проанализирую ваш отзыв для улучшения своего интеллекта!"
        )

    @discord .ui .button (label ="Нет (No)",style =discord .ButtonStyle .red ,custom_id ="feedback_no")
    async def negative_feedback (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if self .clicked :
            return 
        self .clicked =True 
        await interaction .response .defer ()

        # Disable buttons
        for child in self .children :
            child .disabled =True 
        await interaction .message .edit (view =self )

        cog =interaction .client .get_cog ('Ticket')
        if cog and self .channel :
            state =cog ._get_ticket_state (interaction .guild .id ,self .channel .id )
            state ['waiting_for_feedback_text']=True 
            state ['feedback_rating']='negative'
            cog ._save_ticket_state (interaction .guild .id ,self .channel .id ,state )

        await interaction .channel .send (
        "⚠️ **Нам очень жаль!** Пожалуйста, напишите в чат, с какой проблемой вы столкнулись или что именно вам не понравилось?\n"
        "Я проанализирую вашу критику, извлеку уроки и передам информацию администрации!"
        )


class CloseTicketView (discord .ui .View ):
    def __init__ (self ):
        super ().__init__ (timeout =None )

    @discord .ui .button (
    label ="Закрыть тикет",
    style =discord .ButtonStyle .red ,
    custom_id ="ticket_close"
    )
    async def close_ticket (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        channel =interaction .channel 
        if not channel .name .startswith ("ticket-"):
            await interaction .response .send_message ("Это не канал тикета.",ephemeral =True )
            return 

        cog =interaction .client .get_cog ('Ticket')
        if cog :
            state =cog ._get_ticket_state (interaction .guild .id ,channel .id )
            if state .get ('admin_only_close'):
                is_admin =interaction .user .guild_permissions .administrator or interaction .user .guild_permissions .manage_guild 
                if not is_admin :
                    await interaction .response .send_message (
                    "❌ Этот тикет находится под контролем администрации. Только администратор может закрыть его!",
                    ephemeral =True 
                    )
                    return 
            cog ._delete_ticket_state (interaction .guild .id ,channel .id )

        messages =[]
        async for msg in channel .history (limit =200 ,oldest_first =True ):
            if not msg .author .bot :
                messages .append (f"[{msg.created_at.strftime('%d.%m.%Y %H:%M:%S')}] {msg.author.display_name}: {msg.content}")
        transcript ="\n".join (messages )if messages else "Сообщения не найдены."

        owner_id =None 
        if channel .topic and "Ticket sahibi:"in channel .topic :
            try :
                owner_id =int (channel .topic .split ("Ticket sahibi:")[-1 ].strip ())
            except Exception :
                pass 

        ts =int (datetime .datetime .utcnow ().timestamp ())

        log_ch =discord .utils .get (interaction .guild .text_channels ,name ="ticket-log")
        if log_ch :
            log_e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
            log_e .description =(
            "## Тикет закрыт\n"
            f"### {channel.name}\n"
            "\n\n"
            f"**Закрыл:** {interaction.user.mention}\n"
            f"**Дата:** <t:{ts}:F>\n"
            f"**Сообщений:** {len(messages)}\n\n"
            ""
            )
            if interaction .guild .icon :
                log_e .set_footer (text =f"{interaction.guild.name} · Логи",icon_url =interaction .guild .icon .url )
            else :
                log_e .set_footer (text =f"{interaction.guild.name} · Логи")
            file =discord .File (fp =io .StringIO (transcript ),filename =f"{channel.name}_transcript.txt")
            await log_ch .send (embed =log_e ,file =file )

        if owner_id :
            try :
                owner =await interaction .guild .fetch_member (owner_id )
                dm_e =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
                dm_e .description =(
                "## Тикет закрыт\n"
                "### Ваш запрос завершён\n"
                "\n\n"
                f"**Сервер:** {interaction.guild.name}\n"
                f"**Закрыл:** {interaction.user.display_name}\n"
                f"**Закрыт:** <t:{ts}:R>\n"
                f"**Сообщений:** {len(messages)}\n\n"
                "Если у вас возникнут новые вопросы — создайте новый тикет.\n\n"
                ""
                )
                dm_e .set_thumbnail (url =interaction .guild .icon .url if interaction .guild .icon else None )
                if interaction .guild .icon :
                    dm_e .set_footer (text =f"{interaction.guild.name} · Поддержка",icon_url =interaction .guild .icon .url )
                else :
                    dm_e .set_footer (text =f"{interaction.guild.name} · Поддержка")
                await owner .send (embed =dm_e )
            except Exception :
                pass 

                #  FEEDBACK СИСТЕМА 
                # Показать форму обратной связи перед удалением канала
        feedback_embed =discord .Embed (
        title ="Оцените качество поддержки",
        description ="Понравилась ли вам наша услуга?\nПожалуйста, нажмите кнопку ниже для оценки нашего сервиса.",
        color =0xF39C12 ,
        timestamp =datetime .datetime .utcnow ()
        )

        await interaction .response .send_message (
        embed =feedback_embed ,
        view =InteractiveFeedbackView (channel )
        )
        #  END FEEDBACK СИСТЕМА 

    @discord .ui .button (
    label ="🧠 Обучить ИИ / Указать ошибку",
    style =discord .ButtonStyle .blurple ,
    custom_id ="ticket_ai_feedback_btn"
    )
    async def ai_feedback_btn (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        is_admin =interaction .user .guild_permissions .administrator or interaction .user .guild_permissions .manage_guild 
        if not is_admin :
            await interaction .response .send_message ("❌ Только администратор может обучать ИИ и указывать на ошибки!",ephemeral =True )
            return 
        await interaction .response .send_modal (AILearnModal ())


class Ticket (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        bot .add_view (TicketView ())
        bot .add_view (CloseTicketView ())
        bot .add_view (AdminApprovalView (0 ,"",""))

    def _ai_enabled (self ,guild_id ):
        """Статус AI по серверам: глобально включено, можно отключить для конкретного сервера."""
        return bool (AI_ENABLED )and int (guild_id )not in AI_DISABLED_GUILDS 
    def _get_ai_data_path (self ,guild_id :int )->str :
        """AI ticket data dosya yolu"""
        return f"data/ai_tickets_{guild_id}.json"

    def _record_penalty (self ,guild_id :int ,user_id :int ,user_name :str ,reason :str ,duration :int ,quote :str =''):
        """Записать наказание в глобальный файл штрафов"""
        try :
            _penalty_file ='data/ticket_penalties.json'
            _penalties ={}
            if os .path .exists (_penalty_file ):
                with open (_penalty_file ,'r',encoding ='utf-8')as _f :
                    _penalties =json .load (_f )

                    # Новый формат: список как хранение (история наказаний)
            guild_str =str (guild_id )
            user_str =str (user_id )

            if guild_str not in _penalties :
                _penalties [guild_str ]={}
            if user_str not in _penalties [guild_str ]:
                _penalties [guild_str ][user_str ]=[]

                # Добавить запись о наказании
            _penalties [guild_str ][user_str ].append ({
            'name':user_name ,
            'reason':reason ,
            'date':datetime .datetime .utcnow ().isoformat (),
            'duration':duration ,
            'quote':quote [:300 ],
            })

            os .makedirs ('data',exist_ok =True )
            with open (_penalty_file ,'w',encoding ='utf-8')as _f :
                json .dump (_penalties ,_f ,ensure_ascii =False ,indent =2 )
        except Exception as _pe :
            log .info (f'[TICKET] Ошибка записи наказания: {_pe}')

    def _already_punished_for_quote (self ,guild_id :int ,user_id :int ,quote :str ,days :int =14 )->bool :
        """Проверить, наказывался ли пользователь за то же нарушение (quote) за последние days дней —
        чтобы предотвратить повторное наказание (двойное)."""
        try :
            if not quote or not quote .strip ():
                return False 
            _penalty_file ='data/ticket_penalties.json'
            if not os .path .exists (_penalty_file ):
                return False 
            with open (_penalty_file ,'r',encoding ='utf-8')as _f :
                _penalties =json .load (_f )
            guild_str =str (guild_id )
            user_str =str (user_id )
            if guild_str not in _penalties or user_str not in _penalties [guild_str ]:
                return False 
            cutoff =datetime .datetime .utcnow ()-datetime .timedelta (days =days )
            target =quote .strip ().lower ()
            for p in _penalties [guild_str ][user_str ]:
                p_quote =str (p .get ('quote','')or '').strip ().lower ()
                if p_quote and target and p_quote ==target :
                    # Это же нарушение уже было наказано
                    try :
                        p_date =datetime .datetime .fromisoformat (p ['date'])
                        if p_date >cutoff :
                            return True 
                    except Exception :
                        return True 
            return False 
        except Exception as e :
            log .info (f'[TICKET] already_punished Ошибки: {e}')
            return False 

    def _get_penalty_history (self ,guild_id :int ,user_id :int ,days :int =7 )->list :
        """В конец X день в наказание историю getir"""
        try :
            _penalty_file ='data/ticket_penalties.json'
            if not os .path .exists (_penalty_file ):
                return []

            with open (_penalty_file ,'r',encoding ='utf-8')as _f :
                _penalties =json .load (_f )

            guild_str =str (guild_id )
            user_str =str (user_id )

            if guild_str not in _penalties or user_str not in _penalties [guild_str ]:
                return []

            user_penalties =_penalties [guild_str ][user_str ]
            cutoff =datetime .datetime .utcnow ()-datetime .timedelta (days =days )

            recent =[]
            for p in user_penalties :
                try :
                    p_date =datetime .datetime .fromisoformat (p ['date'])
                    if p_date >cutoff :
                        recent .append (p )
                except Exception :
                    pass 

            return recent 
        except Exception as e :
            log .info (f'[TICKET] Penalty history Ошибки: {e}')
            return []

    def _calculate_penalty_duration (self ,guild_id :int ,user_id :int ,base_duration :int )->int :
        """История наказание по длительность hesapla (graduation)"""
        history =self ._get_penalty_history (guild_id ,user_id ,days =7 )
        history_count =len (history )

        # Первое нарушение: base_duration
        # Второе: 2x
        # Третье: 4x
        # Четвёртое+: 8x (макс 24 часа)
        multiplier =2 **min (history_count ,3 )
        calculated =base_duration *multiplier 

        # Макс 1440 минут (24 часа)
        return min (calculated ,1440 )

    def _get_ai_confidence (self ,verdict :str )->int :
        """Рассчитать уровень доверия к решению AI (0–100)"""
        confidence =50 # Начальное значение

        verdict_lower =verdict .lower ()

        # Признаки высокого доверия
        if 'открыт'in verdict_lower or 'явно'in verdict_lower or 'точно'in verdict_lower :
            confidence +=30 
        if 'верно'in verdict_lower or 'прямо'in verdict_lower :
            confidence +=20 
        if 'удалено'in verdict_lower or 'удален'in verdict_lower :
            confidence +=15 

            # Признаки низкого доверия
        if 'неясно'in verdict_lower or 'контекст'in verdict_lower :
            confidence -=30 
        if 'недостаточно'in verdict_lower or 'отсутствует'in verdict_lower :
            confidence -=20 
        if 'возможно'in verdict_lower or 'вероятно'in verdict_lower :
            confidence -=15 

        return max (0 ,min (100 ,confidence ))

    def _load_ai_data (self ,guild_id :int )->dict :
        """Загрузить данные AI-тикетов"""
        path =self ._get_ai_data_path (guild_id )
        if os .path .exists (path ):
            try :
                with open (path ,'r',encoding ='utf-8')as f :
                    return json .load (f )
            except json .JSONDecodeError :
            # Повреждённый JSON — создать резервную копию и сбросить
                import shutil 
                shutil .copy (path ,path +'.bak')
                log .info (f'[TICKET] Резервная копия повреждённого JSON создана: {path}')
                return {}
            except Exception as e :
                log .info (f'[TICKET] Ошибка загрузки данных: {e}')
        return {}

    def _save_ai_data (self ,guild_id :int ,data :dict ):
        """Сохранить данные AI-тикетов"""
        os .makedirs ('data',exist_ok =True )
        path =self ._get_ai_data_path (guild_id )
        try :
        # Сначала пишем во временный файл, затем переименовываем (атомарная запись)
            tmp =path +'.tmp'
            with open (tmp ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            import shutil 
            shutil .move (tmp ,path )
        except Exception as e :
            log .info (f'[TICKET] Ошибка сохранения данных: {e}')

    def _get_ticket_state (self ,guild_id :int ,channel_id :int )->dict :
        """Получить состояние тикета"""
        data =self ._load_ai_data (guild_id )
        return data .get (str (channel_id ),{
        'user_id':None ,
        'category':None ,
        'history':[],
        'status':'ai_handling',
        'ai_message_count':0 ,
        'escalated_at':None ,
        'staff_notified':False 
        })

    def _save_ticket_state (self ,guild_id :int ,channel_id :int ,state :dict ):
        """Ticket state'ini сохранить"""
        data =self ._load_ai_data (guild_id )
        data [str (channel_id )]=state 
        self ._save_ai_data (guild_id ,data )

    def _delete_ticket_state (self ,guild_id :int ,channel_id :int ):
        """Ticket state'ini удалить"""
        data =self ._load_ai_data (guild_id )
        if str (channel_id )in data :
            del data [str (channel_id )]
            self ._save_ai_data (guild_id ,data )

    async def _verify_insult_claim (self ,message ,state )->bool :
        """Проверяет реальные логи канала, если участник жалуется на оскорбление/нарушение от другого пользователя"""
        content =message .content .strip ()
        lower =content .lower ()
        insult_keywords =[
        'оскорб','мат','написал','ебал','рот','сук','хуй','дурак','идиот','обозва','жалоб',
        'обзыва','матер','шлюх','урод','мраз','гнид','пидор','соси','заткнись',
        'sikayet','шikayet','kufur','kюfюr','saygisiz','saygыsыz','hakaret','sёv','sove','sёve','tahrik','rahatsiz','rahatsыz'
        ]
        has_kw =any (w in lower for w in insult_keywords )
        waiting_details =state .get ('waiting_for_insult_claim_details',False )

        if not (has_kw or message .mentions or waiting_details ):
            return False 

        import re as _re 
        accused =None 
        ids =_re .findall (r'\b\d{17,19}\b',content )

        # Поиск обвиняемого
        if message .mentions :
            accused =message .mentions [0 ]
        elif ids :
            for id_str in ids :
                m =message .guild .get_member (int (id_str ))
                if not m :
                    try :
                        m =await message .guild .fetch_member (int (id_str ))
                    except Exception :
                        pass 
                if m and m .id !=message .author .id :
                    accused =m 
                    break 

        stored_accused_id =state .get ('insult_claim_accused_id')
        if stored_accused_id and not accused :
            accused =message .guild .get_member (int (stored_accused_id ))
            if not accused :
                try :
                    accused =await message .guild .fetch_member (int (stored_accused_id ))
                except Exception :
                    pass 

        if accused :
            state ['insult_claim_accused_id']=str (accused .id )
            self ._save_ticket_state (message .guild .id ,message .channel .id ,state )

            # Поиск канала
        target_ch =None 
        if message .channel_mentions :
            target_ch =message .channel_mentions [0 ]
        else :
            c_ids =_re .findall (r'\b\d{17,19}\b',content )
            for cid in c_ids :
                ch =message .guild .get_channel (int (cid ))
                if ch and isinstance (ch ,discord .TextChannel )and ch .id !=message .channel .id :
                    target_ch =ch 
                    break 

        stored_channel_id =state .get ('insult_claim_channel_id')
        if stored_channel_id and not target_ch :
            target_ch =message .guild .get_channel (int (stored_channel_id ))

        if target_ch :
            state ['insult_claim_channel_id']=str (target_ch .id )
            self ._save_ticket_state (message .guild .id ,message .channel .id ,state )

            # Запрос недостающих данных
        if not (accused and target_ch ):
            if not accused :
                state ['waiting_for_insult_claim_details']=True 
                self ._save_ticket_state (message .guild .id ,message .channel .id ,state )
                await message .channel .send (
                "⚖️ Я готов проверить историю сообщений сервера и наказать нарушителя.\n"
                "Пожалуйста, укажите **Discord ID** (17–19 цифр) или **@упоминание** участника, на которого жалуетесь."
                )
                return True 
            elif not target_ch :
                state ['waiting_for_insult_claim_details']=True 
                self ._save_ticket_state (message .guild .id ,message .channel .id ,state )
                await message .channel .send (
                f"⚖️ Нарушитель определен: {accused.mention} (`ID: {accused.id}`).\n"
                "Пожалуйста, укажите **ID канала** или **#упоминание-канала**, в котором произошёл инцидент."
                )
                return True 

                # Сброс состояния ожидания, так как все данные получены
        state ['waiting_for_insult_claim_details']=False 
        state ['insult_claim_accused_id']=None 
        state ['insult_claim_channel_id']=None 
        self ._save_ticket_state (message .guild .id ,message .channel .id ,state )

        # Сканирование канала
        async with message .channel .typing ():
            complainant_id =message .author .id 
            messages_to_analyze =[]
            try :
                async for msg in target_ch .history (limit =300 ,oldest_first =False ):
                    if not msg .author .bot :
                        if msg .author .id ==accused .id :
                            messages_to_analyze .append (f"[{msg.created_at.strftime('%d.%m %H:%M')}] [ОБВИНЯЕМЫЙ: {msg.author.display_name}] {msg.content}")
                        elif msg .author .id ==complainant_id :
                            messages_to_analyze .append (f"[{msg.created_at.strftime('%d.%m %H:%M')}] [ЗАЯВИТЕЛЬ: {msg.author.display_name}] {msg.content}")
            except Exception as e :
                log .info (f"[SCAN ERROR]: {e}")
                await message .channel .send (f"❌ Ошибка при сканировании истории канала: {e}")
                return True 

            if not messages_to_analyze :
                embed =discord .Embed (
                title ="🔍 Судебная проверка реальных логов сервера • Сообщения не найдены",
                description =(
                f"Я тщательно просканировал последние сообщения в канале {target_ch.mention} для **{accused.display_name}** и **{message.author.display_name}**.\n\n"
                "❌ **Результат:** В истории чата этого канала **не обнаружено** сообщений от указанных участников."
                ),
                color =0xE74C3C ,
                timestamp =datetime .datetime .utcnow ()
                )
                await message .channel .send (embed =embed )
                return True 

                # Сортировка от старых к новым
            messages_to_analyze .reverse ()
            logs_text ="\n".join (messages_to_analyze [:120 ])

            # Использование ИИ для глубокого анализа логов на соответствие правилам
            from web .ai_helper import _call_text 

            prompt =f"""Проанализируй историю сообщений между Заявителем ({message.author.display_name}) и Обвиняемым ({accused.display_name}) в канале {target_ch.name}. 
Определи, кто из них (или оба) нарушил официальные правила сервера.

ОФИЦИАЛЬНЫЕ ПРАВИЛА СЕРВЕРА:
Пункт — 1.1
Запрещена реклама любых сторонних ресурсов, а также любая коммерческая деятельность без согласия с администрацией сервера.
Наказание: Бан (на усмотрение администрации)

Пункт — 1.2
Запрещено любое распространение личной информации без согласия ее владельца, угрозы и причинение вреда на этой основе, упоминание докса/свата/деанона, а также любые мошеннические действия в сторону участников сервера.
Наказание: Бан (Навсегда)

Пункт — 1.3
Запрещается трансляция/публикация шокирующего, порнографического и тошнотворного контента, а также изображений, демонстрирующих кровопролитие; косвенные угрозы жизни, пропаганда наркотиков, терроризма, расизма, нацизма, фашизма и тому подобных движений. Also запрещено разжигание национальной розни, дискриминация, сексизм, враждебность к любым религиозным группам и людям с ограниченными возможностями. Данное правило распространяется на активности Discord'а.
Наказание: Бан (Навсегда)

Пункт — 1.4
Запрещены деструктивные действия по отношению к серверу, а именно: неконструктивная критика в сторону модерации/администрации, призыв покинуть сервер, попытки нарушить развитие сервера, попытки обмана администрации и т.д.
Наказание: Пред/Бан (Навсегда)

Пункт — 1.5
Запрещено использование изображений профиля (аватарка, баннер), содержащего оскорбительный, шокирующий, сексуальный, тошнотворный или изображающий кровопролитие контент. Также запрещены изображения профиля, содержащие в себе разжигающую ненависть и иную запрещенную символику.
Наказание: Пред/Бан (Навсегда)

Пункт — 1.6
Запрещено использование другой учетной записи (твинк) на сервере для любых целей, намеренное копирование профилей и ролей, а также оскорбительные или провокационные никнеймы статусы/роли сервера/обо мне.
Наказание: Пред/Бан (Навсегда)

Пункт — 1.7
Запрещен капс, спам, лесенка, флуд в любых его проявлениях, беспричинное многократное упоминание участников и ролей, а также несоблюдение тематики чата (оффтоп).
Наказание: Пред/Мут (От 4 часов до 24 часов)

Пункт — 1.8
Запрещены SoundPad и его аналоги, громкие мешающие звуки, увеличение громкости микрофона, использование программ для изменения голоса, а также программы для улучшения голоса (бас, усилок).
Наказание: Пред/Мут (От 4 часов до 24 часов)

Пункт — 1.9
Запрещено неадекватное поведение в любом его виде: оскорбления, крики, унисон, препятствование общению и тому подобное.
Наказание: Мут/Бан (На усмотрение администрации)


История сообщений (Заявитель и Обвиняемый):
{logs_text}

Инструкции:
1. Тщательно изучи сообщения ОБОИХ участников.
2. Проверь, нарушил ли Обвиняемый правила сервера (особенно пункт 1.9 - оскорбления, мат, неадекватное поведение).
3. Проверь, нарушил ли Заявитель правила сервера (возможно, он сам оскорблял Обвиняемого, провоцировал его или тоже неадекватно себя вел).
4. Определи вердикт (VERDICT):
   - GUILTY_ACCUSED (Виновен только Обвиняемый)
   - GUILTY_COMPLAINANT (Виновен только Заявитель - ложная жалоба или нарушение с его стороны)
   - GUILTY_BOTH (Виновны оба - обоюдные оскорбления/нарушения)
   - INNOCENT (Никто не виновен)
5. Для каждого виновного определи наказание (PUNISHMENT) строго на основе правил сервера:
   - BAN или KICK (для тяжелых нарушений, таких как пункты 1.1, 1.2, 1.3, 1.4, 1.5, 1.6 или критическое неадекватное поведение по 1.9)
   - MUTE (для мата, оскорблений по 1.9, спама/капса по 1.7). Длительность мута должна зависеть от тяжести и количества сообщений:
     * За одиночное (единичное) оскорбление или мат: строго от 30 до 60 минут. Никогда не давай 1 день (1440 минут) за одну фразу!
     * За множественные оскорбления (2-4 сообщения с матом): от 60 до 180 минут.
     * За систематическую злостную ругань (5+ сообщений с жестким матом): от 180 до 360 минут.
     * Максимальный мут за оскорбление в чате не должен превышать 360 минут (6 часов).
   - WARN (для более легких нарушений, устных предупреждений)
6. Все пояснения и причины пиши СТРОГО на русском языке.

Формат ответа (заполни строго по шаблону, без лишнего текста):
[VERDICT]: <GUILTY_ACCUSED / GUILTY_COMPLAINANT / GUILTY_BOTH / INNOCENT>
[ACCUSED_PUNISHMENT]: <BAN / KICK / MUTE / WARN / NONE>
[ACCUSED_DURATION]: <число минут или None>
[ACCUSED_QUOTE]: <точная цитата Обвиняемого, содержащая нарушение>
[ACCUSED_REASON]: <пункт правила и причина на русском языке>
[COMPLAINANT_PUNISHMENT]: <BAN / KICK / MUTE / WARN / NONE>
[COMPLAINANT_DURATION]: <число минут или None>
[COMPLAINANT_QUOTE]: <точная цитата Заявителя, содержащая нарушение>
[COMPLAINANT_REASON]: <пункт правила и причина на русском языке>
"""

            messages_for_llm =[
            {"role":"system","content":"Ты — строгий, справедливый ИИ-Судья на Discord сервере. Твоя задача — объективно анализировать логи на предмет нарушений правил сервера и выносить вердикт на русском языке."},
            {"role":"user","content":prompt }
            ]

            try :
                llm_response =await self .bot .loop .run_in_executor (
                None ,
                lambda :_call_text (messages_for_llm ,max_tokens =600 ,temperature =0.2 )
                )
            except Exception as e :
                log .info (f"[LLM ERROR IN VERIFICATION]: {e}")
                llm_response =""

            verdict ="INNOCENT"

            acc_punishment ="NONE"
            acc_duration =0 
            acc_quote =""
            acc_reason =""

            comp_punishment ="NONE"
            comp_duration =0 
            comp_quote =""
            comp_reason =""

            # Разбор ответа ИИ
            v_match =_re .search (r'\[VERDICT\]:\s*(\w+)',llm_response )
            if v_match :
                verdict =v_match .group (1 ).strip ().upper ()

            acc_p_match =_re .search (r'\[ACCUSED_PUNISHMENT\]:\s*(\w+)',llm_response )
            if acc_p_match :
                acc_punishment =acc_p_match .group (1 ).strip ().upper ()

            acc_d_match =_re .search (r'\[ACCUSED_DURATION\]:\s*(\w+)',llm_response )
            if acc_d_match :
                d_str =acc_d_match .group (1 ).strip ()
                if d_str .isdigit ():
                    acc_duration =int (d_str )

            acc_q_match =_re .search (r'\[ACCUSED_QUOTE\]:\s*([^\n]+)',llm_response )
            if acc_q_match :
                acc_quote =acc_q_match .group (1 ).strip ()

            acc_r_match =_re .search (r'\[ACCUSED_REASON\]:\s*([^\n]+)',llm_response )
            if acc_r_match :
                acc_reason =acc_r_match .group (1 ).strip ()

            comp_p_match =_re .search (r'\[COMPLAINANT_PUNISHMENT\]:\s*(\w+)',llm_response )
            if comp_p_match :
                comp_punishment =comp_p_match .group (1 ).strip ().upper ()

            comp_d_match =_re .search (r'\[COMPLAINANT_DURATION\]:\s*(\w+)',llm_response )
            if comp_d_match :
                d_str =comp_d_match .group (1 ).strip ()
                if d_str .isdigit ():
                    comp_duration =int (d_str )

            comp_q_match =_re .search (r'\[COMPLAINANT_QUOTE\]:\s*([^\n]+)',llm_response )
            if comp_q_match :
                comp_quote =comp_q_match .group (1 ).strip ()

            comp_r_match =_re .search (r'\[COMPLAINANT_REASON\]:\s*([^\n]+)',llm_response )
            if comp_r_match :
                comp_reason =comp_r_match .group (1 ).strip ()

                # Резервный локальный алгоритм поиска, если ИИ офлайн или выдал некорректный ответ
            is_llm_valid =verdict in ("GUILTY_ACCUSED","GUILTY_COMPLAINANT","GUILTY_BOTH","INNOCENT")

            if not is_llm_valid :
                acc_found_quote =None 
                comp_found_quote =None 

                # Поиск нарушений Обвиняемого
                for msg_text in messages_to_analyze :
                    if "[ОБВИНЯЕМЫЙ:"in msg_text :
                        msg_lower =msg_text .lower ()
                        from cogs .ai_chat import _kufur_var_mi 
                        is_match =_kufur_var_mi (msg_text )or any (w in msg_lower for w in [
                        'рот','ебал','сук','хуй','дурак','идиот','урод','мраз','пидор','соси',
                        'salak','aptal','gerizekalы','шerefsiz','namussuz','pezevenk','ibne','lan','aq','orospu','piч','yarrak','gёt','amcыk','oч'
                        ])
                        if is_match :
                            acc_found_quote =_re .sub (r'^\s*\[ОБВИНЯЕМЫЙ:[^\]]+\]\s*','',msg_text )
                            break 

                            # Поиск нарушений Заявителя
                for msg_text in messages_to_analyze :
                    if "[ЗАЯВИТЕЛЬ:"in msg_text :
                        msg_lower =msg_text .lower ()
                        from cogs .ai_chat import _kufur_var_mi 
                        is_match =_kufur_var_mi (msg_text )or any (w in msg_lower for w in [
                        'рот','ебал','сук','хуй','дурак','идиот','урод','мраз','пидор','соси',
                        'salak','aptal','gerizekalы','шerefsiz','namussuz','pezevenk','ibne','lan','aq','orospu','piч','yarrak','gёt','amcыk','oч'
                        ])
                        if is_match :
                            comp_found_quote =_re .sub (r'^\s*\[ЗАЯВИТЕЛЬ:[^\]]+\]\s*','',msg_text )
                            break 

                if acc_found_quote and comp_found_quote :
                    verdict ="GUILTY_BOTH"

                    acc_pun =_get_punishment_for_quote (acc_found_quote )
                    acc_punishment =acc_pun ['action']
                    acc_duration =acc_pun ['duration']or 60 
                    acc_reason =f"Пункт 1.9 (Неадекватное поведение/Оскорбления): {acc_pun['reason']}"
                    acc_quote =acc_found_quote 

                    comp_pun =_get_punishment_for_quote (comp_found_quote )
                    comp_punishment =comp_pun ['action']
                    comp_duration =comp_pun ['duration']or 60 
                    comp_reason =f"Пункт 1.9 (Неадекватное поведение/Оскорбления): {comp_pun['reason']}"
                    comp_quote =comp_found_quote 

                elif acc_found_quote :
                    verdict ="GUILTY_ACCUSED"
                    acc_pun =_get_punishment_for_quote (acc_found_quote )
                    acc_punishment =acc_pun ['action']
                    acc_duration =acc_pun ['duration']or 60 
                    acc_reason =f"Пункт 1.9 (Неадекватное поведение/Оскорбления): {acc_pun['reason']}"
                    acc_quote =acc_found_quote 

                elif comp_found_quote :
                    verdict ="GUILTY_COMPLAINANT"
                    comp_pun =_get_punishment_for_quote (comp_found_quote )
                    comp_punishment =comp_pun ['action']
                    comp_duration =comp_pun ['duration']or 60 
                    comp_reason =f"Пункт 1.9 (Неадекватное поведение/Оскорбления): {comp_pun['reason']}"
                    comp_quote =comp_found_quote 
                else :
                    verdict ="INNOCENT"

            complainant =message .author 

            # Функция выполнения наказания
            async def execute_punishment (target ,p_type ,dur ,p_reason ,p_quote ,label_ru ):
                # ÇİFTE CEZA KORUMASI: aynı suç (quote) bu kullanıcı için son günlerde zaten
                # cezalandırıldıysa tekrar ceza verme — sadece bilgilendir ve dur.
                if self ._already_punished_for_quote (message .guild .id ,target .id ,p_quote ):
                    await message .channel .send (
                    f"⚖️ **{target.display_name}** для этого нарушения уже было вынесено наказание ранее. "
                    "Повторное наказание за одно и то же сообщение не применяется."
                    )
                    return 
            # Проверка накопленных варнов для эскалации в BAN
                warn_count =0 
                try :
                    from cogs .warnings import load_warnings 
                    warnings_data =load_warnings ()
                    user_warnings =warnings_data .get (str (message .guild .id ),{}).get (str (target .id ),[])
                    warn_count =len (user_warnings )
                except Exception :
                    pass 

                if p_type =='MUTE'and warn_count >=2 :
                    p_type ='BAN'
                    p_reason =f"Превышен лимит предупреждений (3+ варна). Последнее нарушение: {p_reason}"

                p_embed =discord .Embed (
                title ="⚖️ Судебная проверка реальных логов сервера • НАРУШЕНИЕ ПОДТВЕРЖДЕНО",
                description =(
                f"Я лично просканировал историю сообщений сервера в канале {target_ch.mention}.\n\n"
                f"• **Нарушитель:** {target.mention} (`ID: {target.id}`)\n"
                f"• **Статус:** `{label_ru}`\n"
                "• **Точная цитата из логов:**\n"
                f"> *«{p_quote}»*\n\n"
                f"**Нарушенное правило:** {p_reason}\n"
                "**Вердикт ИИ-судьи:** ВИНОВЕН (Уверенность: 100% по результатам анализа)."
                ),
                color =0x2ECC71 ,
                timestamp =datetime .datetime .utcnow ()
                )

                if p_type in ('BAN','KICK'):
                # Запрос подтверждения у администрации
                    state ['admin_only_close']=True 
                    state ['status']='escalated'
                    self ._save_ticket_state (message .guild .id ,message .channel .id ,state )

                    p_embed .add_field (
                    name ="⚠️ [ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ АДМИНИСТРАЦИИ]",
                    value =(
                    f"ИИ рекомендует высшую меру наказания (**{p_type}**) для **{target.display_name}**.\n"
                    f"**Причина:** {p_reason}\n\n"
                    "🔒 *Решение передано администрации для одобрения. Использовать кнопки ниже.*"
                    ),
                    inline =False 
                    )

                    view =AdminApprovalView (target .id ,p_type ,p_reason ,message .guild .id ,p_quote )
                    await message .channel .send (embed =p_embed ,view =view )

                    # Уведомление в логах
                    try :
                        await self ._notify_admins_penalty (
                        message .guild ,penalty_type =p_type .lower (),
                        target =target ,reason =p_reason ,
                        source_channel =message .channel ,moderator =message .author ,
                        )
                    except Exception as _ne :
                        log .info (f'[TICKET-NOTIFY] _notify_admins_penalty failed: {_ne}')

                elif p_type =='MUTE':
                    try :
                        import datetime as _dt 
                        until =discord .utils .utcnow ()+_dt .timedelta (minutes =dur )
                        await target .timeout (until ,reason =f"AI Судья: {p_reason}")
                        hours =max (1 ,dur //60 )
                        p_embed .add_field (
                        name ="✅ [СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]",
                        value =f"Участнику **{target.display_name}** выдан реальный тайм-аут (мут) на **{hours} ч.** в Discord.",
                        inline =False 
                        )
                        self ._record_penalty (message .guild .id ,target .id ,target .name ,p_reason ,dur ,p_quote )

                        # Автоматическое начисление варна вместе с мутом
                        try :
                            warnings_cog =self .bot .get_cog ('warnings')
                            if warnings_cog :
                                await warnings_cog .add_warning (target ,message .guild .me ,f"AI Наказание MUTE: {p_reason}")
                                p_embed .add_field (
                                name ="⚠️ [АВТОМАТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ]",
                                value =f"Участнику **{target.display_name}** также начислено 1 предупреждение (варн) за нарушение.",
                                inline =False 
                                )
                        except Exception as _we :
                            log .info (f"Failed to auto-warn: {_we}")
                        try :
                            await self ._notify_admins_penalty (
                            message .guild ,penalty_type ='mute',
                            target =target ,reason =p_reason ,
                            source_channel =message .channel ,moderator =message .author ,
                            )
                        except Exception as _ne :
                            log .info (f'[TICKET-NOTIFY] _notify_admins_penalty failed: {_ne}')
                    except Exception as e :
                        p_embed .add_field (
                        name ="⚠️ [ВНИМАНИЕ МОДЕРАТОРАМ]",
                        value =f"Не удалось выдать тайм-аут автоматически (у бота недостаточно прав над ролью участника): `{e}`",
                        inline =False 
                        )
                    await message .channel .send (embed =p_embed )

                elif p_type =='WARN':
                    try :
                        warnings_cog =self .bot .get_cog ('warnings')
                        if warnings_cog :
                            await warnings_cog .add_warning (target ,message .guild .me ,p_reason )
                            p_embed .add_field (
                            name ="✅ [СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]",
                            value =f"Участнику **{target.display_name}** вынесено официальное предупреждение.",
                            inline =False 
                            )
                            self ._record_penalty (message .guild .id ,target .id ,target .name ,p_reason ,0 ,p_quote )
                            try :
                                await self ._notify_admins_penalty (
                                message .guild ,penalty_type ='warn',
                                target =target ,reason =p_reason ,
                                source_channel =message .channel ,moderator =message .author ,
                                )
                            except Exception as _ne :
                                log .info (f'[TICKET-NOTIFY] _notify_admins_penalty failed: {_ne}')
                        else :
                            p_embed .add_field (
                            name ="⚠️ [ОШИБКА]",
                            value ="Система предупреждений недоступна.",
                            inline =False 
                            )
                    except Exception as e :
                        p_embed .add_field (
                        name ="⚠️ [ОШИБКА]",
                        value =f"Не удалось выдать предупреждение автоматически: `{e}`",
                        inline =False 
                        )
                    await message .channel .send (embed =p_embed )

                    # Применение наказаний на основе вердикта
            if verdict =="GUILTY_BOTH":
                await execute_punishment (accused ,acc_punishment ,acc_duration ,acc_reason ,acc_quote ,"Обвиняемый (Обоюдное нарушение)")
                await execute_punishment (complainant ,comp_punishment ,comp_duration ,comp_reason ,comp_quote ,"Заявитель (Обоюдное нарушение)")
                return True 

            elif verdict =="GUILTY_ACCUSED":
                await execute_punishment (accused ,acc_punishment ,acc_duration ,acc_reason ,acc_quote ,"Обвиняемый (Нарушитель)")
                return True 

            elif verdict =="GUILTY_COMPLAINANT":
                await execute_punishment (complainant ,comp_punishment ,comp_duration ,comp_reason ,comp_quote ,"Заявитель (Сам нарушил / Ложная жалоба)")
                return True 

            else :
                embed =discord .Embed (
                title ="🔍 Судебная проверка реальных логов сервера • Нарушение НЕ подтверждено",
                description =(
                f"Я тщательно просканировал последние сообщения в канале {target_ch.mention} между **{complainant.display_name}** и **{accused.display_name}**.\n\n"
                "❌ **Результат:** В реальных логах чата **не обнаружено** нарушений правил сервера от указанных участников.\n\n"
                "⚠️ *ИИ-судья принимает решения исключительно на основе фактической истории сообщений сервера. Утверждения без подтверждения в логах не являются основанием для наказания.*"
                ),
                color =0xE74C3C ,
                timestamp =datetime .datetime .utcnow ()
                )
                await message .channel .send (embed =embed )

                # Уведомление в логи админов о чистой проверке
                try :
                    await self ._notify_admins_penalty (
                    message .guild ,penalty_type ='check_clean',
                    target =accused ,reason =f"Судебная проверка логов в {target_ch.name} завершилась без нарушений. Заявитель: {complainant.display_name}.",
                    source_channel =message .channel ,moderator =message .author ,
                    )
                except Exception as _ne :
                    log .info (f'[TICKET-NOTIFY] _notify_admins_penalty failed: {_ne}')

                return True 

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        """Слушать сообщения во всех каналах для судебной проверки и в тикетах для поддержки"""
        if message .author .bot :
            return 
        if not message .guild :
            return 

        guild_id =message .guild .id 
        channel_id =message .channel .id 
        state =self ._get_ticket_state (guild_id ,channel_id )

        # Обычные (не ticket) каналы AI не обрабатываются.
        if not message .channel .name .startswith ("ticket-"):
            return 

        if not self ._ai_enabled (guild_id ):
            return 

            #  РЕАЛЬНАЯ ПРОВЕРКА ЛОГОВ И ВЫДАЧА НАКАЗАНИЯ ПРИ ЖАЛОБЕ НА ОСКОРБЛЕНИЕ (ТОЛЬКО В ТИКЕТАХ)
        verified =await self ._verify_insult_claim (message ,state )
        if verified :
            return 

            #  ОБРАБОТКА AI FEEDBACK / САМООБУЧЕНИЕ 
        if state .get ('waiting_for_feedback_text'):
            state ['waiting_for_feedback_text']=False 
            rating =state .get ('feedback_rating','positive')
            self ._save_ticket_state (guild_id ,channel_id ,state )

            feedback_reason =message .content .strip ()

            async with message .channel .typing ():
                from web .ai_helper import _call_text 

                analysis_prompt =f"""Проанализируй следующий отзыв пользователя о работе поддержки Discord бота.
Оценка пользователя: {rating}
Текст отзыва: {feedback_reason}

Твоя задача:
1. Определи, является ли отзыв логичным, конструктивным и полезным для улучшения ума бота (LOGICAL), или же это просто спам/оскорбления/неконструктивный бред (NOT_LOGICAL).
2. Если отзыв логичный, напиши полезный урок или правило, которое бот должен усвоить для самообучения.
3. Напиши ответ пользователю на русском языке.

Формат ответа (строго по шаблону):
[DECISION]: <LOGICAL или NOT_LOGICAL>
[LESSON]: <извлеченный урок на русском языке для базы знаний>
[RESPONSE]: <вежливый ответ пользователю на русском языке>
"""
                messages_for_llm =[
                {"role":"system","content":"Ты — ИИ-аналитик отзывов. Твоя задача — анализировать отзывы пользователей и извлекать из них уроки для улучшения интеллекта бота."},
                {"role":"user","content":analysis_prompt }
                ]

                try :
                    llm_resp =await self .bot .loop .run_in_executor (
                    None ,
                    lambda :_call_text (messages_for_llm ,max_tokens =400 ,temperature =0.2 )
                    )
                except Exception :
                    llm_resp =""

                import re as _re 
                decision ="NOT_LOGICAL"
                lesson =""
                user_resp ="Спасибо за ваш отзыв! Мы ценим ваше мнение и постоянно работаем над улучшением нашего сервиса."

                dec_match =_re .search (r'\[DECISION\]:\s*(\w+)',llm_resp )
                if dec_match :
                    decision =dec_match .group (1 ).strip ().upper ()
                lesson_match =_re .search (r'\[LESSON\]:\s*([^\n]+)',llm_resp )
                if lesson_match :
                    lesson =lesson_match .group (1 ).strip ()
                resp_match =_re .search (r'\[RESPONSE\]:\s*([^\n]+)',llm_resp )
                if resp_match :
                    user_resp =resp_match .group (1 ).strip ()

                if decision =="LOGICAL"and lesson :
                    try :
                        import cogs .ai_chat as ai_mod 
                        guild_key =str (guild_id )
                        if guild_key not in ai_mod ._knowledge_base :
                            ai_mod ._knowledge_base [guild_key ]=[]
                        ai_mod ._knowledge_base [guild_key ].append ({
                        'type':'user_feedback_learning',
                        'question':f"Урок из отзыва пользователя ({rating}): {feedback_reason[:150]}",
                        'info':f"Принятое правило поведения ИИ: {lesson}",
                        'confidence':'high',
                        'source':'user_feedback'
                        })
                        ai_mod ._save_knowledge_base (ai_mod ._knowledge_base )
                    except Exception as _le :
                        log .info (f"Failed to save feedback to knowledge base: {_le}")

                    await message .channel .send (
                    "🤖 **[ОТЗЫВ ИЗУЧЕН И ПРИНЯТ]**\n"
                    f"{user_resp}\n\n"
                    "_*Урок сохранен в базу знаний самообучения ИИ._"
                    )
                else :
                    await message .channel .send (
                    "🤖 **[ОТЗЫВ ЗАПИСАН]**\n"
                    f"{user_resp}"
                    )

            await message .channel .send ("⏱️ *Этот тикет будет автоматически удален через 10 секунд...*")
            await asyncio .sleep (10 )
            await message .channel .delete ()
            return 

            # Staff отправил сообщение — остановить AI
        support_role =discord .utils .get (message .guild .roles ,name =SUPPORT_ROLE_NAME )
        if support_role and support_role in message .author .roles :
            if state ['status']=='ai_handling':
                state ['status']='staff_handling'
                self ._save_ticket_state (guild_id ,channel_id ,state )
            if state ['status']in ('staff_handling','escalated')and message .content .strip ():
                try :
                    from web .faq_manager import learn_from_staff 
                    last_user_q =None 
                    for msg in reversed (state .get ('history',[])):
                        if msg .get ('role')=='user':
                            last_user_q =msg .get ('content','')
                            break 
                    if last_user_q and len (last_user_q )>10 :
                        learn_from_staff (question =last_user_q ,answer =message .content ,
                        guild_id =guild_id ,staff_name =message .author .display_name )
                except Exception as e :
                    log .info (f"FAQ learn error: {e}")
            return 

        if state ['status']=='staff_handling':
            return 
        if state ['status']=='escalated':
            return 
        if state ['ai_message_count']>=MAX_AI_MESSAGES :
            await self ._escalate_ticket (message .channel ,state ,'max_messages')
            return 
            # Если анализ продолжается — не предпринимать действий с новым сообщением
        if state .get ('analyzing'):
            return 



            #  ЖАЛОБА STATE MACHINE 
        complaint =state .get ('complaint',{})
        if complaint .get ('active'):
            await self ._handle_complaint_flow (message ,state ,guild_id ,channel_id ,complaint )
            return 

            #  СИСТЕМА ДОПОЛНИТЕЛЬНЫХ ДОКАЗАТЕЛЬСТВ 
        if state .get ('waiting_for_evidence'):
            content_lower =message .content .lower ().strip ()
            if content_lower in ('да','д','yes','ага','есть'):
                state ['waiting_for_evidence']=False 
                state ['adding_evidence']=True 
                self ._save_ticket_state (guild_id ,channel_id ,state )
                await message .channel .send (
                " **Режим добавления доказательств активирован!**\n\n"
                "Пожалуйста, отправьте дополнительные доказательства сюда:\n"
                "• Скриншоты (изображения)\n"
                "• Дополнительные сообщения (скопировать-вставить)\n"
                "• Скриншоты из ЛС\n\n"
                "Когда закончите, напишите **'готово'**."
                )
            elif content_lower in ('нет','н','no','неа','не'):
                state ['waiting_for_evidence']=False 
                state ['complaint']={}
                self ._save_ticket_state (guild_id ,channel_id ,state )
                await message .channel .send ("Понятно. Могу ли я помочь чем-то ещё?")
                # else: Ждать, повторить вопрос
            return # ← Остановиться здесь, не переходить к обычному потоку AI

            # Режим сбора дополнительных доказательств
        if state .get ('adding_evidence'):
            content_lower =message .content .lower ().strip ()
            if content_lower in ('готово','готова','готово!','готова!','хватит','всё','все'):
                state ['adding_evidence']=False 
                complaint =state .get ('complaint',{})
                self ._save_ticket_state (guild_id ,channel_id ,state )
                if not complaint :
                    await message .channel .send ("Информация о жалобе не найдена.")
                    return 
                await message .channel .send ("Дополнительные доказательства получены. Повторный анализ...")
                await self ._analyze_complaint (message .channel ,state ,guild_id ,channel_id ,complaint )
            else :
                if 'additional_evidence'not in state :
                    state ['additional_evidence']=[]
                evidence_text =message .content 
                if message .attachments :
                    evidence_text +=f"\n[Ek: {len(message.attachments)} dosya]"
                state ['additional_evidence'].append (evidence_text )
                complaint =state .get ('complaint',{})
                if complaint and 'messages'in complaint :
                    complaint ['messages'].append (f"[ДОП. ДОКАЗАТЕЛЬСТВО]: {evidence_text[:300]}")
                    state ['complaint']=complaint 
                self ._save_ticket_state (guild_id ,channel_id ,state )
                await message .add_reaction ("")
            return # ← Остановиться здесь, не переходить к обычному потоку AI

            #  СИСТЕМА АПЕЛЛЯЦИИ 
        itiraz_keywords =['апелляция','подаю апелляцию','несправедливо','неверное решение',
        'нечестно','не согласен','не согласна','не принимаю']
        if any (kw in message .content .lower ()for kw in itiraz_keywords ):
        # Проверяем последние наказания
            user_penalties =self ._get_penalty_history (guild_id ,message .author .id ,days =1 )
            if user_penalties :
                last_penalty =user_penalties [-1 ]

                # Есть ли право на апелляцию?
                if state .get ('appeal_used'):
                    await message .channel .send (
                    "Апелляция уже использована. Повторно подать апелляцию нельзя.\n"
                    "Передаю администрации."
                    )
                    await self ._escalate_ticket (message .channel ,state ,'appeal_rejected')
                    return 

                state ['appeal_used']=True 
                state ['appeal_reason']=message .content 
                self ._save_ticket_state (guild_id ,channel_id ,state )

                await message .channel .send (
                "**Апелляция принята!**\n\n"
                f"Последнее наказание: **{last_penalty['reason']}** ({last_penalty['duration']} мин.)\n"
                f"Причина апелляции: {message.content[:200]}\n\n"
                "Апелляция повторно рассматривается AI..."
                )

                # Апелляция AI'ya отправить
                await self ._handle_appeal (message .channel ,state ,guild_id ,channel_id ,last_penalty )
                return 

                # Ключевые слова жалобы — срабатывают только при открытии тикета
                # ПРИМЕЧАНИЕ: кнопка жалобы уже сразу запускает поток, ключевое слово — только резервный триггер
        sikayet_keywords =['sikayet','жалоба','kufur','мат','оскорбление',
        'tehdit','taciz','bully','zorba','rahatsiz','rahatsыz']
        # Если есть вопросительные слова — не запускать поток жалобы
        question_keywords =['как','что','что такое','почему','как работает',
        'о','расскажи','объясни','опиши']
        content =message .content .lower ()
        is_question =any (kw in content for kw in question_keywords )
        # Если категория уже выбрана — пропустить триггер по ключевым словам
        category_selected =state .get ('category')is not None 
        if any (kw in content for kw in sikayet_keywords )and not is_question and not category_selected :
            state ['complaint']={
            'active':True ,
            'step':'ask_description',
            'type':None ,
            'accused_id':None ,
            'channel_id':None ,
            'messages':[],
            'description':None ,
            }
            state ['ai_message_count']+=1 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            await message .channel .send (" Кратко опишите, что произошло:")
            return 

            #  ЗАПРОС АДМИНИСТРАТОРА 
        admin_keywords =[
        'поговорить с админом','позвать админа','позовите админа',
        'позвать модератора','связаться с администрацией',
        'хочу администратора','вызовите модератора',
        'нужен модератор','нужен админ','позови админа','связь с админом',
        'admini чaгыr','admini cagir','yetkili чaгыr','yetkili cagir',
        'mod чaгыr','mod cagir','call admin','call moderator','call staff',
        'help admin','summon admin','contact admin','contact staff'
        ]
        if any (kw in message .content .lower ()for kw in admin_keywords ):
        # Проверка настроенных ролей из веб-панели
            cfg_path =f'data/ticket_notify_{message.guild.id}.json'
            admin_role_id =None 
            mod_role_id =None 
            owner_role_id =None 

            try :
                if os .path .exists (cfg_path ):
                    with open (cfg_path ,'r',encoding ='utf-8')as f :
                        cfg =json .load (f )
                        admin_role_id =cfg .get ('admin_role_id')
                        mod_role_id =cfg .get ('mod_role_id')
                        owner_role_id =cfg .get ('owner_role_id')
            except Exception :
                pass 

            ping_mentions =[]
            if owner_role_id :
                role =message .guild .get_role (int (owner_role_id ))
                if role :
                    ping_mentions .append (role .mention )
            if admin_role_id :
                role =message .guild .get_role (int (admin_role_id ))
                if role :
                    ping_mentions .append (role .mention )
            if mod_role_id :
                role =message .guild .get_role (int (mod_role_id ))
                if role :
                    ping_mentions .append (role .mention )

                    # Резервный пинг, если роли не настроены на панели
            if not ping_mentions :
                support_role =discord .utils .get (message .guild .roles ,name =SUPPORT_ROLE_NAME )
                if support_role :
                    ping_mentions .append (support_role .mention )
                else :
                    ping_mentions .append ('@Поддержка')

            mention_str =" ".join (ping_mentions )
            await message .channel .send (
            f'{mention_str} — {message.author.mention} хочет связаться с вами.'
            )
            state ['status']='staff_handling'
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

            #  NORMAL AI AKIШI 
        async with message .channel .typing ():
            try :
                from web .ai_helper import ai_ticket_response ,parse_ai_actions 

                def find_channel (guild ,*keywords ):
                    for kw in keywords :
                        ch =discord .utils .find (lambda c :kw in c .name .lower (),guild .text_channels )
                        if ch :
                            return ch .mention 
                    return None 

                guild_context ={
                'guild_name':message .guild .name ,
                'member_count':message .guild .member_count ,
                'user_name':message .author .display_name ,
                'channel_name':message .channel .name ,
                'has_image':len (message .attachments )>0 ,
                'guild_id':message .guild .id ,
                'channel_id':message .channel .id ,
                'user_roles':[r .name for r in message .author .roles if r .name !='@everyone'],
                'channels':{
                'запись':find_channel (message .guild ,'запись','запись','register','проверка','dogrulama','verification'),
                'правила':find_channel (message .guild ,'правило','rules'),
                'announcelar':find_channel (message .guild ,'announce','announce'),
                'ticket':find_channel (message .guild ,'ticket','поддержка','support'),
                'role':find_channel (message .guild ,'role','role'),
                'общий':find_channel (message .guild ,'общий','general','sohbet'),
                'panel':find_channel (message .guild ,'panel','link','web'),
                },
                'panel_url':os .getenv ('PANEL_URL',''),
                'all_channels':[c .name for c in message .guild .text_channels ],
                'channel_mentions':{c .name :c .mention for c in message .guild .text_channels },
                }

                # Добавить историю прошлых тикетов пользователя
                try :
                    all_tickets =self ._load_ai_data (guild_id )
                    past_tickets =[]
                    user_id_str =str (state .get ('user_id',''))
                    for ch_id ,t in all_tickets .items ():
                        if str (ch_id )==str (channel_id ):
                            continue # Пропустить текущий тикет
                        if str (t .get ('user_id',''))==user_id_str and t .get ('history'):
                        # Взять сводку из последнего тикета
                            last_msgs =[h ['content']for h in t ['history'][-3 :]if h .get ('role')=='user']
                            if last_msgs :
                                past_tickets .append (f"Назад ticket: {' | '.join(last_msgs[:2])}")
                    if past_tickets :
                        guild_context ['past_tickets']=past_tickets [-3 :]# Последние 3 тикета
                except Exception :
                    pass 

                full_message =message .content 
                response ,should_escalate ,escalation_category ,updated_history ,detected_category =await ai_ticket_response (
                full_message ,state ['history'],guild_context 
                )
                actions =parse_ai_actions (response )

                # Обрабатываем действия
                if actions .get ('jail'):
                    await self ._apply_jail (message .channel ,actions ['jail']['user_id'],
                    actions ['jail']['duration'],actions ['jail']['reason'],
                    message .author )

                if actions .get ('warn'):
                    await self ._apply_warn (message .channel ,actions ['warn']['user_id'],
                    actions ['warn']['reason'],message .author )

                if actions .get ('role_assign'):
                    await self ._assign_role (message .guild ,actions ['role_assign']['user_id'],
                    actions ['role_assign']['role_id'])

                if actions .get ('channel_redirect'):
                    channel =message .guild .get_channel (actions ['channel_redirect']['channel_id'])
                    if channel :
                        await message .channel .send (f"Перенаправлено в {channel.mention}")

                if actions .get ('delete_messages'):
                    await self ._delete_messages (message .guild ,actions ['delete_messages']['channel_id'],
                    actions ['delete_messages']['count'])

                state ['history']=updated_history 
                state ['ai_message_count']+=1 
                state ['category']=detected_category 

                if should_escalate or actions .get ('escalate'):
                    await self ._escalate_ticket (message .channel ,state ,escalation_category )
                    self ._save_ticket_state (guild_id ,channel_id ,state )
                    return 

                    # 12. Генерируем контекстные подсказки для модераторов
                suggested_actions =[]
                guild =message .guild

                # Если у пользователя есть предупреждения
                if guild_context .get ('user_id'):
                    try :
                        from cogs .warnings import load_warnings 
                        warnings_data =load_warnings ()
                        user_warnings =warnings_data .get (str (guild .id ),{}).get (str (guild_context ['user_id']),[])

                        if len (user_warnings )>=2 :
                            suggested_actions .append ({
                            'label':f'Ban ({len(user_warnings)} предупреждение)',
                            'action':'ban',
                            'user_id':guild_context ['user_id'],
                            'reason':f'{len(user_warnings)} предупреждение'
                            })
                        elif len (user_warnings )>=1 :
                            suggested_actions .append ({
                            'label':'Мут на 1 час',
                            'action':'mute',
                            'user_id':guild_context ['user_id'],
                            'duration':60 ,
                            'reason':'Повторное нарушение'
                            })
                    except Exception :
                        pass 

                        # Отправляем очищенный ответ
                clean_response =actions .get ('cleaned_response',response )
                if clean_response :
                # Если есть предложенные действия — добавляем кнопки
                    if suggested_actions and message .channel .permissions_for (message .guild .me ).send_messages :
                        view =discord .ui .View ()

                        for action_data in suggested_actions [:3 ]:# Максимум 3 кнопки
                            async def action_callback (interaction ,data =action_data ):
                                await interaction .response .defer (ephemeral =True )

                                target_user =guild .get_member (data ['user_id'])
                                if not target_user :
                                    await interaction .followup .send ("Пользователь не найден",ephemeral =True )
                                    return 

                                if data ['action']=='ban':
                                    await target_user .ban (reason =f"AI рекомендация: {data['reason']}")
                                    await interaction .followup .send (f"{target_user.mention} забанен",ephemeral =True )
                                elif data ['action']=='mute':
                                    until =discord .utils .utcnow ()+timedelta (minutes =data ['duration'])
                                    await target_user .timeout (until ,reason =f"AI рекомендация: {data['reason']}")
                                    await interaction .followup .send (f"{target_user.mention} заглушён на {data['duration']} мин",ephemeral =True )

                            button =discord .ui .Button (
                            label =action_data ['label'],
                            style =discord .ButtonStyle .danger if action_data ['action']=='ban'else discord .ButtonStyle .primary 
                            )
                            button .callback =action_callback 
                            view .add_item (button )

                        await message .channel .send (clean_response ,view =view )
                    else :
                        await message .channel .send (clean_response )

                self ._save_ticket_state (guild_id ,channel_id ,state )

            except Exception as e :
                log .info (f"Ошибка AI-модератора: {e}")
                import traceback 
                traceback .print_exc ()
                await self ._escalate_ticket (message .channel ,state ,'ai_error')
                self ._save_ticket_state (guild_id ,channel_id ,state )

    async def _handle_appeal (self ,channel ,state ,guild_id ,channel_id ,penalty ):
        """Апелляция AI с значение"""
        from web .ai_helper import _call_text 

        appeal_reason =state .get ('appeal_reason','')

        prompt =f"""Пользователь подаёт апелляцию на решение AI-модератора.

=== ИНФОРМАЦИЯ О НАКАЗАНИИ ===
Наказание: {penalty['reason']}
Длительность: {penalty['duration']} мин
Дата: {penalty['date']}

=== АПЕЛЛЯЦИЯ ===
{appeal_reason}

=== ЗАДАЧА ===
Оцени апелляцию. Прав ли пользователь?

ПРОВЕРЬ:
1. Содержит ли апелляция обоснованную причину?
2. Было ли наказание несправедливым?
3. Было ли неверное понимание?

ФОРМАТ ОТВЕТА:
[Оценка]: (обоснованность апелляции — 2-3 предложения)
[Решение]: KABUL или RED или BELIRSIZ"""

        async with channel .typing ():
            verdict =_call_text ([
            {'role':'system','content':'Ты эксперт по модерации. Оцени апелляцию справедливо.'},
            {'role':'user','content':prompt }
            ],max_tokens =300 )

        log .info (f"[APPEAL] verdict: {verdict!r}")

        verdict_upper =verdict .strip ().upper ()

        if 'KABUL'in verdict_upper :
            await channel .send (
            "**Апелляция принята!**\n\n"
            "Решение AI пересмотрено, выявлена несправедливость.\n"
            "Наказание будет снято. Передаю администрации."
            )
            await self ._escalate_ticket (channel ,state ,'appeal_accepted')
        elif 'RED'in verdict_upper :
            await channel .send (
            "**Апелляция отклонена.**\n\n"
            "Решение AI пересмотрено и подтверждено как верное.\n"
            "Наказание остаётся в силе."
            )
        else :# НЕОПРЕДЕЛЁННО
            await channel .send (
            " **Апелляция неясна.**\n\n"
            "Ситуация не имеет однозначного решения, передаю администрации."
            )
            await self ._escalate_ticket (channel ,state ,'appeal_unclear')

        self ._save_ticket_state (guild_id ,channel_id ,state )

    async def _handle_complaint_flow (self ,message ,state ,guild_id ,channel_id ,complaint ):
        """Управление потоком жалобы — пошагово"""
        content =message .content .strip ()
        step =complaint .get ('step')
        from cogs ._ai_card import generate_ai_dialogue_bytes 
        import re as _re 

        # 1. Автоматический поиск обвиняемого из упоминания или текста
        if not complaint .get ('accused_id'):
            if message .mentions :
                complaint ['accused_id']=str (message .mentions [0 ].id )
            else :
                ids =_re .findall (r'\b\d{17,19}\b',content )
                for id_str in ids :
                    if message .guild .get_member (int (id_str ))and id_str !=str (message .author .id ):
                        complaint ['accused_id']=id_str 
                        break 

                        # 2. Автоматический поиск канала инцидента из упоминания или текста
        target_ch =None 
        if message .channel_mentions :
            target_ch =message .channel_mentions [0 ]
            complaint ['channel_id']=str (target_ch .id )
        else :
            c_ids =_re .findall (r'\b\d{17,19}\b',content )
            for cid in c_ids :
                ch =message .guild .get_channel (int (cid ))
                if ch and isinstance (ch ,discord .TextChannel ):
                    target_ch =ch 
                    complaint ['channel_id']=str (ch .id )
                    break 

                    # Если найдены и обвиняемый, и канал — сразу переходим к проверке сообщений и анализу!
        if complaint .get ('accused_id')and complaint .get ('channel_id'):
            acc_m =message .guild .get_member (int (complaint ['accused_id']))
            acc_name =acc_m .display_name if acc_m else "Пользователь"
            complaint ['accused_name']=acc_name 
            complaint ['step']='ask_messages'
            self ._save_ticket_state (guild_id ,channel_id ,state )

            img_buf =await self .bot .loop .run_in_executor (
            None ,
            generate_ai_dialogue_bytes ,
            f"Принято! Я запускаю судебное сканирование последних 1000 сообщений в канале для анализа инцидента с {acc_name}.",
            "",
            "investigate"
            )
            file =discord .File (img_buf ,filename ="gojo_dialogue.png")
            await message .channel .send (file =file )
            complaint ['step']='ask_channel'
            content =str (complaint ['channel_id'])
            # Переходим к автоматическому сканированию сообщений ниже

        if step =='ask_description':
            complaint ['description']=content 
            complaint ['step']='ask_accused'
            state ['ai_message_count']+=1 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            img_buf =await self .bot .loop .run_in_executor (
            None ,
            generate_ai_dialogue_bytes ,
            "Я принял вашу жалобу к рассмотрению. Чтобы я мог проверить историю сообщений и вынести решение, пожалуйста, укажите нарушителя (@участник или ID) и канал (#канал).",
            "",
            "investigate"
            )
            file =discord .File (img_buf ,filename ="gojo_dialogue.png")
            await message .channel .send (file =file )
            return 

        if step =='ask_type':
            complaint ['step']='ask_accused'
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

        if step =='ask_accused':
            accused_id =complaint .get ('accused_id')or content .strip ()
            mention_match =_re .search (r'<@!?(\d+)>',accused_id )
            if mention_match :
                accused_id =mention_match .group (1 )
            elif not accused_id .isdigit ():
                found =discord .utils .find (
                lambda m :m .display_name .lower ()==accused_id .lower ()or m .name .lower ()==accused_id .lower (),
                message .guild .members 
                )
                if found :
                    accused_id =str (found .id )
                else :
                    img_buf =await self .bot .loop .run_in_executor (
                    None ,
                    generate_ai_dialogue_bytes ,
                    "Участник не найден. Пожалуйста, упомяните нарушителя (@участник) или введите его Discord ID.",
                    "",
                    "investigate"
                    )
                    file =discord .File (img_buf ,filename ="gojo_dialogue.png")
                    await message .channel .send (file =file )
                    return 
            complaint ['accused_id']=accused_id 
            complaint ['step']='ask_channel'
            state ['ai_message_count']+=1 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            await message .channel .send (
            " В каком канале произошёл инцидент? Введите ID канала.\n"
            "*(Чтобы узнать ID канала: правый клик на канал → Копировать ID)*"
            )
            return 

        if step =='ask_channel':
            complaint ['channel_id']=content .strip ()
            complaint ['step']='ask_messages'
            state ['ai_message_count']+=1 
            self ._save_ticket_state (guild_id ,channel_id ,state )

            # Если ID канала — число, автоматически сканировать сообщения
            if content .strip ().isdigit ():
            #  PROGRESS INDICATOR 
                progress_msg =await message .channel .send (
                "**Сканирование сообщений...**\n\n"
                "```[] 0%```\n"
                "Пожалуйста, подождите..."
                )
                #  END PROGRESS INDICATOR 

                try :
                    target_ch =message .guild .get_channel (int (content .strip ()))
                    if target_ch :
                        accused_id_str =complaint .get ('accused_id','')
                        accused_id_int =int (accused_id_str )if accused_id_str .isdigit ()else None 
                        complainant_id_int =state .get ('user_id')

                        # Найти имя подавшего жалобу
                        complainant_member =message .guild .get_member (complainant_id_int )if complainant_id_int else None 
                        complainant_name =complainant_member .display_name if complainant_member else str (complainant_id_int )

                        # Найти имя обвиняемого
                        accused_member =message .guild .get_member (accused_id_int )if accused_id_int else None 
                        accused_name =accused_member .display_name if accused_member else str (accused_id_int )

                        msgs =[]
                        all_msgs_raw =[]
                        # В конец 1000 сообщение сканировать
                        total_scanned =0 
                        async for msg in target_ch .history (limit =1000 ,oldest_first =False ):
                            if msg .author .bot :
                                continue 
                            all_msgs_raw .append (msg )
                            total_scanned +=1 

                            #  PROGRESS UPDATE 
                            if total_scanned %100 ==0 :
                                percent =min (100 ,int ((total_scanned /1000 )*100 ))
                                filled =int (percent /5 )
                                bar =""*filled +""*(20 -filled )
                                try :
                                    await progress_msg .edit (
                                    content =(
                                    "**Сканирование сообщений...**\n\n"
                                    f"```[{bar}] {percent}%```\n"
                                    f"Обработано: {total_scanned} сообщений"
                                    )
                                    )
                                except Exception :
                                    pass 
                                    #  END PROGRESS UPDATE 

                                    # От старых к новым
                        all_msgs_raw .reverse ()

                        # Собрать сообщения обеих сторон
                        accused_msgs_set =set ()
                        complainant_msgs_set =set ()

                        for i ,msg in enumerate (all_msgs_raw ):
                            is_accused =accused_id_int and msg .author .id ==accused_id_int 
                            is_complainant =complainant_id_int and msg .author .id ==complainant_id_int 
                            if not (is_accused or is_complainant ):
                                continue 

                                # Есть ли собеседник в ближайшем окне сообщений?
                            window_start =max (0 ,i -15 )
                            window_end =min (len (all_msgs_raw ),i +16 )
                            other_id =complainant_id_int if is_accused else accused_id_int 
                            near_other =any (
                            all_msgs_raw [j ].author .id ==other_id 
                            for j in range (window_start ,window_end )if j !=i 
                            )

                            # Прямое упоминание / ответ
                            is_mention =other_id and any (m .id ==other_id for m in msg .mentions )
                            is_reply =False 
                            if msg .reference and msg .reference .resolved :
                                ref =msg .reference .resolved 
                                if hasattr (ref ,'author')and other_id :
                                    is_reply =ref .author .id ==other_id 

                            if not (is_mention or is_reply or near_other ):
                                continue 

                            tag =' ПРЯМОЕ'if (is_mention or is_reply )else ' КОНТЕКСТ'
                            label ='ОБВИНЯЕМЫЙ'if is_accused else 'ЗАЯВИТЕЛЬ'
                            line =(
                            f"[{msg.created_at.strftime('%d.%m %H:%M')}] "
                            f"[{label}: {msg.author.display_name}] {tag}: "
                            f"{msg.content[:300]}"
                            )
                            if is_accused :
                                accused_msgs_set .add (line )
                            else :
                                complainant_msgs_set .add (line )

                                # Объединить сообщения обеих сторон
                        msgs =sorted (accused_msgs_set |complainant_msgs_set )

                        #  PROGRESS COMPLETE 
                        try :
                            await progress_msg .edit (
                            content =(
                            "**Сканирование завершено!**\n\n"
                            "```[] 100%```\n"
                            f"Найдено: {len(msgs)} релевантных сообщений"
                            )
                            )
                            await asyncio .sleep (1 )# Показать результат
                            await progress_msg .delete ()
                        except Exception :
                            pass 
                            #  END PROGRESS COMPLETE 

                        log .info (f"[TICKET] Сканирование: {len(accused_msgs_set)} сообщений обвиняемого, "
                        f"{len(complainant_msgs_set)} сообщений заявителя")

                        # Извлечь удалённые сообщения из кэша — для обеих сторон
                        deleted_msgs =[]
                        try :
                            from cogs .logs import _msg_cache as _lc 
                            for msg_id ,cached_msg in list (_lc .items ()):
                                if cached_msg .get ('channel_id')!=int (content .strip ()):
                                    continue 
                                author_id =cached_msg .get ('author_id')
                                # Только iki сканироватьfыn messagelarыnы al
                                if author_id not in (accused_id_int ,complainant_id_int ):
                                    continue 
                                    # Всё ещё в канале?
                                still_exists =any (m .id ==msg_id for m in all_msgs_raw )
                                if still_exists :
                                    continue 
                                ts =cached_msg .get ('timestamp','')[:16 ].replace ('T',' ')
                                label ='ОБВИНЯЕМЫЙ'if author_id ==accused_id_int else 'ЗАЯВИТЕЛЬ'
                                deleted_msgs .append (
                                f"[{ts}] [{label}: {cached_msg.get('author_name','?')}]  УДАЛЁННОЕ СООБЩЕНИЕ: "
                                f"{cached_msg.get('content', '[Содержимое отсутствует]')[:300]}"
                                )
                        except Exception as _de :
                            log .info (f'[TICKET] Ошибка кэша удалённых сообщений: {_de}')

                        if deleted_msgs :
                            msgs .extend (deleted_msgs )
                            await message .channel .send (
                            f"**Обнаружено {len(deleted_msgs)} удалённых сообщений** (содержимое сохранено)."
                            )

                        if msgs :
                            complaint ['messages']=msgs 
                            complaint ['messages_verified']=True 
                            complaint ['step']='analyze'
                            complaint ['accused_name']=accused_name 
                            complaint ['complainant_name']=complainant_name 
                            self ._save_ticket_state (guild_id ,channel_id ,state )
                            await message .channel .send (
                            f"**Найдено {len(msgs)} сообщений.** Начинаю анализ..."
                            )
                            await self ._analyze_complaint (message .channel ,state ,guild_id ,channel_id ,complaint )
                            return 
                        else :
                            await message .channel .send (
                            f"В канале **{target_ch.mention}** сообщения между **{accused_name}** и **{complainant_name}** не найдены.\n\n"
                            "Скопируйте и вставьте сюда сообщения этого пользователя:"
                            )
                            complaint ['messages_verified']=False 
                            complaint ['step']='ask_messages'
                            self ._save_ticket_state (guild_id ,channel_id ,state )
                            return 
                    else :
                        await message .channel .send (
                        "Канал не найден. Скопируйте и вставьте сюда сообщения этого пользователя:"
                        )
                        complaint ['step']='ask_messages'
                        self ._save_ticket_state (guild_id ,channel_id ,state )
                        return 
                except Exception as e :
                    log .info (f"[TICKET] Channel scan error: {e}")
                    await message .channel .send (
                    "Ошибка при сканировании канала. Скопируйте и вставьте сообщения вручную:"
                    )
                    complaint ['step']='ask_messages'
                    self ._save_ticket_state (guild_id ,channel_id ,state )
                    return 

            await message .channel .send (
            "Скопируйте и вставьте сюда сообщения этого пользователя:"
            )
            return 

        if step =='ask_messages':
            complaint ['messages']=[content ]
            complaint ['messages_verified']=False 
            complaint ['step']='analyze'
            # Если имён нет — добавить сейчас
            if 'complainant_name'not in complaint :
                cm =message .guild .get_member (state .get ('user_id'))
                complaint ['complainant_name']=cm .display_name if cm else str (state .get ('user_id','?'))
            if 'accused_name'not in complaint :
                accused_id_str =complaint .get ('accused_id','')
                am =message .guild .get_member (int (accused_id_str ))if accused_id_str .isdigit ()else None 
                complaint ['accused_name']=am .display_name if am else accused_id_str 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            await self ._analyze_complaint (message .channel ,state ,guild_id ,channel_id ,complaint )
            return 

        if step =='confirm_messages':
            if content .lower ()in ('да','д','yes','ага'):
                complaint ['step']='analyze'
                if 'complainant_name'not in complaint :
                    cm =message .guild .get_member (state .get ('user_id'))
                    complaint ['complainant_name']=cm .display_name if cm else str (state .get ('user_id','?'))
                if 'accused_name'not in complaint :
                    accused_id_str =complaint .get ('accused_id','')
                    am =message .guild .get_member (int (accused_id_str ))if accused_id_str .isdigit ()else None 
                    complaint ['accused_name']=am .display_name if am else accused_id_str 
                self ._save_ticket_state (guild_id ,channel_id ,state )
                await self ._analyze_complaint (message .channel ,state ,guild_id ,channel_id ,complaint )
            else :
                complaint ['messages']=[]
                complaint ['messages_verified']=False 
                complaint ['step']='ask_messages'
                self ._save_ticket_state (guild_id ,channel_id ,state )
                await message .channel .send ("Скопируйте и вставьте сюда сообщения этого пользователя:")
            return 

    async def _analyze_complaint (self ,channel ,state ,guild_id ,channel_id ,complaint ):
        """Глубокий анализ жалобы с проверкой"""
        from web .complaint_analyzer import ComplaintAnalyzer 

        # Создал analizёr
        analyzer =ComplaintAnalyzer (self .bot )

        # Получаем ID заявителя и обвиняемого
        complainant_id =state .get ('user_id')
        accused_id =complaint .get ('accused_id')

        if not complainant_id or not accused_id :
            await channel .send ("Не удалось определить участников жалобы.")
            state ['complaint']={}
            state ['analyzing']=False 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

            # Преобразуем в int, если необходимо
        try :
            complainant_id =int (complainant_id )
            accused_id =int (accused_id )if str (accused_id ).isdigit ()else None 
        except Exception :
            await channel .send ("Некорректный ID пользователя.")
            state ['complaint']={}
            state ['analyzing']=False 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

        if not accused_id :
            await channel .send ("Не удалось определить ID обвиняемого.")
            state ['complaint']={}
            state ['analyzing']=False 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

            # Получаем текст жалобы и сообщения
        complaint_text =complaint .get ('description','')
        provided_messages =complaint .get ('messages',[])

        # Запускаем анализ
        async with channel .typing ():
            try :
                result =await analyzer .analyze_complaint (
                guild =channel .guild ,
                complainant_id =complainant_id ,
                accused_id =accused_id ,
                complaint_text =complaint_text ,
                provided_messages =provided_messages 
                )
            except Exception as e :
                log .info (f"[COMPLAINT] Ошибка analiza: {e}")
                import traceback 
                traceback .print_exc ()
                await channel .send ("Произошла ошибка при анализе жалобы. Передаю модератору.")
                await self ._escalate_ticket (channel ,state ,'ai_error')
                return 

                # Получаем результат анализа
        verdict =result ['verdict']
        confidence =result ['confidence']
        severity =result ['severity']
        recommendation =result ['recommendation']
        analysis_text =result ['analysis']
        evidence =result ['evidence']

        log .info (f"[COMPLAINT] verdict={verdict}, confidence={confidence}, severity={severity}")

        # Получаем профили для embed (analyzer уже импортирован на строке 1146)
        complainant_info =await analyzer ._get_user_profile (channel .guild ,complainant_id )
        accused_info =await analyzer ._get_user_profile (channel .guild ,accused_id )

        # Формируем embed-сообщение
        try :
            embed =analyzer ._form_embed (
            verdict =verdict ,
            confidence =confidence ,
            severity =severity ,
            evidence =evidence ,
            recommendation =recommendation ,
            complainant_info =complainant_info ,
            accused_info =accused_info ,
            )
        except Exception as _ee :
            log .info (f"[COMPLAINT] embed build error: {_ee}")
            embed =None 

            # Отправляем полный подробный отчет анализа по письму (Embed / Текст в чат)
        if embed :
            await channel .send (embed =embed )
        else :
            await channel .send (f"**Анализ инцидента ({confidence}%):**\n\n{analysis_text}")

            # Если уверенность низкая (< 50%) — не наказываем автоматически, но сообщаем результат
        if confidence <50 :
            await channel .send (
            f"⚠️ **Уверенность ИИ ниже порога безопасности ({confidence}% < 50%)**.\n"
            "Анализ инцидента завершен, но автоматическое наказание не применяется."
            )
            state ['complaint']={}
            state ['analyzing']=False 
            self ._save_ticket_state (guild_id ,channel_id ,state )
            return 

            # Применяем рекомендацию на основе вердикта
        action =recommendation ['action']
        duration =recommendation ['duration']
        reason =recommendation ['reason']

        guild =channel .guild 

        # Получаем участников
        complainant =guild .get_member (complainant_id )
        accused =guild .get_member (accused_id )

        # Определяем, кто виноват на основе вердикта
        verdict_upper =verdict .upper ()

        # Функция для применения наказания к пользователю
        async def apply_punishment (target ,target_name ,action_type ,dur ,punishment_reason ):
            if not target :
                return 

            # ЗАЩИТА ОТ ДВОЙНОГО НАКАЗАНИЯ — не наказывать повторно за то же нарушение.
            quote_key =punishment_reason or ''
            try :
                if complaint .get ('messages'):
                    quote_key =str (complaint ['messages'][0 ])[:200 ]
            except Exception :
                pass 
            if self ._already_punished_for_quote (guild_id ,target .id ,quote_key ):
                await channel .send (
                f"⚖️ Для **{target.display_name}** по этому нарушению уже было вынесено наказание ранее. "
                "Повторное наказание за одно и то же нарушение не применяется."
                )
                return 

            try :
                if action_type in ('BAN','KICK'):
                # Для бана и кика — не наказываем сразу, а отправляем админам и блокируем тикет для обычного закрытия
                    state ['admin_only_close']=True 
                    state ['status']='escalated'
                    self ._save_ticket_state (guild_id ,channel_id ,state )

                    embed =discord .Embed (
                    title ="⚠️ [ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ АДМИНИСТРАЦИИ]",
                    description =(
                    f"ИИ рекомендует высшую меру наказания (**{action_type}**) для **{target.display_name}**.\n"
                    f"**Причина:** {punishment_reason}\n\n"
                    "🔒 *Решение передано администрации для одобрения. Использовать кнопки ниже.*"
                    ),
                    color =0xE74C3C ,
                    timestamp =datetime .datetime .utcnow ()
                    )
                    view =AdminApprovalView (target .id ,action_type ,punishment_reason ,guild_id ,quote_key )
                    await channel .send (embed =embed ,view =view )
                    return 

                elif action_type in ('MUTE','TIMEOUT','MUTE_BOTH'):
                    if dur :
                        until =discord .utils .utcnow ()+timedelta (minutes =dur )
                        await target .timeout (until ,reason =f"AI: {punishment_reason}")
                        hours =max (1 ,dur //60 )
                        await channel .send (f"✅ **[СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]**: Участнику **{target.display_name}** выдан тайм-аут на **{hours} ч.**\n**Причина:** {punishment_reason}")
                        self ._record_penalty (guild_id ,target .id ,target .name ,punishment_reason ,dur ,quote_key )

                elif action_type in ('WARN','WARN_COMPLAINANT'):
                    warnings_cog =self .bot .get_cog ('warnings')
                    if warnings_cog :
                        await warnings_cog .add_warning (target ,guild .me ,punishment_reason )
                        await channel .send (f"✅ **[СУДЕБНОЕ РЕШЕНИЕ ВЫПОЛНЕНО]**: Участнику **{target.display_name}** вынесено официальное предупреждение.\n**Причина:** {punishment_reason}")
                        self ._record_penalty (guild_id ,target .id ,target .name ,punishment_reason ,0 ,quote_key )
            except Exception as e :
                log .error (f"[AI Punishment Error]: {e}")
                await channel .send (f"❌ Не удалось применить наказание к {target.display_name}: {e}")

                # Применяем наказание на основе вердикта
        if 'GUILTY'in verdict_upper and 'NOT'not in verdict_upper :
            await apply_punishment (accused ,"обвиняемого",action ,duration ,reason )
        elif 'INNOCENT'in verdict_upper or 'NOT GUILTY'in verdict_upper or 'FALSE'in verdict_upper :
            false_reason =f"Ложная жалоба. {reason}"
            await apply_punishment (complainant ,"заявителя",action ,duration ,false_reason )
        elif 'BOTH'in verdict_upper or 'MUTUAL'in verdict_upper :
            both_reason =f"Обоюдное нарушение. {reason}"
            await apply_punishment (accused ,"обвиняемого",action ,duration ,both_reason )
            await apply_punishment (complainant ,"заявителя",action ,duration ,both_reason )
        elif 'NO_VIOLATION'in verdict_upper or 'NO ACTION'in verdict_upper :
            await channel .send ("⚖️ **Результат:** Нарушений не обнаружено. Жалоба отклонена по результатам проверки логов.")
        else :
            await apply_punishment (accused ,"обвиняемого",action ,duration ,reason )

            # Очищаем состояние
        state ['complaint']={}
        state ['analyzing']=False 
        self ._save_ticket_state (guild_id ,channel_id ,state )
    async def _escalate_ticket (self ,channel :discord .TextChannel ,state :dict ,reason :str ):
        """Передать тикет модераторам"""
        if state ['staff_notified']:
            return # уже передан

        state ['status']='escalated'
        state ['escalated_at']=datetime .datetime .utcnow ().isoformat ()
        state ['staff_notified']=True 

        # Сообщение о передаче модераторам
        e =discord .Embed (color =0xF39C12 ,timestamp =datetime .datetime .utcnow ())

        reason_text ={
        'sikayet':'Жалоба должна быть рассмотрена модератором',
        'teknik':'Техническая проблема требует контроля модератора',
        'администратор':'Действие требует прав модератора',
        'agir_ihlal':'Обнаружено серьёзное нарушение, требуется контроль',
        'апелляция':'Пользователь оспаривает решение AI',
        'ban_talebi':'Бан может быть выдан только модератором',
        'max_messages':'Лимит сообщений превышен, модераторы получают управление',
        'ai_error':'Системная ошибка, модераторы получают управление',
        'другой':'Этот вопрос должен быть рассмотрен модератором'
        }

        e .description =(
        "## Передано модератору\n"
        "\n\n"
        f"**Причина:** {reason_text.get(reason, 'Модераторы получают управление')}\n\n"
        "Наша команда поддержки свяжется с вами в ближайшее время.\n\n"
        ""
        )
        if channel .guild .icon :
            e .set_footer (text =f"{channel.guild.name} · Модерация",icon_url =channel .guild .icon .url )
        else :
            e .set_footer (text =f"{channel.guild.name} · Модерация")

        await channel .send (embed =e )

        # Пинг роли поддержки
        support_role =discord .utils .get (channel .guild .roles ,name =SUPPORT_ROLE_NAME )
        if support_role :
            await channel .send (
            f" {support_role.mention} — Новый тикет передан на рассмотрение!"
            )

            # Сохранить состояние
        self ._save_ticket_state (channel .guild .id ,channel .id ,state )

    async def _apply_jail (self ,channel :discord .TextChannel ,user_id :int ,duration :int ,reason :str ,complainant :discord .Member ):
        """Применить наказание Jail от AI-модератора"""
        try :
            guild =channel .guild 
            target_user =guild .get_member (user_id )
            if not target_user :
                try :
                    target_user =await guild .fetch_member (user_id )
                except Exception :
                    target_user =None 

            if not target_user :
                await channel .send ("Пользователь не найден на этом сервере.")
                return 

                # Найти или создать роль Jail
            jail_role =discord .utils .get (guild .roles ,name ="Jail")
            if not jail_role :
            # Создать роль Jail
                jail_role =await guild .create_role (
                name ="Jail",
                color =discord .Color .dark_gray (),
                reason ="AI Moderator — роль заключения"
                )
                # Запрещаем роль Jail во всех каналах
            for channel_obj in guild .channels :
                try :
                    await channel_obj .set_permissions (jail_role ,send_messages =False ,speak =False )
                except Exception :
                    pass 

                    # Выдаём роль Jail
            await target_user .add_roles (jail_role ,reason =f"AI Moderator: {reason}")

            # Отправляем DM пользователю
            try :
                dm_embed =discord .Embed (color =0xE74C3C ,timestamp =datetime .datetime .utcnow ())
                dm_embed .description =(
                "## Наказание: Заключение\n"
                "### Вы получили заключение\n"
                "\n\n"
                f"**Сервер:** {guild.name}\n"
                f"**Длительность:** {duration} минут\n"
                f"**Причина:** {reason}\n\n"
                "По окончании срока роль заключения будет автоматически снята.\n"
                "Если хотите оспорить — напишите в тикет.\n\n"
                ""
                )
                if guild .icon :
                    dm_embed .set_footer (text =f"{guild.name} · Модерация",icon_url =guild .icon .url )
                else :
                    dm_embed .set_footer (text =f"{guild.name} · Модерация")
                await target_user .send (embed =dm_embed )
            except Exception :
                pass 

                # Канал bildir
            jail_embed =discord .Embed (color =0x2ECC71 ,timestamp =datetime .datetime .utcnow ())
            jail_embed .description =(
            "## Заключение применено\n"
            "### Наказание назначено\n"
            "\n\n"
            f"**Пользователь:** {target_user.mention}\n"
            f"**Длительность:** {duration} минут\n"
            f"**Причина:** {reason}\n\n"
            "Наша команда модераторов поможет решить проблему.\n"
            "Если хотите оспорить — оставьте этот тикет открытым.\n\n"
            ""
            )
            if channel .guild .icon :
                jail_embed .set_footer (text =f"{channel.guild.name} · Модерация",icon_url =channel .guild .icon .url )
            else :
                jail_embed .set_footer (text =f"{channel.guild.name} · Модерация")
            await channel .send (embed =jail_embed )

            # Автоматически снять Jail по истечении срока (в минутах)
            await self ._schedule_unjail (guild ,target_user ,jail_role ,duration )

            # Сохранить в мод-лог
            from cogs .logs import save_event 
            save_event (
            guild .id ,
            'moderation',
            'ai_jail',
            {
            'target':str (target_user ),
            'target_id':target_user .id ,
            'duration':duration ,
            'reason':reason ,
            'complainant':str (complainant ),
            'complainant_id':complainant .id ,
            'timestamp':datetime .datetime .utcnow ().isoformat ()
            }
            )

            # Уведомить администраторов о применённом наказании
            log .info (f'[TICKET-NOTIFY] === JAIL ВЫЗОВ === target={target_user} ({target_user.id}) reason={reason[:80]}')
            try :
                await self ._notify_admins_penalty (
                guild ,penalty_type ='jail',
                target =target_user ,reason =reason ,
                source_channel =channel ,moderator =complainant ,
                )
            except Exception as _ne :
                log .info (f'[TICKET-NOTIFY] _notify_admins_penalty выбросил: {_ne}')
                import traceback as _tb 
                log .info (f'[TICKET-NOTIFY] Traceback: {_tb.format_exc()[:300]}')

        except Exception as e :
            await channel .send (f"Ошибка при выдаче наказания Jail: {str(e)}")
            log .info (f"Ошибка Jail: {e}")

    async def _schedule_unjail (self ,guild :discord .Guild ,user :discord .Member ,jail_role :discord .Role ,duration :int ):
        """Снять jail-наказание после указанного времени"""
        import asyncio 
        await asyncio .sleep (duration *60 )

        try :
        # Пользователь всё ещё на сервере?
            fresh_member =guild .get_member (user .id )
            if not fresh_member :
                try :
                    fresh_member =await guild .fetch_member (user .id )
                except discord .NotFound :
                    log .info (f'[TICKET] Unjail: {user} покинул сервер, роль не снята')
                    return 
                except Exception as e :
                    log .info (f'[TICKET] Unjail — ошибка получения: {e}')
                    return 

                    # Роль Jail всё ещё существует?
            fresh_role =guild .get_role (jail_role .id )
            if not fresh_role :
                log .info ('[TICKET] Unjail: Роль Jail удалена')
                return 

            if fresh_role in fresh_member .roles :
                await fresh_member .remove_roles (fresh_role ,reason ="Срок заключения истёк (AI Moderator)")
                try :
                    dm_embed =discord .Embed (color =0x2ECC71 ,timestamp =datetime .datetime .utcnow ())
                    dm_embed .description =(
                    "## Заключение снято\n"
                    "### Наказание завершено\n"
                    "\n\n"
                    f"**Сервер:** {guild.name}\n\n"
                    "Ваш срок заключения истёк. Теперь вы можете пользоваться сервером как обычно.\n"
                    "Пожалуйста, продолжайте соблюдать правила сервера.\n\n"
                    ""
                    )
                    if guild .icon :
                        dm_embed .set_footer (text =f"{guild.name} · Модерация",icon_url =guild .icon .url )
                    else :
                        dm_embed .set_footer (text =f"{guild.name} · Модерация")
                    await fresh_member .send (embed =dm_embed )
                except Exception :
                    pass 
        except Exception as e :
            log .info (f'[TICKET] Unjail — ошибка: {e}')

    async def _apply_warn (self ,channel :discord .TextChannel ,user_id :int ,reason :str ,moderator :discord .Member ):
        """Выдать предупреждение от AI"""
        try :
            guild =channel .guild 
            target_user =guild .get_member (user_id )
            if not target_user :
                try :
                    target_user =await guild .fetch_member (user_id )
                except Exception :
                    target_user =None 

            if not target_user :
                await channel .send ("Пользователь не найдено на на сервере.")
                return 

                # Выдать предупреждение пользователю с система warnings
            from cogs .warnings import warnings 
            warnings_cog =self .bot .get_cog ('warnings')
            if warnings_cog :
            # Вызвать метод add_warning напрямую (без interaction)
                await warnings_cog .add_warning (target_user ,moderator ,reason )
                await channel .send (f"Предупреждение выдано {target_user.mention}: {reason}")
                # Уведомить администраторов
                log .info (f'[TICKET-NOTIFY] === WARN ВЫЗОВ === target={target_user} ({target_user.id}) reason={reason[:80]}')
                try :
                    await self ._notify_admins_penalty (
                    guild ,penalty_type ='warn',
                    target =target_user ,reason =reason ,
                    source_channel =channel ,moderator =moderator ,
                    )
                except Exception as _ne :
                    log .info (f'[TICKET-NOTIFY] _notify_admins_penalty выбросил: {_ne}')
                    import traceback as _tb 
                    log .info (f'[TICKET-NOTIFY] Traceback: {_tb.format_exc()[:300]}')
            else :
                await channel .send ("Система предупреждений недоступна.")

        except Exception as e :
            await channel .send (f"Ошибка при выдаче предупреждения: {str(e)}")
            log .info (f"Ошибка предупреждения: {e}")

    async def _notify_admins_penalty (self ,guild ,*,penalty_type :str ,target ,
    reason :str ,source_channel ,moderator ):
        """Уведомить администраторов о применённом наказании.

        Канал для уведомлений: сначала `data/ticket_notify_<guild_id>.json` →
        `notify_channel_id`, иначе первый текстовый канал с именем
        'admin-log'/'mod-log'/'логи-модерации', иначе None (тогда DM
        владельцу сервера).
        """
        import traceback 
        #  ДИАГНОСТИКА: детальный print на каждом шаге 
        log .info ('[TICKET-NOTIFY] === ВЫЗОВ УВЕДОМЛЕНИЯ ===')
        log .info (f'[TICKET-NOTIFY] guild={guild.id} ({guild.name}) type={penalty_type}')
        log .info (f'[TICKET-NOTIFY] target={target} ({getattr(target, "id", "?")}) reason={reason[:80] if reason else "(пусто)"}')
        log .info (f'[TICKET-NOTIFY] source_channel={getattr(source_channel, "id", "?")} moderator={getattr(moderator, "id", "?")}')

        notify_ch_id =None 
        cfg_path =f'data/ticket_notify_{guild.id}.json'
        try :
            if os .path .exists (cfg_path ):
                with open (cfg_path ,'r',encoding ='utf-8')as f :
                    notify_ch_id =(json .load (f )or {}).get ('notify_channel_id')
                log .info (f'[TICKET-NOTIFY] Конфиг найден: notify_ch_id={notify_ch_id}')
            else :
                log .info (f'[TICKET-NOTIFY] Конфиг НЕ найден: {cfg_path}')
        except Exception as e :
            log .info (f'[TICKET-NOTIFY] Ошибка чтения конфига: {e}')
            notify_ch_id =None 

        target_ch =None 
        if notify_ch_id :
            try :
                target_ch =guild .get_channel (int (notify_ch_id ))
                if not target_ch :
                    target_ch =await guild .fetch_channel (int (notify_ch_id ))
                log .info (f'[TICKET-NOTIFY] Канал из конфига: {target_ch} ({getattr(target_ch, "id", "?")})')
            except Exception as e :
                log .info (f'[TICKET-NOTIFY] Ошибка получения канала по ID: {e}')
                target_ch =None 
        if target_ch is None :
        # Fallback: ищем канал по имени
            tried =[]
            for name in ('admin-log','mod-log','логи-модерации','staff-log'):
                target_ch =discord .utils .get (guild .text_channels ,name =name )
                tried .append (name )
                if target_ch :
                    log .info (f'[TICKET-NOTIFY] Найден канал по имени: {name} → {target_ch.id}')
                    break 
            if target_ch is None :
                log .info (f'[TICKET-NOTIFY] Ни один из каналов {tried} не найден на сервере. Доступные: {[c.name for c in guild.text_channels[:10]]}...')

        type_emoji ={
        'warn':'',
        'jail':'',
        'ban':'',
        'kick':'',
        'mute':'',
        'check_clean':'🔍',
        }.get (penalty_type ,'')
        type_label ={
        'warn':'Предупреждение',
        'jail':'Jail (ограничение)',
        'ban':'Бан',
        'kick':'Кик',
        'mute':'Мут',
        'check_clean':'Проверка логов (Нарушений не найдено)',
        }.get (penalty_type ,penalty_type .title ())

        embed =discord .Embed (
        title =f"{type_emoji} AI Модератор: {type_label}",
        color =0x2ECC71 if penalty_type =='check_clean'else (0xE74C3C if penalty_type in ('ban','jail')else 0xF1C40F ),
        timestamp =datetime .datetime .utcnow (),
        )
        embed .add_field (name ="Пользователь",value =f"{target.mention} (`{target.id}`)",inline =False )
        embed .add_field (name ="Причина",value =reason [:500 ]if reason else "—",inline =False )
        embed .add_field (name ="Канал тикета",value =source_channel .mention if source_channel else "—",inline =True )
        embed .add_field (name ="Модератор",value =moderator .mention if moderator else "AI",inline =True )
        embed .set_footer (text =f"{guild.name} • AI Moderation",icon_url =guild .icon .url if guild .icon else None )

        # Пинг админов (роли с правами administrator)
        admin_ping =""
        try :
            admin_role =discord .utils .get (guild .roles ,permissions =discord .Permissions (administrator =True ))
            if admin_role and penalty_type !='check_clean':
                admin_ping =admin_role .mention +" "
                log .info (f'[TICKET-NOTIFY] Admin role для пинга: {admin_role.name} ({admin_role.id})')
            else :
                log .info ('[TICKET-NOTIFY] Admin role не найдена (нет роли с правами admin)')
        except Exception as e :
            log .info (f'[TICKET-NOTIFY] Ошибка поиска admin role: {e}')

        sent =False 
        if target_ch is not None :
            try :
                log .info (f'[TICKET-NOTIFY] Отправляю embed в #{getattr(target_ch, "name", "?")} ({target_ch.id})...')
                await target_ch .send (content =admin_ping or None ,embed =embed )
                sent =True 
                log .info (f'[TICKET-NOTIFY] Уведомление отправлено в канал #{target_ch.name}')
            except Exception as e :
                log .info (f'[TICKET-NOTIFY] Ошибка отправки в канал: {e}')
                log .info (f'[TICKET-NOTIFY] Traceback: {traceback.format_exc()[:300]}')
                sent =False 
        if not sent :
        # Fallback: DM владельцу
            try :
                if guild .owner and not guild .owner .bot :
                    log .info (f'[TICKET-NOTIFY] Fallback: отправляю DM владельцу {guild.owner} ({guild.owner.id})...')
                    await guild .owner .send (content =admin_ping ,embed =embed )
                    log .info ('[TICKET-NOTIFY] DM отправлено владельцу')
                else :
                    log .info ('[TICKET-NOTIFY] Нет владельца сервера — уведомление НИКУДА не доставлено!')
            except Exception as e :
                log .info (f'[TICKET-NOTIFY] Ошибка отправки DM владельцу: {e}')
                log .info ('[TICKET-NOTIFY] УВЕДОМЛЕНИЕ ПОТЕРЯНО!')
        log .info ('[TICKET-NOTIFY] === КОНЕЦ ===\n')

    async def _assign_role (self ,guild :discord .Guild ,user_id :int ,role_id :int ):
        """Назначить роль от AI"""
        try :
            target_user =guild .get_member (user_id )
            role =guild .get_role (role_id )

            if not target_user :
                log .info (f"[TICKET] Назначение роли: пользователь {user_id} не найден")
                return 

            if not role :
                log .info (f"[TICKET] Назначение роли: роль {role_id} не найдена")
                return 

            await target_user .add_roles (role ,reason ="AI Ticket Assistant")
            log .info (f"[TICKET] Роль {role.name} выдана {target_user}")

        except Exception as e :
            log .info (f"Ошибка назначения роли: {e}")

    async def _delete_messages (self ,guild :discord .Guild ,channel_id :int ,count :int ):
        """Удалить сообщения от AI"""
        try :
            channel =guild .get_channel (channel_id )
            if not channel :
                log .info (f"[TICKET] Удаление сообщений: канал {channel_id} не найден")
                return 

            deleted =await channel .purge (limit =min (count ,100 ))
            log .info (f"[TICKET] Удалено {len(deleted)} сообщений в {channel.name}")

        except Exception as e :
            log .info (f"Ошибка удаления сообщений: {e}")

    async def _check_message_history (self ,channel :discord .TextChannel ,guild :discord .Guild ,user_id :int =None ,target_channel_id :int =None )->str :
        """Сканировать сообщения указанного пользователя"""
        try :
            target_channel =channel 
            if target_channel_id :
                tc =guild .get_channel (target_channel_id )
                if tc :
                    target_channel =tc 

            messages =[]
            async for msg in target_channel .history (limit =200 ,oldest_first =False ):
                if msg .author .bot :
                    continue 
                if user_id and msg .author .id !=user_id :
                    continue 
                messages .append ({
                'author':msg .author .display_name ,
                'author_id':msg .author .id ,
                'content':msg .content [:300 ],
                'timestamp':msg .created_at .strftime ('%H:%M'),
                'edited':msg .edited_at is not None ,
                })

            if not messages :
                return f"В этом канале сообщения {'этого пользователя ' if user_id else ''}не найдены."

            summary =f"В канале #{target_channel.name} найдено сообщений ({len(messages)}):\n"
            for msg in messages [:20 ]:
                edited_tag =' [ИЗМЕНЕНО]'if msg ['edited']else ''
                summary +=f"[{msg['timestamp']}] {msg['author']}: {msg['content']}{edited_tag}\n"

            return summary 

        except Exception as e :
            return f"Не удалось проверить историю сообщений: {str(e)}"

    @app_commands .command (name ="ticket-panel",description ="Отправить AI панель тикетов в канал")
    @app_commands .checks .has_permissions (administrator =True )
    async def ticket_panel (self ,interaction :discord .Interaction ):
        if interaction .guild .id in TICKET_DISABLED_GUILDS :
            await interaction .response .send_message (
            'На этом сервере система тикетов отключена.',ephemeral =True 
            )
            return 

            # Канал уже содержит панель тикетов от бота?
        async for msg in interaction .channel .history (limit =20 ):
            if (msg .author ==interaction .guild .me and 
            msg .embeds and 
            msg .components and 
            any ('ticket_category_select'in str (c )for c in msg .components )):
                await interaction .response .send_message (
                "В этом канале уже есть панель тикетов. Сначала удалите старую.",
                ephemeral =True 
                )
                return 

                # Генерируем красивую кастомную Pillow карточку пользователя
        img_buf =await interaction .client .loop .run_in_executor (
        None ,generate_ticket_panel_bytes 
        )
        file =discord .File (img_buf ,filename ="ticket_panel.png")

        # Отправляем файл вместе с TicketView, содержащим кастомное Select Menu
        await interaction .channel .send (file =file ,view =TicketView ())
        await interaction .response .send_message ("Панель тикетов успешно отправлена.",ephemeral =True )


    @app_commands .command (name ="ticket-add",description ="Добавить пользователя в тикет")
    @app_commands .checks .has_permissions (manage_channels =True )
    async def ticket_add (self ,interaction :discord .Interaction ,user :discord .Member ):
        await interaction .channel .set_permissions (user ,read_messages =True ,send_messages =True )
        e =discord .Embed (
        description =f"{user.mention} добавлен в канал поддержки.",
        color =0x2ECC71 
        )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ="ticket-remove",description ="Удалить пользователя из тикета")
    @app_commands .checks .has_permissions (manage_channels =True )
    async def ticket_cikar (self ,interaction :discord .Interaction ,user :discord .Member ):
        await interaction .channel .set_permissions (user ,read_messages =False )
        e =discord .Embed (
        description =f" {user.mention} удалён из канала поддержки.",
        color =0xE74C3C 
        )
        await interaction .response .send_message (embed =e )

    @app_commands .command (name ="ticket-ai-stats",description ="Показать статистику AI-поддержки")
    @app_commands .checks .has_permissions (manage_guild =True )
    async def ticket_ai_stats (self ,interaction :discord .Interaction ):
        """Показать статистику AI-поддержки"""
        data =self ._load_ai_data (interaction .guild .id )

        if not data :
            await interaction .response .send_message ("Данных AI-поддержки пока нет.",ephemeral =True )
            return 

        total_tickets =len (data )
        ai_handling =sum (1 for t in data .values ()if t ['status']=='ai_handling')
        escalated =sum (1 for t in data .values ()if t ['status']=='escalated')
        staff_handling =sum (1 for t in data .values ()if t ['status']=='staff_handling')
        closed_tickets =total_tickets -ai_handling -escalated -staff_handling 

        # Custom Menu kullan
        e =StatsMenu .ticket_stats (
        total =total_tickets ,
        open_tickets =ai_handling +escalated +staff_handling ,
        closed_tickets =closed_tickets ,
        ai_handled =ai_handling ,
        escalated =escalated 
        )

        await interaction .response .send_message (embed =e )

    @app_commands .command (name ="ticket-ai-toggle",description ="Включить/отключить AI-поддержку тикетов")
    @app_commands .checks .has_permissions (administrator =True )
    async def ticket_ai_toggle (self ,interaction :discord .Interaction ):
        """Включить/отключить AI-поддержку тикетов (только для этого сервера)"""
        gid =int (interaction .guild .id )
        if gid in AI_DISABLED_GUILDS :
            AI_DISABLED_GUILDS .discard (gid )
            enabled =True 
        else :
            AI_DISABLED_GUILDS .add (gid )
            enabled =False 

        status =("Активна"if enabled else "Отключена")
        e =discord .Embed (
        title =" AI Поддержка Система",
        description =f"AI-система поддержки на **{interaction.guild.name}**: **{status}**",
        color =0x2ECC71 if enabled else 0xE74C3C 
        )
        await interaction .response .send_message (embed =e )


    @app_commands .command (name ="ticket-force-escalate",description ="Перенаправить текущий тикет администрации")
    @app_commands .checks .has_permissions (manage_channels =True )
    async def ticket_force_escalate (self ,interaction :discord .Interaction ):
        """Передать тикет модераторам вручную"""
        if not interaction .channel .name .startswith ("ticket-"):
            await interaction .response .send_message ("Это не канал тикета.",ephemeral =True )
            return 

        state =self ._get_ticket_state (interaction .guild .id ,interaction .channel .id )

        if state ['status']=='escalated':
            await interaction .response .send_message ("Этот тикет уже передан модераторам.",ephemeral =True )
            return 

        await interaction .response .send_message (" Передаю тикет модераторам...",ephemeral =True )
        await self ._escalate_ticket (interaction .channel ,state ,'manual')

    @app_commands .command (name ="ticket-reset-rate-limit",description ="Сбросить rate limit для пользователя")
    @app_commands .checks .has_permissions (manage_guild =True )
    async def ticket_reset_rate_limit (self ,interaction :discord .Interaction ,user :discord .Member ):
        """Сбросить rate limit для указанного пользователя"""
        rate_limiter =get_rate_limiter ()
        await rate_limiter .reset_user (interaction .guild .id ,user .id )

        e =discord .Embed (
        color =0x2ECC71 ,
        description =f"Rate limit для {user.mention} сброшен.\nТеперь пользователь может создавать тикеты без ограничений."
        )
        await interaction .response .send_message (embed =e ,ephemeral =True )
        logger .info (
        f"[RateLimit] Сброшен rate limit: admin={interaction.user} ({interaction.user.id}) "
        f"target={user} ({user.id})"
        )

    @app_commands .command (name ="ticket-rate-limit-info",description ="Показать rate limit информацию для пользователя")
    @app_commands .checks .has_permissions (manage_guild =True )
    async def ticket_rate_limit_info (self ,interaction :discord .Interaction ,user :discord .Member =None ):
        """Показать статистику rate limit для пользователя"""
        target =user or interaction .user 
        rate_limiter =get_rate_limiter ()
        stats =await rate_limiter .get_user_stats (interaction .guild .id ,target .id )

        # Custom Menu kullan
        menu =CustomMenu (
        title =f"Rate Limit — {target.display_name}",
        color ='info',
        border_style ='single',
        thumbnail =target .display_avatar .url ,
        footer_text =f"{interaction.guild.name} • Rate Limit Info",
        footer_icon =interaction .guild .icon .url if interaction .guild .icon else None 
        )

        # Иstatistikler (3'lю grid)
        menu .add_stats ([
        {'label':'За 24ч','value':stats ['tickets_24h'],'emoji':''},
        {'label':'За неделю','value':stats ['tickets_week'],'emoji':''},
        {'label':'За месяц','value':stats ['tickets_month'],'emoji':''},
        ],layout ='grid')

        menu .add_separator ()

        # Son ticket ve cooldown
        if stats ['last_ticket']:
            ts =int (stats ['last_ticket'].timestamp ())
            last_ticket_text =f"<t:{ts}:R>"
        else :
            last_ticket_text ="Нет данных"

        cooldown_text =f"{stats['cooldown_remaining']} сек."if stats ['cooldown_remaining']>0 else "Готов"

        menu .add_section (
        title ="Последний тикет",
        content =last_ticket_text ,
        emoji ="⏰",
        inline =True 
        )

        menu .add_section (
        title ="Кулдаун",
        content =f"```{cooldown_text}```",
        emoji ="⏳",
        inline =True 
        )

        e =menu .build ()
        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="ticket-feedback-stats",description ="Показать статистику обратной связи")
    @app_commands .checks .has_permissions (manage_guild =True )
    async def ticket_feedback_stats (self ,interaction :discord .Interaction ):
        """Показать статистику отзывов пользователей"""
        feedback_service =get_feedback_service ()
        stats =feedback_service .get_guild_stats (interaction .guild .id )

        if stats ['total']==0 :
            await interaction .response .send_message (
            "Отзывов пока нет.",
            ephemeral =True 
            )
            return 

            # Custom Menu kullan
        e =StatsMenu .feedback_stats (
        total =stats ['total'],
        positive =stats ['positive'],
        negative =stats ['negative'],
        avg_rating =stats ['avg_rating'],
        recent_comments =stats ['comments']
        )

        await interaction .response .send_message (embed =e ,ephemeral =True )

    @app_commands .command (name ="ticket-auto-close",description ="Настроить автоматическое закрытие неактивных тикетов")
    @app_commands .checks .has_permissions (administrator =True )
    @app_commands .describe (hours ="Через сколько часов неактивности закрывать тикет (1-168)")
    async def ticket_auto_close (self ,interaction :discord .Interaction ,hours :int =24 ):
        """Настроить время автоматического закрытия тикетов"""
        if hours <1 or hours >168 :
            await interaction .response .send_message (
            "Значение должно быть от 1 до 168 часов (7 дней).",
            ephemeral =True 
            )
            return 

        from services .auto_close_service import get_auto_close_service 
        auto_close =get_auto_close_service (self .bot )
        auto_close .set_inactive_hours (hours )

        # Custom Menu kullan
        menu =CustomMenu (
        title ="Автозакрытие тикетов",
        color ='success',
        border_style ='wave'
        )

        menu .add_section (
        title ="Настройка",
        content =f"Неактивные тикеты будут автоматически закрываться через **{hours}** часов.",
        emoji =""
        )

        menu .add_separator ()

        menu .add_section (
        title ="Что считается неактивностью?",
        content ="Если в тикете не было сообщений указанное время, он будет закрыт автоматически.",
        emoji ="ℹ"
        )

        e =menu .build ()

        await interaction .response .send_message (embed =e ,ephemeral =True )
        logger .info (f"[Ticket] Auto-close настроен на {hours} часов администратором {interaction.user}")

    @app_commands .command (name ="ticket-config",description ="Настройки системы тикетов")
    @app_commands .checks .has_permissions (administrator =True )
    async def ticket_config (self ,interaction :discord .Interaction ):
        """Показать текущие настройки системы тикетов"""
        from services .auto_close_service import get_auto_close_service 
        auto_close =get_auto_close_service (self .bot )
        rate_limiter =get_rate_limiter ()
        limits =rate_limiter .default_limits 

        # Custom Menu kullan
        menu =CustomMenu (
        title ="Настройки системы тикетов",
        color ='primary',
        border_style ='diamond',
        footer_text =f"{interaction.guild.name} • Конфигурация",
        footer_icon =interaction .guild .icon .url if interaction .guild .icon else None 
        )

        # Основные настройки (сетка 3)
        ai_status =("Активна"if self ._ai_enabled (interaction .guild .id )else "Отключена")
        menu .add_stats ([
        {'label':'AI-поддержка','value':ai_status ,'emoji':''},
        {'label':'Автозакрытие','value':f"{auto_close.inactive_hours}ч",'emoji':'⏰'},
        {'label':'Rate Limit','value':f"{limits['max_tickets_per_24h']}/24ч",'emoji':''},
        ],layout ='grid')

        menu .add_separator ()

        # Rate limit detaylarы
        menu .add_stats ([
        {'label':'Кулдаун','value':f"{limits['cooldown_seconds']}с",'emoji':'⏳'},
        {'label':'Недельный лимит','value':str (limits ['max_tickets_per_week']),'emoji':''},
        {'label':'Месячный лимит','value':str (limits ['max_tickets_per_month']),'emoji':''},
        ],layout ='grid')

        menu .add_separator ()

        # Список команд
        menu .add_list (
        title ="Команды управления",
        items =[
        "`/ticket-ai-toggle` — Вкл/выкл AI",
        "`/ticket-auto-close <часы>` — Настроить автозакрытие",
        "`/ticket-reset-rate-limit <@user>` — Сбросить лимит",
        "`/ticket-feedback-stats` — Статистика отзывов",
        ],
        emoji ="",
        numbered =False 
        )

        e =menu .build ()
        await interaction .response .send_message (embed =e ,ephemeral =True )


async def setup (bot ):
    """Загрузка cog и инициализация сервисов"""
    # Загружаем Ticket cog
    await bot .add_cog (
    Ticket (bot ),
    guilds =[
    discord .Object (id =1421244140359909513 ),
    discord .Object (id =1107038411895881788 ),
    discord .Object (id =1498837105915330562 )
    ]
    )

    #  AUTO-CLOSE СЕРВИС 
    # Запускаем фоновую задачу автоматического закрытия неактивных тикетов
    from services .auto_close_service import get_auto_close_service 
    auto_close =get_auto_close_service (bot )
    auto_close .set_inactive_hours (24 )# Закрывать через 24 часа неактивности
    await auto_close .start ()
    logger .info ("[Ticket] Auto-close сервис запущен (24 часа)")
    #  END AUTO-CLOSE СЕРВИС 
