"""
Help Card — image-based command menu using the same professional
black/white/red dashboard aesthetic as the profile card.
"""
import math 
from PIL import Image ,ImageDraw 
from cogs ._card_style import (
BLACK ,WHITE ,RED ,RED_DK ,GRAY ,GRAY_LT ,GRAY_LINE ,
SS ,font ,ss_render ,corner_bracket ,rounded_panel ,text_cx ,fit_font ,bg ,
)

W =1000 

PERM_COLORS ={
"Все":(GRAY ,WHITE ,False ),
"Мод":(BLACK ,WHITE ,True ),
"Админ":(RED ,WHITE ,True ),
}


# ═══════════════════════════════════════════════════════════════════════
# Category line-art icons — drawn in red, crisp thin strokes
# (same visual language as profile.py's icon set)
# ═══════════════════════════════════════════════════════════════════════

def _icon_shield (d ,cx ,cy ,s ,w ):
    top =cy -s *0.38 
    pts =[
    (cx ,top ),(cx +s *0.32 ,top +s *0.12 ),(cx +s *0.32 ,cy +s *0.06 ),
    (cx ,cy +s *0.42 ),(cx -s *0.32 ,cy +s *0.06 ),(cx -s *0.32 ,top +s *0.12 ),
    ]
    d .line (pts +[pts [0 ]],fill =RED ,width =w ,joint ='curve')
    ck =[(cx -s *0.13 ,cy ),(cx -s *0.02 ,cy +s *0.12 ),(cx +s *0.16 ,cy -s *0.14 )]
    d .line (ck ,fill =RED ,width =w ,joint ='curve')


def _icon_alert (d ,cx ,cy ,s ,w ):
    top =cy -s *0.36 
    bot =cy +s *0.32 
    pts =[(cx ,top ),(cx +s *0.36 ,bot ),(cx -s *0.36 ,bot )]
    d .line (pts +[pts [0 ]],fill =RED ,width =w ,joint ='curve')
    d .line ([(cx ,cy -s *0.10 ),(cx ,cy +s *0.06 )],fill =RED ,width =w )
    r =s *0.03 
    d .ellipse ((cx -r ,cy +s *0.16 -r ,cx +r ,cy +s *0.16 +r ),fill =RED )


def _icon_ticket (d ,cx ,cy ,s ,w ):
    bw ,bh =s *0.66 ,s *0.42 
    x0 ,y0 =cx -bw /2 ,cy -bh /2 
    x1 ,y1 =cx +bw /2 ,cy +bh /2 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bh *0.24 ,outline =RED ,width =w )
    notch_r =bh *0.16 
    d .ellipse ((x0 -notch_r ,cy -notch_r ,x0 +notch_r ,cy +notch_r ),fill =WHITE ,outline =RED ,width =max (1 ,int (w *0.8 )))
    d .ellipse ((x1 -notch_r ,cy -notch_r ,x1 +notch_r ,cy +notch_r ),fill =WHITE ,outline =RED ,width =max (1 ,int (w *0.8 )))
    dash_x =cx 
    dy =y0 +bh *0.18 
    while dy <y1 -bh *0.1 :
        d .line ([(dash_x ,dy ),(dash_x ,dy +bh *0.12 )],fill =RED ,width =max (1 ,int (w *0.7 )))
        dy +=bh *0.24 


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


def _icon_note (d ,cx ,cy ,s ,w ):
    stem_x =cx +s *0.14 
    top_y =cy -s *0.32 
    bot_y =cy +s *0.18 
    d .line ([(stem_x ,top_y ),(stem_x ,bot_y )],fill =RED ,width =w )
    d .line ([(stem_x ,top_y ),(stem_x +s *0.22 ,top_y +s *0.08 )],fill =RED ,width =w )
    d .line ([(stem_x +s *0.22 ,top_y +s *0.08 ),(stem_x +s *0.22 ,top_y +s *0.30 )],fill =RED ,width =w )
    rx ,ry =s *0.12 ,s *0.10 
    d .ellipse ((stem_x -rx *1.7 ,bot_y -ry ,stem_x +rx *0.3 ,bot_y +ry ),outline =RED ,width =w )


def _icon_star (d ,cx ,cy ,s ,w ):
    pts =[]
    for i in range (10 ):
        r =s *0.36 if i %2 ==0 else s *0.15 
        ang =math .radians (-90 +i *36 )
        pts .append ((cx +r *math .cos (ang ),cy +r *math .sin (ang )))
    d .line (pts +[pts [0 ]],fill =RED ,width =w ,joint ='curve')


def _icon_gear (d ,cx ,cy ,s ,w ):
    r_out ,r_in =s *0.30 ,s *0.14 
    teeth =8 
    for i in range (teeth ):
        ang =math .radians (i *(360 /teeth ))
        x1p =cx +r_out *math .cos (ang )
        y1p =cy +r_out *math .sin (ang )
        x2p =cx +(r_out +s *0.08 )*math .cos (ang )
        y2p =cy +(r_out +s *0.08 )*math .sin (ang )
        d .line ([(x1p ,y1p ),(x2p ,y2p )],fill =RED ,width =w )
    d .ellipse ((cx -r_out ,cy -r_out ,cx +r_out ,cy +r_out ),outline =RED ,width =w )
    d .ellipse ((cx -r_in ,cy -r_in ,cx +r_in ,cy +r_in ),outline =RED ,width =max (1 ,int (w *0.85 )))


def _icon_headphone (d ,cx ,cy ,s ,w ):
    r =s *0.30 
    d .arc ((cx -r ,cy -r ,cx +r ,cy +r ),180 ,360 ,fill =RED ,width =w )
    cup_w ,cup_h =s *0.14 ,s *0.22 
    d .rounded_rectangle ((cx -r -cup_w *0.3 ,cy -cup_h *0.2 ,cx -r +cup_w *0.7 ,cy +cup_h *0.8 ),
    radius =cup_w *0.4 ,outline =RED ,width =w )
    d .rounded_rectangle ((cx +r -cup_w *0.7 ,cy -cup_h *0.2 ,cx +r +cup_w *0.3 ,cy +cup_h *0.8 ),
    radius =cup_w *0.4 ,outline =RED ,width =w )


def _icon_dice (d ,cx ,cy ,s ,w ):
    bw =s *0.56 
    x0 ,y0 =cx -bw /2 ,cy -bw /2 
    x1 ,y1 =cx +bw /2 ,cy +bw /2 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bw *0.20 ,outline =RED ,width =w )
    r =bw *0.075 
    pts =[(-1 ,-1 ),(1 ,-1 ),(-1 ,1 ),(1 ,1 ),(0 ,0 )]
    for px ,py in pts :
        dx =cx +px *bw *0.26 
        dy =cy +py *bw *0.26 
        d .ellipse ((dx -r ,dy -r ,dx +r ,dy +r ),fill =RED )


def _icon_gift (d ,cx ,cy ,s ,w ):
    bw ,bh =s *0.56 ,s *0.40 
    x0 =cx -bw /2 
    y0 =cy -bh *0.05 
    x1 =cx +bw /2 
    y1 =y0 +bh 
    d .rectangle ((x0 ,y0 ,x1 ,y1 ),outline =RED ,width =w )
    lid_h =bh *0.22 
    d .rectangle ((x0 -s *0.03 ,y0 -lid_h ,x1 +s *0.03 ,y0 ),outline =RED ,width =w )
    d .line ([(cx ,y0 -lid_h ),(cx ,y1 )],fill =RED ,width =w )
    loop_r =s *0.09 
    d .arc ((cx -loop_r *2.1 ,y0 -lid_h -loop_r *1.6 ,cx -loop_r *0.1 ,y0 -lid_h +loop_r *0.4 ),
    0 ,320 ,fill =RED ,width =max (1 ,int (w *0.85 )))
    d .arc ((cx +loop_r *0.1 ,y0 -lid_h -loop_r *1.6 ,cx +loop_r *2.1 ,y0 -lid_h +loop_r *0.4 ),
    220 ,180 ,fill =RED ,width =max (1 ,int (w *0.85 )))


def _icon_idcard (d ,cx ,cy ,s ,w ):
    bw ,bh =s *0.68 ,s *0.48 
    x0 ,y0 =cx -bw /2 ,cy -bh /2 
    x1 ,y1 =cx +bw /2 ,cy +bh /2 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bh *0.18 ,outline =RED ,width =w )
    pr =bh *0.20 
    pcx ,pcy =x0 +bw *0.26 ,y0 +bh *0.42 
    d .ellipse ((pcx -pr ,pcy -pr ,pcx +pr ,pcy +pr ),outline =RED ,width =max (1 ,int (w *0.85 )))
    d .arc ((pcx -pr *1.5 ,pcy +pr *0.6 ,pcx +pr *1.5 ,pcy +pr *2.6 ),180 ,360 ,fill =RED ,width =max (1 ,int (w *0.85 )))
    lx0 =x0 +bw *0.52 
    for i ,frac in enumerate ((0.34 ,0.50 ,0.66 )):
        ly =y0 +bh *frac 
        d .line ([(lx0 ,ly ),(x1 -bw *0.08 ,ly )],fill =RED ,width =max (1 ,int (w *0.7 )))


def _icon_menu (d ,cx ,cy ,s ,w ):
    """Grid/apps icon used for the overview cover."""
    bw =s *0.16 
    gap =s *0.10 
    for row in (-1 ,1 ):
        for col in (-1 ,1 ):
            x =cx +col *(bw /2 +gap /2 )
            y =cy +row *(bw /2 +gap /2 )
            d .rounded_rectangle ((x -bw /2 ,y -bw /2 ,x +bw /2 ,y +bw /2 ),radius =bw *0.22 ,outline =RED ,width =w )


ICON_FUNCS ={
'moderation':_icon_shield ,
'warnings':_icon_alert ,
'tickets':_icon_ticket ,
'economy':_icon_wallet ,
'music':_icon_note ,
'levels':_icon_star ,
'utility':_icon_gear ,
'voice':_icon_headphone ,
'fun':_icon_dice ,
'giveaway':_icon_gift ,
'profile':_icon_idcard ,
'menu':_icon_menu ,
}


def icon_badge (diameter ,glyph_key ,ring_color =BLACK ,ring_w =None ,icon_scale =0.60 ):
    """Rounded-square badge, white fill, thin border, red line-art icon centered."""
    ring_w =ring_w if ring_w is not None else max (2 ,diameter //22 )
    glyph_fn =ICON_FUNCS .get (glyph_key ,_icon_menu )

    def draw (d ,scale ):
        size =diameter *scale 
        rw =ring_w *scale 
        r =size *0.22 
        d .rounded_rectangle ((rw /2 ,rw /2 ,size -rw /2 -1 ,size -rw /2 -1 ),
        radius =r ,fill =WHITE ,outline =ring_color ,width =int (rw ))
        glyph_fn (d ,size /2 ,size /2 ,size *icon_scale ,max (2 ,int (size *0.032 )))

    return ss_render (diameter ,diameter ,draw )


    # ═══════════════════════════════════════════════════════════════════════
    # Overview card — grid of all categories
    # ═══════════════════════════════════════════════════════════════════════

def generate_help_overview (categories ,total_cmds ,prefix ="!"):
    PAD =30 
    cols =4 
    tile_w =220 
    tile_h =132 
    gap =18 
    rows =math .ceil (len (categories )/cols )
    grid_w =cols *tile_w +(cols -1 )*gap 
    header_h =78 
    footer_h =46 
    H =header_h +rows *tile_h +(rows -1 )*gap +footer_h +PAD *2 
    W_local =grid_w +PAD *2 

    img =bg (W_local ,H ).convert ('RGBA')
    d =ImageDraw .Draw (img )

    f_brand =font (bold =True ,sz =15 )
    f_brand_sub =font (bold =False ,sz =12 )
    d .text ((PAD ,24 ),"AETHER",font =f_brand ,fill =BLACK )
    bb =d .textbbox ((PAD ,24 ),"AETHER",font =f_brand )
    d .text ((bb [2 ]+8 ,27 ),"HELP",font =f_brand_sub ,fill =GRAY )
    tag =f"{total_cmds} КОМАНД"
    tb =d .textbbox ((0 ,0 ),tag ,font =f_brand_sub )
    d .text ((W_local -PAD -(tb [2 ]-tb [0 ]),28 ),tag ,font =f_brand_sub ,fill =RED [:3 ])
    d .line ([(PAD ,54 ),(W_local -PAD ,54 )],fill =BLACK ,width =2 )

    gy =header_h 
    for i ,cat in enumerate (categories ):
        col =i %cols 
        row =i //cols 
        x0 =PAD +col *(tile_w +gap )
        y0 =gy +row *(tile_h +gap )

        panel =rounded_panel (tile_w ,tile_h ,radius =16 ,fill =WHITE ,outline =BLACK ,ow =2 )
        img .alpha_composite (panel ,(x0 ,y0 ))
        dd =ImageDraw .Draw (img )

        badge =icon_badge (52 ,cat ["id"],ring_color =BLACK )
        img .alpha_composite (badge ,(x0 +16 ,y0 +16 ))
        dd =ImageDraw .Draw (img )

        f_title =fit_font (dd ,cat ["title"].upper (),True ,15 ,tile_w -84 )
        dd .text ((x0 +80 ,y0 +22 ),cat ["title"].upper (),font =f_title ,fill =BLACK )

        cnt_txt =f"{len(cat['commands'])} команд"
        f_cnt =font (bold =False ,sz =11 )
        dd .text ((x0 +80 ,y0 +44 ),cnt_txt ,font =f_cnt ,fill =GRAY )

        d .line ([(x0 +16 ,y0 +tile_h -34 ),(x0 +tile_w -16 ,y0 +tile_h -34 )],fill =GRAY_LINE ,width =1 )
        hint ="Выберите ниже ↓"
        f_hint =font (bold =False ,sz =10 )
        dd .text ((x0 +16 ,y0 +tile_h -26 ),hint ,font =f_hint ,fill =GRAY_LT )

    fy =H -footer_h -PAD //2 
    d =ImageDraw .Draw (img )
    d .line ([(PAD ,fy ),(W_local -PAD ,fy )],fill =GRAY_LINE ,width =1 )
    f_foot =font (bold =False ,sz =11 )
    foot_txt =f"Выберите категорию в меню ниже  •  Префикс команд: {prefix}"
    fb =d .textbbox ((0 ,0 ),foot_txt ,font =f_foot )
    d .text (((W_local -(fb [2 ]-fb [0 ]))/2 -fb [0 ],fy +12 ),foot_txt ,font =f_foot ,fill =GRAY )

    return img .convert ('RGB')


    # ═══════════════════════════════════════════════════════════════════════
    # Category detail card — icon header + command list (1 or 2 columns)
    # ═══════════════════════════════════════════════════════════════════════

def _draw_perm_pill (img ,d ,x ,y ,perm ):
    fill ,txt_color ,_ =PERM_COLORS .get (perm ,PERM_COLORS ["Все"])
    f =font (bold =True ,sz =10 )
    bb =d .textbbox ((0 ,0 ),perm .upper (),font =f )
    tw ,th =bb [2 ]-bb [0 ],bb [3 ]-bb [1 ]
    pad_x ,pad_y =9 ,5 
    pw ,ph =tw +pad_x *2 ,th +pad_y *2 
    pill =rounded_panel (pw ,ph ,radius =ph /2 ,fill =fill ,outline =fill ,ow =1 )
    img .alpha_composite (pill ,(int (x -pw ),int (y -ph /2 )))
    dd =ImageDraw .Draw (img )
    dd .text ((x -pw +pad_x -bb [0 ],y -ph /2 +pad_y -bb [1 ]),perm .upper (),font =f ,fill =txt_color )
    return pw 


def _command_rows_panel (img ,x0 ,y0 ,w ,rows ,row_h ):
    """rows: list of (cmd, desc, perm). Draws a bordered panel with seденьгиted rows."""
    h =row_h *len (rows )+16 
    panel =rounded_panel (w ,h ,radius =16 ,fill =WHITE ,outline =BLACK ,ow =2 )
    img .alpha_composite (panel ,(x0 ,y0 ))
    d =ImageDraw .Draw (img )

    f_cmd =font (bold =True ,sz =13 )
    f_desc =font (bold =False ,sz =11 )

    for i ,(cmd ,desc ,perm )in enumerate (rows ):
        ry =y0 +8 +i *row_h 
        cy_line =ry +row_h /2 

        # small red bullet
        br =3 
        d .ellipse ((x0 +18 -br ,cy_line -br -8 ,x0 +18 +br ,cy_line +br -8 ),fill =RED )

        max_cmd_w =w -190 
        fcmd =fit_font (d ,cmd ,True ,13 ,max_cmd_w )
        d .text ((x0 +30 ,ry +7 ),cmd ,font =fcmd ,fill =BLACK )
        d .text ((x0 +30 ,ry +27 ),desc ,font =f_desc ,fill =GRAY )

        _draw_perm_pill (img ,d ,x0 +w -18 ,cy_line ,perm )
        d =ImageDraw .Draw (img )

        if i <len (rows )-1 :
            sep_y =ry +row_h -2 
            d .line ([(x0 +18 ,sep_y ),(x0 +w -18 ,sep_y )],fill =GRAY_LINE ,width =1 )
    return h 



def generate_help_category (cat ,index ,total ,prefix ="!"):
    commands_ =cat ["commands"]
    n =len (commands_ )
    two_col =n >6 

    PAD =30 
    RX =PAD +250 +26 
    RW_total =W -PAD -RX 

    row_h =54 
    if two_col :
        col_w =(RW_total -18 )//2 
        left_n =math .ceil (n /2 )
        right_n =n -left_n 
        rows_h =max (left_n ,right_n )*row_h +16 
    else :
        col_w =RW_total 
        rows_h =n *row_h +16 

    header_h =74 
    ly =header_h 
    left_panel_h =rows_h 
    H =header_h +max (left_panel_h ,230 )+PAD 

    img =bg (W ,H ).convert ('RGBA')
    d =ImageDraw .Draw (img )

    f_brand =font (bold =True ,sz =15 )
    f_brand_sub =font (bold =False ,sz =12 )
    d .text ((PAD ,24 ),"AETHER",font =f_brand ,fill =BLACK )
    bb =d .textbbox ((PAD ,24 ),"AETHER",font =f_brand )
    d .text ((bb [2 ]+8 ,27 ),"HELP",font =f_brand_sub ,fill =GRAY )
    nav_txt =f"{index + 1} / {total}"
    nb =d .textbbox ((0 ,0 ),nav_txt ,font =f_brand_sub )
    d .text ((W -PAD -(nb [2 ]-nb [0 ]),28 ),nav_txt ,font =f_brand_sub ,fill =RED [:3 ])
    d .line ([(PAD ,54 ),(W -PAD ,54 )],fill =BLACK ,width =2 )

    # ─── Left: category icon panel ──────────────────────────────
    lw =250 
    left_h =max (left_panel_h ,230 )
    left_panel =rounded_panel (lw ,left_h ,radius =18 ,fill =WHITE ,outline =BLACK ,ow =3 )
    img .alpha_composite (left_panel ,(PAD ,ly ))
    d =ImageDraw .Draw (img )

    badge_sz =92 
    bx =PAD +(lw -badge_sz )//2 
    by =ly +28 
    badge =icon_badge (badge_sz ,cat ["id"],ring_color =BLACK ,icon_scale =0.58 )
    img .alpha_composite (badge ,(bx ,by ))
    d =ImageDraw .Draw (img )

    # corner brackets around icon badge (viewfinder accent, matches profile card)
    bsz ,bt =26 ,3 
    brk =corner_bracket (bsz ,bt ,0.55 )
    img .alpha_composite (brk ,(bx -8 ,by -8 ))
    img .alpha_composite (brk .transpose (Image .FLIP_LEFT_RIGHT ),(bx +badge_sz -bsz +8 ,by -8 ))
    img .alpha_composite (brk .transpose (Image .FLIP_TOP_BOTTOM ),(bx -8 ,by +badge_sz -bsz +8 ))
    img .alpha_composite (brk .transpose (Image .ROTATE_180 ),(bx +badge_sz -bsz +8 ,by +badge_sz -bsz +8 ))
    d =ImageDraw .Draw (img )

    title_y =by +badge_sz +22 
    f_title =fit_font (d ,cat ["title"].upper (),True ,20 ,lw -30 )
    tb =d .textbbox ((0 ,0 ),cat ["title"].upper (),font =f_title )
    d .text ((PAD +(lw -(tb [2 ]-tb [0 ]))/2 -tb [0 ],title_y ),cat ["title"].upper (),font =f_title ,fill =BLACK )

    uy =title_y +(tb [3 ]-tb [1 ])+14 
    d .rectangle ((PAD +lw /2 -22 ,uy ,PAD +lw /2 +22 ,uy +3 ),fill =RED )

    cnt_txt =f"{n} КОМАНД"
    f_cnt =font (bold =True ,sz =11 )
    cb =d .textbbox ((0 ,0 ),cnt_txt ,font =f_cnt )
    d .text ((PAD +(lw -(cb [2 ]-cb [0 ]))/2 ,uy +18 ),cnt_txt ,font =f_cnt ,fill =GRAY )

    # ─── Right: command list panel(s) ───────────────────────────
    if two_col :
        rows_left =commands_ [:left_n ]
        rows_right =commands_ [left_n :]
        _command_rows_panel (img ,RX ,ly ,col_w ,rows_left ,row_h )
        _command_rows_panel (img ,RX +col_w +18 ,ly ,col_w ,rows_right ,row_h )
    else :
        _command_rows_panel (img ,RX ,ly ,col_w ,commands_ ,row_h )

    return img .convert ('RGB')


async def setup (bot ):
    pass 

