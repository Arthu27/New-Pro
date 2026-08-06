"""
Advanced Ticket Features
Расширенные функции тикетов (merging, splitting, cloning, dependencies, sub-tickets)
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import hashlib


class TicketMerger:
    """Объединение тикетов"""
    
    def __init__(self):
        self.merge_history_file = 'data/ticket_merge_history.json'
        self.merge_history = self._load_merge_history()
    
    def _load_merge_history(self) -> Dict[str, Any]:
        """Загрузить историю объединений"""
        if os.path.exists(self.merge_history_file):
            try:
                with open(self.merge_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_merge_history(self):
        """Сохранить историю объединений"""
        os.makedirs('data', exist_ok=True)
        with open(self.merge_history_file, 'w', encoding='utf-8') as f:
            json.dump(self.merge_history, f, ensure_ascii=False, indent=2)
    
    def merge_tickets(self, primary_ticket_id: str,
                      secondary_ticket_ids: List[str],
                      merged_by: str) -> Dict[str, Any]:
        """Объединить тикеты"""
        merge_id = hashlib.md5(f"{primary_ticket_id}{''.join(secondary_ticket_ids)}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        merge_record = {
            'merge_id': merge_id,
            'primary_ticket_id': primary_ticket_id,
            'secondary_ticket_ids': secondary_ticket_ids,
            'merged_by': merged_by,
            'merged_at': datetime.now().isoformat()
        }
        
        self.merge_history[merge_id] = merge_record
        self._save_merge_history()
        
        return merge_record
    
    def get_merge_history(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Получить историю объединений"""
        history = []
        
        for merge_id, record in self.merge_history.items():
            if record['primary_ticket_id'] == ticket_id or ticket_id in record['secondary_ticket_ids']:
                history.append(record)
        
        return history
    
    def get_merged_tickets(self, primary_ticket_id: str) -> List[str]:
        """Получить объединённые тикеты"""
        for record in self.merge_history.values():
            if record['primary_ticket_id'] == primary_ticket_id:
                return record['secondary_ticket_ids']
        
        return []


class TicketSplitter:
    """Разделитель тикетов"""
    
    def __init__(self):
        self.split_history_file = 'data/ticket_split_history.json'
        self.split_history = self._load_split_history()
    
    def _load_split_history(self) -> Dict[str, Any]:
        """Загрузить историю разделений"""
        if os.path.exists(self.split_history_file):
            try:
                with open(self.split_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_split_history(self):
        """Сохранить историю разделений"""
        os.makedirs('data', exist_ok=True)
        with open(self.split_history_file, 'w', encoding='utf-8') as f:
            json.dump(self.split_history, f, ensure_ascii=False, indent=2)
    
    def split_ticket(self, original_ticket_id: str,
                     new_tickets: List[Dict[str, Any]],
                     split_by: str) -> Dict[str, Any]:
        """Разделить тикет"""
        split_id = hashlib.md5(f"{original_ticket_id}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        split_record = {
            'split_id': split_id,
            'original_ticket_id': original_ticket_id,
            'new_ticket_ids': [t.get('id') for t in new_tickets],
            'split_by': split_by,
            'split_at': datetime.now().isoformat(),
            'new_tickets': new_tickets
        }
        
        self.split_history[split_id] = split_record
        self._save_split_history()
        
        return split_record
    
    def get_split_history(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Получить историю разделений"""
        history = []
        
        for split_id, record in self.split_history.items():
            if record['original_ticket_id'] == ticket_id or ticket_id in record['new_ticket_ids']:
                history.append(record)
        
        return history


class TicketCloner:
    """Клонирование тикетов"""
    
    def __init__(self):
        self.clone_history_file = 'data/ticket_clone_history.json'
        self.clone_history = self._load_clone_history()
    
    def _load_clone_history(self) -> Dict[str, Any]:
        """Загрузить историю клонирований"""
        if os.path.exists(self.clone_history_file):
            try:
                with open(self.clone_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_clone_history(self):
        """Сохранить историю клонирований"""
        os.makedirs('data', exist_ok=True)
        with open(self.clone_history_file, 'w', encoding='utf-8') as f:
            json.dump(self.clone_history, f, ensure_ascii=False, indent=2)
    
    def clone_ticket(self, original_ticket: Dict[str, Any],
                     cloned_by: str,
                     modifications: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ticket'ы klonla"""
        clone_id = hashlib.md5(f"{original_ticket.get('id')}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        # Klonlanлиш ticket создать
        cloned_ticket = original_ticket.copy()
        cloned_ticket['id'] = clone_id
        cloned_ticket['cloned_from'] = original_ticket.get('id')
        cloned_ticket['cloned_by'] = cloned_by
        cloned_ticket['cloned_at'] = datetime.now().isoformat()
        cloned_ticket['created_at'] = datetime.now().isoformat()
        cloned_ticket['status'] = 'open'
        
        # Изменениеleri uygula
        if modifications:
            cloned_ticket.update(modifications)
        
        # Kaydet
        self.clone_history[clone_id] = {
            'clone_id': clone_id,
            'original_ticket_id': original_ticket.get('id'),
            'cloned_by': cloned_by,
            'cloned_at': datetime.now().isoformat()
        }
        
        self._save_clone_history()
        
        return cloned_ticket
    
    def get_clone_history(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Получить историю клонирований"""
        history = []
        
        for clone_id, record in self.clone_history.items():
            if record['original_ticket_id'] == ticket_id:
                history.append(record)
        
        return history


class TicketDependencies:
    """Зависимости тикетов"""
    
    def __init__(self):
        self.dependencies_file = 'data/ticket_dependencies.json'
        self.dependencies = self._load_dependencies()
    
    def _load_dependencies(self) -> Dict[str, Any]:
        """Загрузить зависимости"""
        if os.path.exists(self.dependencies_file):
            try:
                with open(self.dependencies_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {'depends_on': {}, 'blocks': {}}
    
    def _save_dependencies(self):
        """Сохранить зависимости"""
        os.makedirs('data', exist_ok=True)
        with open(self.dependencies_file, 'w', encoding='utf-8') as f:
            json.dump(self.dependencies, f, ensure_ascii=False, indent=2)
    
    def add_dependency(self, ticket_id: str, depends_on_ticket_id: str) -> bool:
        """Добавить зависимость"""
        # Dёngю проверка
        if self._would_create_cycle(ticket_id, depends_on_ticket_id):
            return False
        
        if ticket_id not in self.dependencies['depends_on']:
            self.dependencies['depends_on'][ticket_id] = []
        
        if depends_on_ticket_id not in self.dependencies['depends_on'][ticket_id]:
            self.dependencies['depends_on'][ticket_id].append(depends_on_ticket_id)
        
        # Ters baгыmlыlыk
        if depends_on_ticket_id not in self.dependencies['blocks']:
            self.dependencies['blocks'][depends_on_ticket_id] = []
        
        if ticket_id not in self.dependencies['blocks'][depends_on_ticket_id]:
            self.dependencies['blocks'][depends_on_ticket_id].append(ticket_id)
        
        self._save_dependencies()
        
        return True
    
    def remove_dependency(self, ticket_id: str, depends_on_ticket_id: str) -> bool:
        """Удалить зависимость"""
        removed = False
        
        if ticket_id in self.dependencies['depends_on']:
            if depends_on_ticket_id in self.dependencies['depends_on'][ticket_id]:
                self.dependencies['depends_on'][ticket_id].remove(depends_on_ticket_id)
                removed = True
        
        if depends_on_ticket_id in self.dependencies['blocks']:
            if ticket_id in self.dependencies['blocks'][depends_on_ticket_id]:
                self.dependencies['blocks'][depends_on_ticket_id].remove(ticket_id)
                removed = True
        
        if removed:
            self._save_dependencies()
        
        return removed
    
    def _would_create_cycle(self, ticket_id: str, depends_on_ticket_id: str) -> bool:
        """Проверить, не создаст ли цикл"""
        # Basit dёngю проверка
        visited = set()
        
        def has_path(from_id: str, to_id: str) -> bool:
            if from_id == to_id:
                return True
            
            if from_id in visited:
                return False
            
            visited.add(from_id)
            
            for next_id in self.dependencies['depends_on'].get(from_id, []):
                if has_path(next_id, to_id):
                    return True
            
            return False
        
        return has_path(depends_on_ticket_id, ticket_id)
    
    def get_dependencies(self, ticket_id: str) -> List[str]:
        """Получить зависимости"""
        return self.dependencies['depends_on'].get(ticket_id, [])
    
    def get_blocked_tickets(self, ticket_id: str) -> List[str]:
        """Получить блокируемые тикеты"""
        return self.dependencies['blocks'].get(ticket_id, [])
    
    def can_close(self, ticket_id: str, tickets: Dict[str, Dict[str, Any]]) -> bool:
        """Проверить, можно ли закрыть"""
        dependencies = self.get_dependencies(ticket_id)
        
        for dep_id in dependencies:
            dep_ticket = tickets.get(dep_id)
            
            if dep_ticket and dep_ticket.get('status') != 'closed':
                return False
        
        return True


class SubTicketManager:
    """Менеджер подтикетов"""
    
    def __init__(self):
        self.subtickets_file = 'data/subtickets.json'
        self.subtickets = self._load_subtickets()
    
    def _load_subtickets(self) -> Dict[str, Any]:
        """Загрузить подтикеты"""
        if os.path.exists(self.subtickets_file):
            try:
                with open(self.subtickets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_subtickets(self):
        """Сохранить подтикеты"""
        os.makedirs('data', exist_ok=True)
        with open(self.subtickets_file, 'w', encoding='utf-8') as f:
            json.dump(self.subtickets, f, ensure_ascii=False, indent=2)
    
    def create_subticket(self, parent_ticket_id: str,
                         subticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """Alt ticket создать"""
        if parent_ticket_id not in self.subtickets:
            self.subtickets[parent_ticket_id] = []
        
        subticket = subticket_data.copy()
        subticket['parent_ticket_id'] = parent_ticket_id
        subticket['created_at'] = datetime.now().isoformat()
        
        self.subtickets[parent_ticket_id].append(subticket)
        self._save_subtickets()
        
        return subticket
    
    def get_subtickets(self, parent_ticket_id: str) -> List[Dict[str, Any]]:
        """Получить подтикеты"""
        return self.subtickets.get(parent_ticket_id, [])
    
    def delete_subticket(self, parent_ticket_id: str, subticket_id: str) -> bool:
        """Alt ticket'ы удалить"""
        if parent_ticket_id not in self.subtickets:
            return False
        
        subtickets = self.subtickets[parent_ticket_id]
        
        for i, subticket in enumerate(subtickets):
            if subticket.get('id') == subticket_id:
                del subtickets[i]
                self._save_subtickets()
                return True
        
        return False
    
    def get_parent_ticket(self, subticket_id: str) -> Optional[str]:
        """Получить родительский тикет"""
        for parent_id, subtickets in self.subtickets.items():
            for subticket in subtickets:
                if subticket.get('id') == subticket_id:
                    return parent_id
        
        return None
    
    def get_completion_percentage(self, parent_ticket_id: str,
                                  tickets: Dict[str, Dict[str, Any]]) -> float:
        """Получить процент выполнения"""
        subtickets = self.get_subtickets(parent_ticket_id)
        
        if not subtickets:
            return 0.0
        
        closed_count = sum(
            1 for st in subtickets
            if tickets.get(st.get('id'), {}).get('status') == 'closed'
        )
        
        return (closed_count / len(subtickets)) * 100


class CustomWorkflow:
    """Настраиваемый рабочий процесс"""
    
    def __init__(self):
        self.workflows_file = 'data/custom_workflows.json'
        self.workflows = self._load_workflows()
    
    def _load_workflows(self) -> Dict[str, Any]:
        """Загрузить рабочие процессы"""
        if os.path.exists(self.workflows_file):
            try:
                with open(self.workflows_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_workflows(self):
        """Сохранить рабочие процессы"""
        os.makedirs('data', exist_ok=True)
        with open(self.workflows_file, 'w', encoding='utf-8') as f:
            json.dump(self.workflows, f, ensure_ascii=False, indent=2)
    
    def create_workflow(self, name: str, category: str,
                        steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Создать рабочий процесс"""
        workflow_id = hashlib.md5(f"{name}{category}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        workflow = {
            'workflow_id': workflow_id,
            'name': name,
            'category': category,
            'steps': steps,
            'created_at': datetime.now().isoformat()
        }
        
        self.workflows[workflow_id] = workflow
        self._save_workflows()
        
        return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Получить рабочий процесс"""
        return self.workflows.get(workflow_id)
    
    def get_workflows_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Получить рабочие процессы по категории"""
        return [
            wf for wf in self.workflows.values()
            if wf.get('category') == category
        ]
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Удалить рабочий процесс"""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self._save_workflows()
            return True
        
        return False
    
    def get_next_step(self, workflow_id: str, current_step: int) -> Optional[Dict[str, Any]]:
        """Sonraki шагы al"""
        workflow = self.workflows.get(workflow_id)
        
        if not workflow:
            return None
        
        steps = workflow.get('steps', [])
        
        if current_step + 1 < len(steps):
            return steps[current_step + 1]
        
        return None


# Global instances
ticket_merger = TicketMerger()
ticket_splitter = TicketSplitter()
ticket_cloner = TicketCloner()
ticket_dependencies = TicketDependencies()
subticket_manager = SubTicketManager()
custom_workflow = CustomWorkflow()
