"""DeepSeek login test - ne видеть контроль et"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

EMAIL    = os.getenv('DEEPSEEK_EMAIL', '')
PASSWORD = os.getenv('DEEPSEEK_PASSWORD', '')

async def test():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # Видеть açılsın
        page = await browser.new_page()

        print("Siteye gidiliyor...")
        await page.goto('https://chat.deepseek.com/', timeout=30000)
        await page.wait_for_timeout(3000)

        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        # Все input'ları listele
        inputs = await page.locator('input').all()
        print(f"\nInput количество: {len(inputs)}")
        for i, inp in enumerate(inputs):
            try:
                t = await inp.get_attribute('type')
                p = await inp.get_attribute('placeholder')
                n = await inp.get_attribute('name')
                print(f" [{i}] type={t} placeholder={p} name={n}")
            except:
                pass

        # Все кнопки listele
        buttons = await page.locator('button').all()
        print(f"\nButton количество: {len(buttons)}")
        for i, btn in enumerate(buttons[:10]):
            try:
                txt = await btn.inner_text()
                print(f" [{i}] {txt[:50]}")
            except:
                pass

        # Screenshot al
        await page.screenshot(path='deepseek_screenshot.png')
        print("\nScreenshot: deepseek_screenshot.png")

        await browser.close()

asyncio.run(test())
