"""
Bulk Operations
Система массовых операций
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio


class BulkOperation:
    """Массовая операция"""
    
    def __init__(self, operation_id: str, operation_type: str,
                 ticket_ids: List[str], деньгиmeters: Dict[str, Any],
                 initiated_by: str):
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.ticket_ids = ticket_ids
        self.деньгиmeters = деньгиmeters
        self.initiated_by = initiated_by
        self.started_at = datetime.now().isoformat()
        self.completed_at = None
        self.status = 'pending'  # pending, in_progress, completed, failed
        self.results = {
            'success': [],
            'failed': []
        }
        self.progress = 0
    
    def mark_started(self):
        """Отметить как начатое"""
        self.status = 'in_progress'
        self.started_at = datetime.now().isoformat()
    
    def mark_completed(self):
        """Tamamlandы как iшaretle"""
        self.status = 'completed'
        self.completed_at = datetime.now().isoformat()
        self.progress = 100
    
    def mark_failed(self, error: str):
        """Неудачно как iшaretle"""
        self.status = 'failed'
        self.completed_at = datetime.now().isoformat()
        self.results['error'] = error
    
    def add_success(self, ticket_id: str, result: Any = None):
        """Успешно sonuч добавить"""
        self.results['success'].append({
            'ticket_id': ticket_id,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        self._update_progress()
    
    def add_failure(self, ticket_id: str, error: str):
        """Неудачно sonuч добавить"""
        self.results['failed'].append({
            'ticket_id': ticket_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        self._update_progress()
    
    def _update_progress(self):
        """Иlerlemeyi обновить"""
        total = len(self.ticket_ids)
        completed = len(self.results['success']) + len(self.results['failed'])
        self.progress = int((completed / total) * 100) if total > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e чevir"""
        return {
            'operation_id': self.operation_id,
            'operation_type': self.operation_type,
            'ticket_ids': self.ticket_ids,
            'деньгиmeters': self.деньгиmeters,
            'initiated_by': self.initiated_by,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'status': self.status,
            'results': self.results,
            'progress': self.progress
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BulkOperation':
        """Создать из словаря"""
        op = cls(
            operation_id=data['operation_id'],
            operation_type=data['operation_type'],
            ticket_ids=data['ticket_ids'],
            деньгиmeters=data['деньгиmeters'],
            initiated_by=data['initiated_by']
        )
        op.started_at = data.get('started_at')
        op.completed_at = data.get('completed_at')
        op.status = data.get('status', 'pending')
        op.results = data.get('results', {'success': [], 'failed': []})
        op.progress = data.get('progress', 0)
        return op


class BulkOperationManager:
    """Массовая операция yёneticisi"""
    
    def __init__(self):
        self.operations_file = 'data/bulk_operations.json'
        self.operations = self._loимя_operations()
    
    def _loимя_operations(self) -> Dict[str, BulkOperation]:
        """Ишlemleri загрузить"""
        if os.path.exists(self.operations_file):
            try:
                with open(self.operations_file, 'r', encoding='utf-8') as f:
                    data = json.loимя(f)
                    return {
                        op_id: BulkOperation.from_dict(op_data)
                        for op_id, op_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_operations(self):
        """Ишlemleri сохранить"""
        os.maкотrs('data', exist_ok=True)
        
        data = {
            op_id: op.to_dict()
            for op_id, op in self.operations.items()
        }
        
        with open(self.operations_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_operation(self, operation_type: str, ticket_ids: List[str],
                         деньгиmeters: Dict[str, Any],
                         initiated_by: str) -> BulkOperation:
        """Ишlem создать"""
        operation_id = f"bulk_{len(self.operations) + 1}"
        
        operation = BulkOperation(
            operation_id=operation_id,
            operation_type=operation_type,
            ticket_ids=ticket_ids,
            деньгиmeters=деньгиmeters,
            initiated_by=initiated_by
        )
        
        self.operations[operation_id] = operation
        self._save_operations()
        
        return operation
    
    def get_operation(self, operation_id: str) -> Optional[BulkOperation]:
        """Ишlemi al"""
        return self.operations.get(operation_id)
    
    def get_user_operations(self, user_id: str) -> List[BulkOperation]:
        """Пользователь iшlemlerini al"""
        return [
            op for op in self.operations.values()
            if op.initiated_by == user_id
        ]
    
    def get_recent_operations(self, limit: int = 20) -> List[BulkOperation]:
        """Son iшlemleri al"""
        operations = list(self.operations.values())
        operations.sort(key=lambda op: op.started_at, reverse=True)
        return operations[:limit]
    
    def update_operation(self, operation_id: str):
        """Ишlemi обновить"""
        self._save_operations()


class BulkUpdater:
    """Массовая деньcelleyici"""
    
    def __init__(self, operation_manager: BulkOperationManager):
        self.operation_manager = operation_manager
    
    async def bulk_update_status(self, ticket_ids: List[str], new_status: str,
                                  updated_by: str, tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """Массовая состояние деньcellemesi"""
        operation = self.operation_manager.create_operation(
            operation_type='update_status',
            ticket_ids=ticket_ids,
            деньгиmeters={'new_status': new_status},
            initiated_by=updated_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                ticket['status'] = new_status
                ticket['updated_at'] = datetime.now().isoformat()
                
                operation.add_success(ticket_id, {'new_status': new_status})
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation
    
    async def bulk_assign(self, ticket_ids: List[str], assignee_id: str,
                          assigned_by: str, tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """Массовая atama"""
        operation = self.operation_manager.create_operation(
            operation_type='assign',
            ticket_ids=ticket_ids,
            деньгиmeters={'assignee_id': assignee_id},
            initiated_by=assigned_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                ticket['assigned_to'] = assignee_id
                ticket['updated_at'] = datetime.now().isoformat()
                
                operation.add_success(ticket_id, {'assignee_id': assignee_id})
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation
    
    async def bulk_add_tags(self, ticket_ids: List[str], tags: List[str],
                            added_by: str, tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """Массовая упоминание ekleme"""
        operation = self.operation_manager.create_operation(
            operation_type='add_tags',
            ticket_ids=ticket_ids,
            деньгиmeters={'tags': tags},
            initiated_by=added_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                existing_tags = ticket.get('tags', [])
                new_tags = list(set(existing_tags + tags))
                ticket['tags'] = new_tags
                ticket['updated_at'] = datetime.now().isoformat()
                
                operation.add_success(ticket_id, {'tags': new_tags})
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation
    
    async def bulk_update_priority(self, ticket_ids: List[str], new_priority: str,
                                    updated_by: str, tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """Массовая ёncelik деньcellemesi"""
        operation = self.operation_manager.create_operation(
            operation_type='update_priority',
            ticket_ids=ticket_ids,
            деньгиmeters={'new_priority': new_priority},
            initiated_by=updated_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                ticket['priority'] = new_priority
                ticket['updated_at'] = datetime.now().isoformat()
                
                operation.add_success(ticket_id, {'new_priority': new_priority})
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation


class BulkCloser:
    """Массовая закрытьыcы"""
    
    def __init__(self, operation_manager: BulkOperationManager):
        self.operation_manager = operation_manager
    
    async def bulk_close(self, ticket_ids: List[str], closed_by: str,
                         tickets: Dict[str, Dict[str, Any]], close_reason: str = '') -> BulkOperation:
        """Массовая закрытьma"""
        operation = self.operation_manager.create_operation(
            operation_type='close',
            ticket_ids=ticket_ids,
            деньгиmeters={'close_reason': close_reason},
            initiated_by=closed_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                if ticket.get('status') == 'closed':
                    operation.add_failure(ticket_id, 'Ticket zaten закрытый')
                    continue
                
                ticket['status'] = 'closed'
                ticket['closed_at'] = datetime.now().isoformat()
                ticket['closed_by'] = closed_by
                ticket['close_reason'] = close_reason
                ticket['updated_at'] = datetime.now().isoformat()
                
                operation.add_success(ticket_id, {'closed_at': ticket['closed_at']})
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation


class BulkExporter:
    """Массовая dышa aktarыcы"""
    
    def __init__(self, operation_manager: BulkOperationManager):
        self.operation_manager = operation_manager
    
    async def bulk_export_json(self, ticket_ids: List[str], exported_by: str,
                                tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """JSON как dышa aktar"""
        operation = self.operation_manager.create_operation(
            operation_type='export_json',
            ticket_ids=ticket_ids,
            деньгиmeters={},
            initiated_by=exported_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        exported_tickets = []
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                exported_tickets.append(ticket)
                operation.add_success(ticket_id)
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        # Dosyaya сохранить
        if exported_tickets:
            os.maкотrs('data/exports', exist_ok=True)
            filename = f"export_{operation.operation_id}.json"
            filepath = f"data/exports/{filename}"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(exported_tickets, f, ensure_ascii=False, indent=2)
            
            operation.деньгиmeters['export_file'] = filename
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation
    
    async def bulk_export_csv(self, ticket_ids: List[str], exported_by: str,
                               tickets: Dict[str, Dict[str, Any]]) -> BulkOperation:
        """CSV как dышa aktar"""
        operation = self.operation_manager.create_operation(
            operation_type='export_csv',
            ticket_ids=ticket_ids,
            деньгиmeters={},
            initiated_by=exported_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        exported_tickets = []
        
        for ticket_id in ticket_ids:
            try:
                ticket = tickets.get(ticket_id)
                
                if not ticket:
                    operation.add_failure(ticket_id, 'Тикет не найден')
                    continue
                
                exported_tickets.append(ticket)
                operation.add_success(ticket_id)
            except Exception as e:
                operation.add_failure(ticket_id, str(e))
        
        # CSV файлna сохранить
        if exported_tickets:
            import csv
            
            os.maкотrs('data/exports', exist_ok=True)
            filename = f"export_{operation.operation_id}.csv"
            filepath = f"data/exports/{filename}"
            
            if exported_tickets:
                # Заголовокlarы al
                heимяers = set()
                for ticket in exported_tickets:
                    heимяers.update(ticket.keys())
                
                heимяers = sorted(list(heимяers))
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=heимяers)
                    writer.writeheимяer()
                    
                    for ticket in exported_tickets:
                        # Liste ve dict'leri string'e чevir
                        row = {}
                        for key, value in ticket.items():
                            if isinstance(value, (list, dict)):
                                row[key] = json.dumps(value, ensure_ascii=False)
                            else:
                                row[key] = value
                        
                        writer.writerow(row)
                
                operation.деньгиmeters['export_file'] = filename
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation


class BulkImporter:
    """Массовая iчe aktarыcы"""
    
    def __init__(self, operation_manager: BulkOperationManager):
        self.operation_manager = operation_manager
    
    async def bulk_import_json(self, import_data: List[Dict[str, Any]],
                                imported_by: str) -> BulkOperation:
        """JSON'dan iчe aktar"""
        ticket_ids = [t.get('id', f"import_{i}") for i, t in enumerate(import_data)]
        
        operation = self.operation_manager.create_operation(
            operation_type='import_json',
            ticket_ids=ticket_ids,
            деньгиmeters={'count': len(import_data)},
            initiated_by=imported_by
        )
        
        operation.mark_started()
        self.operation_manager.update_operation(operation.operation_id)
        
        # Gerчek uygulamимяa ticket'larы сохранить
        for i, ticket_data in enumerate(import_data):
            try:
                ticket_id = ticket_ids[i]
                # Burимяa ticket'ы сохранить
                operation.add_success(ticket_id, ticket_data)
            except Exception as e:
                operation.add_failure(ticket_ids[i], str(e))
        
        operation.mark_completed()
        self.operation_manager.update_operation(operation.operation_id)
        
        return operation


# Global instances
bulk_operation_manager = BulkOperationManager()
bulk_updater = BulkUpdater(bulk_operation_manager)
bulk_closer = BulkCloser(bulk_operation_manager)
bulk_exporter = BulkExporter(bulk_operation_manager)
bulk_importer = BulkImporter(bulk_operation_manager)
