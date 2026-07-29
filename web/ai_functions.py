"""
AI Function Calling — AI может вызывать функции для получения данных и выполнения действий
"""
import json
import os
import discord
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


class AIFunctions:
    """Набор функций доступных AI"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.functions = {
            'get_user_warnings': self.get_user_warnings,
            'get_user_info': self.get_user_info,
            'get_user_roles': self.get_user_roles,
            'check_message_history': self.check_message_history,
            'search_rules': self.search_rules,
            'get_server_stats': self.get_server_stats,
            'get_ticket_history': self.get_ticket_history,
            'remember_fact': self.remember_fact,
            'recall_facts': self.recall_facts,
            'check_user_reputation': self.check_user_reputation,
            'search_knowledge_base': self.search_knowledge_base,
        }
    
    def get_available_functions(self) -> str:
        """Возвращает описание доступных функций для AI"""
        return """
ДОСТУПНЫЕ ФУНКЦИИ (вызывай когда нужно):

1. get_user_warnings(user_id: int)
   Получить историю предупреждений пользователя
   Пример: get_user_warnings(123456789)

2. get_user_info(user_id: int)
   Получить информацию о пользователе (имя, дата регистрации, время на сервере)
   Пример: get_user_info(123456789)

3. get_user_roles(user_id: int)
   Получить список ролей пользователя
   Пример: get_user_roles(123456789)

4. check_message_history(user_id: int, limit: int = 10)
   Проверить последние сообщения пользователя
   Пример: check_message_history(123456789, 20)

5. search_rules(query: str)
   Поиск по правилам сервера
   Пример: search_rules("спам")

6. get_server_stats()
   Получить статистику сервера (участники, онлайн, каналы)
   Пример: get_server_stats()

7. get_ticket_history(user_id: int)
   Получить историю тикетов пользователя
   Пример: get_ticket_history(123456789)

8. remember_fact(user_id: int, fact: str)
   Запомнить важный факт о пользователе
   Пример: remember_fact(123456789, "Предпочитает краткие ответы")

9. recall_facts(user_id: int)
   Вспомнить все факты о пользователе
   Пример: recall_facts(123456789)

10. check_user_reputation(user_id: int)
    Проверить репутацию пользователя (предупреждения, муты, баны)
    Пример: check_user_reputation(123456789)

11. search_knowledge_base(query: str)
    Поиск по базе знаний сервера (правила, FAQ, тикеты, заметки)
    Пример: search_knowledge_base("спам")

ФОРМАТ ВЫЗОВА:
[FUNC:function_name(param1=value1, param2=value2)]

ПРИМЕР:
[FUNC:get_user_warnings(user_id=123456789)]
"""
    
    async def execute_function(self, func_call: str, guild: discord.Guild) -> Optional[str]:
        """Выполняет функцию из вызова AI"""
        try:
            # Парсим вызов: [FUNC:name(param1=value1, param2=value2)]
            if not func_call.startswith('[FUNC:') or not func_call.endswith(']'):
                return None
            
            func_call = func_call[6:-1]  # Убираем [FUNC: и ]
            
            # Парсим имя функции и параметры
            if '(' not in func_call or ')' not in func_call:
                return None
            
            func_name = func_call.split('(')[0].strip()
            params_str = func_call.split('(')[1].rsplit(')', 1)[0].strip()
            
            # Парсим параметры
            params = {}
            if params_str:
                for param in params_str.split(','):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Конвертируем типы
                        if value.isdigit():
                            value = int(value)
                        elif value.replace('.', '').isdigit():
                            value = float(value)
                        elif value.lower() in ('true', 'false'):
                            value = value.lower() == 'true'
                        
                        params[key] = value
            
            # Вызываем функцию
            if func_name not in self.functions:
                return f"Ошибка: функция {func_name} не найдена"
            
            result = await self.functions[func_name](guild=guild, **params)
            return str(result)
            
        except Exception as e:
            return f"Ошибка выполнения функции: {str(e)}"
    
    async def get_user_warnings(self, guild: discord.Guild, user_id: int) -> str:
        """Получить историю предупреждений"""
        try:
            from cogs.warnings import load_warnings
            warnings_data = load_warnings()
            gid = str(guild.id)
            uid = str(user_id)
            
            user_warnings = warnings_data.get(gid, {}).get(uid, [])
            
            if not user_warnings:
                return f"У пользователя <@{user_id}> нет предупреждений."
            
            result = f"Предупреждения <@{user_id}> ({len(user_warnings)}):\n"
            for i, warn in enumerate(user_warnings[-5:], 1):  # Последние 5
                result += f"{i}. {warn.get('reason', 'Без причины')} — {warn.get('mod', '?')} ({warn.get('timestamp', '?')[:10]})\n"
            
            return result
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def get_user_info(self, guild: discord.Guild, user_id: int) -> str:
        """Получить информацию о пользователе"""
        try:
            member = guild.get_member(user_id)
            if not member:
                return f"Пользователь <@{user_id}> не найден на сервере."
            
            created = member.created_at.strftime("%d.%m.%Y")
            joined = member.joined_at.strftime("%d.%m.%Y") if member.joined_at else "?"
            days_on_server = (datetime.utcnow() - member.joined_at).days if member.joined_at else 0
            
            return (
                f"Информация о <@{user_id}>:\n"
                f"Имя: {member.display_name}\n"
                f"ID: {user_id}\n"
                f"Зарегистрирован: {created}\n"
                f"На сервере: {joined} ({days_on_server} дней)\n"
                f"Ролей: {len(member.roles)}"
            )
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def get_user_roles(self, guild: discord.Guild, user_id: int) -> str:
        """Получить роли пользователя"""
        try:
            member = guild.get_member(user_id)
            if not member:
                return f"Пользователь <@{user_id}> не найден."
            
            roles = [role.name for role in member.roles if role.name != "@everyone"]
            if not roles:
                return f"У <@{user_id}> нет ролей."
            
            return f"Роли <@{user_id}>: {', '.join(roles)}"
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def check_message_history(self, guild: discord.Guild, user_id: int, limit: int = 10) -> str:
        """Проверить последние сообщения пользователя"""
        try:
            from cogs.logs import _msg_cache
            
            user_messages = [
                msg for msg in _msg_cache.values()
                if msg.get('author_id') == user_id
            ][:limit]
            
            if not user_messages:
                return f"Нет недавних сообщений от <@{user_id}> в кэше."
            
            result = f"Последние {len(user_messages)} сообщений <@{user_id}>:\n"
            for msg in reversed(user_messages):
                content = msg.get('content', '')[:100]
                channel = msg.get('channel_name', '?')
                result += f"#{channel}: {content}\n"
            
            return result
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def search_rules(self, guild: discord.Guild, query: str) -> str:
        """Поиск по правилам сервера"""
        try:
            rules_file = f"data/rules_{guild.id}.json"
            if not os.path.exists(rules_file):
                return "Правила сервера не найдены."
            
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
            
            rules = rules_data.get('rules', [])
            query_lower = query.lower()
            
            matches = [
                rule for rule in rules
                if query_lower in rule.get('text', '').lower()
            ]
            
            if not matches:
                return f"Не найдено правил по запросу '{query}'."
            
            result = f"Найдено {len(matches)} правил:\n"
            for i, rule in enumerate(matches[:5], 1):
                result += f"{i}. {rule.get('text', '')}\n"
            
            return result
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def get_server_stats(self, guild: discord.Guild) -> str:
        """Получить статистику сервера"""
        try:
            total_members = guild.member_count
            online_members = len([m for m in guild.members if m.status == discord.Status.online])
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            roles = len(guild.roles)
            
            return (
                f"Статистика сервера {guild.name}:\n"
                f"Участников: {total_members} (онлайн: {online_members})\n"
                f"Текстовых каналов: {text_channels}\n"
                f"Голосовых каналов: {voice_channels}\n"
                f"Ролей: {roles}"
            )
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def get_ticket_history(self, guild: discord.Guild, user_id: int) -> str:
        """Получить историю тикетов"""
        try:
            ticket_file = f"data/tickets_{guild.id}.json"
            if not os.path.exists(ticket_file):
                return f"У <@{user_id}> нет истории тикетов."
            
            with open(ticket_file, 'r', encoding='utf-8') as f:
                tickets_data = json.load(f)
            
            user_tickets = [
                t for t in tickets_data.get('tickets', [])
                if t.get('user_id') == user_id
            ]
            
            if not user_tickets:
                return f"У <@{user_id}> нет тикетов."
            
            result = f"Тикеты <@{user_id}> ({len(user_tickets)}):\n"
            for ticket in user_tickets[-5:]:  # Последние 5
                status = ticket.get('status', '?')
                category = ticket.get('category', '?')
                created = ticket.get('created_at', '?')[:10]
                result += f"- {category} ({status}) — {created}\n"
            
            return result
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def remember_fact(self, guild: discord.Guild, user_id: int, fact: str) -> str:
        """Запомнить факт о пользователе"""
        try:
            memory_file = 'data/ai_memory.json'
            memory = {}
            
            if os.path.exists(memory_file):
                with open(memory_file, 'r', encoding='utf-8') as f:
                    memory = json.load(f)
            
            user_key = str(user_id)
            if user_key not in memory:
                memory[user_key] = []
            
            memory[user_key].append({
                'fact': fact,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            # Ограничиваем 50 фактами
            if len(memory[user_key]) > 50:
                memory[user_key] = memory[user_key][-50:]
            
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
            
            return f"Запомнил: {fact}"
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def recall_facts(self, guild: discord.Guild, user_id: int) -> str:
        """Вспомнить факты о пользователе"""
        try:
            memory_file = 'data/ai_memory.json'
            if not os.path.exists(memory_file):
                return f"Нет сохранённых фактов о <@{user_id}>."
            
            with open(memory_file, 'r', encoding='utf-8') as f:
                memory = json.load(f)
            
            user_key = str(user_id)
            facts = memory.get(user_key, [])
            
            if not facts:
                return f"Нет сохранённых фактов о <@{user_id}>."
            
            result = f"Факты о <@{user_id}> ({len(facts)}):\n"
            for fact_data in facts[-10:]:  # Последние 10
                fact = fact_data.get('fact', '')
                result += f"- {fact}\n"
            
            return result
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def check_user_reputation(self, guild: discord.Guild, user_id: int) -> str:
        """Проверить репутацию пользователя"""
        try:
            warnings_text = await self.get_user_warnings(guild, user_id)
            info_text = await self.get_user_info(guild, user_id)
            tickets_text = await self.get_ticket_history(guild, user_id)
            
            return (
                f"=== РЕПУТАЦИЯ <@{user_id}> ===\n\n"
                f"{info_text}\n\n"
                f"{warnings_text}\n\n"
                f"{tickets_text}"
            )
        except Exception as e:
            return f"Ошибка: {str(e)}"
    
    async def search_knowledge_base(self, guild: discord.Guild, query: str) -> str:
        """Поиск по базе знаний сервера (правила, FAQ, тикеты, заметки)"""
        try:
            from web.ai_rag import get_knowledge_base
            
            kb = get_knowledge_base(guild.id)
            context = kb.get_context_for_query(query)
            
            if not context:
                return f"Не найдено информации в базе знаний по запросу: {query}"
            
            return context
        except Exception as e:
            return f"Ошибка поиска в базе знаний: {str(e)}"
