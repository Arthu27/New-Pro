"""
DeepSeek web scraper — API olmadan chat.deepseek.com использовать.
Gereksinim: pip install playwright && python -m playwright install chromium

Использование: .env'e add:
  DEEPSEEK_EMAIL=email@gmail.com
  DEEPSEEK_PASSWORD=sifren
"""

from logger import get_logger

_log = get_logger("deepseek_scraper")

import os 
import json 
import asyncio 
import threading 
from datetime import datetime, timezone

DEEPSEEK_EMAIL =os .getenv ('DEEPSEEK_EMAIL','')
DEEPSEEK_PASSWORD =os .getenv ('DEEPSEEK_PASSWORD','')

# Статус сессии (логин один раз, потом переиспользуется)
_browser =None 
_page =None 
_lock =threading .Lock ()
_logged_in =False 


async def _ensure_login ():
    """Запустить браузер и войти (один раз)."""
    global _browser ,_page ,_logged_in 

    from playwright .async_api import async_playwright 

    if _logged_in and _page :
        return True 

    try :
        pw =await async_playwright ().start ()
        _browser =await pw .chromium .launch (
        headless =True ,
        args =['--no-sandbox','--disable-dev-shm-usage']
        )
        context =await _browser .new_context (
        user_agent =(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
        )
        )
        _page =await context .new_page ()

        # Вход sayfasыna git
        await _page .goto ('https://chat.deepseek.com/',timeout =30000 )
        await _page .wait_for_timeout (2000 )

        # Вход butonu
        try :
            login_btn =_page .locator ('text=Лог in').first 
            await login_btn .click (timeout =5000 )
            await _page .wait_for_timeout (1000 )
        except Exception as _ex:
            _log.debug("_ensure_login(): подавлено: %s", _ex)

            # Email
        email_input =_page .locator ('input[type="email"], input[name="email"], input[placeholder*="email" i]').first 
        await email_input .fill (DEEPSEEK_EMAIL ,timeout =10000 )

        # Parola
        pass_input =_page .locator ('input[type="password"]').first 
        await pass_input .fill (DEEPSEEK_PASSWORD ,timeout =5000 )

        # Кнопка входа
        submit =_page .locator ('button[type="submit"]').first 
        await submit .click (timeout =5000 )

        # Ждём завершения входа
        await _page .wait_for_url ('**/chat**',timeout =20000 )
        await _page .wait_for_timeout (2000 )

        _logged_in =True 
        print ('[DeepSeek] Вход успешно')
        return True 

    except Exception as e :
        print (f'[DeepSeek] Вход Ошибки: {e}')
        _logged_in =False 
        return False 


async def _ask_deepseek_async (prompt :str ,timeout :int =60 )->str :
    """Задать вопрос DeepSeek, вернуть ответ."""
    global _logged_in 

    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD :
        return ''

    if not _logged_in :
        ok =await _ensure_login ()
        if not ok :
            return ''

    try :
    # Новый sohbet запустить
        try :
            new_chat =_page .locator ('text=New Chat, text=Новый Sohbet, [aria-label*="new" i]').first 
            await new_chat .click (timeout =3000 )
            await _page .wait_for_timeout (500 )
        except Exception as _ex:
            _log.debug("_ask_deepseek_async(): подавлено: %s", _ex)

            # Сообщение kutusunu bul ve написать
        textarea =_page .locator ('textarea, [contenteditable="true"]').first 
        await textarea .click (timeout =5000 )
        await textarea .fill (prompt ,timeout =5000 )

        # Отправить (Enter или кнопка)
        await textarea .press ('Enter')

        # Ждём ответа — пока не закончится анимация «думает»
        await _page .wait_for_timeout (2000 )

        # Ждём появления элемента ответа
        start =datetime.now(timezone.utc).replace(tzinfo=None)
        last_text =''
        stable_count =0 

        while (datetime.now(timezone.utc).replace(tzinfo=None)-start ).seconds <timeout :
            await _page .wait_for_timeout (1000 )

            # В конец message bloгunu получить
            msgs =await _page .locator ('.message-content, .ds-markdown, [class*="message"], [class*="response"]').all ()
            if msgs :
                current_text =await msgs [-1 ].inner_text ()
                if current_text ==last_text and current_text .strip ():
                    stable_count +=1 
                    if stable_count >=3 :# 3 секунды не меняется — готово
                        return current_text .strip ()
                else :
                    stable_count =0 
                    last_text =current_text 

        return last_text .strip ()if last_text else ''

    except Exception as e :
        print (f'[DeepSeek] Soru Ошибки: {e}')
        _logged_in =False # Новыйden login denensin
        return ''


def ask_deepseek (prompt :str ,timeout :int =60 )->str :
    """
    Sync-обёртка — вызывается из ai_helper.py.
    Задаёт вопрос DeepSeek, возвращает ответ строкой.
    Неудачно olursa пусто string возвращает.
    """
    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD :
        return ''

    try :
    # Используем текущий event loop, если его нет — создаём новый
        try :
            loop =asyncio .get_event_loop ()
            if loop .is_running ():
            # Discord bot loop'u в, thread'de работатьtыr
                import concurrent .futures 
                with concurrent .futures .ThreadPoolExecutor ()as pool :
                    future =pool .submit (asyncio .run ,_ask_deepseek_async (prompt ,timeout ))
                    return future .result (timeout =timeout +10 )
            else :
                return loop .run_until_complete (_ask_deepseek_async (prompt ,timeout ))
        except RuntimeError :
            return asyncio .run (_ask_deepseek_async (prompt ,timeout ))
    except Exception as e :
        print (f'[DeepSeek] Wrapper Ошибки: {e}')
        return ''
