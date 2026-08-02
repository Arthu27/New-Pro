"""
Changelog
Система журнала изменений
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
from enum import Enum


class ChangeType(Enum):
    """Изменение tipi"""
    ADDED = 'added'
    CHANGED = 'changed'
    FIXED = 'fixed'
    REMOVED = 'removed'
    DEPRECATED = 'deprecated'
    SECURITY = 'security'


class ChangeSeverity(Enum):
    """Изменение ёnemi"""
    MAJOR = 'major'
    MINOR = 'minor'
    PATCH = 'patch'


class ChangelogEntry:
    """Журнал изменений записейi"""
    
    def __init__(self, entry_id: str, version: str, change_type: ChangeType,
                 title: str, description: str = ''):
        self.entry_id = entry_id
        self.version = version
        self.change_type = change_type
        self.title = title
        self.description = description
        self.severity = ChangeSeverity.MINOR
        self.author = None
        self.timestamp = datetime.now()
        self.tags = []
        self.affected_components = []
        self.breaking_change = False
        self.migration_guide = None
        self.related_issues = []
        self.metadata = {}
    
    def set_severity(self, severity: ChangeSeverity):
        """Ёnem derecesi настроить"""
        self.severity = severity
    
    def set_author(self, author: str):
        """Написатьar настроить"""
        self.author = author
    
    def add_tag(self, tag: str):
        """Добавить метку"""
        if tag not in self.tags:
            self.tags.append(tag)
    
    def add_affected_component(self, component: str):
        """Etkilenen bileшen добавить"""
        if component not in self.affected_components:
            self.affected_components.append(component)
    
    def mark_breaking_change(self, migration_guide: str = None):
        """Kыrыlma deгiшikliгi как iшaretle"""
        self.breaking_change = True
        self.migration_guide = migration_guide
        self.severity = ChangeSeverity.MAJOR
    
    def add_related_issue(self, issue_id: str):
        """Иlgili sorun добавить"""
        if issue_id not in self.related_issues:
            self.related_issues.append(issue_id)
    
    def add_metadata(self, key: str, value: Any):
        """Metadata добавить"""
        self.metadata[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Dict'e чevir"""
        return {
            'entry_id': self.entry_id,
            'version': self.version,
            'change_type': self.change_type.value,
            'title': self.title,
            'description': self.description,
            'severity': self.severity.value,
            'author': self.author,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags,
            'affected_components': self.affected_components,
            'breaking_change': self.breaking_change,
            'migration_guide': self.migration_guide,
            'related_issues': self.related_issues,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChangelogEntry':
        """Создать из словаря"""
        entry = cls(
            entry_id=data['entry_id'],
            version=data['version'],
            change_type=ChangeType(data['change_type']),
            title=data['title'],
            description=data.get('description', '')
        )
        entry.severity = ChangeSeverity(data.get('severity', 'minor'))
        entry.author = data.get('author')
        entry.timestamp = datetime.fromisoformat(data['timestamp'])
        entry.tags = data.get('tags', [])
        entry.affected_components = data.get('affected_components', [])
        entry.breaking_change = data.get('breaking_change', False)
        entry.migration_guide = data.get('migration_guide')
        entry.related_issues = data.get('related_issues', [])
        entry.metadata = data.get('metadata', {})
        return entry


class ChangelogManager:
    """Журнал изменений yёneticisi"""
    
    def __init__(self):
        self.changelog_file = 'data/changelog.json'
        self.entries = self._load_entries()
    
    def _load_entries(self) -> Dict[str, ChangelogEntry]:
        """Загрузить записи"""
        if os.path.exists(self.changelog_file):
            try:
                with open(self.changelog_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        entry_id: ChangelogEntry.from_dict(entry_data)
                        for entry_id, entry_data in data.items()
                    }
            except Exception:
                pass
        
        return {}
    
    def _save_entries(self):
        """Сохранить записи"""
        os.makedirs('data', exist_ok=True)
        
        data = {
            entry_id: entry.to_dict()
            for entry_id, entry in self.entries.items()
        }
        
        with open(self.changelog_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_entry(self, version: str, change_type: ChangeType, title: str,
                  description: str = '', author: str = None) -> ChangelogEntry:
        """Вход добавить"""
        entry_id = f"entry_{len(self.entries) + 1}"
        
        entry = ChangelogEntry(
            entry_id=entry_id,
            version=version,
            change_type=change_type,
            title=title,
            description=description
        )
        entry.author = author
        
        self.entries[entry_id] = entry
        self._save_entries()
        
        return entry
    
    def get_entry(self, entry_id: str) -> Optional[ChangelogEntry]:
        """Входi al"""
        return self.entries.get(entry_id)
    
    def get_all_entries(self, version: str = None, change_type: ChangeType = None,
                        severity: ChangeSeverity = None) -> List[ChangelogEntry]:
        """Все записейleri al"""
        entries = list(self.entries.values())
        
        if version:
            entries = [e for e in entries if e.version == version]
        
        if change_type:
            entries = [e for e in entries if e.change_type == change_type]
        
        if severity:
            entries = [e for e in entries if e.severity == severity]
        
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        
        return entries
    
    def get_entries_by_version(self, version: str) -> List[ChangelogEntry]:
        """Versiyona по записейleri al"""
        return self.get_all_entries(version=version)
    
    def get_entries_by_type(self, change_type: ChangeType) -> List[ChangelogEntry]:
        """Tip'e по записейleri al"""
        return self.get_all_entries(change_type=change_type)
    
    def get_breaking_changes(self) -> List[ChangelogEntry]:
        """Kыrыlma изменениеlerini al"""
        return [e for e in self.entries.values() if e.breaking_change]
    
    def get_recent_entries(self, limit: int = 10) -> List[ChangelogEntry]:
        """Son записейleri al"""
        entries = list(self.entries.values())
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]
    
    def delete_entry(self, entry_id: str) -> bool:
        """Входi удалить"""
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save_entries()
            return True
        
        return False
    
    def get_all_versions(self) -> List[str]:
        """Все версийlarы al"""
        versions = set(entry.version for entry in self.entries.values())
        return sorted(list(versions), reverse=True)


class ChangelogGenerator:
    """Журнал изменений создатьucu"""
    
    def __init__(self, changelog_manager: ChangelogManager):
        self.changelog_manager = changelog_manager
    
    def generate_markdown(self, version: str = None) -> str:
        """Markdown создать"""
        if version:
            entries = self.changelog_manager.get_entries_by_version(version)
        else:
            entries = self.changelog_manager.get_all_entries()
        
        if not entries:
            return "# Changelog\n\nNo entries found."
        
        # Versiyonlara по grupla
        by_version = defaultdict(list)
        for entry in entries:
            by_version[entry.version].append(entry)
        
        markdown = "# Changelog\n\n"
        
        for version in sorted(by_version.keys(), reverse=True):
            version_entries = by_version[version]
            
            markdown += f"## [{version}] - {version_entries[0].timestamp.strftime('%Y-%m-%d')}\n\n"
            
            # Tip'e по grupla
            by_type = defaultdict(list)
            for entry in version_entries:
                by_type[entry.change_type].append(entry)
            
            # Имяded
            if ChangeType.ADDED in by_type:
                markdown += "### Имяded\n\n"
                for entry in by_type[ChangeType.ADDED]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Changed
            if ChangeType.CHANGED in by_type:
                markdown += "### Changed\n\n"
                for entry in by_type[ChangeType.CHANGED]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Fixed
            if ChangeType.FIXED in by_type:
                markdown += "### Fixed\n\n"
                for entry in by_type[ChangeType.FIXED]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Removed
            if ChangeType.REMOVED in by_type:
                markdown += "### Removed\n\n"
                for entry in by_type[ChangeType.REMOVED]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Deprecated
            if ChangeType.DEPRECATED in by_type:
                markdown += "### Deprecated\n\n"
                for entry in by_type[ChangeType.DEPRECATED]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Security
            if ChangeType.SECURITY in by_type:
                markdown += "### Security\n\n"
                for entry in by_type[ChangeType.SECURITY]:
                    markdown += f"- {entry.title}"
                    if entry.description:
                        markdown += f" - {entry.description}"
                    markdown += "\n"
                markdown += "\n"
            
            # Breaking changes
            breaking_changes = [e for e in version_entries if e.breaking_change]
            if breaking_changes:
                markdown += "### Breaking Changes\n\n"
                for entry in breaking_changes:
                    markdown += f"- **{entry.title}**"
                    if entry.migration_guide:
                        markdown += f"\n - Migration: {entry.migration_guide}"
                    markdown += "\n"
                markdown += "\n"
        
        return markdown
    
    def generate_html(self, version: str = None) -> str:
        """HTML создать"""
        markdown = self.generate_markdown(version)
        
        # Basit markdown -> HTML dёnюшюmю
        html = markdown.replace('# ', '<h1>').replace('\n\n', '</h1>\n')
        html = html.replace('## ', '<h2>').replace('\n\n', '</h2>\n')
        html = html.replace('### ', '<h3>').replace('\n\n', '</h3>\n')
        html = html.replace('- ', '<li>').replace('\n', '</li>\n')
        
        html = f"""<!DOCTYPE html>
<html>
<head>
 <meta charset="UTF-8">
 <title>Changelog</title>
 <style>
 body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
 h1 {{ color: #333; border-bottom: 2px solid #333; }}
 h2 {{ color: #555; border-bottom: 1px solid #ccc; }}
 h3 {{ color: #777; }}
 li {{ margin: 5px 0; }}
 </style>
</head>
<body>
{html}
</body>
</html>"""
        return html
    
    def generate_json(self, version: str = None) -> str:
        """JSON создать"""
        if version:
            entries = self.changelog_manager.get_entries_by_version(version)
        else:
            entries = self.changelog_manager.get_all_entries()
        
        data = {
            'changelog': [entry.to_dict() for entry in entries]
        }
        
        return json.dumps(data, ensure_ascii=False, indent=2)


class ChangelogNotification:
    """Журнал изменений уведомлениеi"""
    
    def __init__(self, changelog_manager: ChangelogManager):
        self.changelog_manager = changelog_manager
        self.subscriptions_file = 'data/changelog_subscriptions.json'
        self.subscriptions = self._load_subscriptions()
    
    def _load_subscriptions(self) -> Dict[str, Any]:
        """Abonelikleri загрузить"""
        if os.path.exists(self.subscriptions_file):
            try:
                with open(self.subscriptions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {}
    
    def _save_subscriptions(self):
        """Abonelikleri сохранить"""
        os.makedirs('data', exist_ok=True)
        with open(self.subscriptions_file, 'w', encoding='utf-8') as f:
            json.dump(self.subscriptions, f, ensure_ascii=False, indent=2)
    
    def subscribe(self, user_id: str, notification_types: List[str] = None):
        """Abone ol"""
        self.subscriptions[user_id] = {
            'notification_types': notification_types or ['major', 'minor'],
            'subscribed_at': datetime.now().isoformat()
        }
        
        self._save_subscriptions()
    
    def unsubscribe(self, user_id: str) -> bool:
        """Abonelikten выйти"""
        if user_id in self.subscriptions:
            del self.subscriptions[user_id]
            self._save_subscriptions()
            return True
        
        return False
    
    def get_subscribers(self, severity: ChangeSeverity) -> List[str]:
        """Aboneleri al"""
        subscribers = []
        
        for user_id, subscription in self.subscriptions.items():
            notification_types = subscription.get('notification_types', [])
            
            if severity.value in notification_types:
                subscribers.append(user_id)
        
        return subscribers
    
    def should_notify(self, entry: ChangelogEntry, user_id: str) -> bool:
        """Уведомление gёnderilip gёnderilmeyeceгini проверить et"""
        if user_id not in self.subscriptions:
            return False
        
        subscription = self.subscriptions[user_id]
        notification_types = subscription.get('notification_types', [])
        
        return entry.severity.value in notification_types


# Global instances
changelog_manager = ChangelogManager()
changelog_generator = ChangelogGenerator(changelog_manager)
changelog_notification = ChangelogNotification(changelog_manager)
