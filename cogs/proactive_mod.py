from typing import Dict 
"""
Проактивная модерация — AI сам замечает проблемы в чате
Токсичность, спам, подозрительные ссылки, повторяющиеся вопросы
"""
import discord 
from discord .ext import commands ,tasks 
import re 
import json 
import os 
from datetime import datetime ,timedelta, timezone
from typing import Dict ,List ,Optional 
import asyncio 

from logger import get_logger 
log =get_logger ("proactive_mod")


def _as_utc (dt ):
    """К aware-UTC: naive-метки считаем UTC (единый мир сравнения в окне спама).

    Буфер пишет datetime.now(timezone.utc) — aware; но легаси/сторонние
    write'ы могли положить naive. TypeError на вычитании naive/aware
    клал весь on_message — нормализуем на чтении.
    """
    if dt .tzinfo is None :
        return dt .replace (tzinfo =timezone .utc )
    return dt 



class ProactiveModeration (commands .Cog ):
    """AI kotoriy kendi sledit для catom"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .message_buffer :Dict [int ,List [Dict ]]={}# channel_id -> messages
        self .toxicity_patterns =[
        r'\b(tvar|ublyudok|mraz|svoloc|aptal|aptal|aptal|aptal)\b',
        r'\b(posel|idi)\s*(на|в)\s*(aptal|каждый|pizdu|jopu)\b',
        r'\b(suka|blyat|blya|nahuy|pizdec|ebat)\b',
        ]
        self .spam_threshold =5 # Сообщение для 10 секунд
        self .spam_window =10 # секунд
        self .link_patterns =[
        r'https?://[^\s]+',
        r'www\.[^\s]+',
        r'discord\.gg/[^\s]+',
        ]

    @commands .Cog .listener ()
    async def on_message (self ,message :discord .Message ):
        """Analiz ediyor каждый сообщение"""
        if message .author .bot or not message .guild :
            return 

        # Счётчик сообщений для профи-статистики модераторов (панель /mod-history).
        # Ошибки счётчика глушатся внутри — on_message не должен падать из-за метрики.
        try :
            from services .mod_activity import record_message
            record_message (message .guild .id ,message .author .id ,str (message .author ))
        except Exception as _ex :
            log.debug('on_message(): счётчик сообщений: %s',_ex )

        channel_id =message .channel .id 

        # Analiz duygu
        from web .sentiment_analyzer import get_sentiment_analyzer 
        sentiment_analyzer =get_sentiment_analyzer ()
        sentiment_analyzer .analyze_message (message )

        # Ekliyoruz в pano
        if channel_id not in self .message_buffer :
            self .message_buffer [channel_id ]=[]

        self .message_buffer [channel_id ].append ({
        'author_id':message .author .id ,
        'author_name':str (message .author ),
        'content':message .content ,
        'timestamp':datetime.now(timezone.utc),
        'message_id':message .id ,
        })

        # Ограничиваем pano 50 сообщениями
        if len (self .message_buffer [channel_id ])>50 :
            self .message_buffer [channel_id ]=self .message_buffer [channel_id ][-50 :]

            # Контроль ediyoruz на problemi
        await self ._check_toxicity (message )
        await self ._check_spam (message )
        await self ._check_suspicious_links (message )

        # Контроль ediyoruz предупреждение duygu
        alerts =await sentiment_analyzer .check_for_alerts (message .guild )
        for alert in alerts :
            await self ._send_sentiment_alert (message .guild ,alert )

    async def _send_sentiment_alert (self ,guild :discord .Guild ,alert :Dict ):
        """Тихо фиксирует предупреждения о настроении"""
        try :
        # Arыyoruz канал для uvedomleniy
            alert_channel =discord .utils .get (guild .text_channels ,name ="ai-alerts")
            if alert_channel is None :
                try :
                    from cogs .logs import ensure_log_channel
                    alert_channel =await ensure_log_channel (guild ,'ai-alerts')
                    if alert_channel is None :
                        alert_channel =await ensure_log_channel (guild ,'модерация')
                except Exception as _ex:
                    log.debug("_send_sentiment_alert(): подавлено: %s", _ex)
            if not alert_channel :
                return 

                # Создал embed
            color_map ={
            'negative_sentiment':0xFFA500 ,
            'potential_conflict':0xFF0000 ,
            }

            e =discord .Embed (
            color =color_map .get (alert ['type'],0xFF0000 ),
            timestamp =datetime.now(timezone.utc)
            )

            e .description =(
            "## ⚠️ AI-анализ настроений\n"
            f"{alert['message']}\n\n"
            )

            if alert ['type']=='negative_sentiment':
                e .description +=(
                f"**Настроение:** {alert['sentiment']}\n"
                f"**Сообщение:** {alert['message_count']}\n"
                )
            elif alert ['type']=='potential_conflict':
                e .description +=(
                f"**Негативных сообщений:** {alert['negative_messages']}\n"
                "**Рекомендация:** проконтролируйте канал на предмет конфликта\n"
                )

            e .set_footer (text =f"{guild.name} · Анализ настроений")

            await alert_channel .send (embed =e )

        except Exception as e :
            log .info (f"[SENTIMENT] Ошибка фоновой проверки настроения: {e}")

    async def _check_toxicity (self ,message :discord .Message ):
        """Контроль ediyor на toksisite"""
        content_lower =message .content .lower ()

        for pattern in self .toxicity_patterns :
            if re .search (pattern ,content_lower ,re .IGNORECASE ):
            # Nasli toksisite
                await self ._alert_moderators (
                message .guild ,
                'toxicity',
                f"Обнаружена токсичность от {message.author.mention}",
                message 
                )
                break 

    async def _check_spam (self ,message :discord .Message ):
        """Контроль ediyor на spam"""
        channel_id =message .channel .id 
        author_id =message .author .id 

        # Scitaem сообщения den bunun yazarыn для son N секунд
        now =datetime.now(timezone.utc)
        recent_messages =[
        msg for msg in self .message_buffer .get (channel_id ,[])
        if msg ['author_id']==author_id 
        and (now -_as_utc (msg ['timestamp'])).total_seconds ()<=self .spam_window 
        ]

        if len (recent_messages )>=self .spam_threshold :
        # Spam obnarujen
            await self ._alert_moderators (
            message .guild ,
            'spam',
            f"Obnarujen spam den {message.author.mention} ({len(recent_messages)} сообщений за {self.spam_window} с)",
            message 
            )

    async def _check_suspicious_links (self ,message :discord .Message ):
        """Проверяет подозрительные ссылки"""
        # Propuskaem модератор
        if message .author .guild_permissions .kick_members :
            return 

        for pattern in self .link_patterns :
            links =re .findall (pattern ,message .content )
            if links :
            # Контроль ediyoruz на шюpheli domeni
                suspicious_domains =['bit.ly','tinyurl.com','discord.gg']
                for link in links :
                    if any (domain in link .lower ()for domain in suspicious_domains ):
                        await self ._alert_moderators (
                        message .guild ,
                        'suspicious_link',
                        f"Подозрительная ссылка от {message.author.mention}: {link}",
                        message 
                        )
                        break 

    async def _alert_moderators (self ,guild :discord .Guild ,alert_type :str ,description :str ,message :discord .Message ):
        """Уведомляет модераторов о настроении"""
        try :
        # Arыyoruz канал для uvedomleniy
            alert_channel =discord .utils .get (guild .text_channels ,name ="ai-alerts")
            if alert_channel is None :
                try :
                    from cogs .logs import ensure_log_channel
                    alert_channel =await ensure_log_channel (guild ,'ai-alerts')
                    if alert_channel is None :
                        alert_channel =await ensure_log_channel (guild ,'модерация')
                except Exception as _ex:
                    log.debug("_alert_moderators(): подавлено: %s", _ex)
            if not alert_channel :
            # Создал канал если нет
                overwrites ={
                guild .default_role :discord .PermissionOverwrite (read_messages =False ),
                guild .me :discord .PermissionOverwrite (read_messages =True ,send_messages =True ),
                }

                # Daem eriшim модератор
                for role in guild .roles :
                    if role .permissions .kick_members or role .permissions .ban_members :
                        overwrites [role ]=discord .PermissionOverwrite (read_messages =True )

                alert_channel =await guild .create_text_channel (
                'ai-alerts',
                overwrites =overwrites ,
                reason ="AI-проактивная модерация"
                )

                # Создал embed
            color_map ={
            'toxicity':0xFF6B6B ,
            'spam':0xFFA500 ,
            'suspicious_link':0xFFD700 ,
            }

            e =discord .Embed (
            color =color_map .get (alert_type ,0xFF0000 ),
            timestamp =datetime.now(timezone.utc)
            )

            e .description =(
            f"## AI Alert: {alert_type.upper()}\n"
            f"{description}\n\n"
            f"**Канал:** {message.channel.mention}\n"
            f"**Сообщение:** {message.content[:200]}\n"
            f"**Ссылка:** [Перейти]({message.jump_url})"
            )

            e .set_footer (text =f"{guild.name} · Проактивная модерация")

            await alert_channel .send (embed =e )

        except Exception as e :
            log .info (f"[PROACTIVE] Ошибка уведомления: {e}")

    @commands .command (name ="proactive-stats")
    @commands .has_permissions (kick_members =True )
    async def proactive_stats (self ,ctx ):
        """Статистика проактивной модерации"""
        total_messages =sum (len (msgs )for msgs in self .message_buffer .values ())
        channels_monitored =len (self .message_buffer )

        e =discord .Embed (
        title ="Статистика проактивной модерации",
        color =0x5865F2 
        )
        e .description =(
        f"**Каналы pod nablyudeniem:** {channels_monitored}\n"
        f"**Сообщение в panoda:** {total_messages}\n"
        f"**Порог спама:** {self.spam_threshold} сообщений за {self.spam_window} с"
        )
        e .set_footer (text =f"{ctx.guild.name}")

        await ctx .send (embed =e )


async def setup (bot ):
    await bot .add_cog (ProactiveModeration (bot ))
