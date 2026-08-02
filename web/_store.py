"""
Центрk performans yardimcisi.
- atomic_write_json: gecici dosya + os.replace ile atomik написатьma (yaris статусu нет, indent нет).
- read_json: dosya yoksa None; JSON bozuksa None (uyarхорошо bir key написатьdirir).
- ttl_cache: basit TTL onbellegi; sыk okunan JSON dosyalari icin.
- PeriodicFlush: лог написатьimini toplu (batch) ve periyodik yapar; onyuzde bloklama нет.
- make_etag: JSON dump etmeden быстрый (weak) ETag uretir.
"""
import json 
import os 
import time 
import threading 
import hashlib 
from collections import OrderedDict 


# ── Atomic file I/O ───────────────────────────────────────────────────────────
def atomic_write_json (path ,data ,ensure_ascii =False ):
    """Написатьarken once gecici dosyaya написать, после os.replace ile atomik tasi."""
    tmp =f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    try :
        os .makedirs (os .path .dirname (path )or '.',exist_ok =True )
        with open (tmp ,'w',encoding ='utf-8')as fp :
            json .dump (data ,fp ,ensure_ascii =False )
            fp .flush ()
            try :
                os .fsync (fp .fileno ())
            except OSError :
                pass 
        os .replace (tmp ,path )
    except Exception :
        try :
            if os .path .exists (tmp ):
                os .remove (tmp )
        except OSError :
            pass 
        raise 


def read_json (path ,default =None ):
    """Guvenli okuma. Ошибка статусunda default dondurur."""
    if not os .path .exists (path ):
        return default 
    try :
        with open (path ,'r',encoding ='utf-8')as fp :
            return json .load (fp )
    except Exception :
        return default 


        # ── TTL cache ────────────────────────────────────────────────────────────────
class _TTLCache :
    def __init__ (self ,maxsize =256 ):
        self ._d =OrderedDict ()
        self ._lock =threading .RLock ()
        self ._max =maxsize 

    def get (self ,key ,ttl ):
        with self ._lock :
            entry =self ._d .get (key )
            if entry is None :
                return None 
            value ,expires =entry 
            if expires <time .time ():
                self ._d .pop (key ,None )
                return None 
                # LRU: eriудалитьeni basa получить
            self ._d .move_to_end (key )
            return value 

    def set (self ,key ,value ,ttl ):
        with self ._lock :
            self ._d [key ]=(value ,time .time ()+ttl )
            self ._d .move_to_end (key )
            while len (self ._d )>self ._max :
                self ._d .popitem (last =False )

    def invalidate (self ,key ):
        with self ._lock :
            self ._d .pop (key ,None )

    def clear (self ):
        with self ._lock :
            self ._d .clear ()


_cache =_TTLCache (maxsize =512 )


def cached_read_json (path ,ttl =5.0 ,default =None ):
    """Dosyayi TTL onbellдобавить. Длительность doldugunda новыйden okur."""
    if ttl <=0 :
        return read_json (path ,default )
    key =('json',os .path .abspath (path ),os .path .getmtime (path )if os .path .exists (path )else 0 )
    v =_cache .get (key ,ttl )
    if v is None :
        v =read_json (path ,default )
        if v is not None :
            _cache .set (key ,v ,ttl )
    return v 


def invalidate_path (path ):
    """Belirli bir dosya ile ilgili cache girdilerini очистить."""
    abspath =os .path .abspath (path )
    with _cache ._lock :
        for k in list (_cache ._d .keys ()):
            if k and k [0 ]=='json'and k [1 ]==abspath :
                _cache ._d .pop (k ,None )


                # ── ETag helpers (saf, Flask'siz) ─────────────────────────────────────────────
def make_etag (payload ):
    """Слабый (weak) ETag создать. JSON dump etmeden быстрый sekilde."""
    try :
        h =hashlib .md5 ()
        if isinstance (payload ,(list ,tuple )):
            for item in payload :
                _etag_hash_item (h ,item )
        elif isinstance (payload ,dict ):
            for k in sorted (payload .keys ()):
                _etag_hash_item (h ,(k ,payload [k ]))
        else :
            _etag_hash_item (h ,payload )
            # Werkzeug'un set_etag'i "W/<etag>" или "<etag>" seklinde принять eder;
            # tirnak icermeyen weak prefix kullaniyoruz.
        return 'W/'+h .hexdigest ()
    except Exception :
        return None 


def _etag_hash_item (h ,item ):
    try :
        h .update (repr (item ).encode ('utf-8','replace'))
        h .update (b'|')
    except Exception :
        h .update (str (type (item )).encode ())


        # ── Periodic flush (panel_logs icin) ──────────────────────────────────────────
class PeriodicFlush :
    """append() быстрый, настоящий dosya написатьimini arka planda toplu yapar."""
    def __init__ (self ,path ,flush_interval =5.0 ,max_entries =1000 ,batch_threshold =50 ):
        self ._path =path 
        self ._interval =flush_interval 
        self ._max =max_entries 
        self ._threshold =batch_threshold 
        self ._buf =[]
        self ._lock =threading .Lock ()
        self ._cv =threading .Condition (self ._lock )
        self ._stop =False 
        self ._thread =threading .Thread (target =self ._loop ,daemon =True ,name ='PeriodicFlush')
        self ._thread .start ()

    def append (self ,entry ):
        with self ._cv :
            self ._buf .append (entry )
            if len (self ._buf )>=self ._threshold :
                self ._cv .notify_all ()

    def maybe_notify (self ):
        """Tetiklemeli как uyandirma (esik degilse de doluysa bildir)."""
        with self ._cv :
            if self ._buf :
                self ._cv .notify_all ()

    def _loop (self ):
        while not self ._stop :
            with self ._cv :
                self ._cv .wait (timeout =self ._interval )
                if self ._stop :
                    break 
                items ,self ._buf =self ._buf ,[]
            if items :
                self ._flush (items )

    def flush_now (self ):
        with self ._lock :
            items ,self ._buf =self ._buf ,[]
        if items :
            self ._flush (items )

    def _flush (self ,items ):
        try :
            existing =read_json (self ._path ,default =[])
            if not isinstance (existing ,list ):
                existing =[]
            existing .extend (items )
            existing =existing [-self ._max :]
            atomic_write_json (self ._path ,existing )
            invalidate_path (self ._path )
        except Exception :
        # Sessizce yut; loglayici hatayi paneli kiramaz
            pass 

    def shutdown (self ):
        with self ._lock :
            self ._stop =True 
            self ._cv .notify_all ()
        try :
            self ._thread .join (timeout =2 )
        except Exception :
            pass 
        self .flush_now ()
