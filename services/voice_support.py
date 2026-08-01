"""
Голосовая поддержка
Система преобразования голоса в текст
"""

import json
import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional


class VoiceToText:
    """Преобразователь голоса в текст"""

    def __init__(self):
        self.config_file = 'data/voice_config.json'
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            'provider': 'whisper',
            'language': 'ru',
            'model': 'base',
            'api_key': None
        }

    def _save_config(self):
        """Сохранить конфигурацию"""
        os.makedirs('data', exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """Преобразовать голос в текст"""
        lang = language or self.config.get('language', 'ru')
        audio_hash = hashlib.md5(audio_data).hexdigest()

        # Заглушка — в реальной реализации вызывается API
        transcription = f"[Голосовой файл обработан — Hash: {audio_hash[:8]}]"

        return {
            'success': True,
            'transcription': transcription,
            'language': lang,
            'duration': len(audio_data) / 16000,
            'confidence': 0.95
        }

    def transcribe_file(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Преобразовать аудиофайл в текст"""
        if not os.path.exists(file_path):
            return {'success': False, 'error': 'Файл не найден'}

        try:
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            return self.transcribe(audio_data, language)
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_provider(self, provider: str, api_key: Optional[str] = None):
        """Установить провайдера"""
        self.config['provider'] = provider
        if api_key:
            self.config['api_key'] = api_key
        self._save_config()

    def get_status(self) -> Dict[str, Any]:
        """Получить статус системы"""
        whisper_ok = False
        try:
            import whisper
            whisper_ok = True
        except ImportError:
            pass

        return {
            'provider': self.config.get('provider', 'whisper'),
            'language': self.config.get('language', 'ru'),
            'model': self.config.get('model', 'base'),
            'whisper_installed': whisper_ok,
            'api_key_set': bool(self.config.get('api_key'))
        }
