"""
Social Features
Социальные функции (комментарии, лайки, упоминания)
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional


class CommentSystem:
    """Система комментариев"""
    
    def __init__(self):
        self.comments_file = 'data/comments.json'
        self.comments = self._load_comments()
    
    def _load_comments(self) -> Dict[str, Any]:
        """Загрузить комментарии"""
        if os.path.exists(self.comments_file):
            try:
                with open(self.comments_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_comments(self):
        """Сохранить комментарии"""
        os.makedirs('data', exist_ok=True)
        with open(self.comments_file, 'w', encoding='utf-8') as f:
            json.dump(self.comments, f, ensure_ascii=False, indent=2)
    
    def add_comment(self, ticket_id: str, user_id: str, content: str,
                    parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Добавить комментарий"""
        if ticket_id not in self.comments:
            self.comments[ticket_id] = []
        
        comment_id = f"comment_{len(self.comments[ticket_id]) + 1}"
        
        # Mentions удалить
        mentions = self._extract_mentions(content)
        
        comment = {
            'comment_id': comment_id,
            'user_id': user_id,
            'content': content,
            'parent_id': parent_id,
            'mentions': mentions,
            'reactions': {},
            'created_at': datetime.now().isoformat(),
            'updated_at': None
        }
        
        self.comments[ticket_id].append(comment)
        self._save_comments()
        
        return comment
    
    def edit_comment(self, ticket_id: str, comment_id: str, 
                     new_content: str) -> Optional[Dict[str, Any]]:
        """Редактировать комментарий"""
        if ticket_id not in self.comments:
            return None
        
        for comment in self.comments[ticket_id]:
            if comment['comment_id'] == comment_id:
                comment['content'] = new_content
                comment['mentions'] = self._extract_mentions(new_content)
                comment['updated_at'] = datetime.now().isoformat()
                self._save_comments()
                return comment
        
        return None
    
    def delete_comment(self, ticket_id: str, comment_id: str) -> bool:
        """Удалить комментарий"""
        if ticket_id not in self.comments:
            return False
        
        comments = self.comments[ticket_id]
        for i, comment in enumerate(comments):
            if comment['comment_id'] == comment_id:
                del comments[i]
                self._save_comments()
                return True
        
        return False
    
    def get_comments(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Получить комментарии"""
        return self.comments.get(ticket_id, [])
    
    def get_replies(self, ticket_id: str, comment_id: str) -> List[Dict[str, Any]]:
        """Получить ответы"""
        comments = self.comments.get(ticket_id, [])
        return [c for c in comments if c.get('parent_id') == comment_id]
    
    def _extract_mentions(self, content: str) -> List[str]:
        """Удалить упоминания (@user)"""
        pattern = r'@(\w+)'
        return re.findall(pattern, content)


class ReactionSystem:
    """Система реакций"""
    
    AVAILABLE_REACTIONS = ['', '', '', '', '', '', '', '']
    
    def __init__(self, comment_system: CommentSystem):
        self.comment_system = comment_system
    
    def add_reaction(self, ticket_id: str, comment_id: str, 
                     user_id: str, reaction: str) -> bool:
        """Добавить реакцию"""
        if reaction not in self.AVAILABLE_REACTIONS:
            return False
        
        comments = self.comment_system.comments.get(ticket_id, [])
        
        for comment in comments:
            if comment['comment_id'] == comment_id:
                if reaction not in comment['reactions']:
                    comment['reactions'][reaction] = []
                
                if user_id not in comment['reactions'][reaction]:
                    comment['reactions'][reaction].append(user_id)
                    self.comment_system._save_comments()
                    return True
        
        return False
    
    def remove_reaction(self, ticket_id: str, comment_id: str,
                        user_id: str, reaction: str) -> bool:
        """Удалить реакцию"""
        comments = self.comment_system.comments.get(ticket_id, [])
        
        for comment in comments:
            if comment['comment_id'] == comment_id:
                if reaction in comment['reactions']:
                    if user_id in comment['reactions'][reaction]:
                        comment['reactions'][reaction].remove(user_id)
                        
                        # Если пусто — удаляем реакцию
                        if not comment['reactions'][reaction]:
                            del comment['reactions'][reaction]
                        
                        self.comment_system._save_comments()
                        return True
        
        return False
    
    def get_reactions(self, ticket_id: str, comment_id: str) -> Dict[str, List[str]]:
        """Получить реакции"""
        comments = self.comment_system.comments.get(ticket_id, [])
        
        for comment in comments:
            if comment['comment_id'] == comment_id:
                return comment.get('reactions', {})
        
        return {}


class MentionSystem:
    """Система упоминаний"""
    
    def __init__(self):
        self.mentions_file = 'data/mentions.json'
        self.mentions = self._load_mentions()
    
    def _load_mentions(self) -> Dict[str, Any]:
        """Загрузить упоминания"""
        if os.path.exists(self.mentions_file):
            try:
                with open(self.mentions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_mentions(self):
        """Сохранить упоминания"""
        os.makedirs('data', exist_ok=True)
        with open(self.mentions_file, 'w', encoding='utf-8') as f:
            json.dump(self.mentions, f, ensure_ascii=False, indent=2)
    
    def record_mention(self, mentioned_user_id: str, mentioning_user_id: str,
                       ticket_id: str, comment_id: str) -> Dict[str, Any]:
        """Сохранить упоминание"""
        if mentioned_user_id not in self.mentions:
            self.mentions[mentioned_user_id] = []
        
        упоминание = {
            'mentioning_user_id': mentioning_user_id,
            'ticket_id': ticket_id,
            'comment_id': comment_id,
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
        
        self.mentions[mentioned_user_id].append(упоминание)
        self._save_mentions()
        
        return упоминание
    
    def get_user_mentions(self, user_id: str, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Получить упоминания пользователя"""
        mentions = self.mentions.get(user_id, [])
        
        if unread_only:
            mentions = [m for m in mentions if not m.get('read', False)]
        
        return mentions
    
    def mark_mention_read(self, user_id: str, comment_id: str) -> bool:
        """Отметить упоминания прочитанными"""
        if user_id not in self.mentions:
            return False
        
        for упоминание in self.mentions[user_id]:
            if упоминание['comment_id'] == comment_id:
                упоминание['read'] = True
                self._save_mentions()
                return True
        
        return False
    
    def mark_all_mentions_read(self, user_id: str) -> int:
        """Отметить все упоминания пользователя прочитанными"""
        if user_id not in self.mentions:
            return 0
        
        count = 0
        for упоминание in self.mentions[user_id]:
            if not упоминание.get('read', False):
                упоминание['read'] = True
                count += 1
        
        if count > 0:
            self._save_mentions()
        
        return count
    
    def get_unread_count(self, user_id: str) -> int:
        """Получить количество непрочитанных упоминаний"""
        mentions = self.mentions.get(user_id, [])
        return sum(1 for m in mentions if not m.get('read', False))


class VotingSystem:
    """Система голосования"""
    
    def __init__(self):
        self.votes_file = 'data/votes.json'
        self.votes = self._load_votes()
    
    def _load_votes(self) -> Dict[str, Any]:
        """Загрузить голоса"""
        if os.path.exists(self.votes_file):
            try:
                with open(self.votes_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_votes(self):
        """Сохранить голоса"""
        os.makedirs('data', exist_ok=True)
        with open(self.votes_file, 'w', encoding='utf-8') as f:
            json.dump(self.votes, f, ensure_ascii=False, indent=2)
    
    def vote(self, item_id: str, user_id: str, vote_type: str) -> Dict[str, Any]:
        """Проголосовать (upvote/downvote)"""
        if vote_type not in ['upvote', 'downvote']:
            return {'error': 'Invalid vote type'}
        
        if item_id not in self.votes:
            self.votes[item_id] = {
                'upvotes': [],
                'downvotes': []
            }
        
        # Ёnceki oyu удалить
        if user_id in self.votes[item_id]['upvotes']:
            self.votes[item_id]['upvotes'].remove(user_id)
        if user_id in self.votes[item_id]['downvotes']:
            self.votes[item_id]['downvotes'].remove(user_id)
        
        # Новый oyu добавить
        self.votes[item_id][f'{vote_type}s'].append(user_id)
        self._save_votes()
        
        return {
            'item_id': item_id,
            'upvotes': len(self.votes[item_id]['upvotes']),
            'downvotes': len(self.votes[item_id]['downvotes']),
            'score': len(self.votes[item_id]['upvotes']) - len(self.votes[item_id]['downvotes'])
        }
    
    def get_votes(self, item_id: str) -> Dict[str, Any]:
        """Получить голоса"""
        if item_id not in self.votes:
            return {
                'upvotes': 0,
                'downvotes': 0,
                'score': 0
            }
        
        votes = self.votes[item_id]
        return {
            'upvotes': len(votes.get('upvotes', [])),
            'downvotes': len(votes.get('downvotes', [])),
            'score': len(votes.get('upvotes', [])) - len(votes.get('downvotes', []))
        }
    
    def get_user_vote(self, item_id: str, user_id: str) -> Optional[str]:
        """Получить голос пользователя"""
        if item_id not in self.votes:
            return None
        
        votes = self.votes[item_id]
        
        if user_id in votes.get('upvotes', []):
            return 'upvote'
        elif user_id in votes.get('downvotes', []):
            return 'downvote'
        
        return None


class SharingSystem:
    """Система публикаций"""
    
    def __init__(self):
        self.shares_file = 'data/shares.json'
        self.shares = self._load_shares()
    
    def _load_shares(self) -> Dict[str, Any]:
        """Загрузить публикации"""
        if os.path.exists(self.shares_file):
            try:
                with open(self.shares_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_shares(self):
        """Сохранить публикации"""
        os.makedirs('data', exist_ok=True)
        with open(self.shares_file, 'w', encoding='utf-8') as f:
            json.dump(self.shares, f, ensure_ascii=False, indent=2)
    
    def share(self, item_id: str, user_id: str, 
              platform: str, message: Optional[str] = None) -> Dict[str, Any]:
        """Поделиться"""
        if item_id not in self.shares:
            self.shares[item_id] = []
        
        share = {
            'user_id': user_id,
            'platform': platform,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        self.shares[item_id].append(share)
        self._save_shares()
        
        return share
    
    def get_shares(self, item_id: str) -> List[Dict[str, Any]]:
        """Получить публикации"""
        return self.shares.get(item_id, [])
    
    def get_share_count(self, item_id: str) -> int:
        """Получить количество публикаций"""
        return len(self.shares.get(item_id, []))
    
    def get_popular_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить популярные элементы"""
        popular = [
            {
                'item_id': item_id,
                'share_count': len(shares)
            }
            for item_id, shares in self.shares.items()
        ]
        
        popular.sort(key=lambda x: x['share_count'], reverse=True)
        
        return popular[:limit]


class FollowingSystem:
    """Система подписок"""
    
    def __init__(self):
        self.following_file = 'data/following.json'
        self.following = self._load_following()
    
    def _load_following(self) -> Dict[str, Any]:
        """Загрузить подписки"""
        if os.path.exists(self.following_file):
            try:
                with open(self.following_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_following(self):
        """Сохранить подписки"""
        os.makedirs('data', exist_ok=True)
        with open(self.following_file, 'w', encoding='utf-8') as f:
            json.dump(self.following, f, ensure_ascii=False, indent=2)
    
    def follow(self, user_id: str, target_user_id: str) -> bool:
        """Подписаться"""
        if user_id == target_user_id:
            return False
        
        if user_id not in self.following:
            self.following[user_id] = []
        
        if target_user_id not in self.following[user_id]:
            self.following[user_id].append(target_user_id)
            self._save_following()
            return True
        
        return False
    
    def unfollow(self, user_id: str, target_user_id: str) -> bool:
        """Отписаться"""
        if user_id not in self.following:
            return False
        
        if target_user_id in self.following[user_id]:
            self.following[user_id].remove(target_user_id)
            self._save_following()
            return True
        
        return False
    
    def is_following(self, user_id: str, target_user_id: str) -> bool:
        """Проверить, подписан ли"""
        return target_user_id in self.following.get(user_id, [])
    
    def get_following(self, user_id: str) -> List[str]:
        """Получить подписки"""
        return self.following.get(user_id, [])
    
    def get_followers(self, user_id: str) -> List[str]:
        """Получить подписчиков"""
        followers = []
        
        for follower_id, following_list in self.following.items():
            if user_id in following_list:
                followers.append(follower_id)
        
        return followers
    
    def get_following_count(self, user_id: str) -> int:
        """Получить количество подписок"""
        return len(self.following.get(user_id, []))
    
    def get_followers_count(self, user_id: str) -> int:
        """Получить количество подписчиков"""
        return len(self.get_followers(user_id))


# Global instances
comment_system = CommentSystem()
reaction_system = ReactionSystem(comment_system)
mention_system = MentionSystem()
voting_system = VotingSystem()
sharing_system = SharingSystem()
following_system = FollowingSystem()
