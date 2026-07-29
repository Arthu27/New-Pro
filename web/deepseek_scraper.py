"""
DeepSeek web scraper — API olmadan chat.deepseek.com kullanır.
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

DEEPSEEK_EMAIL    = os.getenv('DEEPSEEK_EMAIL', '')
DEEPSEEK_PASSWORD = os.getenv('DEEPSEEK_PASSWORD', '')

# Oturum statusu (tek seferlik login, sonra yeniden используется)
_browser   = None
_page      = None
_lock      = threading.Lock()
_logged_in = False


async def _ensure_login():
    """Tarayıcıyı запустить ve вход yap (bir kez)."""
    global _browser, _page, _logged_in

    from playwright.async_api import async_playwright

    if _logged_in and _page:
        return True

    try:
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await _browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        )
        _page = await context.new_page()

        # Вход sayfasına git
        await _page.goto('https://chat.deepseek.com/', timeout=30000)
        await _page.wait_for_timeout(2000)

        # Вход butonu
        try:
            login_btn = _page.locator('text=Лог in').first
            await login_btn.click(timeout=5000)
            await _page.wait_for_timeout(1000)
        except Exception:
            pass

        # Email
        email_input = _page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first
        await email_input.fill(DEEPSEEK_EMAIL, timeout=10000)

        # Паrole
        pass_input = _page.locator('input[type="password"]').first
        await pass_input.fill(DEEPSEEK_PASSWORD, timeout=5000)

        # Вход yap butonu
        submit = _page.locator('button[type="submit"]').first
        await submit.click(timeout=5000)

        # Вход tamamlanana kadar badd
        await _page.wait_for_url('**/chat**', timeout=20000)
        await _page.wait_for_timeout(2000)

        _logged_in = True
        print('[DeepSeek] Вход успешно')
        return True

    except Exception as e:
        print(f'[DeepSeek] Вход Ошибкаsı: {e}')
        _logged_in = False
        return False


async def _ask_deepseek_async(prompt: str, timeout: int = 60) -> str:
    """DeepSeek'e soru sor, cevabı döndür."""
    global _page, _logged_in

    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD:
        return ''

    if not _logged_in:
        ok = await _ensure_login()
        if not ok:
            return ''

    try:
        # Новый sohbet запустить
        try:
            new_chat = _page.locator('text=New Chat, text=Новый Sohbet, [aria-label*="new" i]').first
            await new_chat.click(timeout=3000)
            await _page.wait_for_timeout(500)
        except Exception:
            pass

        # Сообщение kutusunu bul ve yaz
        textarea = _page.locator('textarea, [contenteditable="true"]').first
        await textarea.click(timeout=5000)
        await textarea.fill(prompt, timeout=5000)

        # Отправить (Enter veya buton)
        await textarea.press('Enter')

        # Cevabın gelmesini badd — "düşünüyor" animasyonu bitene kadar
        await _page.wait_for_timeout(2000)

        # Cevap elementini badd
        start = datetime.utcnow()
        last_text = ''
        stable_count = 0

        while (datetime.utcnow() - start).seconds < timeout:
            await _page.wait_for_timeout(1000)

            # Последний message bloğunu al
            msgs = await _page.locator('.message-content, .ds-markdown, [class*="message"], [class*="response"]').all()
            if msgs:
                current_text = await msgs[-1].inner_text()
                if current_text == last_text and current_text.strip():
                    stable_count += 1
                    if stable_count >= 3:  # 3 saniye değişmezse tamamdır
                        return current_text.strip()
                else:
                    stable_count = 0
                    last_text = current_text

        return last_text.strip() if last_text else ''

    except Exception as e:
        print(f'[DeepSeek] Soru Ошибкаsı: {e}')
        _logged_in = False  # Новыйden login denensin
        return ''


def ask_deepseek(prompt: str, timeout: int = 60) -> str:
    """
    Sync wrapper — ai_helper.py'den çağrılır.
    DeepSeek'e soru sorar, cevabı string olarak döndürür.
    Неудачно olursa boş string döner.
    """
    if not DEEPSEEK_EMAIL or not DEEPSEEK_PASSWORD:
        return ''

    try:
        # Mevcut event loop varsa kullan, yoksa yeni создать
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Discord bot loop'u içindeyiz, thread'de çalıştır
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _ask_deepseek_async(prompt, timeout))
                    return future.result(timeout=timeout + 10)
            else:
                return loop.run_until_complete(_ask_deepseek_async(prompt, timeout))
        except RuntimeError:
            return asyncio.run(_ask_deepseek_async(prompt, timeout))
    except Exception as e:
        print(f'[DeepSeek] Wrapper Ошибкаsı: {e}')
        return ''
