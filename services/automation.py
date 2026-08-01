"""
Automation & Workflows Engine
Движок автоматизации и рабочих процессов
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import uuid


class TriggerType(Enum):
    """Типы триггеров"""
    TICKET_CREATED = 'ticket_created'
    TICKET_UPDATED = 'ticket_updated'
    TICKET_CLOSED = 'ticket_closed'
    MESSAGE_ADDED = 'message_имяded'
    SCHEDULE = 'schedule'
    WEBHOOK = 'webhook'
    MANUAL = 'manual'


class ActionType(Enum):
    """Типы действий"""
    SEND_NOTIFICATION = 'send_notification'
    ASSIGN_TICKET = 'assign_ticket'
    UPDATE_PRIORITY = 'update_priority'
    ADD_TAG = 'имяd_tag'
    CLOSE_TICKET = 'close_ticket'
    ESCALATE = 'escalate'
    SEND_EMAIL = 'send_email'
    CREATE_JIRA_ISSUE = 'create_jira_issue'
    SEND_SLACK_MESSAGE = 'send_slack_message'
    SEND_TELEGRAM_MESSAGE = 'send_telegram_message'
    DELAY = 'delay'
    CONDITION = 'condition'


class ConditionOperator(Enum):
    """Операторы условий"""
    EQUALS = 'equals'
    NOT_EQUALS = 'not_equals'
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    GREATER_THAN = 'greater_than'
    LESS_THAN = 'less_than'
    IN = 'in'
    NOT_IN = 'not_in'


class Workflow:
    """Рабочий процесс"""
    
    def __init__(self, workflow_id: str, name: str, description: str = ''):
        self.id = workflow_id
        self.name = name
        self.description = description
        self.trigger = None
        self.conditions = []
        self.actions = []
        self.enabled = True
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.execution_count = 0
        self.last_executed = None
    
    def set_trigger(self, trigger_type: TriggerType, config: dict):
        """Установить триггер"""
        self.trigger = {
            'type': trigger_type.value,
            'config': config
        }
    
    def имяd_condition(self, field: str, operator: ConditionOperator, value: Any):
        """Добавить условие"""
        self.conditions.append({
            'field': field,
            'operator': operator.value,
            'value': value
        })
    
    def имяd_action(self, action_type: ActionType, config: dict):
        """Добавить действие"""
        self.actions.append({
            'type': action_type.value,
            'config': config
        })
    
    def to_dict(self) -> dict:
        """Преобразовать в словарь"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'trigger': self.trigger,
            'conditions': self.conditions,
            'actions': self.actions,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'execution_count': self.execution_count,
            'last_executed': self.last_executed
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Workflow':
        """Создать из словаря"""
        workflow = cls(data['id'], data['name'], data.get('description', ''))
        workflow.trigger = data.get('trigger')
        workflow.conditions = data.get('conditions', [])
        workflow.actions = data.get('actions', [])
        workflow.enabled = data.get('enabled', True)
        workflow.created_at = data.get('created_at', datetime.now().isoformat())
        workflow.updated_at = data.get('updated_at', datetime.now().isoformat())
        workflow.execution_count = data.get('execution_count', 0)
        workflow.last_executed = data.get('last_executed')
        return workflow


class AutomationEngine:
    """Движок автоматизации"""
    
    def __init__(self):
        self.workflows_file = 'data/workflows.json'
        self.workflows = self._loимя_workflows()
        self.action_handlers = {}
        self._register_default_handlers()
    
    def _loимя_workflows(self) -> Dict[str, Workflow]:
        """Загрузить рабочие процессы"""
        if os.path.exists(self.workflows_file):
            try:
                with open(self.workflows_file, 'r', encoding='utf-8') as f:
                    data = json.loимя(f)
                    return {
                        wf_id: Workflow.from_dict(wf_data)
                        for wf_id, wf_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_workflows(self):
        """Сохранить рабочие процессы"""
        os.maкотrs('data', exist_ok=True)
        data = {
            wf_id: wf.to_dict()
            for wf_id, wf in self.workflows.items()
        }
        
        with open(self.workflows_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _register_default_handlers(self):
        """Зарегистрировать стандартные обработчики действий"""
        self.register_action_handler(ActionType.SEND_NOTIFICATION, self._handle_send_notification)
        self.register_action_handler(ActionType.ASSIGN_TICKET, self._handle_assign_ticket)
        self.register_action_handler(ActionType.UPDATE_PRIORITY, self._handle_update_priority)
        self.register_action_handler(ActionType.ADD_TAG, self._handle_имяd_tag)
        self.register_action_handler(ActionType.CLOSE_TICKET, self._handle_close_ticket)
        self.register_action_handler(ActionType.ESCALATE, self._handle_escalate)
        self.register_action_handler(ActionType.DELAY, self._handle_delay)
    
    def register_action_handler(self, action_type: ActionType, handler: Callable):
        """Зарегистрировать обработчик действия"""
        self.action_handlers[action_type.value] = handler
    
    async def _handle_send_notification(self, context: dict, config: dict) -> bool:
        """Обработчик: отправить уведомление"""
        # Placeholder для отправки уведомления
        print(f"[Automation] Отправка уведомления: {config.get('message', '')}")
        return True
    
    async def _handle_assign_ticket(self, context: dict, config: dict) -> bool:
        """Обработчик: назначить тикет"""
        ticket_id = context.get('ticket_id')
        assignee = config.get('assignee')
        print(f"[Automation] Назначение тикета {ticket_id} пользователю {assignee}")
        return True
    
    async def _handle_update_priority(self, context: dict, config: dict) -> bool:
        """Обработчик: обновить приоритет"""
        ticket_id = context.get('ticket_id')
        priority = config.get('priority')
        print(f"[Automation] Обновление приоритета тикета {ticket_id} на {priority}")
        return True
    
    async def _handle_имяd_tag(self, context: dict, config: dict) -> bool:
        """Обработчик: добавить тег"""
        ticket_id = context.get('ticket_id')
        tag = config.get('tag')
        print(f"[Automation] Добавление тега '{tag}' к тикету {ticket_id}")
        return True
    
    async def _handle_close_ticket(self, context: dict, config: dict) -> bool:
        """Обработчик: закрыть тикет"""
        ticket_id = context.get('ticket_id')
        print(f"[Automation] Закрытие тикета {ticket_id}")
        return True
    
    async def _handle_escalate(self, context: dict, config: dict) -> bool:
        """Обработчик: эскалация"""
        ticket_id = context.get('ticket_id')
        level = config.get('level', 1)
        print(f"[Automation] Эскалация тикета {ticket_id} на уровень {level}")
        return True
    
    async def _handle_delay(self, context: dict, config: dict) -> bool:
        """Обработчик: задержка"""
        seconds = config.get('seconds', 0)
        await asyncio.sleep(seconds)
        return True
    
    def _evaluate_condition(self, condition: dict, context: dict) -> bool:
        """Оценить условие"""
        field = condition['field']
        operator = condition['operator']
        expected_value = condition['value']
        
        # Получить значение поля из контекста
        actual_value = context.get(field)
        
        if operator == ConditionOperator.EQUALS.value:
            return actual_value == expected_value
        elif operator == ConditionOperator.NOT_EQUALS.value:
            return actual_value != expected_value
        elif operator == ConditionOperator.CONTAINS.value:
            return expected_value in str(actual_value)
        elif operator == ConditionOperator.NOT_CONTAINS.value:
            return expected_value not in str(actual_value)
        elif operator == ConditionOperator.GREATER_THAN.value:
            return actual_value > expected_value
        elif operator == ConditionOperator.LESS_THAN.value:
            return actual_value < expected_value
        elif operator == ConditionOperator.IN.value:
            return actual_value in expected_value
        elif operator == ConditionOperator.NOT_IN.value:
            return actual_value not in expected_value
        
        return False
    
    def _check_conditions(self, workflow: Workflow, context: dict) -> bool:
        """Проверить все условия"""
        if not workflow.conditions:
            return True
        
        return all(
            self._evaluate_condition(condition, context)
            for condition in workflow.conditions
        )
    
    async def execute_workflow(self, workflow: Workflow, context: dict) -> bool:
        """Выполнить рабочий процесс"""
        if not workflow.enabled:
            return False
        
        # Проверить условия
        if not self._check_conditions(workflow, context):
            return False
        
        # Выполнить действия
        success = True
        for action in workflow.actions:
            action_type = action['type']
            config = action['config']
            
            handler = self.action_handlers.get(action_type)
            if handler:
                try:
                    result = await handler(context, config)
                    if not result:
                        success = False
                        break
                except Exception as e:
                    print(f"[Automation] Ошибка выполнения действия {action_type}: {e}")
                    success = False
                    break
            else:
                print(f"[Automation] Неизвестный тип действия: {action_type}")
                success = False
                break
        
        # Обновить статистику
        workflow.execution_count += 1
        workflow.last_executed = datetime.now().isoformat()
        workflow.updated_at = datetime.now().isoformat()
        self._save_workflows()
        
        return success
    
    async def trigger_workflows(self, trigger_type: TriggerType, context: dict):
        """Запустить рабочие процессы по триггеру"""
        for workflow in self.workflows.values():
            if not workflow.enabled or not workflow.trigger:
                continue
            
            if workflow.trigger['type'] == trigger_type.value:
                await self.execute_workflow(workflow, context)
    
    def create_workflow(self, name: str, description: str = '') -> Workflow:
        """Создать новый рабочий процесс"""
        workflow_id = str(uuid.uuid4())[:8]
        workflow = Workflow(workflow_id, name, description)
        self.workflows[workflow_id] = workflow
        self._save_workflows()
        return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Получить рабочий процесс"""
        return self.workflows.get(workflow_id)
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Удалить рабочий процесс"""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self._save_workflows()
            return True
        return False
    
    def list_workflows(self) -> List[Workflow]:
        """Получить список всех рабочих процессов"""
        return list(self.workflows.values())
    
    def enable_workflow(self, workflow_id: str) -> bool:
        """Включить рабочий процесс"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            workflow.enabled = True
            workflow.updated_at = datetime.now().isoformat()
            self._save_workflows()
            return True
        return False
    
    def disable_workflow(self, workflow_id: str) -> bool:
        """Отключить рабочий процесс"""
        workflow = self.workflows.get(workflow_id)
        if workflow:
            workflow.enabled = False
            workflow.updated_at = datetime.now().isoformat()
            self._save_workflows()
            return True
        return False


# Глобальный экземпляр
automation_engine = AutomationEngine()
