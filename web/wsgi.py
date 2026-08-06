"""
WSGI entry point — загружается gunicorn.
- Можно использовать и 'web.app:app', но этот модуль есть,
  чтобы гарантировать правильный порядок инициализации flask_session и др.
"""
import os 
import sys 

# Root path добавить ki 'from web.app import app' calissin
_HERE =os .path .dirname (os .path .abspath (__file__ ))
_ROOT =os .path .abspath (os .path .join (_HERE ,'..'))
if _ROOT not in sys .path :
    sys .path .insert (0 ,_ROOT )

from web .app import app # noqa: E402

# Gunicorn 'application' degiskenini veya 'app' degiskenini arar
application =app 
