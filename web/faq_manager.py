"""
FAQ / Öğrenme Система — Dosya tayasaklanmış

Dosyalar:
  data/learned_faq.json      — Öğrenilen soru-cevaplar (bot использовать)
  data/unknown_questions.json — Cevaplanamayan sorular (sen inceliyorsun)

Управление:
  - learned_faq.json'u верно redaktirovatyebilirsin
  - unknown_questions.json'daki вопросы inceleyip learned_faq.json'a addyebilirsin
  - Bir FAQ'ı devre dışı bırakmak для "active": false yap
"""
import os
import json
import re
from datetime import datetime

FAQ_FILE     = 'data/learned_faq.json'
UNKNOWN_FILE = 'data/unknown_questions.json'


# ─── Помощник ────────────────────────────────────────────────────────────────

def _load(path: str) -> list:
    os.makedirs('data', exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save(path: str, data: list):
    os.makedirs('data', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _tokenize(text: str) -> set:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return set(text.split())


def _similarity(a: str, b: str) -> float:
    """Jaccard benzerliği (0.0 – 1.0)"""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ─── Bilinmeyen Soru Сохранить ───────────────────────────────────────────────────

def save_unknown_question(question: str, guild_id: int, channel_id: int, history: list):
    """Escalate olan soruyu unknown_questions.json'a add."""
    items = _load(UNKNOWN_FILE)

    # Zaten benzer bir soru var mı? Sayacı artır
    for item in items:
        if _similarity(question, item.get('question', '')) > 0.7:
            item['count'] = item.get('count', 1) + 1
            item['last_seen'] = datetime.utcnow().isoformat()
            _save(UNKNOWN_FILE, items)
            return item['id']

    new_id = f"uq_{int(datetime.utcnow().timestamp())}_{guild_id}"
    items.append({
        'id': new_id,
        'question': question,
        'guild_id': guild_id,
        'channel_id': channel_id,
        'history_snapshot': history[-6:],  # В конец 6 message bağlam для
        'count': 1,
        'created_at': datetime.utcnow().isoformat(),
        'last_seen': datetime.utcnow().isoformat(),
        # status: pending | learned | ignored
        'status': 'pending'
    })
    _save(UNKNOWN_FILE, items)
    return new_id


# ─── Staff Cevabından Öğren ───────────────────────────────────────────────────

def learn_from_staff(question: str, answer: str, guild_id: int, staff_name: str = 'Администратор'):
    """
    Staff'ın ticket'ta данные cevabı learned_faq.json'a add.
    Benzer soru zaten varsa обновл.
    """
    faq = _load(FAQ_FILE)

    # Benzer soru var mı? Обновить
    for item in faq:
        if _similarity(question, item.get('question', '')) > 0.75:
            item['answer'] = answer
            item['updated_at'] = datetime.utcnow().isoformat()
            item['updated_by'] = staff_name
            _save(FAQ_FILE, faq)
            # unknown_questions'da işaretle
            _mark_unknown_learned(question)
            print(f"[FAQ] Обновлено: {question[:60]}")
            return item['id']

    new_id = f"faq_{int(datetime.utcnow().timestamp())}_{guild_id}"
    faq.append({
        'id': new_id,
        'question': question,
        'answer': answer,
        'guild_id': guild_id,
        'created_by': staff_name,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat(),
        'use_count': 0,
        'active': True
    })
    _save(FAQ_FILE, faq)
    _mark_unknown_learned(question)
    print(f"[FAQ] Новый öğrenildi: {question[:60]}")
    return new_id


def _mark_unknown_learned(question: str):
    """unknown_questions'da benzer soruyu 'learned' как işaretle."""
    items = _load(UNKNOWN_FILE)
    changed = False
    for item in items:
        if item.get('status') == 'pending' and _similarity(question, item.get('question', '')) > 0.65:
            item['status'] = 'learned'
            changed = True
    if changed:
        _save(UNKNOWN_FILE, items)


# ─── Benzer FAQ Bul (AI сканироватьfından çağrılır) ─────────────────────────────────

def find_relevant_faqs(question: str, guild_id: int = None, top_k: int = 3, threshold: float = 0.25) -> list:
    """
    Soruya en benzer FAQ'ları вернуть.
    Returns: [{'question': str, 'answer': str, 'score': float}, ...]
    """
    faq = _load(FAQ_FILE)
    results = []

    for item in faq:
        if not item.get('active', True):
            continue
        score = _similarity(question, item.get('question', ''))
        if score >= threshold:
            results.append({
                'question': item['question'],
                'answer': item['answer'],
                'score': score,
                'id': item['id']
            })

    results.sort(key=lambda x: x['score'], reverse=True)

    # Использование число artır
    if results:
        faq_map = {item['id']: item for item in faq}
        for r in results[:top_k]:
            if r['id'] in faq_map:
                faq_map[r['id']]['use_count'] = faq_map[r['id']].get('use_count', 0) + 1
        _save(FAQ_FILE, list(faq_map.values()))

    return results[:top_k]
