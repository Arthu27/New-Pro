"""
Süper-umniy analiz жалоба на оскорбление
Glubokiy analiz istorii, reputacii, контекстn, dokazatelstv
"""
import discord
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


class ComplaintAnalyzer:
    """Prodvinutiy analizör жалоба"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.toxicity_patterns = [
            # Russkie оскорбление
            r'\b(tvar|ublyudok|mraz|svoloc|aptal|aptal|aptal|aptal|durak|dura)\b',
            r'\b(posel|idi)\s*(на|в)\s*(aptal|каждый|pizdu|jopu)\b',
            r'\b(suka|blyat|blya|nahuy|pizdec|ebat|ebaniy|ebanutiy)\b',
            r'\b(aptal|huya|hue|pizd|eb|blyad|mudak|gandon)\w*',
            # Tureckie оскорбление
            r'\b(amk|amq|orospu|piç|yarrak|siktir|göt|amcık)\b',
            r'\b(ananı|bacını|karını|kızını)\s*(sikeyim|becereyim)\b',
            # Tehditler
            r'\b(ubyu|ubit|zaryaju|zastrelyu|povesu)\b',
            r'\b(öldüreceğim|öldür|gebert|vuracağım)\b',
        ]
    
    async def analyze_complaint(
        self,
        guild: discord.Guild,
        complainant_id: int,
        accused_id: int,
        complaint_text: str,
        provided_messages: List[str] = None
    ) -> Dict:
        """
        Polniy analiz жалобы
        
        Returns:
            {
                'verdict': 'GUILTY' | 'INNOCENT' | 'MUTUAL' | 'FALSE_COMPLAINT' | 'UNCLEAR',
                'confidence': 0-100,
                'evidence': {...},
                'recommendation': {...},
                'analysis': str
            }
        """
        # 1. Topluyoruz информация о каждый ikisi пользователь
        complainant_info = await self._get_user_profile(guild, complainant_id)
        accused_info = await self._get_user_profile(guild, accused_id)
        
        # 2. Analiz ediyoruz история сообщение
        message_history = await self._get_message_history(guild, complainant_id, accused_id)
        
        # 3. Контроль ediyoruz itibarı каждый ikisi
        complainant_rep = await self._get_reputation(guild, complainant_id)
        accused_rep = await self._get_reputation(guild, accused_id)
        
        # 4. Analiz ediyoruz predostavlennie сообщения
        provided_analysis = self._analyze_provided_messages(provided_messages or [])
        
        # 5. Контроль ediyoruz bağlam (bila mı provokasyon)
        context_analysis = await self._analyze_context(guild, message_history, complainant_id, accused_id)
        
        # 6. Ocenivaem ciddiyet
        severity = self._assess_severity(provided_analysis, context_analysis)
        
        # 7. Создан karar
        verdict_data = self._form_verdict(
            complainant_info, accused_info,
            complainant_rep, accused_rep,
            provided_analysis, context_analysis,
            severity
        )
        
        return verdict_data
    
    async def _get_user_profile(self, guild: discord.Guild, user_id: int) -> Dict:
        """Al profil пользователь"""
        member = guild.get_member(user_id)
        if not member:
            return {'found': False, 'id': user_id}
        
        return {
            'found': True,
            'id': user_id,
            'name': member.display_name,
            'joined_at': member.joined_at.isoformat() if member.joined_at else None,
            'days_on_sunucu': (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0,
            'role': [role.name for role in member.roles if role.name != "@everyone"],
            'is_moderator': member.guild_permissions.kick_members or member.guild_permissions.ban_members,
            'account_age': (datetime.now(timezone.utc) - member.created_at).days,
        }
    
    async def _get_message_history(
        self,
        guild: discord.Guild,
        user1_id: int,
        user2_id: int,
        limit: int = 100
    ) -> List[Dict]:
        """Al история сообщение mejdu dvumya пользователь"""
        from cogs.logs import _msg_cache
        
        # Arıyoruz сообщения den каждый ikisi в kese
        messages = []
        for msg in _msg_cache.values():
            if msg.get('author_id') in [user1_id, user2_id]:
                messages.append(msg)
        
        # Sortiruem по время
        messages.sort(key=lambda x: x.get('timestamp', ''))
        
        # Ограничиваем
        return messages[-limit:]
    
    async def _get_reputation(self, guild: discord.Guild, user_id: int) -> Dict:
        """Al itibarı пользователь"""
        from cogs.warnings import load_warnings
        
        warnings_data = load_warnings()
        guild_warnings = warnings_data.get(str(guild.id), {}).get(str(user_id), [])
        
        # Scitaem предупреждения для raznie periodi
        now = datetime.now(timezone.utc)
        warnings_7d = 0
        warnings_30d = 0
        warnings_total = len(guild_warnings)
        
        for warn in guild_warnings:
            warn_date_raw = warn.get('timestamp', now.isoformat())
            try:
                warn_date = datetime.fromisoformat(warn_date_raw)
            except (ValueError, TypeError):
                continue
            # Если naive — делаем aware (UTC)
            if warn_date.tzinfo is None:
                warn_date = warn_date.replace(tzinfo=timezone.utc)
            days_ago = (now - warn_date).days
            
            if days_ago <= 7:
                warnings_7d += 1
            if days_ago <= 30:
                warnings_30d += 1
        
        # Контроль ediyoruz история banov/mutov
        mod_data_file = 'data/mod_data.json'
        mod_history = []
        if os.path.exists(mod_data_file):
            try:
                with open(mod_data_file, 'r', encoding='utf-8') as f:
                    mod_data = json.load(f)
                    guild_mods = mod_data.get('cases', {}).get(str(guild.id), [])
                    mod_history = [
                        case for case in guild_mods
                        if case.get('user_id') == str(user_id)
                    ]
            except:
                pass
        
        bans = sum(1 for case in mod_history if case.get('action') == 'ban')
        mutes = sum(1 for case in mod_history if case.get('action') in ['timeout', 'mute'])
        
        return {
            'warnings_total': warnings_total,
            'warnings_7d': warnings_7d,
            'warnings_30d': warnings_30d,
            'bans': bans,
            'mutes': mutes,
            'recent_warnings': guild_warnings[-5:] if guild_warnings else [],
        }
    
    def _analyze_provided_messages(self, messages: List[str]) -> Dict:
        """Analiz ediyor predostavlennie сообщения"""
        import re
        
        toxicity_count = 0
        threats_count = 0
        complainer_toxic = 0
        accused_toxic = 0
        
        for msg in messages:
            msg_lower = msg.lower()
            
            # Контроль ediyoruz на toksisite
            is_toxic = any(
                re.search(pattern, msg_lower, re.IGNORECASE)
                for pattern in self.toxicity_patterns
            )
            
            if is_toxic:
                toxicity_count += 1
                
                # Belirliyoruz кто toksicit
                if '[ЖАЛОБА EDEN' in msg or '[ЖАЛОБА' in msg:
                    complainer_toxic += 1
                elif '[ЖАЛОБА EDİLEN' in msg or '[OBVINYaEMIY' in msg:
                    accused_toxic += 1
            
            # Контроль ediyoruz на tehditler
            threat_patterns = [r'\b(ubyu|ubit|zaryaju|öldüreceğim|öldür)\b']
            if any(re.search(p, msg_lower, re.IGNORECASE) for p in threat_patterns):
                threats_count += 1
        
        return {
            'total_messages': len(messages),
            'toxic_messages': toxicity_count,
            'threats': threats_count,
            'complainer_toxic': complainer_toxic,
            'accused_toxic': accused_toxic,
            'mutual_toxicity': complainer_toxic > 0 and accused_toxic > 0,
        }
    
    async def _analyze_context(
        self,
        guild: discord.Guild,
        message_history: List[Dict],
        complainant_id: int,
        accused_id: int
    ) -> Dict:
        """Analiz ediyor bağlam разговор"""
        
        # Arıyoruz сообщения pryamo pered incidentom
        context_messages = []
        for msg in message_history[-20:]:  # В конец 20
            if msg.get('author_id') in [complainant_id, accused_id]:
                context_messages.append(msg)
        
        # Контроль ediyoruz bila mı provokasyon
        provocation_indicators = [
            'kendi takoy',
            'otvecu',
            'a sen кто',
            'zatknis',
            'kapa çeneni',
            'sen кто',
        ]
        
        provocation_count = 0
        for msg in context_messages:
            content = msg.get('content', '').lower()
            if any(indicator in content for indicator in provocation_indicators):
                provocation_count += 1
        
        # Контроль ediyoruz кто nacal
        first_aggressor = None
        for msg in context_messages:
            content = msg.get('content', '').lower()
            is_toxic = any(
                re.search(pattern, content, re.IGNORECASE)
                for pattern in self.toxicity_patterns
            )
            if is_toxic:
                first_aggressor = msg.get('author_id')
                break
        
        return {
            'context_messages_count': len(context_messages),
            'provocation_indicators': provocation_count,
            'first_aggressor': first_aggressor,
            'had_provocation': provocation_count > 0,
        }
    
    def _assess_severity(self, provided_analysis: Dict, context_analysis: Dict) -> str:
        """Ocenivaet ciddiyet naruseniya"""
        
        # Tehditler — каждый время kriticno
        if provided_analysis['threats'] > 0:
            return 'CRITICAL'
        
        # Очень toksicnih сообщение
        if provided_analysis['toxic_messages'] >= 5:
            return 'HIGH'
        
        # Neskolko toksicnih сообщение
        if provided_analysis['toxic_messages'] >= 2:
            return 'MEDIUM'
        
        # Bir toksicnoe сообщение
        if provided_analysis['toxic_messages'] == 1:
            return 'LOW'
        
        return 'NONE'
    
    def _form_verdict(
        self,
        complainant_info: Dict,
        accused_info: Dict,
        complainant_rep: Dict,
        accused_rep: Dict,
        provided_analysis: Dict,
        context_analysis: Dict,
        severity: str
    ) -> Dict:
        """Создан finalniy karar"""
        
        # Belirliyoruz karar
        if provided_analysis['mutual_toxicity']:
            verdict = 'MUTUAL'
            confidence = 85
        elif provided_analysis['complainer_toxic'] > provided_analysis['accused_toxic']:
            verdict = 'FALSE_COMPLAINT'
            confidence = 80
        elif provided_analysis['accused_toxic'] > 0:
            verdict = 'GUILTY'
            confidence = 75
        elif provided_analysis['toxic_messages'] == 0:
            verdict = 'INNOCENT'
            confidence = 70
        else:
            verdict = 'UNCLEAR'
            confidence = 40
        
        # Korrektiruem доверие на osnove reputacii
        if accused_rep['warnings_7d'] >= 3:
            if verdict == 'GUILTY':
                confidence += 10
        elif complainant_rep['warnings_7d'] >= 3:
            if verdict == 'FALSE_COMPLAINT':
                confidence += 10
        
        # Создан предложение
        recommendation = self._form_recommendation(
            verdict, severity, accused_rep, complainant_rep
        )
        
        # Создан analiz
        analysis = self._form_analysis_text(
            complainant_info, accused_info,
            provided_analysis, context_analysis,
            verdict, confidence, severity
        )
        
        return {
            'verdict': verdict,
            'confidence': min(confidence, 100),
            'severity': severity,
            'evidence': {
                'toxic_messages': provided_analysis['toxic_messages'],
                'threats': provided_analysis['threats'],
                'mutual_toxicity': provided_analysis['mutual_toxicity'],
                'accused_warnings': accused_rep['warnings_total'],
                'complainer_warnings': complainant_rep['warnings_total'],
                'had_provocation': context_analysis['had_provocation'],
            },
            'recommendation': recommendation,
            'analysis': analysis,
        }
    
    def _form_recommendation(
        self,
        verdict: str,
        severity: str,
        accused_rep: Dict,
        complainant_rep: Dict
    ) -> Dict:
        """Создан предложение для модератор"""
        
        if verdict == 'GUILTY':
            if severity == 'CRITICAL':
                return {
                    'action': 'BAN',
                    'duration': None,  # Permanent
                    'reason': 'Tehditler + оскорбление'
                }
            elif severity == 'HIGH':
                if accused_rep['warnings_total'] >= 3:
                    return {
                        'action': 'BAN',
                        'duration': 7 * 24 * 60,  # 7 день
                        'reason': 'Sistemticeskie оскорбление'
                    }
                else:
                    return {
                        'action': 'MUTE',
                        'duration': 24 * 60,  # 24 saat
                        'reason': 'Mnojestvennie оскорбление'
                    }
            elif severity == 'MEDIUM':
                return {
                    'action': 'MUTE',
                    'duration': 4 * 60,  # 4 saat
                    'reason': 'Hakaret'
                }
            else:  # LOW
                return {
                    'action': 'WARN',
                    'duration': None,
                    'reason': 'Oskorblenie'
                }
        
        elif verdict == 'MUTUAL':
            return {
                'action': 'MUTE_BOTH',
                'duration': 2 * 60,  # 2 saat oboim
                'reason': 'Vzaimnie оскорбление'
            }
        
        elif verdict == 'FALSE_COMPLAINT':
            return {
                'action': 'WARN_COMPLAINANT',
                'duration': None,
                'reason': 'Lojnaya жалоба'
            }
        
        else:  # INNOCENT or UNCLEAR
            return {
                'action': 'NO_ACTION',
                'duration': None,
                'reason': 'Yetersiz dokazatelstv'
            }
    
    def _form_analysis_text(
        self,
        complainant_info: Dict,
        accused_info: Dict,
        provided_analysis: Dict,
        context_analysis: Dict,
        verdict: str,
        confidence: int,
        severity: str
    ) -> str:
        """Создан metinoviy analiz"""
        
        analysis_parts = [
            f"## Analiz жалобы\n",
            f"**Karar:** {verdict} (доверие: {confidence}%)\n",
            f"**Ciddiyet:** {severity}\n\n",
            
            f"### Dokazatelstva:\n",
            f"- Toksicnih сообщение: {provided_analysis['toxic_messages']}\n",
            f"- Ugroz: {provided_analysis['threats']}\n",
            f"- Vzaimnaya toksisite: {'Evet' if provided_analysis['mutual_toxicity'] else 'Yok'}\n\n",
            
            f"### Bağlam:\n",
            f"- Bila provokasyon: {'Evet' if context_analysis['had_provocation'] else 'Yok'}\n",
            f"- Ilk agressor: {context_analysis.get('first_aggressor', 'Не opredelen')}\n\n",
        ]
        
        return ''.join(analysis_parts)
