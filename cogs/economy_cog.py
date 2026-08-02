"""
Economy Cog
Экономическая система — database (SQLite)
Тёмная тема, без эмодзи, русский язык
"""

import discord 
from discord .ext import commands 
from datetime import datetime ,timedelta 
import random 

from logger import get_logger 
from db import UserData 

log =get_logger ("economy_cog")

DEFAULT_DATA ={
'balance':100 ,
'bank':0 ,
'daily_last':None ,
'daily_streak':0 ,
'weekly_last':None ,
'work_last':None ,
'work_total':0 ,
'beg_last':None ,
'inventory':[] ,
'pets':[] ,
'job':None ,
'job_xp':0 ,
'job_level':1 ,
'bank_interest':0.02 ,
'bank_level':1 ,
'history':[] ,
'equipped_pet':None ,
'vault':0 ,  # редкая валюта (гемы)
}


RARITY_ORDER =['обычный','необычный','редкий','эпический','легендарный','мифический','божественный']
RARITY_COLORS ={
'обычный':0x95A5A6 ,'необычный':0x2ECC71 ,'редкий':0x3498DB ,'эпический':0x9B59B6 ,
'легендарный':0xF1C40F ,'мифический':0xE74C3C ,'божественный':0x8E44AD }

# Расширенный магазин: предмет -> {price, rarity, desc, sell, category}
ITEM_DETAILS ={
'игровая консоль':{'price':500 ,'rarity':'обычный','desc':'Игровая приставка','sell':250 ,'category':'техника'},
'ноутбук':{'price':2000 ,'rarity':'необычный','desc':'Мощный ноутбук','sell':1000 ,'category':'техника'},
'машина':{'price':10000 ,'rarity':'редкий','desc':'Спортивная машина','sell':5000 ,'category':'машины'},
'дом':{'price':50000 ,'rarity':'эпический','desc':'Уютный дом','sell':25000 ,'category':'недвижимость'},
'самолёт':{'price':100000 ,'rarity':'легендарный','desc':'Личный самолёт','sell':50000 ,'category':'машины'},
'удочка':{'price':300 ,'rarity':'обычный','desc':'Удочка для рыбалки','sell':150 ,'category':'инструменты'},
'кирка':{'price':400 ,'rarity':'обычный','desc':'Кирка для шахты','sell':200 ,'category':'инструменты'},
'топор':{'price':350 ,'rarity':'обычный','desc':'Топор лесоруба','sell':175 ,'category':'инструменты'},
'телефон':{'price':1500 ,'rarity':'необычный','desc':'Смартфон','sell':750 ,'category':'техника'},
'велосипед':{'price':2000 ,'rarity':'необычный','desc':'Велосипед','sell':1000 ,'category':'машины'},
'мотоцикл':{'price':8000 ,'rarity':'редкий','desc':'Мотоцикл','sell':4000 ,'category':'машины'},
'вилла':{'price':200000 ,'rarity':'мифический','desc':'Вилла у океана','sell':100000 ,'category':'недвижимость'},
'остров':{'price':500000 ,'rarity':'божественный','desc':'Личный остров','sell':250000 ,'category':'недвижимость'},
'кошка':{'price':3000 ,'rarity':'редкий','desc':'Домашняя кошка','sell':1500 ,'category':'питомцы','pet_bonus':10},
'собака':{'price':3500 ,'rarity':'редкий','desc':'Верный пёс','sell':1750 ,'category':'питомцы','pet_bonus':15},
'лиса':{'price':6000 ,'rarity':'эпический','desc':'Хитрая лиса','sell':3000 ,'category':'питомцы','pet_bonus':20},
'волк':{'price':8000 ,'rarity':'эпический','desc':'Дикий волк','sell':4000 ,'category':'питомцы','pet_bonus':25},
'дракон':{'price':30000 ,'rarity':'мифический','desc':'Дракон','sell':15000 ,'category':'питомцы','pet_bonus':50},
}

# Профессии
JOBS ={
'программист':{'pay':(300 ,600 ),'crit':(600 ,1200 ),'crit_chance':0.2 ,'icon':'💻'},
'полицейский':{'pay':(250 ,550 ),'crit':(500 ,1100 ),'crit_chance':0.18 ,'icon':'👮'},
'доктор':{'pay':(320 ,650 ),'crit':(640 ,1300 ),'crit_chance':0.18 ,'icon':'🩺'},
'фермер':{'pay':(150 ,400 ),'crit':(300 ,800 ),'crit_chance':0.25 ,'icon':'🌾'},
'рыбак':{'pay':(180 ,420 ),'crit':(360 ,840 ),'crit_chance':0.25 ,'icon':'🎣'},
'шахтер':{'pay':(200 ,450 ),'crit':(400 ,900 ),'crit_chance':0.22 ,'icon':'⛏️'},
'таксист':{'pay':(160 ,380 ),'crit':(320 ,760 ),'crit_chance':0.2 ,'icon':'🚕'},
'курьер':{'pay':(140 ,350 ),'crit':(280 ,700 ),'crit_chance':0.25 ,'icon':'📦'},
'повар':{'pay':(190 ,430 ),'crit':(380 ,860 ),'crit_chance':0.22 ,'icon':'👨‍🍳'},
'стример':{'pay':(280 ,580 ),'crit':(560 ,1160 ),'crit_chance':0.18 ,'icon':'🎮'},
}

# Биржа
STOCKS ={
'apple':{'name':'Apple','base':150 ,'emoji':'🍎'},
'discord':{'name':'Discord','base':220 ,'emoji':'💬'},
'ia corp':{'name':'AI Corp','base':300 ,'emoji':'🤖'},
'crypto':{'name':'Crypto','base':100 ,'emoji':'🪙'},
}

# Казино-игры
CASINO_GAMES =['coinflip','slots','blackjack','roulette','dice','crash']

def _rarity_color (rarity :str )->int :
    return RARITY_COLORS .get (rarity ,0x95A5A6 )

class _EconomyExtra (commands .Cog ):
    """Профессиональная экономическая система"""

    def _log_tx (self ,user_id :int ,data :dict ,label :str ,amount :int ,meta :str =''):
        """Запись в историю операций (макс 50)"""
        if 'history' not in data :
            data ['history']=[]
        data ['history'].append ({
        'label':label ,'amount':amount ,'meta':meta ,
        'ts':datetime .now ().isoformat ()})
        data ['history']=data ['history'][-50 :]
        self ._save (user_id ,data )

    def _migrate (self ,user_id :int ,data :dict )->dict :
        """Добавить недостающие поля в старые данные"""
        changed =False 
        for k ,v in DEFAULT_DATA .items ():
            if k not in data :
                data [k ]=v 
                changed =True 
        if changed :
            self ._save (user_id ,data )
        return data 

    # ── БАНК: проценты и лимит ──────────────────────────────
    @commands .command (name ='bank',aliases =['банк'])
    async def bank (self ,ctx ):
        """Проценты по вкладу + улучшение банка"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        rate =0.02 +0.01 *(data .get ('bank_level',1 )-1 )
        cap =50000 *data .get ('bank_level',1 )
        rows =[
        ("Счёт",f"${data['bank']:,}"),
        ("Процент",f"{rate*100:.1f}%"),
        ("Лимит",f"${cap:,}"),
        ("Уровень банка",str (data ['bank_level'])),
        ("Улучшить","!bankup"),
        ("Проценты","!interest"),
        ]
        img =await self .bot .loop .run_in_executor (
        None ,generate_eco_bytes ,"Банк",f"Профиль • {ctx.author.display_name}",rows ,(0 ,150 ,136 )
        )
        await ctx .send (file =discord .File (img ,filename ="bank.png" ))

    @commands .command (name ='bankup',aliases =['банк-улучшить'])
    async def bankup (self ,ctx ):
        """Улучшить банк (уровень, лимит, процент)"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        lvl =data ['bank_level']
        cost =5000 *lvl 
        if data ['balance']<cost :
            await ctx .send (f"Недостаточно денег! Нужно ${cost:,}.")
            return 
        data ['balance']-=cost 
        data ['bank_level']=lvl +1 
        self ._log_tx (ctx .author .id ,data ,'Банк улучшен',-cost ,f'ур. {lvl+1}')
        e =discord .Embed (title ="🏦 Банк улучшен!",color =0x2ECC71 ,
        description =f"Уровень банка: **{lvl} → {lvl+1}**\nНовый лимит: ${50000*(lvl+1):,}\nПроцент: {0.02+0.01*lvl:.1f}%")
        await ctx .send (embed =e )

    @commands .command (name ='interest',aliases =['проценты'])
    async def interest (self ,ctx ):
        """Получить проценты по вкладу (раз в 6 часов)"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        now =datetime .now ()
        if data .get ('interest_last'):
            last =datetime .fromisoformat (data ['interest_last'])
            if now -last <timedelta (hours =6 ):
                rem =timedelta (hours =6 )-(now -last )
                await ctx .send (f"Проценты будут через {int(rem.total_seconds()//3600)}ч.")
                return 
        rate =0.02 +0.01 *(data .get ('bank_level',1 )-1 )
        earned =int (data ['bank']*rate )
        data ['bank']+=earned 
        data ['interest_last']=now .isoformat ()
        self ._log_tx (ctx .author .id ,data ,'Проценты',earned )
        e =discord .Embed (title ="💰 Проценты начислены",color =0x2ECC71 ,
        description =f"Получено: **${earned:,}**\nСчёт: ${data['bank']:,}")
        await ctx .send (embed =e )

    # ── DAILY / WEEKLY со стриком ───────────────────────────
    @commands .command (name ='weekly',aliases =['недельная'])
    async def weekly (self ,ctx ):
        """Еженедельная награда"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        now =datetime .now ()
        if data .get ('weekly_last'):
            last =datetime .fromisoformat (data ['weekly_last'])
            if now -last <timedelta (days =7 ):
                rem =timedelta (days =7 )-(now -last )
                await ctx .send (f"Недельная награда будет через {int(rem.total_seconds()//86400)}д.")
                return 
        amount =random .randint (1500 ,4000 )
        data ['balance']+=amount 
        data ['weekly_last']=now .isoformat ()
        self ._log_tx (ctx .author .id ,data ,'Weekly',amount )
        e =discord .Embed (title ="📅 Недельная награда",color =0x3498DB ,
        description =f"Получено: **${amount:,}**")
        await ctx .send (embed =e )

    # Улучшение daily: стрик
    # (переопределяем существующий daily — добавляем стрик)

    # ── ПРОФЕССИИ ───────────────────────────────────────────
    @commands .command (name ='job',aliases =['работа','профессия'])
    async def job (self ,ctx ,job :str =None ):
        """Устроиться на работу или показать текущую"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if job :
            key =job .lower ().strip ()
            if key in JOBS :
                data ['job']=key 
                data ['job_xp']=0 
                data ['job_level']=1 
                self ._save (ctx .author .id ,data )
                j =JOBS [key ]
                e =discord .Embed (title =f"{j['icon']} Работа получена",color =0x2ECC71 ,
                description =f"Профессия: **{key.capitalize()}**\nЗарплата: ${j['pay'][0]}-{j['pay'][1]}\nКрит: {j['crit_chance']*100:.0f}%")
                await ctx .send (embed =e )
                return 
            else :
                await ctx .send (f"Профессия не найдена. Доступные: {', '.join(JOBS.keys())}")
                return 
        if not data ['job']:
            await ctx .send ("Вы без работы! Выберите: `!job программист` / `!job фермер` ...")
            return 
        j =JOBS [data ['job']]
        rows =[
        ("Профессия",data ['job'].capitalize ()),
        ("Уровень",str (data ['job_level'])),
        ("Опыт",f"{data['job_xp']}/100"),
        ("Зарплата",f"${j['pay'][0]}-{j['pay'][1]}"),
        ("Крит. шанс",f"{j['crit_chance']*100:.0f}%"),
        ("Бонус питомца",f"+{ITEM_DETAILS.get(data.get('equipped_pet'),{}).get('pet_bonus',0)}%"),
        ]
        img =await self .bot .loop .run_in_executor (
        None ,generate_eco_bytes ,"Работа",f"{data['job'].capitalize()} • {ctx.author.display_name}",rows ,(52 ,211 ,153 )
        )
        await ctx .send (file =discord .File (img ,filename ="job.png" ))

    @commands .command (name ='jobs',aliases =['профессии'])
    async def jobs_list (self ,ctx ):
        """Список всех профессий"""
        e =discord .Embed (title ="🧑‍💼 Профессии",color =0x95A5A6 )
        for name ,j in JOBS .items ():
            e .add_field (name =f"{j['icon']} {name.capitalize()}",value =f"${j['pay'][0]}-{j['pay'][1]} · крит {j['crit_chance']*100:.0f}%",inline =True )
        await ctx .send (embed =e )

    # Переопределяем work с учётом профессии
    @commands .command (name ='work',aliases =['чalыш','работать'])
    async def work (self ,ctx ):
        """Работать по профессии"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        now =datetime .now ()
        if data ['work_last']:
            last =datetime .fromisoformat (data ['work_last'])
            if now -last <timedelta (minutes =30 ):
                m =int ((timedelta (minutes =30 )-(now -last )).total_seconds ()/60 )
                await ctx .send (f"Отдохните. Попробуйте через {m} мин.")
                return 
        # бонус питомца
        pet_bonus =1.0 
        equipped =data .get ('equipped_pet')
        if equipped and equipped in ITEM_DETAILS :
            pet_bonus =1 +(ITEM_DETAILS [equipped ].get ('pet_bonus',0 )/100 )

        if not data ['job']:
            # случайная подработка
            jobs =list (JOBS .keys ())
            jname =random .choice (jobs )
            j =JOBS [jname ]
            lo ,hi =j ['pay']
            amount =int (random .randint (lo ,hi )*pet_bonus )
            data ['balance']+=amount 
            data ['work_last']=now .isoformat ()
            data ['work_total']=data .get ('work_total',0 )+amount 
            self ._log_tx (ctx .author .id ,data ,'Подработка',amount )
            e =discord .Embed (title =f"{j['icon']} Подработка",color =0x95A5A6 ,
            description =f"Вы подработали {jname}. Заработано: **${amount:,}**")
            await ctx .send (embed =e )
            return 

        j =JOBS [data ['job']]
        lo ,hi =j ['pay']
        crit =random .random ()<j ['crit_chance']
        if crit :
            amount =random .randint (*j ['crit'])
            base =f"{j['icon']} Критический успех!"
            extra ="✨"
        else :
            amount =random .randint (lo ,hi )
            base =f"{j['icon']} Работа: {data['job'].capitalize()}"
            extra =""
        amount =int (amount *pet_bonus )
        # случайное событие
        event_roll =random .random ()
        if event_roll <0.08 :
            bonus =random .randint (50 ,200 )
            amount +=bonus 
            base +="\n💡 Нашли бонус!"
        elif event_roll <0.13 :
            penalty =random .randint (30 ,100 )
            amount =max (0 ,amount -penalty )
            base +="\n⚠️ Неудачный день!"
        data ['balance']+=amount 
        data ['work_last']=now .isoformat ()
        data ['work_total']=data .get ('work_total',0 )+amount 
        # опыт профессии
        xp_gain =random .randint (15 ,30 )
        data ['job_xp']=data .get ('job_xp',0 )+xp_gain 
        lvl_up =""
        if data ['job_xp']>=100 :
            data ['job_xp']-=100 
            data ['job_level']=data .get ('job_level',1 )+1 
            lvl_up =f"\n🎉 Профессия повышена до **{data['job_level']}**!"
        self ._log_tx (ctx .author .id ,data ,'Работа',amount )
        e =discord .Embed (title =base ,color =0x95A5A6 ,timestamp =datetime .now (),
        description =f"Заработано: **${amount:,}**{extra}{lvl_up}\nОпыт: {data['job_xp']}/100")
        await ctx .send (embed =e )

    # ── ИНВЕНТАРЬ / ПРОДАЖА / ИСПОЛЬЗОВАНИЕ ─────────────────
    @commands .command (name ='sell',aliases =['продать'])
    async def sell (self ,ctx ,*,item :str ):
        """Продать предмет из инвентаря"""
        key =item .lower ().strip ()
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        inv =data .get ('inventory',[])
        if key not in inv :
            await ctx .send ("У вас нет такого предмета.")
            return 
        det =ITEM_DETAILS .get (key ,{})
        price =det .get ('sell',det .get ('price',100 ))
        inv .remove (key )
        data ['inventory']=inv 
        data ['balance']+=price 
        self ._log_tx (ctx .author .id ,data ,'Продажа',price ,key )
        e =discord .Embed (title ="🏷️ Продано",color =0x2ECC71 ,
        description =f"**{key.capitalize()}** продано за **${price:,}**")
        await ctx .send (embed =e )

    @commands .command (name ='use',aliases =['использовать'])
    async def use (self ,ctx ,*,item :str ):
        """Использовать предмет (питомца)"""
        key =item .lower ().strip ()
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        inv =data .get ('inventory',[])
        if key not in inv :
            await ctx .send ("У вас нет такого предмета.")
            return 
        if key not in ITEM_DETAILS :
            await ctx .send ("Этот предмет нельзя использовать.")
            return 
        cat =ITEM_DETAILS [key ].get ('category')
        if cat =='питомцы':
            data ['equipped_pet']=key 
            self ._save (ctx .author .id ,data )
            e =discord .Embed (title ="🐾 Питомец выбран",color =0x2ECC71 ,
            description =f"**{key.capitalize()}** активен! Бонус к работе: +{ITEM_DETAILS[key].get('pet_bonus',0)}%")
            await ctx .send (embed =e )
        else :
            await ctx .send ("Этот предмет нельзя использовать.")

    @commands .command (name ='pets',aliases =['питомцы'])
    async def pets (self ,ctx ):
        """Ваши питомцы"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        inv =data .get ('inventory',[])
        my_pets =[p for p in inv if p in ITEM_DETAILS and ITEM_DETAILS [p ].get ('category')=='питомцы']
        equipped =data .get ('equipped_pet')
        if not my_pets :
            await ctx .send ("У вас нет питомцев. Купите в магазине: `!buy кошка`")
            return 
        lines =[]
        for p in my_pets :
            mark ="⭐"if p ==equipped else "•"
            lines .append ((f"{mark} {p.capitalize()}",f"+{ITEM_DETAILS[p].get('pet_bonus',0)}% к работе"))
        if not lines :
            lines =[("Питомцы","Нет")]
        img =await self .bot .loop .run_in_executor (
        None ,generate_eco_bytes ,"Питомцы",f"Профиль • {ctx.author.display_name}",lines ,(155 ,89 ,182 )
        )
        await ctx .send (file =discord .File (img ,filename ="pets.png" ))

    # ── КАЗИНО ──────────────────────────────────────────────
    @commands .command (name ='slots',aliases =['слоты'])
    async def slots (self ,ctx ,bet :int =100 ):
        """Игровые автоматы"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if bet <10 or bet >data ['balance']:
            await ctx .send ("Ставка должна быть от 10 до вашего баланса.")
            return 
        symbols =['🍒','🍋','🍇','💎','7️⃣','⭐']
        r1 ,r2 ,r3 =random .choices (symbols ,k =3 )
        data ['balance']-=bet 
        if r1 ==r2 ==r3 :
            mult ={'🍒':3 ,'🍋':4 ,'🍇':5 ,'💎':8 ,'⭐':12 ,'7️⃣':25 }.get (r1 ,3 )
            win =bet *mult 
            data ['balance']+=win 
            self ._log_tx (ctx .author .id ,data ,'Слоты',win ,f'{r1}{r2}{r3}' )
            result =f"🎉 ДЖЕКПОТ! +${win:,} (x{mult})"
        elif r1 ==r2 or r2 ==r3 :
            win =int (bet *1.5 )
            data ['balance']+=win 
            self ._log_tx (ctx .author .id ,data ,'Слоты',win )
            result =f"✌️ Малый выигрыш! +${win:,}"
        else :
            self ._log_tx (ctx .author .id ,data ,'Слоты',-bet )
            result =f"💸 Проигрыш: -${bet:,}"
        e =discord .Embed (title ="🎰 Слоты",color =0x95A5A6 ,
        description =f"{r1} {r2} {r3}\n\n{result}\nБаланс: ${data['balance']:,}")
        await ctx .send (embed =e )

    @commands .command (name ='casino-coinflip',aliases =['монетка'])
    async def coinflip (self ,ctx ,bet :int ,choice :str ='орел'):
        """Казино: монетка"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if bet <10 or bet >data ['balance']:
            await ctx .send ("Неверная ставка.")
            return 
        choice =choice .lower ()
        if choice not in ('орел','решка','орёл','орeл'):
            await ctx .send ("Выберите орел или решка.")
            return 
        result =random .choice (['орел','решка'])
        data ['balance']-=bet 
        win =choice in ('орел','орёл','орeл')and result =='орел'or choice =='решка'and result =='решка'
        if win :
            data ['balance']+=bet *2 
            self ._log_tx (ctx .author .id ,data ,'Coinflip',bet )
            desc =f"🪙 {result.capitalize()} — Вы выиграли +${bet:,}!"
        else :
            self ._log_tx (ctx .author .id ,data ,'Coinflip',-bet )
            desc =f"🪙 {result.capitalize()} — Вы проиграли -${bet:,}"
        e =discord .Embed (title ="🪙 Казино",color =0x95A5A6 ,description =desc )
        await ctx .send (embed =e )

    @commands .command (name ='casino-dice',aliases =['casino-zar'])
    async def dice (self ,ctx ,bet :int =100 ,prediction :str ='higher'):
        """Казино: угадай 4+ (higher) или 3- (lower)"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if bet <10 or bet >data ['balance']:
            await ctx .send ("Неверная ставка.")
            return 
        prediction =prediction .lower ()
        roll =random .randint (1 ,6 )
        win =False 
        if prediction in ('higher','больше','выше')and roll >=4 : win =True 
        elif prediction in ('lower','меньше','ниже')and roll <=3 : win =True 
        data ['balance']-=bet 
        if win :
            data ['balance']+=bet *2 
            self ._log_tx (ctx .author .id ,data ,'Кость',bet )
            desc =f"🎲 Выпало **{roll}** — Вы выиграли +${bet:,}!"
        else :
            self ._log_tx (ctx .author .id ,data ,'Кость',-bet )
            desc =f"🎲 Выпало **{roll}** — Вы проиграли -${bet:,}"
        e =discord .Embed (title ="🎲 Казино",color =0x95A5A6 ,description =desc )
        await ctx .send (embed =e )

    # ── КЕЙСЫ ───────────────────────────────────────────────
    CASES ={
    'обычный':{'price':500 ,'pool':['обычный','необычный']},
    'редкий':{'price':2000 ,'pool':['необычный','редкий']},
    'эпический':{'price':8000 ,'pool':['редкий','эпический']},
    'легендарный':{'price':25000 ,'pool':['эпический','легендарный']},
    }

    @commands .command (name ='kasa',aliases =['кейс'])
    async def case (self ,ctx ,case :str ='обычный'):
        """Открыть кейс"""
        key =case .lower ().strip ()
        if key not in self .CASES :
            await ctx .send ("Кейсы: обычный / редкий / эпический / легендарный")
            return 
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        price =self .CASES [key ]['price']
        if data ['balance']<price :
            await ctx .send (f"Недостаточно денег! Нужно ${price:,}.")
            return 
        data ['balance']-=price 
        # шанс получить предмет
        pool =self .CASES [key ]['pool']
        if random .random ()<0.4 :
            # предмет
            candidates =[i for i ,d in ITEM_DETAILS .items ()if d ['rarity']in pool ]
            if candidates :
                item =random .choice (candidates )
                data ['inventory'].append (item )
                self ._log_tx (ctx .author .id ,data ,'Кейс',-price ,f'+{item}' )
                e =discord .Embed (title =f"📦 Кейс: {key}",color =_rarity_color (ITEM_DETAILS [item]['rarity']) ,
                description =f"Вы получили предмет: **{item.capitalize()}** ({ITEM_DETAILS[item]['rarity']})")
            else :
                win =random .randint (100 ,500 )
                data ['balance']+=win 
                self ._log_tx (ctx .author .id ,data ,'Кейс',-price +win ,'+деньги' )
                e =discord .Embed (title ="📦 Кейс",color =0x95A5A6 ,description =f"Вы получили **${win:,}**")
        else :
            win =random .randint (price //2 ,price *2 )
            data ['balance']+=win 
            self ._log_tx (ctx .author .id ,data ,'Кейс',-price +win ,'+деньги' )
            e =discord .Embed (title ="📦 Кейс",color =0x95A5A6 ,description =f"Вы получили **${win:,}**")
        await ctx .send (embed =e )

    # ── БИРЖА ───────────────────────────────────────────────
    @commands .command (name ='stock',aliases =['акции','биржа'])
    async def stock (self ,ctx ,action :str ='view',stock :str =None ,amount :int =0 ):
        """Биржа: view / buy / sell"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        # генерируем текущие цены
        if action .lower ()=='view' or action .lower ()=='показать':
            e =discord .Embed (title ="📈 Биржа",color =0x95A5A6 ,timestamp =datetime .now ())
            for k ,s in STOCKS .items ():
                price =int (s ['base']+random .randint (-30 ,30 ))
                e .add_field (name =f"{s['emoji']} {s['name']}",value =f"${price:,} · `!stock buy {k} N`",inline =True )
            await ctx .send (embed =e )
            return 
        if not stock or stock .lower ()not in STOCKS :
            await ctx .send ("Неверная акция.")
            return 
        key =stock .lower ()
        price =int (STOCKS [key ]['base']+random .randint (-30 ,30 ))
        if action .lower ()in ('buy','купить'):
            cost =price *amount 
            if amount <=0 or cost >data ['balance']:
                await ctx .send ("Недостаточно денег или неверное кол-во.")
                return 
            data ['balance']-=cost 
            data ['stocks']=data .get ('stocks',{})
            data ['stocks'][key ]=data ['stocks'].get (key ,0 )+amount 
            self ._log_tx (ctx .author .id ,data ,'Покупка акций',-cost ,f'{amount} {key}' )
            e =discord .Embed (title ="📈 Куплено",color =0x2ECC71 ,description =f"{amount} {STOCKS[key]['name']} за ${cost:,}")
            await ctx .send (embed =e )
        elif action .lower ()in ('sell','продать'):
            have =data .get ('stocks',{}).get (key ,0 )
            if amount <=0 or amount >have :
                await ctx .send ("Недостаточно акций.")
                return 
            data ['stocks'][key ]=have -amount 
            gain =price *amount 
            data ['balance']+=gain 
            self ._log_tx (ctx .author .id ,data ,'Продажа акций',gain ,f'{amount} {key}' )
            e =discord .Embed (title ="📈 Продано",color =0x2ECC71 ,description =f"{amount} {STOCKS[key]['name']} за ${gain:,}")
            await ctx .send (embed =e )
        else :
            await ctx .send ("Используйте: `!stock buy|sell [акция] [кол-во]`")

    # ── ТОРГОВЛЯ ────────────────────────────────────────────
    @commands .command (name ='trade',aliases =['трейд'])
    async def trade (self ,ctx ,member :discord .Member ,amount :int ):
        """Передать деньги (безопасный перевод)"""
        if member ==ctx .author or member .bot or amount <=0 :
            await ctx .send ("Неверный получатель или сумма.")
            return 
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if data ['balance']<amount :
            await ctx .send ("Недостаточно денег.")
            return 
        target =self ._get (member .id )
        data ['balance']-=amount 
        target ['balance']+=amount 
        self ._log_tx (ctx .author .id ,data ,'Перевод',-amount ,member .display_name )
        self ._log_tx (member .id ,target ,'Получено',amount ,ctx .author .display_name )
        e =discord .Embed (title ="💸 Трейд",color =0x2ECC71 ,
        description =f"{ctx.author.mention} → {member.mention}\n**${amount:,}**")
        await ctx .send (embed =e )

    # ── ИСТОРИЯ ─────────────────────────────────────────────
    @commands .command (name ='eko-gecmis',aliases =['история'])
    async def history (self ,ctx ):
        """История операций"""
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        hist =data .get ('history',[])
        if not hist :
            await ctx .send ("История пуста.")
            return 
        e =discord .Embed (title ="🧾 История операций",color =0x95A5A6 )
        for h in reversed (hist [-15 :]):
            amt =h ['amount']
            sign ='+'if amt >=0 else ''
            e .add_field (name =f"{h['label']} · {sign}${amt:,}",value =h .get ('meta','')or '—',inline =False )
        await ctx .send (embed =e )

    # ── ЛИДЕРЫ ──────────────────────────────────────────────
    @commands .command (name ='top',aliases =['топ'])
    async def top (self ,ctx ,field :str ='balance'):
        """Топ: balance / bank / work / total"""
        field =field .lower ()
        try :
            all_users =self .db .get_all ()
        except Exception :
            all_users ={}
        if not all_users :
            await ctx .send ("Нет данных.")
            return 
        rows =[]
        for uid ,d in all_users .items ():
            if not isinstance (d ,dict ):
                continue 
            if field in ('balance','bank','total'):
                val =d .get (field ,0 )
                if field =='total' : val =d .get ('balance',0 )+d .get ('bank',0 )
            elif field in ('work','работа'):
                val =d .get ('work_total',0 )
            elif field =='level':
                val =d .get ('job_level',1 )
            else :
                val =d .get ('balance',0 )
            if val >0 :
                rows .append ((uid ,val ))
        rows .sort (key =lambda x :-x [1 ])
        if not rows :
            await ctx .send ("Нет данных.")
            return 
        medals =['🥇','🥈','🥉']
        lines =[]
        for i ,(uid ,val )in enumerate (rows [:8 ],1 ):
            try :
                u =await self .bot .fetch_user (int (uid ))
                name =u .name 
            except Exception :
                name =str (uid )[:12 ]
            medal =medals [i -1 ]if i <=3 else f"#{i}"
            lines .append ((f"{medal} {name}",f"${val:,}"))
        img =await self .bot .loop .run_in_executor (
        None ,generate_eco_bytes ,"Топ",f"Рейтинг по {field}",lines ,(241 ,196 ,15 )
        )
        await ctx .send (file =discord .File (img ,filename ="top.png" ))

    # ── МАГАЗИН / ПОКУПКА / ИНВЕНТАРЬ / ПЕРЕВОД ─────────────
    @commands .command (name ='shop',aliases =['магазин','maгaza'])
    async def shop (self ,ctx ):
        """Профессиональное меню магазина сервера"""
        img_buf =await self .bot .loop .run_in_executor (
        None ,generate_economy_bytes ,self ,ctx .author ,"shop"
        )
        file =discord .File (img_buf ,filename ="economy_card.png")
        view =EconomyView (self ,ctx .author ,current_cat ="shop")
        await ctx .send (file =file ,view =view )

    @commands .command (name ='buy',aliases =['satыnal','купить'])
    async def buy (self ,ctx ,*,item :str ):
        """Купить предмет из магазина"""
        key =item .lower ()
        det =ITEM_DETAILS .get (key )
        if not det :
            await ctx .send (f"Предмет не найден. Доступно: {', '.join(ITEM_DETAILS.keys())}")
            return 
        price =det ['price']
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if data ['balance']<price :
            await ctx .send (f"Недостаточно денег! Нужно ${price:,}.")
            return 
        data ['balance']-=price 
        if 'inventory' not in data : data ['inventory']=[]
        data ['inventory'].append (key )
        self ._log_tx (ctx .author .id ,data ,'Покупка',-price ,key )
        e =discord .Embed (title ="🛒 Покупка",color =_rarity_color (det ['rarity']),
        description =f"**{key.capitalize()}**\nЦена: ${price:,}\nРедкость: {det['rarity']}")
        await ctx .send (embed =e )

    @commands .command (name ='inventory',aliases =['envanter','инвентарь'])
    async def inventory (self ,ctx ,member :discord .Member =None ):
        """Профессиональное меню инвентаря"""
        member =member or ctx .author 
        img_buf =await self .bot .loop .run_in_executor (
        None ,generate_economy_bytes ,self ,member ,"inventory"
        )
        file =discord .File (img_buf ,filename ="economy_card.png")
        view =EconomyView (self ,member ,current_cat ="inventory")
        await ctx .send (file =file ,view =view )

    @commands .command (name ='transfer',aliases =['отправить','gonder'])
    async def transfer (self ,ctx ,member :discord .Member ,amount :int ):
        """Перевести деньги"""
        if member ==ctx .author or member .bot or amount <=0 :
            await ctx .send ("Неверный получатель или сумма.")
            return 
        data =self ._migrate (ctx .author .id ,self ._get (ctx .author .id ))
        if data ['balance']<amount :
            await ctx .send ("Недостаточно денег.")
            return 
        target =self ._get (member .id )
        data ['balance']-=amount 
        target ['balance']+=amount 
        self ._log_tx (ctx .author .id ,data ,'Перевод',-amount ,member .display_name )
        self ._log_tx (member .id ,target ,'Получено',amount ,ctx .author .display_name )
        e =discord .Embed (title ="💸 Перевод",color =0x2ECC71 ,
        description =f"{ctx.author.mention} → {member.mention}\n**${amount:,}**")
        await ctx .send (embed =e )




class EconomyCog (_EconomyExtra ,commands .Cog ):
    """Экономическая система"""

    def __init__ (self ,bot ):
        self .bot =bot 
        self .db =UserData ("economy")

    def _get (self ,user_id :int )->dict :
        data =self .db .get (user_id )
        if data is None :
            data =dict (DEFAULT_DATA )
            self .db .set (user_id ,data )
        return data 

    def _save (self ,user_id :int ,data :dict ):
        self .db .set (user_id ,data )

        # ── balance ──────────────────────────────────────────────────────────
    @commands .command (name ='balance',aliases =['bakiye','cюzdan','деньги'])
    async def balance (self ,ctx ,member :discord .Member =None ):
        """Показать баланс"""
        member =member or ctx .author 
        data =self ._get (member .id )
        data =self ._migrate (member .id ,data )

        job_name =data .get ('job')or 'Нет'
        pet =data .get ('equipped_pet')or 'Нет'
        rows =[
        ("Кошелёк",f"${data['balance']:,}"),
        ("Банк",f"${data['bank']:,}"),
        ("Итого",f"${data['balance']+data['bank']:,}"),
        ("Профессия",job_name .capitalize ()),
        ("Уровень работы",str (data .get ('job_level',1 ))),
        ("Питомец",pet .capitalize ()),
        ]
        img =await self .bot .loop .run_in_executor (
        None ,generate_eco_bytes ,"Баланс",f"Профиль • {member.display_name}",rows ,(16 ,185 ,129 )
        )
        await ctx .send (file =discord .File (img ,filename ="balance.png" ))

        # ── daily ────────────────────────────────────────────────────────────
    @commands .command (name ='daily',aliases =['gюnlюk','ежедневная'])
    async def daily (self ,ctx ):
        """Ежедневная награда со стриком"""
        data =self ._get (ctx .author .id )
        data =self ._migrate (ctx .author .id ,data )

        now =datetime .now ()
        streak =data .get ('daily_streak',0 )

        if data ['daily_last']:
            last =datetime .fromisoformat (data ['daily_last'])
            diff =now -last 
            if diff <timedelta (hours =24 ):
                remaining =timedelta (hours =24 )-diff 
                h =int (remaining .total_seconds ()/3600 )
                m =int ((remaining .total_seconds ()%3600 )/60 )
                embed =discord .Embed (
                title ="Ежедневная награда",
                description =f"Вы уже получили награду. Попробуйте через {h}ч {m}мин.\nСерия: **{streak} дн.**",
                color =discord .Color .dark_grey ()
                )
                await ctx .send (embed =embed )
                return 
            # стрик продолжается, если прошло <48ч
            if diff <timedelta (hours =48 ):
                streak +=1 
            else :
                streak =1 
        else :
            streak =1 

        base =random .randint (100 ,500 )
        bonus =int (base *(streak -1 )*0.1 )
        amount =base +bonus 
        data ['balance']+=amount 
        data ['daily_last']=now .isoformat ()
        data ['daily_streak']=streak 
        self ._log_tx (ctx .author .id ,data ,'Daily',amount ,f'серия {streak}' )

        embed =discord .Embed (
        title ="Ежедневная награда",
        description =f"Получено: **${amount:,}**\nСерия: **{streak} дн.** (+${bonus:,} бонус)",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )
        await ctx .send (embed =embed )

        # ── work ─────────────────────────────────────────────────────────────
        # ── beg ──────────────────────────────────────────────────────────────
    @commands .command (name ='beg',aliases =['dilenci'])
    async def beg (self ,ctx ):
        """Попросить деньги"""
        data =self ._get (ctx .author .id )

        if data ['beg_last']:
            last =datetime .fromisoformat (data ['beg_last'])
            diff =datetime .now ()-last 
            if diff <timedelta (minutes =15 ):
                m =int ((timedelta (minutes =15 )-diff ).total_seconds ()/60 )
                embed =discord .Embed (
                title ="Попрошайничество",
                description =f"Попробуйте через {m} мин.",
                color =discord .Color .dark_grey ()
                )
                await ctx .send (embed =embed )
                return 

        data ['beg_last']=datetime .now ().isoformat ()

        if random .random ()<0.3 :
            self ._save (ctx .author .id ,data )
            embed =discord .Embed (
            title ="Попрошайничество",
            description ="Никто не дал вам денег.",
            color =discord .Color .dark_grey ()
            )
            await ctx .send (embed =embed )
            return 

        amount =random .randint (10 ,100 )
        data ['balance']+=amount 
        self ._save (ctx .author .id ,data )

        embed =discord .Embed (
        title ="Попрошайничество",
        description =f"Получено: ${amount:,}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )
        await ctx .send (embed =embed )

        # ── rob ──────────────────────────────────────────────────────────────
    @commands .command (name ='rob',aliases =['soy'])
    async def rob (self ,ctx ,member :discord .Member ):
        """Ограбить пользователя"""
        if member ==ctx .author :
            await ctx .send ("Нельзя грабить себя.")
            return 
        if member .bot :
            await ctx .send ("Нельзя грабить ботов.")
            return 

        data =self ._get (ctx .author .id )
        target =self ._get (member .id )

        if target ['balance']<50 :
            await ctx .send (f"У {member.display_name} недостаточно денег.")
            return 

        if random .random ()<0.5 :
            penalty =min (data ['balance'],100 )
            data ['balance']-=penalty 
            self ._save (ctx .author .id ,data )
            embed =discord .Embed (
            title ="Ограбление",
            description =f"Вас поймали! Потеряно: ${penalty:,}",
            color =discord .Color .dark_grey ()
            )
            await ctx .send (embed =embed )
            return 

        amount =min (target ['balance'],random .randint (50 ,200 ))
        data ['balance']+=amount 
        target ['balance']-=amount 
        self ._save (ctx .author .id ,data )
        self ._save (member .id ,target )

        embed =discord .Embed (
        title ="Ограбление",
        description =f"Украдено у {member.display_name}: ${amount:,}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )
        await ctx .send (embed =embed )

        # ── deposit / withdraw ───────────────────────────────────────────────
    @commands .command (name ='deposit',aliases =['yatыr'])
    async def deposit (self ,ctx ,amount :int ):
        """Положить деньги в банк"""
        data =self ._get (ctx .author .id )
        if amount <=0 :
            await ctx .send ("Неверная сумма.")
            return 
        if amount >data ['balance']:
            await ctx .send ("Недостаточно денег в кошельке.")
            return 

        data ['balance']-=amount 
        data ['bank']+=amount 
        self ._save (ctx .author .id ,data )

        embed =discord .Embed (
        title ="Депозит",
        description =f"Положено в банк: ${amount:,}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )
        await ctx .send (embed =embed )

    @commands .command (name ='withdraw',aliases =['чek'])
    async def withdraw (self ,ctx ,amount :int ):
        """Снять деньги из банка"""
        data =self ._get (ctx .author .id )
        if amount <=0 :
            await ctx .send ("Неверная сумма.")
            return 
        if amount >data ['bank']:
            await ctx .send ("Недостаточно денег в банке.")
            return 

        data ['bank']-=amount 
        data ['balance']+=amount 
        self ._save (ctx .author .id ,data )

        embed =discord .Embed (
        title ="Снятие",
        description =f"Снято из банка: ${amount:,}",
        color =discord .Color .dark_grey (),
        timestamp =datetime .now ()
        )
        await ctx .send (embed =embed )

        # ── shop / buy / inventory ───────────────────────────────────────────
import io 
import os 
import math 
from PIL import Image ,ImageDraw ,ImageFont 
from cogs ._menu_bg import load_menu_bg 

WHITE =(255 ,255 ,255 )
BLACK =(20 ,20 ,25 )
EMERALD =(16 ,185 ,129 )
MUTED =(110 ,115 ,125 )
SS =4 

ROOT =os .path .join (os .path .dirname (__file__ ),'..')
FONTS =os .path .join (ROOT ,'assets','fonts')
BG_PATH =os .path .join (ROOT ,'assets','profile_bg_pro.jpg')
FONT_B =os .path .join (FONTS ,'Bold.ttf')
FONT_R =os .path .join (FONTS ,'Regular.ttf')


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


def _load_bg (w ,h ):
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


def _icon_wallet (d ,cx ,cy ,s ,w ,color ):
    bw ,bh =s *0.64 ,s *0.46 
    x0 ,y0 =cx -bw /2 ,cy -bh /2 
    x1 ,y1 =cx +bw /2 ,cy +bh /2 
    d .rounded_rectangle ((x0 ,y0 ,x1 ,y1 ),radius =bh *0.22 ,outline =color ,width =w )
    d .line ([(x0 ,y0 +bh *0.32 ),(x1 ,y0 +bh *0.32 )],fill =color ,width =max (1 ,int (w *0.7 )))
    r =s *0.085 
    ccx =x1 -r *1.5 
    ccy =y0 +bh *0.66 
    d .ellipse ((ccx -r ,ccy -r ,ccx +r ,ccy +r ),outline =color ,width =max (1 ,int (w *0.8 )))


def _icon_badge (diameter ,glyph_fn ,ring_color =BLACK ,ring_w =None ,icon_color =EMERALD ):
    ring_w =ring_w if ring_w is not None else max (2 ,diameter //22 )

    def draw (d ,scale ):
        size =diameter *scale 
        rw =ring_w *scale 
        r =size *0.22 
        d .rounded_rectangle ((rw /2 ,rw /2 ,size -rw /2 -1 ,size -rw /2 -1 ),
        radius =r ,fill =WHITE ,outline =ring_color ,width =rw )
        glyph_fn (d ,size /2 ,size /2 ,size *0.60 ,max (2 ,int (size *0.032 )),icon_color )

    return _ss_render (diameter ,diameter ,draw )


def _corner_bracket (size ,thickness ,length_ratio =0.35 ,color =EMERALD ):
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


def generate_economy_card (cog ,member :discord .Member ,category :str ="shop")->Image .Image :
    W =920 
    data =cog ._get (member .id )
    items =list (ITEM_DETAILS .items ())if category =="shop"else []
    if category =="inventory":
        items =[(itm ,0 )for itm in data .get ('inventory',[])]

    H =max (520 ,110 +max (3 ,len (items ))*104 +30 )
    bg =load_menu_bg (W ,H ,"emerald")
    d =ImageDraw .Draw (bg )

    # Header
    header_box =_rounded_panel (872 ,72 ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
    bg .alpha_composite (header_box ,(24 ,20 ))

    badge =_icon_badge (52 ,_icon_wallet ,ring_color =BLACK ,ring_w =2 ,icon_color =EMERALD )
    bg .alpha_composite (badge ,(36 ,30 ))

    title_map ={
    "shop":"МАГАЗИН СЕРВЕРА",
    "inventory":f"ИНВЕНТАРЬ • {member.display_name.upper()}",
    "balance":f"БАЛАНС • {member.display_name.upper()}"
    }
    title_text =title_map .get (category ,"ЭКОНОМИКА СЕРВЕРА")
    d .text ((100 ,26 ),title_text ,fill =BLACK ,font =_f (True ,24 ))
    d .text ((100 ,56 ),"ФИНАНСОВАЯ СИСТЕМА • ИНВЕНТАРЬ И ПРИВИЛЕГИИ",fill =MUTED ,font =_f (False ,15 ))

    pill =_rounded_panel (156 ,36 ,radius =10 ,fill =WHITE ,outline =EMERALD ,ow =2 )
    bg .alpha_composite (pill ,(724 ,38 ))
    d .text ((742 ,46 ),"ECONOMY v4.0",fill =EMERALD ,font =_f (True ,14 ))

    if category =="balance":
        box_w ,box_h =872 ,130 
        box1 =_rounded_panel (box_w ,box_h ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
        bg .alpha_composite (box1 ,(24 ,110 ))
        d .text ((60 ,135 ),"НАЛИЧНЫЙ БАЛАНС",fill =MUTED ,font =_f (False ,18 ))
        d .text ((60 ,170 ),f"{data['balance']:,} МОНЕТ".replace (","," "),fill =BLACK ,font =_f (True ,38 ))

        box2 =_rounded_panel (box_w ,box_h ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
        bg .alpha_composite (box2 ,(24 ,260 ))
        d .text ((60 ,285 ),"БАНКОВСКИЙ СЧЁТ",fill =MUTED ,font =_f (False ,18 ))
        d .text ((60 ,320 ),f"{data['bank']:,} МОНЕТ".replace (","," "),fill =EMERALD ,font =_f (True ,38 ))
    else :
        box_w ,box_h =872 ,92 
        gap_y =12 
        start_x ,start_y =24 ,108 
        display_items =items if items else [("Пусто",0 )]
        for idx ,(name ,det )in enumerate (display_items ):
            price =det .get ('price',0 )if isinstance (det ,dict )else det 
            bx =start_x 
            by =start_y +idx *(box_h +gap_y )

            box =_rounded_panel (box_w ,box_h ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
            bg .alpha_composite (box ,(bx ,by ))

            ibadge =_icon_badge (64 ,_icon_wallet ,ring_color =BLACK ,ring_w =2 ,icon_color =EMERALD )
            bg .alpha_composite (ibadge ,(bx +16 ,by +14 ))

            d .text ((bx +94 ,by +15 ),name .title (),fill =BLACK ,font =_f (True ,30 ))
            d .text ((bx +94 ,by +53 ),"Предмет магазина сервера"if price >0 else "В инвентаре",fill =MUTED ,font =_f (False ,22 ))

            if price >0 :
                p_txt =f"{price:,} МОНЕТ".replace (","," ")
                pw =len (p_txt )*14 
                d .text ((bx +box_w -24 -pw ,by +32 ),p_txt ,fill =EMERALD ,font =_f (True ,22 ))
            else :
                d .text ((bx +box_w -180 ,by +32 ),"В НАЛИЧИИ",fill =EMERALD ,font =_f (True ,22 ))

    br =_corner_bracket (40 ,4 ,color =EMERALD )
    bg .alpha_composite (br ,(6 ,6 ))
    bg .alpha_composite (br .rotate (270 ),(W -46 ,6 ))
    bg .alpha_composite (br .rotate (90 ),(6 ,H -46 ))
    bg .alpha_composite (br .rotate (180 ),(W -46 ,H -46 ))

    return bg 


def generate_economy_bytes (cog ,member :discord .Member ,category :str ="shop")->io .BytesIO :
    card =generate_economy_card (cog ,member ,category ).convert ('RGB')
    buf =io .BytesIO ()
    card .save (buf ,format ='PNG',optimize =True )
    buf .seek (0 )
    return buf 


# ═══════════════════════════════════════════════════════════════════
#  ГЕНЕРАТОР УНИВЕРСАЛЬНОЙ ЭКОНОМИЧЕСКОЙ КАРТОЧКИ (в стиле !help)
# ═══════════════════════════════════════════════════════════════════
def generate_eco_card (title :str ,subtitle :str ,rows :list ,accent :tuple =EMERALD )->Image .Image :
    """Универсальная карточка: заголовок + строки (name: value) + акцент.
    rows: список (label, value) пар."""
    W =920 
    H =max (520 ,130 +len (rows )*54 +30 )
    bg =load_menu_bg (W ,H ,"emerald")
    d =ImageDraw .Draw (bg )

    # Header
    header_box =_rounded_panel (872 ,72 ,radius =14 ,fill =WHITE ,outline =BLACK ,ow =2 )
    bg .alpha_composite (header_box ,(24 ,20 ))
    badge =_icon_badge (52 ,_icon_wallet ,ring_color =BLACK ,ring_w =2 ,icon_color =accent )
    bg .alpha_composite (badge ,(36 ,30 ))
    d .text ((100 ,26 ),title .upper (),fill =BLACK ,font =_f (True ,24 ))
    d .text ((100 ,56 ),subtitle .upper (),fill =MUTED ,font =_f (False ,15 ))

    pill =_rounded_panel (156 ,36 ,radius =10 ,fill =WHITE ,outline =accent ,ow =2 )
    bg .alpha_composite (pill ,(724 ,38 ))
    d .text ((742 ,46 ),"ECONOMY v5.0",fill =accent ,font =_f (True ,14 ))

    y =110 
    for label ,value in rows :
        box =_rounded_panel (872 ,46 ,radius =10 ,fill =WHITE ,outline =BLACK ,ow =1 )
        bg .alpha_composite (box ,(24 ,y ))
        d .text ((44 ,y +11 ),str (label ),fill =MUTED ,font =_f (False ,20 ))
        d .text ((460 ,y +10 ),str (value )[:38 ],fill =BLACK ,font =_f (True ,20 ))
        y +=56

    br =_corner_bracket (40 ,4 ,color =accent )
    bg .alpha_composite (br ,(6 ,6 ))
    bg .alpha_composite (br .rotate (270 ),(W -46 ,6 ))
    bg .alpha_composite (br .rotate (90 ),(6 ,H -46 ))
    bg .alpha_composite (br .rotate (180 ),(W -46 ,H -46 ))
    return bg


def generate_eco_bytes (title ,subtitle ,rows ,accent =EMERALD )->io .BytesIO :
    card =generate_eco_card (title ,subtitle ,rows ,accent ).convert ('RGB')
    buf =io .BytesIO ()
    card .save (buf ,format ='PNG',optimize =True )
    buf .seek (0 )
    return buf


class EconomySelect (discord .ui .Select ):
    def __init__ (self ,cog ,member ,current_cat ="shop"):
        self .cog =cog 
        self .member =member 
        options =[
        discord .SelectOption (
        label ="Магазин сервера",
        value ="shop",
        description ="Просмотр и покупка ролей и предметов",
        emoji ="🛍️",
        default =(current_cat =="shop")
        ),
        discord .SelectOption (
        label ="Инвентарь пользователя",
        value ="inventory",
        description ="Список купленных предметов в инвентаре",
        emoji ="🎒",
        default =(current_cat =="inventory")
        ),
        discord .SelectOption (
        label ="Баланс и банковский счёт",
        value ="balance",
        description ="Текущее финансовое состояние",
        emoji ="💰",
        default =(current_cat =="balance")
        )
        ]
        super ().__init__ (
        placeholder ="📂 Выберите раздел экономики...",
        options =options ,
        custom_id ="economy_select_v4_pro"
        )

    async def callback (self ,interaction :discord .Interaction ):
        await interaction .response .defer ()
        cat_id =self .values [0 ]
        img_buf =await interaction .client .loop .run_in_executor (
        None ,generate_economy_bytes ,self .cog ,interaction .user ,cat_id 
        )
        file =discord .File (img_buf ,filename ="economy_card.png")
        view =EconomyView (self .cog ,interaction .user ,current_cat =cat_id )
        await interaction .edit_original_response (embed =None ,attachments =[file ],view =view )


class EconomyView (discord .ui .View ):
    def __init__ (self ,cog ,member ,current_cat ="shop"):
        super ().__init__ (timeout =300 )
        self .add_item (EconomySelect (cog ,member ,current_cat =current_cat ))




async def setup (bot ):
    await bot .add_cog (EconomyCog (bot ))
    log .info ("EconomyCog загружен (database)")
