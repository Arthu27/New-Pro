"""
Ticket System
Лёгкий адаптер доступа к тикетам для сервисов (SLA и т.п.).
Читает данные из обоих хранилищ проекта: портала клиентов
(data/customer_tickets.json) и Discord-тикетов (data/tickets.json).
"""

import json
import os
from typing import Any, Dict, List, Optional


class TicketManager:
    """Менеджер тикетов (только чтение — запись делают свои коги)."""

    FILES = ('data/customer_tickets.json', 'data/tickets.json')

    def _load(self, path: str) -> Any:
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _iter_tickets(self, data: Any):
        """Отдать тикеты из любой схемы: список / {id: ticket} / {guild: {...}}."""
        if isinstance(data, list):
            for t in data:
                if isinstance(t, dict):
                    yield t
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and (str(v.get('id', '')) or str(v.get('ticket_id', ''))):
                    yield v
                elif isinstance(v, dict):
                    yield from self._iter_tickets(v)
                elif isinstance(v, list):
                    yield from self._iter_tickets(v)

    def get_all_tickets(self) -> List[Dict[str, Any]]:
        """Все тикеты из всех хранилищ."""
        out = []
        for path in self.FILES:
            data = self._load(path)
            if data:
                out.extend(self._iter_tickets(data))
        return out

    def get_ticket(self, ticket_id: Any) -> Optional[Dict[str, Any]]:
        """Найти тикет по ID (строка/число)."""
        tid = str(ticket_id)
        for t in self.get_all_tickets():
            if str(t.get('id', t.get('ticket_id', ''))) == tid:
                return t
        return None


# Глобальный экземпляр
ticket_manager = TicketManager()
