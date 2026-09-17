# -*- coding: utf-8 -*-
"""Тесты age-guard: <18 везде, знакомства строже.

Запуск: python3 tests/test_channel_guards.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_guards_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.channel_guards import (  # noqa: E402
    claimed_underage, message_has_media,
    AGE_GUARD_GUILD_WIDE, AGE_GUARD_CHANNELS, _should_scan_channel,
)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== claimed_underage (<18 удаляем, 18+ нет) ==')
check(claimed_underage('мне 16') == 16, 'мне 16 → 16')
check(claimed_underage('Мне 15 лет') == 15, 'Мне 15 лет → 15')
check(claimed_underage('мне17') == 17, 'мне17 → 17')
check(claimed_underage('я 14') == 14, 'я 14 → 14')
check(claimed_underage('мне есть 12 лет') == 12, 'мне есть 12 лет → 12')
check(claimed_underage('возраст 13') == 13, 'возраст 13 → 13')
check(claimed_underage('возраст:16') == 16, 'возраст:16 → 16')
check(claimed_underage('ему 15 лет уже') == 15, '15 лет → 15')
check(claimed_underage('мне пятнадцать') == 15, 'мне пятнадцать → 15')
check(claimed_underage('мне семнадцать лет') == 17, 'мне семнадцать лет → 17')
check(claimed_underage('мне тринадцать') == 13, 'мне тринадцать → 13')

# 18+ — НЕ удаляем
check(claimed_underage('мне 18') is None, 'мне 18 → None')
check(claimed_underage('мне 18 лет') is None, 'мне 18 лет → None')
check(claimed_underage('18 лет') is None, '18 лет → None')
check(claimed_underage('18') is None, 'голое 18 → None')
check(claimed_underage('мне 19') is None, 'мне 19 → None')
check(claimed_underage('мне двадцать') is None, 'мне двадцать → None')
check(claimed_underage('привет всем') is None, 'обычный текст → None')
check(claimed_underage('2 года на сервере') is None, '2 года на сервере → None')
check(claimed_underage('2 года') is None, 'голые «2 года» → None')
check(claimed_underage('мне 2 года') == 2, 'мне 2 года → 2')

# обходы символами (<18)
check(claimed_underage('мне +16') == 16, 'мне +16 → 16')
check(claimed_underage('мне =15') == 15, 'мне =15 → 15')
check(claimed_underage('мне ~14 лет') == 14, 'мне ~14 лет → 14')
check(claimed_underage('мне 1 6') == 16, 'мне 1 6 → 16')
check(claimed_underage('мне 1-7') == 17, 'мне 1-7 → 17')
check(claimed_underage('+12 лет') == 12, '+12 лет → 12')
check(claimed_underage('возраст=+17') == 17, 'возраст=+17 → 17')
check(claimed_underage('мне ||16||') == 16, 'spoiler 16 → 16')
check(claimed_underage('мне 17+') == 17, 'мне 17+ → 17')
check(claimed_underage('мне 17_') == 17, 'мне 17_ → 17')
check(claimed_underage('17_') == 17, '17_ → 17')
check(claimed_underage('17+') == 17, '17+ → 17')
check(claimed_underage('+17') == 17, '+17 → 17')
check(claimed_underage('мне +18') is None, 'мне +18 → None')
check(claimed_underage('18+') is None, '18+ → None')
check(claimed_underage('2017') is None, '2017 → None')

# обходы «меньше/до/под 18»
check(claimed_underage('ищу девушку меньше 18') == 17, 'ищу девушку меньше 18')
check(claimed_underage('ищу девушку младше 18') == 17, 'ищу младше 18')
check(claimed_underage('девушка до 18') == 17, 'девушка до 18')
check(claimed_underage('под 18') == 17, 'под 18')
check(claimed_underage('<18') == 17, '<18')
check(claimed_underage('несовершеннолетнюю') == 17, 'несовершеннолетнюю')
check(claimed_underage('under 18') == 17, 'under 18')
check(claimed_underage('не меньше 18') is None, 'не меньше 18 → None')
check(claimed_underage('не младше 18') is None, 'не младше 18 → None')
check(claimed_underage('старше 18') is None, 'старше 18 → None')
check(claimed_underage('от 18') is None, 'от 18 → None')
check(claimed_underage('ищу девушку 18+') is None, 'ищу 18+ → None')

check(claimed_underage('') is None, 'пустая строка')
check(claimed_underage(None) is None, 'None')

print('== живой кейс Morg: Ищу девушку мне 16 ==')
check(claimed_underage('Ищу девушку мне 16') == 16,
      'Ищу девушку мне 16 → 16')
check(claimed_underage('Ищу девушку мне 16', allow_bare=False) == 16,
      'guild-wide: Ищу девушку мне 16 → 16')
check(claimed_underage('ищу парня 16', allow_bare=False) == 16,
      'guild-wide: ищу парня 16 → 16')
check(claimed_underage('16 ищу девушку', allow_bare=False) == 16,
      'guild-wide: 16 ищу девушку → 16')
check(claimed_underage('ищу девушку 16 лет', allow_bare=False) == 16,
      'guild-wide: ищу девушку 16 лет → 16')
check(claimed_underage('Ищу девушку, мне 16 лет', allow_bare=False) == 16,
      'guild-wide: с запятой → 16')
check(claimed_underage('ищу гайд на 16 уровень', allow_bare=False) is None,
      'не знакомства: гайд 16 уровень → None')
check(claimed_underage('ищу девушку 18', allow_bare=False) is None,
      'ищу девушку 18 → None')

print('== guild-wide: без голых цифр (allow_bare=False) ==')
check(AGE_GUARD_GUILD_WIDE is True, 'AGE_GUARD_GUILD_WIDE включён')
check(_should_scan_channel(999999), 'скан любого канала при guild-wide')
check(_should_scan_channel(next(iter(AGE_GUARD_CHANNELS))),
      'скан канала знакомств')
check(claimed_underage('мне 14', allow_bare=False) == 14, 'guild: мне 14')
check(claimed_underage('ищу девушку меньше 18', allow_bare=False) == 17,
      'guild: меньше 18')
check(claimed_underage('мне семнадцать', allow_bare=False) == 17,
      'guild: семнадцать')
check(claimed_underage('17+', allow_bare=False) is None,
      'guild: голое 17+ не трогаем')
check(claimed_underage('просто 16 в чате', allow_bare=False) is None,
      'guild: голое 16 в общем чате → None')
check(claimed_underage('17+', allow_bare=True) == 17,
      'знакомства: 17+ → 17')


print('== message_has_media (shape) ==')


class _Att:
    def __init__(self, content_type='', filename=''):
        self.content_type = content_type
        self.filename = filename


class _Emb:
    def __init__(self, image=None, thumbnail=None, video=None):
        self.image = image
        self.thumbnail = thumbnail
        self.video = video


class _Msg:
    def __init__(self, attachments=None, embeds=None):
        self.attachments = attachments or []
        self.embeds = embeds or []


check(message_has_media(_Msg(attachments=[_Att('image/png', 'a.png')])),
      'png вложение → True')
check(message_has_media(_Msg(attachments=[_Att('video/mp4', 'a.mp4')])),
      'mp4 вложение → True')
check(message_has_media(_Msg(attachments=[_Att('', 'shot.JPEG')])),
      'JPEG по имени → True')
check(message_has_media(_Msg(embeds=[_Emb(image=object())])),
      'embed.image → True')
check(not message_has_media(_Msg(attachments=[_Att('text/plain', 'a.txt')])),
      'txt → False')
check(not message_has_media(_Msg()), 'пусто → False')


print(f'\n=== {PASS} passed, {FAIL} failed ===')
sys.exit(1 if FAIL else 0)
