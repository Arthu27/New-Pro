"""
Samoobucenie — AI ucitsya на svoih ошибка ve uspehah
Analiz geri ссылки, korrektirovka povedeniya
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict


class SelfLearning:
    """Система samoeğitimi AI"""
    
    def __init__(self):
        self.feedback_log = []  # Loglar geri ссылки
        self.learned_patterns = {}  # Viucennie kalıplar
        self.mistakes = []  # Ошибки AI
        self.successes = []  # Uspesnie cevaplar
        
        # Загруз veriler
        self._load_data()
    
    def record_feedback(
        self,
        user_message: str,
        ai_response: str,
        feedback_type: str,
        feedback_details: Dict = None
    ):
        """Сохран obratnuyu ссылка"""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'ai_response': ai_response,
            'feedback_type': feedback_type,  # 'positive', 'negative', 'correction'
            'details': feedback_details or {}
        }
        
        self.feedback_log.append(entry)
        
        # Ограничиваем log
        if len(self.feedback_log) > 1000:
            self.feedback_log = self.feedback_log[-1000:]
        
        # Analiz ediyoruz ve obucaemsya
        self._analyze_and_learn(entry)
        
        # Сохран
        self._save_data()
    
    def record_mistake(
        self,
        user_message: str,
        ai_response: str,
        correct_response: str,
        mistake_type: str
    ):
        """Сохран ошибка AI"""
        mistake = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'wrong_response': ai_response,
            'correct_response': correct_response,
            'mistake_type': mistake_type  # 'wrong_info', 'inappropriate', 'misunderstanding'
        }
        
        self.mistakes.append(mistake)
        
        # Ограничиваем
        if len(self.mistakes) > 500:
            self.mistakes = self.mistakes[-500:]
        
        # Ucimsya на osibke
        self._learn_from_mistake(mistake)
        
        # Сохран
        self._save_data()
    
    def record_success(
        self,
        user_message: str,
        ai_response: str,
        success_type: str
    ):
        """Сохран uspesniy ответ"""
        success = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_message': user_message,
            'ai_response': ai_response,
            'success_type': success_type  # 'helpful', 'accurate', 'empathetic'
        }
        
        self.successes.append(success)
        
        # Ограничиваем
        if len(self.successes) > 500:
            self.successes = self.successes[-500:]
        
        # Ucimsya на uspehe
        self._learn_from_success(success)
        
        # Сохран
        self._save_data()
    
    def _analyze_and_learn(self, feedback: Dict):
        """Analiz ediyor obratnuyu ссылка ve obucaetsya"""
        feedback_type = feedback['feedback_type']
        
        if feedback_type == 'negative':
            # Negativnaya obratnaya ссылка — ucimsya izbegat
            self._learn_from_mistake({
                'user_message': feedback['user_message'],
                'wrong_response': feedback['ai_response'],
                'correct_response': feedback.get('details', {}).get('suggested_response', ''),
                'mistake_type': 'negative_feedback'
            })
        
        elif feedback_type == 'positive':
            # Pozitivnaya obratnaya ссылка — zapominaem ne работает
            self._learn_from_success({
                'user_message': feedback['user_message'],
                'ai_response': feedback['ai_response'],
                'success_type': 'positive_feedback'
            })
        
        elif feedback_type == 'correction':
            # Korrektirovka — zapominaem правил ответ
            correct_response = feedback.get('details', {}).get('correction', '')
            if correct_response:
                self._learn_from_mistake({
                    'user_message': feedback['user_message'],
                    'wrong_response': feedback['ai_response'],
                    'correct_response': correct_response,
                    'mistake_type': 'correction'
                })
    
    def _learn_from_mistake(self, mistake: Dict):
        """Ucitsya на osibke"""
        user_msg = mistake['user_message'].lower()
        wrong_resp = mistake['wrong_response']
        correct_resp = mistake.get('correct_response', '')
        mistake_type = mistake['mistake_type']
        
        # Удалить anahtar kelimeler
        keywords = self._extract_keywords(user_msg)
        
        # Zapominaem pattern
        pattern_key = f"avoid_{mistake_type}"
        if pattern_key not in self.learned_patterns:
            self.learned_patterns[pattern_key] = []
        
        self.learned_patterns[pattern_key].append({
            'keywords': keywords,
            'wrong_response': wrong_resp[:200],  # Ограничиваем uzunluğu
            'correct_response': correct_resp[:200] if correct_resp else '',
            'timestamp': mistake['timestamp']
        })
        
        # Ограничиваем kalıplar
        if len(self.learned_patterns[pattern_key]) > 100:
            self.learned_patterns[pattern_key] = self.learned_patterns[pattern_key][-100:]
    
    def _learn_from_success(self, success: Dict):
        """Ucitsya на uspehe"""
        user_msg = success['user_message'].lower()
        ai_resp = success['ai_response']
        success_type = success['success_type']
        
        # Удалить anahtar kelimeler
        keywords = self._extract_keywords(user_msg)
        
        # Zapominaem pattern
        pattern_key = f"repeat_{success_type}"
        if pattern_key not in self.learned_patterns:
            self.learned_patterns[pattern_key] = []
        
        self.learned_patterns[pattern_key].append({
            'keywords': keywords,
            'response': ai_resp[:200],  # Ограничиваем uzunluğu
            'timestamp': success['timestamp']
        })
        
        # Ограничиваем kalıplar
        if len(self.learned_patterns[pattern_key]) > 100:
            self.learned_patterns[pattern_key] = self.learned_patterns[pattern_key][-100:]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Izvlekaet anahtar kelimeler den metina"""
        import re
        
        # Удален stop-kelimeler
        stop_words = {
            've', 'в', 'на', 'с', 'по', 'для', 'den', 'do', 'den', 'e', 'u',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'
        }
        
        # Удалить kelimeler
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filtreliyoruz
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        # Удален dublikati
        return list(set(keywords))
    
    def get_learning_context(self, user_message: str) -> str:
        """Alıyor bağlam eğitimi для prompta"""
        user_msg_lower = user_message.lower()
        keywords = self._extract_keywords(user_msg_lower)
        
        if not keywords:
            return ""
        
        context_parts = []
        
        # Arıyoruz pohojie kalıplar
        for pattern_type, patterns in self.learned_patterns.items():
            matching_patterns = []
            
            for pattern in patterns[-20:]:  # В конец 20
                # Контроль ediyoruz peresecenie anahtarevih slov
                pattern_keywords = set(pattern['keywords'])
                message_keywords = set(keywords)
                intersection = pattern_keywords & message_keywords
                
                if len(intersection) >= 2:  # Minimum 2 obsih kelimeler
                    matching_patterns.append(pattern)
            
            if matching_patterns:
                if pattern_type.startswith('avoid_'):
                    # Kalıplar kotorih необходимо izbegat
                    context_parts.append(
                        f"\n⚠️ IZBEGAY podobnih cevapların (idi ошибки):\n"
                    )
                    for p in matching_patterns[:3]:  # Maksimum 3
                        if p.get('wrong_response'):
                            context_parts.append(f"- {p['wrong_response']}\n")
                        if p.get('correct_response'):
                            context_parts.append(f"+ Vmesto: {p['correct_response']}\n")
                
                elif pattern_type.startswith('repeat_'):
                    # Kalıplar kotorie необходимо povtoryat
                    context_parts.append(
                        f"\n✅ ISPOLZUY podobnie cevaplar (idi uspesni):\n"
                    )
                    for p in matching_patterns[:3]:  # Maksimum 3
                        if p.get('response'):
                            context_parts.append(f"- {p['response']}\n")
        
        return ''.join(context_parts)
    
    def get_learning_stats(self) -> Dict:
        """Alıyor istatistiği eğitimi"""
        return {
            'total_feedback': len(self.feedback_log),
            'total_mistakes': len(self.mistakes),
            'total_successes': len(self.successes),
            'learned_patterns': sum(len(p) for p in self.learned_patterns.values()),
            'pattern_types': list(self.learned_patterns.keys()),
            'recent_mistakes': self.mistakes[-5:] if self.mistakes else [],
            'recent_successes': self.successes[-5:] if self.successes else [],
        }
    
    def _load_data(self):
        """Загруз veriler den dosyaya"""
        data_file = 'data/ai_learning.json'
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.feedback_log = data.get('feedback_log', [])
                    self.learned_patterns = data.get('learned_patterns', {})
                    self.mistakes = data.get('mistakes', [])
                    self.successes = data.get('successes', [])
            except:
                pass
    
    def _save_data(self):
        """Сохран veriler в dosya"""
        try:
            os.makedirs('data', exist_ok=True)
            data_file = 'data/ai_learning.json'
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'feedback_log': self.feedback_log[-200:],  # Сохран только son 200
                    'learned_patterns': self.learned_patterns,
                    'mistakes': self.mistakes[-100:],  # В конец 100
                    'successes': self.successes[-100:],  # В конец 100
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SELF LEARNING] Ошибка sohraneniya: {e}")


# Küresel пример
_self_learning = None

def get_self_learning() -> SelfLearning:
    """Alıyor küresel пример SelfLearning"""
    global _self_learning
    if _self_learning is None:
        _self_learning = SelfLearning()
    return _self_learning
