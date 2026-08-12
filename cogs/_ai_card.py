"""
AI Visual Novel Dialogue Card Generator — ИИ пишет текст прямо на картинке
Вместо обычного текста в чате ИИ-ассистент Годжо отвечает через карточку визуальной новеллы,
где слева стоит соответствующий VTuber-аватар, а справа в диалоговом окне написан ответ ИИ.
"""

from logger import get_logger

_log = get_logger("_ai_card")

import os 
import io 
import math 
import textwrap 
from PIL import Image ,ImageDraw ,ImageFont 

ROOT =os .path .join (os .path .dirname (__file__ ),'..')
FONTS =os .path .join (ROOT ,'assets','fonts')
FONT_B =os .path .join (FONTS ,'Bold.ttf')
FONT_R =os .path .join (FONTS ,'Regular.ttf')

WHITE =(245 ,248 ,255 )
BLACK =(15 ,17 ,24 )
CYAN =(0 ,210 ,235 )
MUTED =(140 ,145 ,160 )
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


def _rounded_panel (w ,h ,radius ,fill ,outline ,ow =3 ):
    def draw (d ,scale ):
        r =radius *scale 
        o =ow *scale 
        d .rounded_rectangle ((o /2 ,o /2 ,w *scale -o /2 -1 ,h *scale -o /2 -1 ),
        radius =r ,fill =fill ,outline =outline ,width =o )
    return _ss_render (w ,h ,draw )


def _get_avatar_file (character_state :str ,text :str )->str :
    lower =text .lower ()
    if character_state =="investigate"or any (k in lower for k in ["проверяю","лог","баз","данные","настройки","сервер","система","контрол","incele","жалоб","наруш","оскорб"]):
        return os .path .join (ROOT ,"assets","ai_gojo","vtuber_investigating.png")
    elif character_state =="verdict"or any (k in lower for k in ["вердикт","наказан","апелляц","забанен","мьют","мут","штраф","суд","verdict"]):
        return os .path .join (ROOT ,"assets","ai_gojo","vtuber_verdict.png")
    elif character_state =="solution"or any (k in lower for k in ["решение","готово","исправлено","сделано","помочь","помощ","решен","чёzюm","halled","готово","успех"]):
        return os .path .join (ROOT ,"assets","ai_gojo","vtuber_solution.png")
    else :
        return os .path .join (ROOT ,"assets","ai_gojo","vtuber_welcome.png")


def generate_ai_dialogue_card (ai_text :str ,question :str ="",character_state :str ="welcome")->Image .Image :
    """Создает карточку диалога 920px (или выше), где текст написан прямо на картинке"""
    W =920 
    # Разбиваем текст ответа на строки (по 42 символа)
    clean_text =ai_text .strip ()or "Здравствуйте! Я Аэйтер, ваш ИИ-ассистент в тикетах."
    lines =[]
    for paragraph in clean_text .split ('\n'):
        wrapped =textwrap .wrap (paragraph ,width =42 )
        if wrapped :
            lines .extend (wrapped )
        else :
            lines .append ("")

    num_lines =max (1 ,len (lines ))
    H =max (480 ,160 +num_lines *32 +50 )

    # Темный кибер-фон
    bg =Image .new ('RGBA',(W ,H ),BLACK )
    d =ImageDraw .Draw (bg )

    # Легкие декоративные диагональные линии фона
    line_col =(30 ,34 ,48 ,255 )
    for i in range (0 ,W +H ,80 ):
        d .line ([(i ,0 ),(0 ,i )],fill =line_col ,width =1 )

        # 1. Загружаем и вставляем VTuber-спрайт Годжо слева (x=0..340)
    sprite_path =_get_avatar_file (character_state ,clean_text +" "+question )
    if os .path .exists (sprite_path ):
        try :
            sprite =Image .open (sprite_path ).convert ('RGBA')
            sw ,sh =sprite .size 
            target_h =int (H *0.96 )
            target_w =int (sw *(target_h /sh ))
            if target_w >340 :
                target_w =340 
                target_h =int (sh *(target_w /sw ))
            sprite =sprite .resize ((target_w ,target_h ),Image .Resampling .LANCZOS )
            bg .alpha_composite (sprite ,(10 ,H -target_h ))
        except Exception as _ex:
            _log.debug("generate_ai_dialogue_card(): подавлено: %s", _ex)

            # 2. Диалоговое окно визуальной новеллы справа (x=360, w=536)
    box_w =536 
    box_h =H -60 
    box_x =360 
    box_y =30 

    speech_box =_rounded_panel (
    box_w ,box_h ,radius =16 ,
    fill =(24 ,27 ,38 ,245 ),
    outline =CYAN ,ow =2 
    )
    bg .alpha_composite (speech_box ,(box_x ,box_y ))

    # 3. Имя персонажа и статус (Nameplate)
    name_pill =_rounded_panel (280 ,36 ,radius =10 ,fill =(12 ,14 ,20 ,255 ),outline =CYAN ,ow =2 )
    bg .alpha_composite (name_pill ,(box_x +20 ,box_y -14 ))
    d .text ((box_x +36 ,box_y -8 ),"АЭЙТЕР • ИИ ПОДДЕРЖКИ",fill =CYAN ,font =_f (True ,16 ))

    status_txt ="СЛУЖБА ПОДДЕРЖКИ"
    d .text ((box_x +box_w -170 ,box_y +14 ),status_txt ,fill =MUTED ,font =_f (False ,13 ))

    # 4. Текст ответа ИИ прямо на картинке
    text_x =box_x +28 
    text_y =box_y +45 
    line_height =32 

    for idx ,line in enumerate (lines ):
        y =text_y +idx *line_height 
        if y <box_y +box_h -40 :
            d .text ((text_x ,y ),line ,fill =WHITE ,font =_f (False ,20 ))

            # 5. Нижняя подсказка в диалоговом окне
    d .text ((box_x +28 ,box_y +box_h -30 ),"• Напишите сообщение ниже для продолжения диалога •",fill =MUTED ,font =_f (False ,13 ))

    return bg 


def generate_ai_dialogue_bytes (ai_text :str ,question :str ="",character_state :str ="welcome")->io .BytesIO :
    card =generate_ai_dialogue_card (ai_text ,question ,character_state ).convert ('RGB')
    buf =io .BytesIO ()
    card .save (buf ,format ='PNG',optimize =True )
    buf .seek (0 )
    return buf 


async def setup (bot ):
    pass 
