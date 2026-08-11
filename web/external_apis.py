"""
Vnesnie API — integraciya с servisami контроль
Reputaciya, NSFW, vredonosnie ссылка, avatari
"""
import aiohttp 
import json 
import os 
import hashlib 
from typing import Optional ,Dict ,List 
from datetime import datetime 


class ExternalAPIs :
    """Integraciya с vnesnimi API"""

    def __init__ (self ):
        self .session =None 
        self .api_keys =self ._load_api_keys ()

    def _load_api_keys (self )->Dict :
        """Загруз API anahtarve из konfiga"""
        config_file ='data/external_apis.json'
        if os .path .exists (config_file ):
            try :
                with open (config_file ,'r',encoding ='utf-8')as f :
                    return json .load (f )
            except Exception:
                pass 
        return {}

    async def _get_session (self )->aiohttp .ClientSession :
        """Получает aiohttp-сессию"""
        if self .session is None or self .session .closed :
            self .session =aiohttp .ClientSession ()
        return self .session 

    async def close (self ):
        """Zakrivaet sessiyu"""
        if self .session and not self .session .closed :
            await self .session .close ()

            # ─── КОНТРОЛЬ REPUTACII ─────────────────────────────────────────────

    async def check_user_reputation (self ,user_id :int ,username :str )->Dict :
        """Проверяет репутацию пользователя по внешним сервисам"""
        results ={
        'user_id':user_id ,
        'username':username ,
        'reputation_score':0 ,
        'flags':[],
        'sources':[]
        }

        # 1. Контроль с DiscordRep (если есть API anahtar)
        if 'discordrep_key'in self .api_keys :
            rep_data =await self ._check_discordrep (user_id )
            if rep_data :
                results ['reputation_score']+=rep_data .get ('reputation',0 )
                results ['flags'].extend (rep_data .get ('flags',[]))
                results ['sources'].append ('DiscordRep')

                # 2. Контроль с AntiFish (fising/skam)
        antifish_data =await self ._check_antifish (username )
        if antifish_data :
            if antifish_data .get ('match'):
                results ['flags'].append ('potential_scam')
                results ['reputation_score']-=50 
            results ['sources'].append ('AntiFish')

        return results 

    async def _check_discordrep (self ,user_id :int )->Optional [Dict ]:
        """Проверяет репутацию через DiscordRep API"""
        try :
            session =await self ._get_session ()
            url =f"https://discordrep.com/api/v4/user/{user_id}"
            headers ={'Authorization':self .api_keys ['discordrep_key']}

            async with session .get (url ,headers =headers ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()
                    return {
                    'reputation':data .get ('reputation',0 ),
                    'flags':data .get ('flags',[])
                    }
        except Exception as e :
            print (f"[EXTERNAL API] DiscordRep error: {e}")

        return None 

    async def _check_antifish (self ,username :str )->Optional [Dict ]:
        """Контроль ediyor с AntiFish API"""
        try :
            session =await self ._get_session ()
            url ="https://phish.sinking.yachts/v2/check"
            headers ={'Content-Type':'application/json'}
            payload ={'domain':username }

            async with session .post (url ,headers =headers ,json =payload ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()
                    return {'match':data .get ('match',False )}
        except Exception as e :
            print (f"[EXTERNAL API] AntiFish error: {e}")

        return None 

        # ─── NSFW DETEKCIYa ───────────────────────────────────────────────────

    async def check_nsfw (self ,image_url :str )->Dict :
        """Контроль ediyor izobrajenie на NSFW kontent"""
        results ={
        'image_url':image_url ,
        'is_nsfw':False ,
        'confidence':0.0 ,
        'categories':[]
        }

        # 1. Контроль с SightEngine (если есть API anahtar)
        if 'sightengine_user'in self .api_keys and 'sightengine_secret'in self .api_keys :
            nsfw_data =await self ._check_sightengine (image_url )
            if nsfw_data :
                results ['is_nsfw']=nsfw_data .get ('is_nsfw',False )
                results ['confidence']=nsfw_data .get ('confidence',0.0 )
                results ['categories']=nsfw_data .get ('categories',[])

                # 2. Fallback — контроль по hesu (если есть veritabanы)
        if not results ['is_nsfw']:
            hash_check =await self ._check_image_hash (image_url )
            if hash_check :
                results ['is_nsfw']=True 
                results ['confidence']=1.0 
                results ['categories']=['known_nsfw']

        return results 

    async def _check_sightengine (self ,image_url :str )->Optional [Dict ]:
        """Контроль ediyor с SightEngine API"""
        try :
            session =await self ._get_session ()
            url ="https://api.sightengine.com/1.0/check.json"
            params ={
            'models':'nudity-2.1,sexual-activity-2.0,offensive-2.0',
            'url':image_url ,
            'api_user':self .api_keys ['sightengine_user'],
            'api_secret':self .api_keys ['sightengine_secret']
            }

            async with session .get (url ,params =params ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()

                    # Analiz ediyoruz результат
                    nudity =data .get ('nudity',{})
                    sexual =data .get ('sexual_activity',{})
                    offensive =data .get ('offensive',{})

                    is_nsfw =(
                    nudity .get ('sexual_activity',0 )>0.5 or 
                    nudity .get ('sexual_display',0 )>0.5 or 
                    sexual .get ('sexual_activity',0 )>0.5 or 
                    offensive .get ('prob',0 )>0.7 
                    )

                    confidence =max (
                    nudity .get ('sexual_activity',0 ),
                    nudity .get ('sexual_display',0 ),
                    sexual .get ('sexual_activity',0 ),
                    offensive .get ('prob',0 )
                    )

                    categories =[]
                    if nudity .get ('sexual_activity',0 )>0.5 :
                        categories .append ('sexual_activity')
                    if nudity .get ('sexual_display',0 )>0.5 :
                        categories .append ('sexual_display')
                    if offensive .get ('prob',0 )>0.7 :
                        categories .append ('offensive')

                    return {
                    'is_nsfw':is_nsfw ,
                    'confidence':confidence ,
                    'categories':categories 
                    }
        except Exception as e :
            print (f"[EXTERNAL API] SightEngine error: {e}")

        return None 

    async def _check_image_hash (self ,image_url :str )->bool :
        """Контроль ediyor hes izobrajeniya в tabanda"""
        try :
        # Загруз izobrajenie
            session =await self ._get_session ()
            async with session .get (image_url ,timeout =10 )as resp :
                if resp .status ==200 :
                    image_data =await resp .read ()
                    image_hash =hashlib .md5 (image_data ).hexdigest ()

                    # Контроль ediyoruz в tabanda
                    hash_db_file ='data/nsfw_hashes.json'
                    if os .path .exists (hash_db_file ):
                        with open (hash_db_file ,'r',encoding ='utf-8')as f :
                            hash_db =json .load (f )
                            return image_hash in hash_db 
        except Exception as e :
            print (f"[EXTERNAL API] Hash check error: {e}")

        return False 

        # ─── ANALIZ SSILOK ──────────────────────────────────────────────────

    async def check_url_safety (self ,url :str )->Dict :
        """Контроль ediyor bezopasnost ссылка"""
        results ={
        'url':url ,
        'is_safe':True ,
        'threats':[],
        'reputation':'unknown',
        'sources':[]
        }

        # 1. Контроль с Google Safe Browsing (если есть API anahtar)
        if 'google_safebrowsing_key'in self .api_keys :
            gsb_data =await self ._check_google_safebrowsing (url )
            if gsb_data :
                if gsb_data .get ('threats'):
                    results ['is_safe']=False 
                    results ['threats']=gsb_data ['threats']
                results ['sources'].append ('Google Safe Browsing')

                # 2. Контроль с VirusTotal (если есть API anahtar)
        if 'virustotal_key'in self .api_keys :
            vt_data =await self ._check_virustotal (url )
            if vt_data :
                if vt_data .get ('malicious',0 )>0 :
                    results ['is_safe']=False 
                    results ['threats'].append (f"malicious:{vt_data['malicious']}")
                results ['reputation']=vt_data .get ('reputation','unknown')
                results ['sources'].append ('VirusTotal')

                # 3. Контроль с URLhaus
        urlhaus_data =await self ._check_urlhaus (url )
        if urlhaus_data :
            if urlhaus_data .get ('query_status')=='ok':
                results ['is_safe']=False 
                results ['threats'].append ('malware')
            results ['sources'].append ('URLhaus')

        return results 

    async def _check_google_safebrowsing (self ,url :str )->Optional [Dict ]:
        """Контроль ediyor с Google Safe Browsing API"""
        try :
            session =await self ._get_session ()
            api_url =f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={self.api_keys['google_safebrowsing_key']}"

            payload ={
            "client":{
            "clientId":"aether-bot",
            "clientVersion":"1.0"
            },
            "threatInfo":{
            "threatTypes":["MALWARE","SOCIAL_ENGINEERING","UNWANTED_SOFTWARE"],
            "platformTypes":["ANY_PLATFORM"],
            "threatEntryTypes":["URL"],
            "threatEntries":[{"url":url }]
            }
            }

            async with session .post (api_url ,json =payload ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()
                    matches =data .get ('matches',[])

                    if matches :
                        threats =[match .get ('threatType','unknown')for match in matches ]
                        return {'threats':threats }
                    else :
                        return {'threats':[]}
        except Exception as e :
            print (f"[EXTERNAL API] Google Safe Browsing error: {e}")

        return None 

    async def _check_virustotal (self ,url :str )->Optional [Dict ]:
        """Контроль ediyor с VirusTotal API"""
        try :
            session =await self ._get_session ()

            # До alыyoruz rapor
            url_id =hashlib .sha256 (url .encode ()).hexdigest ()
            api_url =f"https://www.virustotal.com/api/v3/urls/{url_id}"
            headers ={'x-apikey':self .api_keys ['virustotal_key']}

            async with session .get (api_url ,headers =headers ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()
                    stats =data .get ('data',{}).get ('attributes',{}).get ('last_analysis_stats',{})

                    return {
                    'malicious':stats .get ('malicious',0 ),
                    'suspicious':stats .get ('suspicious',0 ),
                    'reputation':data .get ('data',{}).get ('attributes',{}).get ('reputation','unknown')
                    }
        except Exception as e :
            print (f"[EXTERNAL API] VirusTotal error: {e}")

        return None 

    async def _check_urlhaus (self ,url :str )->Optional [Dict ]:
        """Контроль ediyor с URLhaus API"""
        try :
            session =await self ._get_session ()
            api_url ="https://urlhaus-api.abuse.ch/v1/url/"
            payload ={'url':url }

            async with session .post (api_url ,data =payload ,timeout =10 )as resp :
                if resp .status ==200 :
                    data =await resp .json ()
                    return data 
        except Exception as e :
            print (f"[EXTERNAL API] URLhaus error: {e}")

        return None 


        # Kюresel пример
_external_apis =None 

async def get_external_apis ()->ExternalAPIs :
    """Получает глобальный экземпляр ExternalAPIs"""
    global _external_apis 
    if _external_apis is None :
        _external_apis =ExternalAPIs ()
    return _external_apis 
