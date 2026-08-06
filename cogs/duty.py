import discord 
from discord .ext import commands 
from config import Config 
from discord import app_commands 
import json ,os 
from datetime import datetime ,timedelta ,timezone 

DUTY_FILE ="data/duty_log.json"
POINTS_FILE ="data/duty_points.json"
REQUIRED_ROLE_ID =Config .REQUIRED_ROLE_ID 

# Animasyonlu GIF'ler
GIF_PANEL ="https://media.giphy.com/media/xT9IgG50Lg7russbDa/giphy.gif"
GIF_START ="https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif"
GIF_END ="https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.gif"

TASK_DEFS ={
"ses":{"label":"🎙 Оставайся в войсе","desc":"Проведи 3 часа в голосовом канале","target":10800 ,"unit":"sn","points":50 },
"message":{"label":"💬 Напиши сообщения","desc":"Отправь 150 сообщений","target":150 ,"unit":"msg","points":30 },
"invite":{"label":"📨 Пригласи друзей","desc":"Пригласи 5 человек на сервер","target":5 ,"unit":"inv","points":40 },
"администратор":{"label":"🛡 Приведи модераторов","desc":"Приведи 2 кандидатов в модераторы","target":2 ,"unit":"rec","points":60 },
}

#  helpers 
def load_duty ():
    os .makedirs ("data",exist_ok =True )
    if os .path .exists (DUTY_FILE ):
        with open (DUTY_FILE ,"r",encoding ="utf-8")as f :
            return json .load (f )
    return {}

def save_duty (data ):
    with open (DUTY_FILE ,"w",encoding ="utf-8")as f :
        json .dump (data ,f ,indent =2 ,ensure_ascii =False )

def load_points ():
    os .makedirs ("data",exist_ok =True )
    if os .path .exists (POINTS_FILE ):
        with open (POINTS_FILE ,"r",encoding ="utf-8")as f :
            return json .load (f )
    return {}

def save_points (data ):
    with open (POINTS_FILE ,"w",encoding ="utf-8")as f :
        json .dump (data ,f ,indent =2 ,ensure_ascii =False )

def add_points (guild_id ,user_id ,amount ,reason ):
    pts =load_points ()
    gid ,uid =str (guild_id ),str (user_id )
    pts .setdefault (gid ,{}).setdefault (uid ,{"total":0 ,"history":[]})
    pts [gid ][uid ]["total"]+=amount 
    pts [gid ][uid ]["history"].append ({
    "amount":amount ,"reason":reason ,
    "timestamp":datetime .now (timezone .utc ).isoformat ()
    })
    save_points (pts )
    return pts [gid ][uid ]["total"]

def progress_bar (current ,total ,length =14 ):
    pct =min (current /total ,1.0 )if total else 0 
    filled =int (pct *length )
    bar =""*filled +""*(length -filled )
    return f"{bar}  {int(pct*100)}%"

def fmt_dur (sec ):
    h ,m ,s =int (sec //3600 ),int ((sec %3600 )//60 ),int (sec %60 )
    return f"{h}s {m}d"if h else f"{m}d {s}sn"

def now_iso ():
    return datetime .now (timezone .utc ).isoformat ()

def has_role (member ):
    role =member .guild .get_role (REQUIRED_ROLE_ID )
    return role is None or role in member .roles 


    #  Задача выбор view (ephemeral, timeout'lu) 
class TaskPickView (discord .ui .View ):
    def __init__ (self ,uid :str ,gid :str ):
        super ().__init__ (timeout =60 )
        self .uid =uid 
        self .gid =gid 
        self .selected :set =set ()

    def _toggle_btn (self ,key :str ,btn :discord .ui .Button ):
        if key in self .selected :
            self .selected .discard (key )
            btn .style =discord .ButtonStyle .secondary 
        else :
            self .selected .add (key )
            btn .style =discord .ButtonStyle .primary 

    async def _refresh (self ,interaction :discord .Interaction ):
        count =len (self .selected )
        self .confirm_btn .disabled =count ==0 
        self .confirm_btn .label =f"▶️ Начать задачи ({count})"if count else "▶️ Начать задачи"
        await interaction .response .edit_message (view =self )

    @discord .ui .button (label ="🎙 Войс  •  50",style =discord .ButtonStyle .secondary ,row =0 )
    async def btn_ses (self ,i ,b ):self ._toggle_btn ("ses",b );await self ._refresh (i )

    @discord .ui .button (label ="💬 Сообщения  •  30",style =discord .ButtonStyle .secondary ,row =0 )
    async def btn_message (self ,i ,b ):self ._toggle_btn ("message",b );await self ._refresh (i )

    @discord .ui .button (label ="📨 Приглашения  •  40",style =discord .ButtonStyle .secondary ,row =1 )
    async def btn_invite (self ,i ,b ):self ._toggle_btn ("invite",b );await self ._refresh (i )

    @discord .ui .button (label ="🛡 Модераторы  •  60",style =discord .ButtonStyle .secondary ,row =1 )
    async def btn_yetkili (self ,i ,b ):self ._toggle_btn ("администратор",b );await self ._refresh (i )

    @discord .ui .button (label ="▶️ Начать задачи",style =discord .ButtonStyle .success ,
    disabled =True ,row =2 )
    async def confirm_btn (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        data =load_duty ()
        data .setdefault (self .gid ,{}).setdefault (self .uid ,{"active":None ,"history":[]})

        if data [self .gid ][self .uid ].get ("active"):
            await interaction .response .edit_message (
            content =" Вы уже на дежурстве! Сначала завершите смену.",view =None )
            return 

        tasks =list (self .selected )
        data [self .gid ][self .uid ]["active"]={
        "start":now_iso (),
        "tasks":tasks ,
        "progress":{t :0 for t in tasks },
        "user_name":interaction .user .display_name 
        }
        # Ses задача varsa baшlangыч значение сохранить
        if "ses"in tasks :
            vf =f'data/voice_stats_{self.gid}.json'
            voice_at_start =0 
            if os .path .exists (vf ):
                import json as _j 
                with open (vf ,encoding ='utf-8')as fp :
                    vdata =_j .load (fp )
                voice_at_start =vdata .get ('users',{}).get (self .uid ,{}).get ('total_seconds',0 )
            data [self .gid ][self .uid ]["active"]["voice_seconds_at_start"]=voice_at_start 
        save_duty (data )

        embed =discord .Embed (color =0x2ECC71 ,timestamp =datetime .now (timezone .utc ))
        embed .set_author (name =f"{interaction.user.display_name} начал(а) задачи!",
        icon_url =interaction .user .display_avatar .url )
        embed .set_thumbnail (url =GIF_START )
        embed .description ="```ansi\n\u001b[1;32m ЗАДАЧИ НАЧАТЫ\u001b[0m\n```\n"
        for t in tasks :
            td =TASK_DEFS [t ]
            embed .add_field (
            name =f"{td['label']}  ·  **{td['points']} очков**",
            value =f"```{progress_bar(0, td['target'])}```*{td['desc']}*",
            inline =False 
            )
        embed .set_footer (text ="Чтобы завершить — нажми кнопку «Выйти из задачи» на панели")
        await interaction .response .edit_message (content =None ,embed =embed ,view =None )


        #  Ana panel view (persistent) 
class DutyPanelView (discord .ui .View ):
    def __init__ (self ):
        super ().__init__ (timeout =None )

    @discord .ui .button (label ="▶️ Начать задачи",style =discord .ButtonStyle .success ,
    custom_id ="duty_start_v2",row =0 )
    async def start_btn (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not has_role (interaction .user ):
            await interaction .response .send_message (" Эту кнопку использовать администратор нет.",ephemeral =True )
            return 

        data =load_duty ()
        uid ,gid =str (interaction .user .id ),str (interaction .guild .id )
        data .setdefault (gid ,{}).setdefault (uid ,{"active":None ,"history":[]})

        if data [gid ][uid ].get ("active"):
            await interaction .response .send_message (" Вы уже на дежурстве! Сначала завершите смену.",ephemeral =True )
            return 

        pick_view =TaskPickView (uid ,gid )
        await interaction .response .send_message (
        content ="** Задача выбрать** *(birden fazla выбрать)*",
        view =pick_view ,
        ephemeral =True 
        )

    @discord .ui .button (label ="🚪 Выйти из задачи",style =discord .ButtonStyle .danger ,
    custom_id ="duty_end_v2",row =0 )
    async def end_btn (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        data =load_duty ()
        uid ,gid =str (interaction .user .id ),str (interaction .guild .id )

        # Данные yoksa или bozuksa dюzelt
        if gid not in data or uid not in data [gid ]:
            await interaction .response .send_message (" Активен задача нет.",ephemeral =True )
            return 

        active =data [gid ][uid ].get ("active")

        # Старый format контроль (string ise clear)
        if isinstance (active ,str ):
            data [gid ][uid ]["active"]=None 
            save_duty (data )
            await interaction .response .send_message (" Активен задача нет.",ephemeral =True )
            return 

        if not active or not isinstance (active ,dict ):
            await interaction .response .send_message (" Активен задача нет.",ephemeral =True )
            return 

        start_dt =datetime .fromisoformat (active ["start"])
        end_dt =datetime .now (timezone .utc )
        elapsed =(end_dt -start_dt ).total_seconds ()

        # Ses длительностьni voice_tracker'dan al (более верно)
        if "ses"in active .get ("tasks",[]):
            vf =f'data/voice_stats_{gid}.json'
            if os .path .exists (vf ):
                import json as _j 
                with open (vf ,encoding ='utf-8')as fp :
                    vdata =_j .load (fp )
                    # Задача baшlangыcыndan bu yana geчen ses длительность
                    # voice_tracker собратьm длительность tutuyor, задача baшыndaki значение sakladыk
                voice_at_start =active .get ("voice_seconds_at_start",0 )
                voice_now =vdata .get ('users',{}).get (uid ,{}).get ('total_seconds',0 )
                # Шu an ses channelыndaysa активен session'ы da add
                from cogs .voice_tracker import VoiceTracker 
                vt_cog =self .bot .get_cog ('VoiceTracker')
                if vt_cog :
                    session_start =vt_cog .sessions .get (gid ,{}).get (uid )
                    if session_start :
                        import time as _t 
                        voice_now +=int (_t .time ()-session_start )
                active ["progress"]["ses"]=max (0 ,voice_now -voice_at_start )
            else :
                active ["progress"]["ses"]=int (elapsed )

        tasks =active .get ("tasks",[])
        progress =active .get ("progress",{})

        # Очки hesapla
        total_pts =0 
        results =[]
        for t in tasks :
            td =TASK_DEFS [t ]
            cur =progress .get (t ,0 )
            done =cur >=td ["target"]
            if done :
                total_pts +=td ["points"]
            results .append ((t ,td ,cur ,done ))

        new_total =add_points (gid ,uid ,total_pts ,"Задача завершено")if total_pts >0 else load_points ().get (gid ,{}).get (uid ,{}).get ("total",0 )

        # Сохранить
        entry ={
        "start":active ["start"],"end":end_dt .isoformat (),
        "duration_seconds":int (elapsed ),"tasks":tasks ,
        "progress":progress ,"points_earned":total_pts ,
        "user_name":interaction .user .display_name 
        }
        data [gid ][uid ]["active"]=None 
        data [gid ][uid ].setdefault ("history",[]).append (entry )
        week_ago =(datetime .now (timezone .utc )-timedelta (days =7 )).isoformat ()
        data [gid ][uid ]["history"]=[h for h in data [gid ][uid ]["history"]if h ["end"]>week_ago ]
        save_duty (data )

        # результат embed
        embed =discord .Embed (color =0xDC143C ,timestamp =end_dt )
        embed .set_author (name =f"{interaction.user.display_name} задача заверш",
        icon_url =interaction .user .display_avatar .url )
        embed .set_thumbnail (url =GIF_END )
        embed .description =(
        "```ansi\n\u001b[1;31m ЗАДАЧА ЗАВЕРШЕНА\u001b[0m\n```\n"
        ""
        )
        embed .add_field (name ="⏱ Длительность",value =f"**{fmt_dur(elapsed)}**",inline =True )
        embed .add_field (name =" Заработано",value =f"**+{total_pts} очков**",inline =True )
        embed .add_field (name =" Всего",value =f"**{new_total} очков**",inline =True )
        embed .add_field (name ="​",value ="",inline =False )

        for t ,td ,cur ,done in results :
            bar =progress_bar (cur ,td ["target"])
            status ="✅ Выполнено"if done else "⏳ В процессе"
            detail =f"{fmt_dur(cur)} / {fmt_dur(td['target'])}"if t =="ses"else f"{cur} / {td['target']}"
            embed .add_field (
            name =f"{td['label']}  ·  {status}",
            value =f"```{bar}```{detail}",
            inline =False 
            )
        embed .set_footer (text =f"Всего очки: {new_total}   ·  Aether Задача Система")
        await interaction .response .send_message (embed =embed ,ephemeral =True )

    @discord .ui .button (label ="🏆 Мои очки",style =discord .ButtonStyle .secondary ,
    custom_id ="duty_points_v2",row =0 )
    async def points_btn (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        pts =load_points ()
        uid ,gid =str (interaction .user .id ),str (interaction .guild .id )
        udata =pts .get (gid ,{}).get (uid ,{"total":0 ,"history":[]})
        total =udata .get ("total",0 )
        hist =udata .get ("history",[])[-5 :]

        embed =discord .Embed (title ="🏆 Мои очки",color =0xF1C40F )
        embed .set_author (name =interaction .user .display_name ,
        icon_url =interaction .user .display_avatar .url )
        embed .add_field (name ="Всего очков",value =f"```{total} ```",inline =False )

        if hist :
            lines ="\n".join ([f"+{h['amount']}  {h['reason']}"for h in reversed (hist )])
            embed .add_field (name ="🕘 Последние начисления",value =f"```{lines}```",inline =False )

            # Активен задача ilerlemesi
        data =load_duty ()
        active =data .get (gid ,{}).get (uid ,{}).get ("active")
        if active :
            elapsed =(datetime .now (timezone .utc )-datetime .fromisoformat (active ["start"])).total_seconds ()
            if "ses"in active .get ("tasks",[]):
                active ["progress"]["ses"]=int (elapsed )
            embed .add_field (name ="​",value ="**🟢 Прогресс активных задач**",inline =False )
            for t in active .get ("tasks",[]):
                td =TASK_DEFS [t ]
                cur =active ["progress"].get (t ,0 )
                embed .add_field (
                name =td ["label"],
                value =f"```{progress_bar(cur, td['target'])}```",
                inline =False 
                )
        await interaction .response .send_message (embed =embed ,ephemeral =True )


        #  Cog 
class Duty (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        bot .add_view (DutyPanelView ())

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        if message .author .bot or not message .guild :
            return 
        data =load_duty ()
        uid ,gid =str (message .author .id ),str (message .guild .id )
        active =data .get (gid ,{}).get (uid ,{}).get ("active")
        if active and "message"in active .get ("tasks",[]):
            active ["progress"]["message"]=active ["progress"].get ("message",0 )+1 
            data [gid ][uid ]["active"]=active 
            save_duty (data )

    @app_commands .command (name ="duty-panel",description ="Отправить панель задач в канал")
    @app_commands .checks .has_permissions (administrator =True )
    async def duty_panel (self ,interaction :discord .Interaction ):
        embed =discord .Embed (color =0xDC143C )
        embed .set_image (url =GIF_PANEL )
        embed .description =(
        "```ansi\n"
        "\u001b[1;31m\u001b[0m\n"
        "\u001b[1;37m            ПАНЕЛЬ ЗАДАЧ            \u001b[0m\n"
        "\u001b[1;31m\u001b[0m\n"
        "```\n"
        "\n"
        "Начни задание, достигни цели — **заработай очки!**\n"
        "\n\n"
        " **Seste Kal**  **50 **\n"
        " *3 часов ses в канале активен kal*\n\n"
        " **Сообщение At**  **30 **\n"
        " *На сервере 150 message отправить*\n\n"
        " **Invite Тянуть**  **40 **\n"
        "📨 *Пригласи 5 человек на сервер*\n\n"
        " **Администратор Тянуть**  **60 **\n"
        "🛡 *Приведи 2 кандидатов в модераторы*\n\n"
        "\n"
        ">  Birden fazla задача выбрать!\n"
        "> ℹ️ Прогресс показывается по завершении задачи."
        )
        embed .set_footer (
        text ="Aether · Система задач · Начать → Завершить → Получить очки",
        icon_url =interaction .guild .icon .url if interaction .guild .icon else None 
        )
        await interaction .channel .send (embed =embed ,view =DutyPanelView ())
        await interaction .response .send_message (" Panel отправлено.",ephemeral =True )

    @app_commands .command (name ="duty-stats",description ="Таблица очков задач")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def duty_stats (self ,interaction :discord .Interaction ,uye :discord .Member =None ):
        pts =load_points ()
        gid =str (interaction .guild .id )
        gpts =pts .get (gid ,{})
        if not gpts :
            await interaction .response .send_message ("Пока нет записей очков.",ephemeral =True )
            return 
        embed =discord .Embed (title ="⭐ Таблица очков дежурства",color =0xDC143C )
        if uye :
            uid =str (uye .id )
            total =gpts .get (uid ,{}).get ("total",0 )
            embed .set_thumbnail (url =uye .display_avatar .url )
            embed .add_field (name =uye .display_name ,value =f"**{total} **",inline =False )
        else :
            top =sorted (gpts .items (),key =lambda x :x [1 ].get ("total",0 ),reverse =True )[:10 ]
            medals =["🥇","🥈","🥉"]
            for i ,(uid ,udata )in enumerate (top ,1 ):
                m =interaction .guild .get_member (int (uid ))
                name =m .display_name if m else uid 
                embed .add_field (
                name =f"{medals[i-1] if i<=3 else f'#{i}'}  {name}",
                value =f"**{udata.get('total',0)} **",
                inline =False 
                )
        await interaction .response .send_message (embed =embed ,ephemeral =True )

    @app_commands .command (name ="duty-add",description ="Ручное добавление прогресса (приглашения/модер)")
    @app_commands .checks .has_permissions (moderate_members =True )
    async def duty_add (self ,interaction :discord .Interaction ,
    uye :discord .Member ,gorev :str ,miktar :int =1 ):
        if gorev not in TASK_DEFS :
            await interaction .response .send_message (
            f"❌ Неверная задача. Выберите: {', '.join(TASK_DEFS)}",ephemeral =True )
            return 
        data =load_duty ()
        uid ,gid =str (uye .id ),str (interaction .guild .id )
        active =data .get (gid ,{}).get (uid ,{}).get ("active")
        if not active or gorev not in active .get ("tasks",[]):
            await interaction .response .send_message (
            f"У {uye.display_name} нет активных задач.",ephemeral =True )
            return 
        active ["progress"][gorev ]=active ["progress"].get (gorev ,0 )+miktar 
        data [gid ][uid ]["active"]=active 
        save_duty (data )
        td =TASK_DEFS [gorev ]
        cur =active ["progress"][gorev ]
        await interaction .response .send_message (
        f" {uye.display_name} → {td['label']}: `{progress_bar(cur, td['target'])}` ({cur}/{td['target']})",
        ephemeral =True )


async def setup (bot ):
    await bot .add_cog (Duty (bot ),guilds =Config .guild_objects ())
