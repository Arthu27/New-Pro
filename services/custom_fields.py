"""
Custom Fields
Система пользовательских полей
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import re


class CustomField:
    """Особый alan"""
    
    FIELD_TYPES = ['text', 'number', 'date', 'select', 'multiselect', 'checkbox', 'url', 'email']
    
    def __init__(self, field_id: str, name: str, field_type: str,
                 required: bool = False, description: str = ''):
        self.field_id = field_id
        self.name = name
        self.field_type = field_type
        self.required = required
        self.description = description
        self.options = []  # For select/multiselect
        self.default_value = None
        self.validation_rules = {}
        self.conditions = []
    
    def add_option(self, value: str, label: str):
        """Добавить вариант (select/multiselect для)"""
        if self.field_type in ['select', 'multiselect']:
            self.options.append({'value': value, 'label': label})
    
    def set_default_value(self, value: Any):
        """Настроить значение по умолчанию"""
        self.default_value = value
    
    def add_validation_rule(self, rule_type: str, value: Any):
        """Doğrulama kuralı добавить"""
        self.validation_rules[rule_type] = value
    
    def add_condition(self, field_id: str, operator: str, value: Any):
        """Koşul добавить (bu alan ne zaman görünür)"""
        self.conditions.append({
            'field_id': field_id,
            'operator': operator,
            'value': value
        })
    
    def validate(self, value: Any) -> Dict[str, Any]:
        """Değeri doğrula"""
        errors = []
        
        # Zorunlu kontrolü
        if self.required and (value is None or value == ''):
            errors.append('Bu alan zorunludur')
            return {'valid': False, 'errors': errors}
        
        # Boşsa ve zorunlu değilse geçerli
        if value is None or value == '':
            return {'valid': True, 'errors': []}
        
        # Tip kontrolü
        if self.field_type == 'number':
            try:
                num_value = float(value)
                
                # Min/max kontrolü
                if 'min' in self.validation_rules and num_value < self.validation_rules['min']:
                    errors.append(f"Değer en az {self.validation_rules['min']} olmalıdır")
                
                if 'max' in self.validation_rules and num_value > self.validation_rules['max']:
                    errors.append(f"Değer en fazla {self.validation_rules['max']} olmalıdır")
            except (ValueError, TypeError):
                errors.append('Geçerli bir sayı giriniz')
        
        elif self.field_type == 'email':
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, str(value)):
                errors.append('Geçerli bir e-posta adresi giriniz')
        
        elif self.field_type == 'url':
            url_pattern = r'^https?://'
            if not re.match(url_pattern, str(value)):
                errors.append('Geçerli bir URL giriniz (http:// или https://)')
        
        elif self.field_type == 'date':
            try:
                datetime.fromisoformat(str(value))
            except ValueError:
                errors.append('Geçerli bir tarih giriniz (YYYY-MM-DD)')
        
        elif self.field_type == 'select':
            valid_values = [opt['value'] for opt in self.options]
            if value not in valid_values:
                errors.append('Geçerli bir seçenek seçiniz')
        
        elif self.field_type == 'multiselect':
            valid_values = [opt['value'] for opt in self.options]
            if not isinstance(value, list):
                errors.append('Birden fazla seçenek seçiniz')
            elif not all(v in valid_values for v in value):
                errors.append('Geçersiz seçenekler var')
        
        # Uzunluk kontrolü
        if 'max_length' in self.validation_rules:
            if len(str(value)) > self.validation_rules['max_length']:
                errors.append(f"Değer en fazla {self.validation_rules['max_length']} karakter olabilir")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def should_display(self, field_values: Dict[str, Any]) -> bool:
        """Görüntülenip görüntülenmeyeceğini проверить et"""
        if not self.conditions:
            return True
        
        for condition in self.conditions:
            field_id = condition['field_id']
            operator = condition['operator']
            expected_value = condition['value']
            
            actual_value = field_values.get(field_id)
            
            if operator == 'equals' and actual_value != expected_value:
                return False
            elif operator == 'not_equals' and actual_value == expected_value:
                return False
            elif operator == 'contains' and expected_value not in str(actual_value):
                return False
            elif operator == 'in' and actual_value not in expected_value:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e çevir"""
        return {
            'field_id': self.field_id,
            'name': self.name,
            'field_type': self.field_type,
            'required': self.required,
            'description': self.description,
            'options': self.options,
            'default_value': self.default_value,
            'validation_rules': self.validation_rules,
            'conditions': self.conditions
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CustomField':
        """Создать из словаря"""
        field = cls(
            field_id=data['field_id'],
            name=data['name'],
            field_type=data['field_type'],
            required=data.get('required', False),
            description=data.get('description', '')
        )
        field.options = data.get('options', [])
        field.default_value = data.get('default_value')
        field.validation_rules = data.get('validation_rules', {})
        field.conditions = data.get('conditions', [])
        return field


class CustomFieldManager:
    """Особый alan yöneticisi"""
    
    def __init__(self):
        self.fields_file = 'data/custom_fields.json'
        self.fields = self._load_fields()
    
    def _load_fields(self) -> Dict[str, CustomField]:
        """Alanları загрузить"""
        if os.path.exists(self.fields_file):
            try:
                with open(self.fields_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        field_id: CustomField.from_dict(field_data)
                        for field_id, field_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_fields(self):
        """Alanları сохранить"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            field_id: field.to_dict()
            for field_id, field in self.fields.items()
        }
        
        with open(self.fields_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_field(self, name: str, field_type: str,
                     required: bool = False, description: str = '') -> CustomField:
        """Alan создать"""
        field_id = f"field_{len(self.fields) + 1}"
        
        field = CustomField(
            field_id=field_id,
            name=name,
            field_type=field_type,
            required=required,
            description=description
        )
        
        self.fields[field_id] = field
        self._save_fields()
        
        return field
    
    def update_field(self, field_id: str, **kwargs) -> Optional[CustomField]:
        """Alanı обновить"""
        if field_id not in self.fields:
            return None
        
        field = self.fields[field_id]
        
        for key, value in kwargs.items():
            if hasattr(field, key):
                setattr(field, key, value)
        
        self._save_fields()
        
        return field
    
    def delete_field(self, field_id: str) -> bool:
        """Alanı удалить"""
        if field_id in self.fields:
            del self.fields[field_id]
            self._save_fields()
            return True
        
        return False
    
    def get_field(self, field_id: str) -> Optional[CustomField]:
        """Alanı al"""
        return self.fields.get(field_id)
    
    def get_all_fields(self) -> List[CustomField]:
        """Tüm alanları al"""
        return list(self.fields.values())
    
    def get_fields_by_type(self, field_type: str) -> List[CustomField]:
        """Tip'e по alanları al"""
        return [f for f in self.fields.values() if f.field_type == field_type]
    
    def validate_ticket_data(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ticket verilerini doğrula"""
        errors = {}
        
        for field_id, field in self.fields.items():
            value = ticket_data.get(field_id)
            
            # Görüntülenip görüntülenmeyeceğini проверить et
            if not field.should_display(ticket_data):
                continue
            
            validation_result = field.validate(value)
            
            if not validation_result['valid']:
                errors[field_id] = validation_result['errors']
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def get_display_fields(self, ticket_data: Dict[str, Any]) -> List[CustomField]:
        """Görüntülenecek alanları al"""
        return [
            field for field in self.fields.values()
            if field.should_display(ticket_data)
        ]


class CustomFieldValueStorage:
    """Особый alan değer deposu"""
    
    def __init__(self):
        self.values_file = 'data/custom_field_values.json'
        self.values = self._load_values()
    
    def _load_values(self) -> Dict[str, Any]:
        """Değerleri загрузить"""
        if os.path.exists(self.values_file):
            try:
                with open(self.values_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_values(self):
        """Değerleri сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.values_file, 'w', encoding='utf-8') as f:
            json.dump(self.values, f, ensure_ascii=False, indent=2)
    
    def set_value(self, ticket_id: str, field_id: str, value: Any):
        """Değer настроить"""
        if ticket_id not in self.values:
            self.values[ticket_id] = {}
        
        self.values[ticket_id][field_id] = value
        self._save_values()
    
    def get_value(self, ticket_id: str, field_id: str) -> Any:
        """Değeri al"""
        return self.values.get(ticket_id, {}).get(field_id)
    
    def get_all_values(self, ticket_id: str) -> Dict[str, Any]:
        """Tüm değerleri al"""
        return self.values.get(ticket_id, {})
    
    def delete_ticket_values(self, ticket_id: str):
        """Ticket değerlerini удалить"""
        if ticket_id in self.values:
            del self.values[ticket_id]
            self._save_values()
    
    def delete_field_values(self, field_id: str):
        """Alan değerlerini удалить"""
        for ticket_id in self.values:
            if field_id in self.values[ticket_id]:
                del self.values[ticket_id][field_id]
        
        self._save_values()


class CustomFieldTemplate:
    """Особый alan şablonu"""
    
    def __init__(self, field_manager: CustomFieldManager):
        self.field_manager = field_manager
        self.templates_file = 'data/custom_field_templates.json'
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Any]:
        """Şablonları загрузить"""
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_templates(self):
        """Şablonları сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.templates_file, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
    
    def create_template(self, name: str, category: str,
                        field_ids: List[str]) -> Dict[str, Any]:
        """Şablon создать"""
        template_id = f"template_{len(self.templates) + 1}"
        
        template = {
            'template_id': template_id,
            'name': name,
            'category': category,
            'field_ids': field_ids,
            'created_at': datetime.now().isoformat()
        }
        
        self.templates[template_id] = template
        self._save_templates()
        
        return template
    
    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Şablonu al"""
        return self.templates.get(template_id)
    
    def get_templates_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Kategoriye по şablonları al"""
        return [
            t for t in self.templates.values()
            if t.get('category') == category
        ]
    
    def get_template_fields(self, template_id: str) -> List[CustomField]:
        """Şablon alanlarını al"""
        template = self.templates.get(template_id)
        
        if not template:
            return []
        
        field_ids = template.get('field_ids', [])
        
        return [
            self.field_manager.get_field(field_id)
            for field_id in field_ids
            if self.field_manager.get_field(field_id)
        ]
    
    def delete_template(self, template_id: str) -> bool:
        """Şablonu удалить"""
        if template_id in self.templates:
            del self.templates[template_id]
            self._save_templates()
            return True
        
        return False


class CustomFieldPermissions:
    """Особый alan izinleri"""
    
    def __init__(self):
        self.permissions_file = 'data/custom_field_permissions.json'
        self.permissions = self._load_permissions()
    
    def _load_permissions(self) -> Dict[str, Any]:
        """İzinleri загрузить"""
        if os.path.exists(self.permissions_file):
            try:
                with open(self.permissions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_permissions(self):
        """İzinleri сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.permissions_file, 'w', encoding='utf-8') as f:
            json.dump(self.permissions, f, ensure_ascii=False, indent=2)
    
    def set_field_permissions(self, field_id: str, 
                              can_view: List[str],
                              can_edit: List[str]):
        """Alan izinlerini настроить"""
        self.permissions[field_id] = {
            'can_view': can_view,
            'can_edit': can_edit
        }
        
        self._save_permissions()
    
    def can_view_field(self, field_id: str, user_role: str) -> bool:
        """Alanı görüntüleyip görüntüleyemeyeceğini проверить et"""
        if field_id not in self.permissions:
            return True  # Varsayılan: herkes görebilir
        
        can_view = self.permissions[field_id].get('can_view', [])
        
        if not can_view:
            return True  # Boşsa herkes görebilir
        
        return user_role in can_view
    
    def can_edit_field(self, field_id: str, user_role: str) -> bool:
        """Alanı düzenleyip düzenleyemeyeceğini проверить et"""
        if field_id not in self.permissions:
            return True  # Varsayılan: herkes düzenleyebilir
        
        can_edit = self.permissions[field_id].get('can_edit', [])
        
        if not can_edit:
            return True  # Boşsa herkes düzenleyebilir
        
        return user_role in can_edit
    
    def get_field_permissions(self, field_id: str) -> Dict[str, List[str]]:
        """Alan izinlerini al"""
        return self.permissions.get(field_id, {
            'can_view': [],
            'can_edit': []
        })


# Global instances
custom_field_manager = CustomFieldManager()
custom_field_value_storage = CustomFieldValueStorage()
custom_field_template = CustomFieldTemplate(custom_field_manager)
custom_field_permissions = CustomFieldPermissions()
