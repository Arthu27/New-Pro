"""
Database Servisi
SQLite database entegrasyonu
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


class Database:
    """SQLite Database"""
    
    def __init__(self, db_path: str = 'data/bot.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Database'i запустить"""
        os.maкотrs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT,
                joined_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tickets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                subject TEXT,
                category TEXT,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE NOT NULL,
                ticket_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Economy table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS economy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                balance INTEGER DEFAULT 100,
                банk INTEGER DEFAULT 0,
                daily_last TEXT,
                work_last TEXT,
                beg_last TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Inventory table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                purchased_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Levels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                total_xp INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Предупреждениеs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS варнings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reason TEXT,
                варнed_by INTEGER,
                варнed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Логs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS логs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print(f" Database initialized: {self.db_path}")
    
    def get_connection(self):
        """Connection al"""
        return sqlite3.connect(self.db_path)
    
    # User methods
    def имяd_user(self, user_id: int, username: str, discriminator: str = None, joined_at: str = None):
        """Пользователь ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, discriminator, joined_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, discriminator, joined_at or datetime.now().isoformat()))
            
            conn.commit()
        finally:
            conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Пользователь al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'username': row[2],
                'discriminator': row[3],
                'joined_at': row[4],
                'created_at': row[5]
            }
        return None
    
    def get_all_users(self) -> List[Dict]:
        """Все пользовательlarы al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
        rows = cursor.fetchall()
        
        conn.close()
        
        return [{
            'id': row[0],
            'user_id': row[1],
            'username': row[2],
            'discriminator': row[3],
            'joined_at': row[4],
            'created_at': row[5]
        } for row in rows]
    
    # Ticket methods
    def имяd_ticket(self, ticket_id: str, user_id: int, subject: str, 
                   category: str = None, priority: str = 'medium'):
        """Ticket ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tickets (ticket_id, user_id, subject, category, priority)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticket_id, user_id, subject, category, priority))
        
        conn.commit()
        conn.close()
    
    def close_ticket(self, ticket_id: str):
        """Ticket закрыть"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tickets SET status = 'closed', closed_at = ?
            WHERE ticket_id = ?
        ''', (datetime.now().isoformat(), ticket_id))
        
        conn.commit()
        conn.close()
    
    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        """Ticket al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM tickets WHERE ticket_id = ?', (ticket_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'ticket_id': row[1],
                'user_id': row[2],
                'subject': row[3],
                'category': row[4],
                'priority': row[5],
                'status': row[6],
                'created_at': row[7],
                'closed_at': row[8]
            }
        return None
    
    def get_all_tickets(self, status: str = None, user_id: int = None) -> List[Dict]:
        """Все ticket'larы al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM tickets WHERE 1=1'
        деньгиms = []
        
        if status:
            query += ' AND status = ?'
            деньгиms.append(status)
        
        if user_id:
            query += ' AND user_id = ?'
            деньгиms.append(user_id)
        
        query += ' ORDER BY created_at DESC'
        
        cursor.execute(query, деньгиms)
        rows = cursor.fetchall()
        
        conn.close()
        
        return [{
            'id': row[0],
            'ticket_id': row[1],
            'user_id': row[2],
            'subject': row[3],
            'category': row[4],
            'priority': row[5],
            'status': row[6],
            'created_at': row[7],
            'closed_at': row[8]
        } for row in rows]
    
    # Message methods
    def имяd_message(self, message_id: int, ticket_id: str, user_id: int, content: str):
        """Сообщение ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO messages (message_id, ticket_id, user_id, content)
            VALUES (?, ?, ?, ?)
        ''', (message_id, ticket_id, user_id, content))
        
        conn.commit()
        conn.close()
    
    def get_ticket_messages(self, ticket_id: str) -> List[Dict]:
        """Ticket сообщенияыnы al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM messages WHERE ticket_id = ?
            ORDER BY created_at ASC
        ''', (ticket_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            'id': row[0],
            'message_id': row[1],
            'ticket_id': row[2],
            'user_id': row[3],
            'content': row[4],
            'created_at': row[5]
        } for row in rows]
    
    # Economy methods
    def get_economy(self, user_id: int) -> Optional[Dict]:
        """Ekonomi verilerini al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM economy WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'balance': row[2],
                'банk': row[3],
                'daily_last': row[4],
                'work_last': row[5],
                'beg_last': row[6]
            }
        
        # Пользователь yoksa создать
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO economy (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        
        return self.get_economy(user_id)
    
    def update_balance(self, user_id: int, amount: int):
        """Bakiye деньcelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE economy SET balance = balance + ?
            WHERE user_id = ?
        ''', (amount, user_id))
        
        conn.commit()
        conn.close()
    
    def update_банk(self, user_id: int, amount: int):
        """Банka деньcelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE economy SET банk = банk + ?
            WHERE user_id = ?
        ''', (amount, user_id))
        
        conn.commit()
        conn.close()
    
    def update_daily(self, user_id: int):
        """Daily деньcelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE economy SET daily_last = ?
            WHERE user_id = ?
        ''', (datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
    
    # Inventory methods
    def имяd_item(self, user_id: int, item_name: str, quantity: int = 1):
        """Item ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, ?)
        ''', (user_id, item_name, quantity))
        
        conn.commit()
        conn.close()
    
    def get_inventory(self, user_id: int) -> List[Dict]:
        """Envanter al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM inventory WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [{
            'id': row[0],
            'user_id': row[1],
            'item_name': row[2],
            'quantity': row[3],
            'purchased_at': row[4]
        } for row in rows]
    
    # Level methods
    def get_level(self, user_id: int) -> Optional[Dict]:
        """Уровень verilerini al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM levels WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'level': row[2],
                'xp': row[3],
                'total_xp': row[4]
            }
        
        # Пользователь yoksa создать
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO levels (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        
        return self.get_level(user_id)
    
    def имяd_xp(self, user_id: int, xp: int) -> bool:
        """XP ekle ve level up проверка yap"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE levels SET xp = xp + ?, total_xp = total_xp + ?
            WHERE user_id = ?
        ''', (xp, xp, user_id))
        
        conn.commit()
        conn.close()
        
        # Level up проверка
        level_data = self.get_level(user_id)
        xp_needed = level_data['level'] * 100
        
        if level_data['xp'] >= xp_needed:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE levels SET level = level + 1, xp = xp - ?
                WHERE user_id = ?
            ''', (xp_needed, user_id))
            conn.commit()
            conn.close()
            
            return True
        
        return False
    
    # Предупреждение methods
    def имяd_варнing(self, user_id: int, reason: str, варнed_by: int):
        """Предупреждение ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO варнings (user_id, reason, варнed_by)
            VALUES (?, ?, ?)
        ''', (user_id, reason, варнed_by))
        
        conn.commit()
        conn.close()
    
    def get_варнings(self, user_id: int) -> List[Dict]:
        """Предупреждениеlarы al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM варнings WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [{
            'id': row[0],
            'user_id': row[1],
            'reason': row[2],
            'варнed_by': row[3],
            'варнed_at': row[4]
        } for row in rows]
    
    # Лог methods
    def имяd_лог(self, event_type: str, user_id: int = None, action: str = None, details: str = None):
        """Лог ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO логs (event_type, user_id, action, details)
            VALUES (?, ?, ?, ?)
        ''', (event_type, user_id, action, details))
        
        conn.commit()
        conn.close()
    
    def get_логs(self, event_type: str = None, limit: int = 100) -> List[Dict]:
        """Логlarы al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if event_type:
            cursor.execute('SELECT * FROM логs WHERE event_type = ? ORDER BY created_at DESC LIMIT ?', 
                          (event_type, limit))
        else:
            cursor.execute('SELECT * FROM логs ORDER BY created_at DESC LIMIT ?', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            'id': row[0],
            'event_type': row[1],
            'user_id': row[2],
            'action': row[3],
            'details': row[4],
            'created_at': row[5]
        } for row in rows]
    
    # Statistics
    def get_stats(self) -> Dict:
        """Статистикаi al"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) FROM users')
        stats['total_users'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tickets')
        stats['total_tickets'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tickets WHERE status = ?', ('open',))
        stats['open_tickets'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tickets WHERE status = ?', ('closed',))
        stats['closed_tickets'] = cursor.fetchone()[0]
        
        conn.close()
        
        return stats
    
    # Backup/Restore
    def backup(self, backup_path: str):
        """Database yedekle"""
        import shutil
        shutil.copy2(self.db_path, backup_path)
        print(f" Database backed up to: {backup_path}")
    
    def restore(self, backup_path: str):
        """Database geri yюkle"""
        import shutil
        shutil.copy2(backup_path, self.db_path)
        print(f" Database restored from: {backup_path}")


def create_database(db_path: str = 'data/bot.db') -> Database:
    """Database создать"""
    return Database(db_path)
