"""
Profile Cog — Professional dashboard/ID-card style generation via Pillow
Clean black/white/red palette, custom line-art icons, fully anti-aliased
via supersampled rendering (no jagged pixels on curves/rotations)
"""
import discord 
from discord .ext import commands 
from discord import app_commands 
import os ,io ,json ,math ,aiohttp 
from datetime import datetime 
from PIL import Image ,ImageDraw ,ImageFont ,ImageFilter ,ImageEnhance 
from logger import get_logger 
from db import UserData ,GuildData 

log =get_logger ("profile")

ROOT =os .path .join (os .path .dirname (__file__ ),'..')
FONTS =os .path .join (ROOT ,'assets','fonts')
BG_PATH =os .path .join (ROOT ,'assets','profile_bg_pro.jpg')
FONT_B =os .path .join (FONTS ,'Bold.ttf')
FONT_R =os .path .join (FONTS ,'Regular.ttf')

# ═══════════════════════════════════════════════════════════════════════
# Palette — professional black / white / red
# ═══════════════════════════════════════════════════════════════════════
BLACK =(18 ,18 ,20 ,255 )
INK =(18 ,18 ,20 ,255 )
WHITE =(255 ,255 ,255 ,255 )
RED =(222 ,28 ,42 ,255 )
RED_DK =(168 ,18 ,30 ,255 )
GRAY =(128 ,128 ,132 ,255 )
GRAY_LT =(205 ,205 ,208 ,255 )
GRAY_LINE =(225 ,225 ,228 ,255 )
GOLD_TXT =(180 ,138 ,20 ,255 )
SILVER_TXT =(110 ,112 ,118 ,255 )
BRONZE_TXT =(150 ,92 ,46 ,255 )

SS =4 # supersampling factor for crisp anti-aliased vector shapes

W ,H =1000 ,580 


def _f (bold =False ,sz =20 ):
    try :
        return ImageFont .truetype (FONT_B if bold else FONT_R ,sz )
    except Exception :
        return ImageFont .load_default ()


        # ═══════════════════════════════════════════════════════════════════════
        # Supersampled rendering helper — draw at 4x then downscale for
        # perfectly smooth anti-aliased edges (no jagged pixels on any shape)
        # ═══════════════════════════════════════════════════════════════════════

def _ss_render (w ,h ,draw_fn ,scale =SS ):
    """Render a transparent RGBA tile at `scale`x resolution using draw_fn(d, scale),
    then Lanczos-downscale to (w, h) for crisp anti-aliased output."""
    big =Image .new ('RGBA',(w *scale ,h *scale ),(0 ,0 ,0 ,0 ))
    d =ImageDraw .Draw (big )
    draw_fn (d ,scale )
    return big .resize ((w ,h ),Image .Resampling .LANCZOS )


    # ═══════════════════════════════════════════════════════════════════════
    # Custom line-art icons — drawn in red, crisp thin strokes
    # ═══════════════════════════════════════════════════════════════════════

def _icon_chat (d ,cx ,cy ,s ,w ):
    bw ,bh =s *0.62 ,s *0.46 
    x0 ,y0 =cx -bw /2 ,cy -bh /2 -s *0.05 
    x1 ,y1 =cx +bw /2 ,cy +bh /2 -s *0.05 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bh *0.32 ,outline =RED ,width =w )
    tail =[(cx -bw *0.18 ,y1 -w *0.3 ),(cx -bw *0.04 ,y1 +bh *0.30 ),(cx +bw *0.12 ,y1 -w *0.3 )]
    d .line (tail ,fill =RED ,width =w ,joint ='curve')
    for i in (-1 ,0 ,1 ):
        r =s *0.028 
        dx =i *s *0.13 
        d .ellipse ((cx +dx -r ,cy -s *0.05 -r ,cx +dx +r ,cy -s *0.05 +r ),fill =RED )


def _icon_voice (d ,cx ,cy ,s ,w ):
    bx =cx -s *0.20 
    hw ,hh =s *0.14 ,s *0.20 
    d .rounded_rectangle ((bx -hw ,cy -hh ,bx +hw *0.3 ,cy +hh ),radius =hw *0.5 ,outline =RED ,width =w )
    tri =[(bx +hw *0.15 ,cy -hh *0.9 ),(bx +s *0.20 ,cy -s *0.28 ),(bx +s *0.20 ,cy +s *0.28 ),(bx +hw *0.15 ,cy +hh *0.9 )]
    d .line (tri ,fill =RED ,width =w ,joint ='curve')
    for r in (s *0.11 ,s *0.20 ,s *0.29 ):
        bbox =(cx +s *0.05 -r ,cy -r ,cx +s *0.05 +r ,cy +r )
        d .arc (bbox ,-42 ,42 ,fill =RED ,width =w )


def _icon_wallet (d ,cx ,cy ,s ,w ):
    bw ,bh =s *0.64 ,s *0.46 
    x0 ,y0 =cx -bw /2 ,cy -bh /2 
    x1 ,y1 =cx +bw /2 ,cy +bh /2 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bh *0.22 ,outline =RED ,width =w )
    d .line ([(x0 ,y0 +bh *0.32 ),(x1 ,y0 +bh *0.32 )],fill =RED ,width =max (1 ,int (w *0.7 )))
    r =s *0.085 
    ccx =x1 -r *1.5 
    ccy =y0 +bh *0.66 
    d .ellipse ((ccx -r ,ccy -r ,ccx +r ,ccy +r ),outline =RED ,width =max (1 ,int (w *0.8 )))


ICON_FUNCS ={'chat':_icon_chat ,'voice':_icon_voice ,'balance':_icon_wallet }


def _icon_badge (diameter ,glyph_key ,ring_color =BLACK ,ring_w =None ):
    """Square badge, white fill, thin black border, red line-art icon centered."""
    ring_w =ring_w if ring_w is not None else max (2 ,diameter //22 )

    def draw (d ,scale ):
        size =diameter *scale 
        rw =ring_w *scale 
        r =size *0.22 
        d .rounded_rectangle ((rw /2 ,rw /2 ,size -rw /2 -1 ,size -rw /2 -1 ),
        radius =r ,fill =WHITE ,outline =ring_color ,width =rw )
        ICON_FUNCS [glyph_key ](d ,size /2 ,size /2 ,size *0.60 ,max (2 ,int (size *0.032 )))

    return _ss_render (diameter ,diameter ,draw )


def _corner_bracket (size ,thickness ,length_ratio =0.30 ,color =RED ):
    """A single L-shaped corner bracket (top-left orientation), used rotated/flipped for other corners."""
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


def _avatar_frame (square_avatar ,size ,radius ,border =BLACK ,bw =6 ):
    """Rounded-square avatar with a crisp anti-aliased border/mask."""
    av =square_avatar 
    if av .size !=(size ,size ):
        av =av .resize ((size ,size ),Image .Resampling .LANCZOS )

    def mask_draw (d ,scale ):
        r =radius *scale 
        d .rounded_rectangle ((0 ,0 ,size *scale -1 ,size *scale -1 ),radius =r ,fill =(255 ,255 ,255 ,255 ))
    mask_big =Image .new ('RGBA',(size *SS ,size *SS ),(0 ,0 ,0 ,0 ))
    ImageDraw .Draw (mask_big ).rounded_rectangle ((0 ,0 ,size *SS -1 ,size *SS -1 ),radius =radius *SS ,fill =(255 ,255 ,255 ,255 ))
    mask =mask_big .resize ((size ,size ),Image .Resampling .LANCZOS ).split ()[-1 ]

    canvas =Image .new ('RGBA',(size ,size ),(0 ,0 ,0 ,0 ))
    canvas .paste (av ,(0 ,0 ),mask )

    def border_draw (d ,scale ):
        r =radius *scale 
        o =bw *scale 
        d .rounded_rectangle ((o /2 ,o /2 ,size *scale -o /2 -1 ,size *scale -o /2 -1 ),
        radius =r ,outline =border ,width =o )
    border_layer =_ss_render (size ,size ,border_draw )
    canvas .alpha_composite (border_layer )
    return canvas 


def _text_cx (draw ,text ,font ,x1 ,x2 ):
    bb =draw .textbbox ((0 ,0 ),text ,font =font )
    return x1 +(x2 -x1 -(bb [2 ]-bb [0 ]))//2 


def _xp_bar (w ,h ,progress ):
    def draw (d ,scale ):
        o =3 *scale 
        r =5 *scale 
        d .rounded_rectangle ((o /2 ,o /2 ,w *scale -o /2 -1 ,h *scale -o /2 -1 ),
        radius =r ,fill =WHITE ,outline =BLACK ,width =o )
        fw =max (0 ,int ((w *scale -o *2 )*min (progress ,1.0 )))
        if fw >0 :
            d .rounded_rectangle ((o ,o ,o +fw ,h *scale -o -1 ),radius =max (1 ,r -o ),fill =RED )
    return _ss_render (w ,h ,draw )


def _bg (w ,h ):
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


def _fmt (n ):
    return f"{n:,}".replace (","," ")


def _fmt_t (s ):
    h ,m =s //3600 ,(s %3600 )//60 
    return f"{h}ч {m}м"if h else f"{m}м"


async def _avatar (url ,sz =180 ,shape ='square'):
    try :
        async with aiohttp .ClientSession ()as s :
            async with s .get (url ,timeout =aiohttp .ClientTimeout (total =10 ))as r :
                data =await r .read ()
        av =Image .open (io .BytesIO (data )).convert ('RGBA').resize ((sz ,sz ),Image .Resampling .LANCZOS )
    except Exception :
        av =Image .new ('RGBA',(sz ,sz ),(235 ,235 ,238 ,255 ))
        d =ImageDraw .Draw (av )
        d .ellipse ((sz *0.28 ,sz *0.16 ,sz *0.72 ,sz *0.56 ),fill =(190 ,190 ,195 ,255 ))
        d .ellipse ((sz *0.12 ,sz *0.55 ,sz *0.88 ,sz *1.15 ),fill =(190 ,190 ,195 ,255 ))
    if shape =='circle':
        m =Image .new ('L',(sz ,sz ),0 )
        ImageDraw .Draw (m ).ellipse ((0 ,0 ,sz ,sz ),fill =255 )
        av .putalpha (m )
    return av 


def _rank_color (rank ):
    if rank ==1 :
        return RED 
    if rank ==2 :
        return SILVER_TXT 
    if rank ==3 :
        return BRONZE_TXT 
    return BLACK 


    # ═══════════════════════════════════════════════════════════════════════
    # Card Generator — clean professional black/white/red dashboard layout
    # ═══════════════════════════════════════════════════════════════════════

def generate_profile_card (avatar ,nickname ,level ,xp ,xp_needed ,
messages ,voice_seconds ,balance ,
rank_messages ,rank_voice ,rank_balance ):

    img =_bg (W ,H ).convert ('RGBA')
    d =ImageDraw .Draw (img )
    avg_rank =max (1 ,round ((rank_messages +rank_voice +rank_balance )/3 ))

    PAD =30 

    # ─── Top brand strip ─────────────────────────────────────────────
    f_brand =_f (bold =True ,sz =14 )
    f_brand_sub =_f (bold =False ,sz =11 )
    d .text ((PAD ,18 ),"AETHER",font =f_brand ,fill =BLACK )
    bb =d .textbbox ((PAD ,18 ),"AETHER",font =f_brand )
    # подпись справа от логотипа на ОДНОЙ базовой линии — чтобы ничего не наезжало
    pbb =d .textbbox ((0 ,0 ),"PROFILE",font =f_brand_sub )
    sub_y =bb [3 ]-(pbb [3 ]-pbb [1 ])-pbb [1 ]
    d .text ((bb [2 ]+8 ,sub_y ),"PROFILE",font =f_brand_sub ,fill =GRAY )
    tag =f"AVG RANK #{avg_rank}"
    tb =d .textbbox ((0 ,0 ),tag ,font =f_brand_sub )
    d .text ((W -PAD -(tb [2 ]-tb [0 ])-tb [0 ],sub_y ),tag ,font =f_brand_sub ,fill =_rank_color (avg_rank )[:3 ])
    line_y =bb [3 ]+12 
    d .line ([(PAD ,line_y ),(W -PAD ,line_y )],fill =BLACK ,width =2 )

    # ─── LEFT COLUMN — avatar card ───────────────────────────────────
    lx =PAD 
    ly =74 
    av_size =208 
    av_frame =_avatar_frame (avatar ,av_size ,radius =18 ,border =BLACK ,bw =5 )
    img .alpha_composite (av_frame ,(lx ,ly ))
    d =ImageDraw .Draw (img )

    # corner brackets (viewfinder style) around avatar — red accent
    bsz ,bt ,blen =40 ,4 ,0.55 
    bl =_corner_bracket (bsz ,bt ,blen )
    img .alpha_composite (bl ,(lx -10 ,ly -10 ))
    img .alpha_composite (bl .transpose (Image .FLIP_LEFT_RIGHT ),(lx +av_size -bsz +10 ,ly -10 ))
    img .alpha_composite (bl .transpose (Image .FLIP_TOP_BOTTOM ),(lx -10 ,ly +av_size -bsz +10 ))
    img .alpha_composite (bl .transpose (Image .ROTATE_180 ),(lx +av_size -bsz +10 ,ly +av_size -bsz +10 ))
    d =ImageDraw .Draw (img )

    # Ник: ужимаем по шрифту, при нехватке места — обрезаем с «…»,
    # чтобы не уползал под правые панели и за край карточки
    name_y =ly +av_size +26 
    max_nw =av_size +20 
    f_nick =_f (bold =True ,sz =22 )
    nick_up =nickname .upper ()
    nb =d .textbbox ((0 ,0 ),nick_up ,font =f_nick )
    while nb [2 ]-nb [0 ]>max_nw and f_nick .size >11 :
        f_nick =_f (bold =True ,sz =f_nick .size -1 )
        nb =d .textbbox ((0 ,0 ),nick_up ,font =f_nick )
    cut =nick_up 
    while nb [2 ]-nb [0 ]>max_nw and len (cut )>4 :
        cut =cut [:-1 ]
        nb =d .textbbox ((0 ,0 ),cut .rstrip ()+'…',font =f_nick )
    if len (cut )<len (nick_up ):
        nick_up =cut .rstrip ()+'…'
    nx =int (lx +(av_size -(nb [2 ]-nb [0 ]))/2 -nb [0 ])
    nx =max (lx ,min (nx ,lx +av_size +20 -(nb [2 ]-nb [0 ])))
    d .text ((nx ,name_y ),nick_up ,font =f_nick ,fill =BLACK )

    # red underline accent
    uy =name_y +(nb [3 ]-nb [1 ])+14 
    d .rectangle ((lx +av_size /2 -24 ,uy ,lx +av_size /2 +24 ,uy +3 ),fill =RED )

    # Server rank block
    f_rl =_f (bold =True ,sz =11 )
    f_rv =_f (bold =True ,sz =34 )
    rl_txt ="СРЕДНИЙ РЕЙТИНГ"
    rly =uy +22 
    rlb =d .textbbox ((0 ,0 ),rl_txt ,font =f_rl )
    while rlb [2 ]-rlb [0 ]>av_size and f_rl .size >8 :
        f_rl =_f (bold =True ,sz =f_rl .size -1 )
        rlb =d .textbbox ((0 ,0 ),rl_txt ,font =f_rl )
    d .text ((lx +(av_size -(rlb [2 ]-rlb [0 ]))/2 ,rly ),rl_txt ,font =f_rl ,fill =GRAY )

    rv_txt =f"#{avg_rank}"
    rvb =d .textbbox ((0 ,0 ),rv_txt ,font =f_rv )
    rv_color =_rank_color (avg_rank )
    d .text ((lx +(av_size -(rvb [2 ]-rvb [0 ]))/2 -rvb [0 ],rly +20 ),rv_txt ,font =f_rv ,fill =rv_color )

    # ─── RIGHT SIDE — LEVEL panel ─────────────────────────────────────
    RX =lx +av_size +30 
    RW =W -PAD -RX 
    top_h =172 
    top_panel =_rounded_panel (RW ,top_h ,radius =16 ,fill =WHITE ,outline =BLACK ,ow =3 )
    img .alpha_composite (top_panel ,(RX ,ly ))
    d =ImageDraw .Draw (img )

    f_lvl_lbl =_f (bold =True ,sz =13 )
    f_lvl_num =_f (bold =True ,sz =68 )
    d .text ((RX +26 ,ly +20 ),"УРОВЕНЬ",font =f_lvl_lbl ,fill =GRAY )
    lvl_str =str (level )
    d .text ((RX +24 ,ly +34 ),lvl_str ,font =f_lvl_num ,fill =BLACK )
    lvb =d .textbbox ((RX +24 ,ly +34 ),lvl_str ,font =f_lvl_num )

    # thin vertical divider + XP block to the right of the big number
    div_x =lvb [2 ]+26 
    d .line ([(div_x ,ly +30 ),(div_x ,ly +top_h -60 )],fill =GRAY_LINE ,width =2 )

    f_xp_lbl =_f (bold =True ,sz =11 )
    f_xp_val =_f (bold =True ,sz =20 )
    d .text ((div_x +22 ,ly +34 ),"ОПЫТ",font =f_xp_lbl ,fill =GRAY )
    xp_val_txt =f"{_fmt(xp)}"
    d .text ((div_x +22 ,ly +52 ),xp_val_txt ,font =f_xp_val ,fill =BLACK )
    f_xp_need =_f (bold =False ,sz =12 )
    d .text ((div_x +22 ,ly +80 ),f"из {_fmt(xp_needed)}",font =f_xp_need ,fill =GRAY )

    # XP progress bar across the bottom of the panel
    barw =RW -52 
    barh =22 
    prog =xp /xp_needed if xp_needed >0 else 0 
    bar =_xp_bar (barw ,barh ,prog )
    bar_x ,bar_y =RX +26 ,ly +top_h -46 
    img .alpha_composite (bar ,(bar_x ,bar_y ))
    d =ImageDraw .Draw (img )
    pct_txt =f"{int(prog * 100)}%"
    f_pct =_f (bold =True ,sz =12 )
    pb =d .textbbox ((0 ,0 ),pct_txt ,font =f_pct )
    pct_w =pb [2 ]-pb [0 ]
    fill_px =barw *min (prog ,1.0 )
    if fill_px >pct_w +20 :
    # enough room inside the filled (red) portion — draw in white, right-aligned inside it
        px =bar_x +fill_px -pct_w -10 
        pct_color =WHITE 
    else :
    # места внутри полоски мало — рисуем процент справа от неё, чёрным
        px =bar_x +barw +10 
        pct_color =BLACK 
    d .text ((px -pb [0 ],bar_y +(barh -(pb [3 ]-pb [1 ]))/2 -pb [1 ]),pct_txt ,font =f_pct ,fill =pct_color )

    # ─── BOTTOM — STATISTICS + RANKINGS panels ────────────────────────
    by =ly +top_h +22 
    bh_panel =H -PAD -by 
    PW =(RW -20 )//2 

    f_t =_f (bold =True ,sz =13 )
    f_v =_f (bold =True ,sz =19 )
    f_l =_f (bold =False ,sz =11 )

    def _stat_panel (x0 ,title ,rows ):
        panel =_rounded_panel (PW ,bh_panel ,radius =16 ,fill =WHITE ,outline =BLACK ,ow =3 )
        img .alpha_composite (panel ,(x0 ,by ))
        dd =ImageDraw .Draw (img )
        dd .text ((x0 +22 ,by +16 ),title ,font =f_t ,fill =BLACK )
        dd .line ([(x0 +22 ,by +42 ),(x0 +PW -22 ,by +42 )],fill =GRAY_LINE ,width =2 )

        row_h =(bh_panel -54 )//len (rows )
        badge_sz =46 
        for i ,(glyph ,val ,label )in enumerate (rows ):
            ry =by +50 +i *row_h 
            badge =_icon_badge (badge_sz ,glyph )
            img .alpha_composite (badge ,(x0 +20 ,ry +(row_h -badge_sz )//2 -6 ))
            dd =ImageDraw .Draw (img )
            tx =x0 +20 +badge_sz +16 
            dd .text ((tx ,ry +row_h //2 -24 ),val ,font =f_v ,fill =BLACK )
            dd .text ((tx ,ry +row_h //2 +2 ),label ,font =f_l ,fill =GRAY )
            if i <len (rows )-1 :
                sep_y =ry +row_h -4 
                dd .line ([(x0 +20 ,sep_y ),(x0 +PW -20 ,sep_y )],fill =GRAY_LINE ,width =1 )

    _stat_panel (RX ,"СТАТИСТИКА",[
    ('chat',_fmt (messages ),"сообщения"),
    ('voice',_fmt_t (voice_seconds ),"время в войсе"),
    ('balance',f"${_fmt(balance)}","баланс"),
    ])

    rkx =RX +PW +20 

    def _rank_panel (x0 ,title ,rows ):
        panel =_rounded_panel (PW ,bh_panel ,radius =16 ,fill =WHITE ,outline =BLACK ,ow =3 )
        img .alpha_composite (panel ,(x0 ,by ))
        dd =ImageDraw .Draw (img )
        dd .text ((x0 +22 ,by +16 ),title ,font =f_t ,fill =BLACK )
        dd .line ([(x0 +22 ,by +42 ),(x0 +PW -22 ,by +42 )],fill =GRAY_LINE ,width =2 )

        row_h =(bh_panel -54 )//len (rows )
        badge_sz =46 
        for i ,(glyph ,rank ,label )in enumerate (rows ):
            ry =by +50 +i *row_h 
            badge =_icon_badge (badge_sz ,glyph ,ring_color =_rank_color (rank ))
            img .alpha_composite (badge ,(x0 +20 ,ry +(row_h -badge_sz )//2 -6 ))
            dd =ImageDraw .Draw (img )
            tx =x0 +20 +badge_sz +16 
            dd .text ((tx ,ry +row_h //2 -24 ),f"#{rank}",font =f_v ,fill =_rank_color (rank ))
            dd .text ((tx ,ry +row_h //2 +2 ),label ,font =f_l ,fill =GRAY )
            if i <len (rows )-1 :
                sep_y =ry +row_h -4 
                dd .line ([(x0 +20 ,sep_y ),(x0 +PW -20 ,sep_y )],fill =GRAY_LINE ,width =1 )

    _rank_panel (rkx ,"РЕЙТИНГ",[
    ('chat',rank_messages ,"сообщения"),
    ('voice',rank_voice ,"время в войсе"),
    ('balance',rank_balance ,"баланс"),
    ])

    return img .convert ('RGB')



    # Data Fetchers
    # ═══════════════════════════════════════════════════════════════════════

def _lb (gid ):
    p =os .path .join ('data',f'leaderboard_{gid}.json')
    try :
        with open (p ,'r',encoding ='utf-8')as f :return json .load (f )
    except Exception:return {'messages':{},'voice_minutes':{}}

def _vs (gid ):
    p =os .path .join ('data',f'voice_stats_{gid}.json')
    try :
        with open (p ,'r',encoding ='utf-8')as f :return json .load (f )
    except Exception:return {'users':{}}

def _rank (sl ,uid ):
    for i ,(u ,_ )in enumerate (sl ):
        if u ==uid :return i +1 
    return len (sl )+1 


    # ═══════════════════════════════════════════════════════════════════════
    # Cog
    # ═══════════════════════════════════════════════════════════════════════

class ProfileCog (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        self .eco =UserData ("economy")

    def _data (self ,gid ,uid ):
        uid_s =str (uid )
        lb =_lb (gid )
        msgs =lb .get ('messages',{}).get (uid_s ,0 )

        voice =0 
        vs =_vs (gid )
        u =vs .get ('users',{}).get (uid_s ,{})
        if isinstance (u ,dict ):voice =u .get ('total_seconds',0 )
        if not voice :
            voice =lb .get ('voice_minutes',{}).get (uid_s ,0 )*60 

        eco =self .eco .get (uid )
        bal =eco .get ('balance',0 )+eco .get ('bank',0 )if isinstance (eco ,dict )else 0 

        lvl ,xp ,xp_need =1 ,0 ,200 
        try :
            from services .gamification import level_system ,points_system 
            ld =level_system .get_level (uid )
            lvl =ld .get ('level',1 )if isinstance (ld ,dict )else (ld if isinstance (ld ,int )else 1 )
            xp =points_system .get_points (uid )
            xp_need =100 +(lvl **2 )*50 
        except Exception:
            xp_need =100 +(lvl **2 )*50 

        ms =sorted (lb .get ('messages',{}).items (),key =lambda x :x [1 ],reverse =True )
        vsd ={k :v .get ('total_seconds',0 )for k ,v in vs .get ('users',{}).items ()if isinstance (v ,dict )}
        vss =sorted (vsd .items (),key =lambda x :x [1 ],reverse =True )
        all_e =self .eco .get_all ()
        bs =sorted ([(str (u ),d .get ('balance',0 )+d .get ('bank',0 ))for u ,d in all_e .items ()if isinstance (d ,dict )],key =lambda x :x [1 ],reverse =True )

        return dict (level =lvl ,xp =xp ,xp_needed =xp_need ,messages =msgs ,
        voice_seconds =voice ,balance =bal ,
        rank_messages =_rank (ms ,uid_s ),rank_voice =_rank (vss ,uid_s ),
        rank_balance =_rank (bs ,uid_s ))

    @commands .command (name ="profile",aliases =["профиль","карточка","me"])
    async def profile_cmd (self ,ctx ,member :discord .Member =None ):
        member =member or ctx .author 
        msg =await ctx .send (embed =discord .Embed (title ="...",color =discord .Color .dark_grey ()))
        try :
            av =await _avatar (member .display_avatar .url ,sz =260 ,shape ='square')
            d =self ._data (ctx .guild .id ,member .id )
            card =generate_profile_card (avatar =av ,nickname =member .display_name [:14 ],**d )
            buf =io .BytesIO ()
            card .save (buf ,format ='PNG')
            buf .seek (0 )
            await msg .delete ()
            await ctx .send (file =discord .File (buf ,filename ='profile.png'))
        except Exception as e :
            log .error (f"Profile error: {e}")
            import traceback ;traceback .print_exc ()
            await msg .edit (embed =discord .Embed (title ="Error",color =discord .Color .dark_grey ()))

    @app_commands .command (name ="profile",description ="Profile card")
    async def profile_slash (self ,interaction :discord .Interaction ,member :discord .Member =None ):
        member =member or interaction .user 
        await interaction .response .defer ()
        try :
            av =await _avatar (member .display_avatar .url ,sz =260 ,shape ='square')
            d =self ._data (interaction .guild .id ,member .id )
            card =generate_profile_card (avatar =av ,nickname =member .display_name [:14 ],**d )
            buf =io .BytesIO ()
            card .save (buf ,format ='PNG')
            buf .seek (0 )
            await interaction .followup .send (file =discord .File (buf ,filename ='profile.png'))
        except Exception as e :
            log .error (f"Profile error: {e}")
            await interaction .followup .send (embed =discord .Embed (title ="Error",color =discord .Color .dark_grey ()),ephemeral =True )


async def setup (bot ):
    await bot .add_cog (ProfileCog (bot ))
    log .info ("ProfileCog loaded (premium)")
