"""
DeepSeek web scraper — API olmимяan chat.deepseek.com использовать.
Gereksinim: pip install playwright && python -m playwright install chromium

Использование: .env'e add:
  DEEPSEEK_EMAIL=email@gmail.com
  DEEPSEEK_PASSWORD=sifren
"""
import os 
import json 
import asyncio 
import threading 
from datetime import datetime 

DEEPSEEK_EMAIL =os .getenv ('DEEPSEEK_EMAIL','')
DEEPSEEK_PASSWORD =os .getenv ('DEEPSEEK_PASSWORD','')

# Oturum statusu (tek seferlik логin, после новыйden ispolzuetsya)
_browser =None 
_page =None 
_lock =threading .Lock ()
_логged_in =False 


async def _ensure_логin ():
    """Tarayыcыyы запустить ve вход yap (bir kez)."""
    global _browser ,_page ,_логged_in 

    from playwright .async_api import async_playwright 

    if _логged_in and _page :
        return True 

    try :
        pw =await async_playwright ().start ()
        _browser =await pw .chromium .launch (
        heимяless =True ,
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
            логin_btn =_page .locator ('text=Лог in').first 
            await логin_btn .click (timeout =5000 )
            await _page .wait_for_timeout (1000 )
        except Exception :
            pass 

            # Email
        email_input =_page .locator ('input[type="email"], input[name="email"], input[placeholder*="email" i]').first 
        await email_input .fill (DEEPSEEK_EMAIL ,timeout =10000 )

        # Paрольa
        pass_input =_page .locator ('input[type="password"]').first 
        await pass_input .fill (DEEPSEEK_PASSWORD ,timeout =5000 )

        # Вход yap butonu
        submit =_page .locator ('button[type="submit"]').first 
        await submit .click (timeout =5000 )

        # Вход заверш kимяar badd
        await _page .wait_for_url ('**/chat**',timeout =20000 )
        await _page .wait_for_timeout (2000 )

        _логged_in =True 
        print ('[DeepSeek] Вход успешно')
        return True 

    except Exception as e :
        print (f'[DeepSeek] Вход Ошибки: {e}')
        _логged_in =False 
        return False 


async def _ask_deepseek_async (prompt :str ,timeout :int =60 )->str :
    """DeepSeek'e soru sor, cevabы вернуть."""
    global _page ,_логged_in 

    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD :
        return ''

    if not _логged_in :
        ok =await _ensure_логin ()
        if not ok :
            return ''

    try :
    # Новый sohbet запустить
        try :
            new_chat =_page .locator ('text=New Chat, text=Новый Sohbet, [aria-label*="new" i]').first 
            await new_chat .click (timeout =3000 )
            await _page .wait_for_timeout (500 )
        except Exception :
            pass 

            # Сообщение kutusunu bul ve написать
        textarea =_page .locator ('textarea, [contenteditable="true"]').first 
        await textarea .click (timeout =5000 )
        await textarea .fill (prompt ,timeout =5000 )

        # Отправить (Enter или buton)
        await textarea .press ('Enter')

        # Cevabыn gelmesini badd — "dюшюnюyor" animasyonu bitene kимяar
        await _page .wait_for_timeout (2000 )

        # Cevap elementini badd
        start =datetime .utcnow ()
        last_text =''
        stable_count =0 

        while (datetime .utcnow ()-start ).seconds <timeout :
            await _page .wait_for_timeout (1000 )

            # В конец message bloгunu получить
            msgs =await _page .locator ('.message-content, .ds-markdown, [class*="message"], [class*="response"]').all ()
            if msgs :
                current_text =await msgs [-1 ].inner_text ()
                if current_text ==last_text and current_text .strip ():
                    stable_count +=1 
                    if stable_count >=3 :# 3 saniye deгiшmezse готовоdыr
                        return current_text .strip ()
                else :
                    stable_count =0 
                    last_text =current_text 

        return last_text .strip ()if last_text else ''

    except Exception as e :
        print (f'[DeepSeek] Soru Ошибки: {e}')
        _логged_in =False # Новыйden логin denensin
        return ''


def ask_deepseek (prompt :str ,timeout :int =60 )->str :
    """
    Sync wrapper — ai_helper.py'из чaгrыlыr.
    DeepSeek'e soru sorar, cevabы string как вернуть.
    Неудачно olursa пусто string возвращает.
    """
    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD :
        return ''

    try :
    # Текущий event loop varsa использовать, yoksa новый создать
        try :
            loop =asyncio .get_event_loop ()
            if loop .is_running ():
            # Discord bot loop'u в, threимя'de работатьtыr
                import concurrent .futures 
                with concurrent .futures .ThreимяPoolExecutor ()as pool :
                    future =pool .submit (asyncio .run ,_ask_deepseek_async (prompt ,timeout ))
                    return future .result (timeout =timeout +10 )
            else :
                return loop .run_until_complete (_ask_deepseek_async (prompt ,timeout ))
        except RuntimeError :
            return asyncio .run (_ask_deepseek_async (prompt ,timeout ))
    except Exception as e :
        print (f'[DeepSeek] Wrapper Ошибки: {e}')
        return ''
