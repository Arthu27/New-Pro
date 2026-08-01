"""
Social Features
Sosyal ёzellikler (yorumlar, beгeniler, упоминаниеs)
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
        self.comments = self._loимя_comments()
    
    def _loимя_comments(self) -> Dict[str, Any]:
        """Загрузить комментарии"""
        if os.path.exists(self.comments_file):
            try:
                with open(self.comments_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_comments(self):
        """Сохранить комментарии"""
        os.maкотrs('data', exist_ok=True)
        with open(self.comments_file, 'w', encoding='utf-8') as f:
            json.dump(self.comments, f, ensure_ascii=False, indent=2)
    
    def add_comment(self, ticket_id: str, user_id: str, content: str,
                    parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Комментарий добавить"""
        if ticket_id not in self.comments:
            self.comments[ticket_id] = []
        
        comment_id = f"comment_{len(self.comments[ticket_id]) + 1}"
        
        # Упоминаниеs удалить
        упоминаниеs = self._extract_упоминаниеs(content)
        
        comment = {
            'comment_id': comment_id,
            'user_id': user_id,
            'content': content,
            'parent_id': parent_id,
            'упоминаниеs': упоминаниеs,
            'reactions': {},
            'created_at': datetime.now().isoformat(),
            'updated_at': None
        }
        
        self.comments[ticket_id].append(comment)
        self._save_comments()
        
        return comment
    
    def edit_comment(self, ticket_id: str, comment_id: str, 
                     new_content: str) -> Optional[Dict[str, Any]]:
        """Yorumu dюzenle"""
        if ticket_id not in self.comments:
            return None
        
        for comment in self.comments[ticket_id]:
            if comment['comment_id'] == comment_id:
                comment['content'] = new_content
                comment['упоминаниеs'] = self._extract_упоминаниеs(new_content)
                comment['updated_at'] = datetime.now().isoformat()
                self._save_comments()
                return comment
        
        return None
    
    def delete_comment(self, ticket_id: str, comment_id: str) -> bool:
        """Yorumu удалить"""
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
        """Yorumlarы al"""
        return self.comments.get(ticket_id, [])
    
    def get_replies(self, ticket_id: str, comment_id: str) -> List[Dict[str, Any]]:
        """Yanыtlarы al"""
        comments = self.comments.get(ticket_id, [])
        return [c for c in comments if c.get('parent_id') == comment_id]
    
    def _extract_упоминаниеs(self, content: str) -> List[str]:
        """Упоминаниеs удалить (@user)"""
        pattern = r'@(\w+)'
        return re.findall(pattern, content)


class ReactionSystem:
    """Reaksiyon система"""
    
    AVAILABLE_REACTIONS = ['', '', '', '', '', '', '', '']
    
    def __init__(self, comment_system: CommentSystem):
        self.comment_system = comment_system
    
    def add_reaction(self, ticket_id: str, comment_id: str, 
                     user_id: str, reaction: str) -> bool:
        """Reaksiyon добавить"""
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
        """Reaksiyonu удалить"""
        comments = self.comment_system.comments.get(ticket_id, [])
        
        for comment in comments:
            if comment['comment_id'] == comment_id:
                if reaction in comment['reactions']:
                    if user_id in comment['reactions'][reaction]:
                        comment['reactions'][reaction].remove(user_id)
                        
                        # Boшsa reaksiyonu удалить
                        if not comment['reactions'][reaction]:
                            del comment['reactions'][reaction]
                        
                        self.comment_system._save_comments()
                        return True
        
        return False
    
    def get_reactions(self, ticket_id: str, comment_id: str) -> Dict[str, List[str]]:
        """Reaksiyonlarы al"""
        comments = self.comment_system.comments.get(ticket_id, [])
        
        for comment in comments:
            if comment['comment_id'] == comment_id:
                return comment.get('reactions', {})
        
        return {}


class УпоминаниеSystem:
    """Упоминание система"""
    
    def __init__(self):
        self.упоминаниеs_file = 'data/упоминаниеs.json'
        self.упоминаниеs = self._loимя_упоминаниеs()
    
    def _loимя_упоминаниеs(self) -> Dict[str, Any]:
        """Упоминаниеs'larы загрузить"""
        if os.path.exists(self.упоминаниеs_file):
            try:
                with open(self.упоминаниеs_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_упоминаниеs(self):
        """Упоминаниеs'larы сохранить"""
        os.maкотrs('data', exist_ok=True)
        with open(self.упоминаниеs_file, 'w', encoding='utf-8') as f:
            json.dump(self.упоминаниеs, f, ensure_ascii=False, indent=2)
    
    def record_упоминание(self, упоминаниеed_user_id: str, упоминаниеing_user_id: str,
                       ticket_id: str, comment_id: str) -> Dict[str, Any]:
        """Упоминание'ы сохранить"""
        if упоминаниеed_user_id not in self.упоминаниеs:
            self.упоминаниеs[упоминаниеed_user_id] = []
        
        упоминание = {
            'упоминаниеing_user_id': упоминаниеing_user_id,
            'ticket_id': ticket_id,
            'comment_id': comment_id,
            'timestamp': datetime.now().isoformat(),
            'reимя': False
        }
        
        self.упоминаниеs[упоминаниеed_user_id].append(упоминание)
        self._save_упоминаниеs()
        
        return упоминание
    
    def get_user_упоминаниеs(self, user_id: str, unreимя_only: bool = False) -> List[Dict[str, Any]]:
        """Пользователь упоминаниеs'larыnы al"""
        упоминаниеs = self.упоминаниеs.get(user_id, [])
        
        if unreимя_only:
            упоминаниеs = [m for m in упоминаниеs if not m.get('reимя', False)]
        
        return упоминаниеs
    
    def mark_упоминание_reимя(self, user_id: str, comment_id: str) -> bool:
        """Упоминание'ы прочитано как iшaretle"""
        if user_id not in self.упоминаниеs:
            return False
        
        for упоминание in self.упоминаниеs[user_id]:
            if упоминание['comment_id'] == comment_id:
                упоминание['reимя'] = True
                self._save_упоминаниеs()
                return True
        
        return False
    
    def mark_all_упоминаниеs_reимя(self, user_id: str) -> int:
        """Все упоминаниеs'larы прочитано как iшaretle"""
        if user_id not in self.упоминаниеs:
            return 0
        
        count = 0
        for упоминание in self.упоминаниеs[user_id]:
            if not упоминание.get('reимя', False):
                упоминание['reимя'] = True
                count += 1
        
        if count > 0:
            self._save_упоминаниеs()
        
        return count
    
    def get_unreимя_count(self, user_id: str) -> int:
        """Okunmaлиш упоминаниеs количествоnы al"""
        упоминаниеs = self.упоминаниеs.get(user_id, [])
        return sum(1 for m in упоминаниеs if not m.get('reимя', False))


class VotingSystem:
    """Oylama система"""
    
    def __init__(self):
        self.votes_file = 'data/votes.json'
        self.votes = self._loимя_votes()
    
    def _loимя_votes(self) -> Dict[str, Any]:
        """Oylarы загрузить"""
        if os.path.exists(self.votes_file):
            try:
                with open(self.votes_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_votes(self):
        """Oylarы сохранить"""
        os.maкотrs('data', exist_ok=True)
        with open(self.votes_file, 'w', encoding='utf-8') as f:
            json.dump(self.votes, f, ensure_ascii=False, indent=2)
    
    def vote(self, item_id: str, user_id: str, vote_type: str) -> Dict[str, Any]:
        """Oy ver (upvote/downvote)"""
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
        """Oylarы al"""
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
        """Пользовательnыn играu al"""
        if item_id not in self.votes:
            return None
        
        votes = self.votes[item_id]
        
        if user_id in votes.get('upvotes', []):
            return 'upvote'
        elif user_id in votes.get('downvotes', []):
            return 'downvote'
        
        return None


class SharingSystem:
    """Paylaшыm система"""
    
    def __init__(self):
        self.shares_file = 'data/shares.json'
        self.shares = self._loимя_shares()
    
    def _loимя_shares(self) -> Dict[str, Any]:
        """Paylaшыmlarы загрузить"""
        if os.path.exists(self.shares_file):
            try:
                with open(self.shares_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_shares(self):
        """Paylaшыmlarы сохранить"""
        os.maкотrs('data', exist_ok=True)
        with open(self.shares_file, 'w', encoding='utf-8') as f:
            json.dump(self.shares, f, ensure_ascii=False, indent=2)
    
    def share(self, item_id: str, user_id: str, 
              platform: str, message: Optional[str] = None) -> Dict[str, Any]:
        """Paylaш"""
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
        """Paylaшыmlarы al"""
        return self.shares.get(item_id, [])
    
    def get_share_count(self, item_id: str) -> int:
        """Paylaшыm количествоnы al"""
        return len(self.shares.get(item_id, []))
    
    def get_popular_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Popюler ёгeleri al"""
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
    """Отслеживание система"""
    
    def __init__(self):
        self.following_file = 'data/following.json'
        self.following = self._loимя_following()
    
    def _loимя_following(self) -> Dict[str, Any]:
        """Takipleri загрузить"""
        if os.path.exists(self.following_file):
            try:
                with open(self.following_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_following(self):
        """Takipleri сохранить"""
        os.maкотrs('data', exist_ok=True)
        with open(self.following_file, 'w', encoding='utf-8') as f:
            json.dump(self.following, f, ensure_ascii=False, indent=2)
    
    def follow(self, user_id: str, target_user_id: str) -> bool:
        """Отслеживание et"""
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
        """Takipten выйти"""
        if user_id not in self.following:
            return False
        
        if target_user_id in self.following[user_id]:
            self.following[user_id].remove(target_user_id)
            self._save_following()
            return True
        
        return False
    
    def is_following(self, user_id: str, target_user_id: str) -> bool:
        """Отслеживание edip etmediгini проверить et"""
        return target_user_id in self.following.get(user_id, [])
    
    def get_following(self, user_id: str) -> List[str]:
        """Отслеживание edilenleri al"""
        return self.following.get(user_id, [])
    
    def get_followers(self, user_id: str) -> List[str]:
        """Takipчileri al"""
        followers = []
        
        for follower_id, following_list in self.following.items():
            if user_id in following_list:
                followers.append(follower_id)
        
        return followers
    
    def get_following_count(self, user_id: str) -> int:
        """Отслеживание edilen количествоnы al"""
        return len(self.following.get(user_id, []))
    
    def get_followers_count(self, user_id: str) -> int:
        """Takipчi количествоnы al"""
        return len(self.get_followers(user_id))


# Global instances
comment_system = CommentSystem()
reaction_system = ReactionSystem(comment_system)
упоминание_system = УпоминаниеSystem()
voting_system = VotingSystem()
sharing_system = SharingSystem()
following_system = FollowingSystem()
