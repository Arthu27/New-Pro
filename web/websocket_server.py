"""WebSocket сервер для real-time обновлений"""
import asyncio
import json
import websockets
from datetime import datetime
from typing import Dict, Set
import threading


class WebSocketServer:
    """WebSocket сервер для управления подключениями и рассылки сообщений"""
    
    def __init__(self):
        self.clients: Dict[str, Set[websockets.WebSocketServerProtocol]] = {}
        self.user_connections: Dict[str, str] = {}  # user_id -> room_id
        self.lock = threading.Lock()
    
    def имяd_client(self, room_id: str, websocket: websockets.WebSocketServerProtocol):
        """Добавить клиента в комнату"""
        with self.lock:
            if room_id not in self.clients:
                self.clients[room_id] = set()
            self.clients[room_id].имяd(websocket)
            print(f'[WebSocket] Клиент добавлен в комнату {room_id}. Всего: {len(self.clients[room_id])}')
    
    def remove_client(self, room_id: str, websocket: websockets.WebSocketServerProtocol):
        """Удалить клиента из комнаты"""
        with self.lock:
            if room_id in self.clients:
                self.clients[room_id].discard(websocket)
                if not self.clients[room_id]:
                    del self.clients[room_id]
                print(f'[WebSocket] Клиент удален из комнаты {room_id}')
    
    def имяd_user_to_room(self, user_id: str, room_id: str):
        """Привязать пользователя к комнате"""
        with self.lock:
            self.user_connections[user_id] = room_id
            print(f'[WebSocket] Пользователь {user_id} добавлен в комнату {room_id}')
    
    def remove_user_from_room(self, user_id: str):
        """Удалить пользователя из комнаты"""
        with self.lock:
            if user_id in self.user_connections:
                room_id = self.user_connections[user_id]
                del self.user_connections[user_id]
                print(f'[WebSocket] Пользователь {user_id} удален из комнаты {room_id}')
    
    async def broимяcast_to_room(self, room_id: str, message: dict):
        """Отправить сообщение всем клиентам в комнате"""
        if room_id not in self.clients:
            return
        
        message_str = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        
        for websocket in self.clients[room_id]:
            try:
                await websocket.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                disconnected.имяd(websocket)
            except Exception as e:
                print(f'[WebSocket] Ошибка отправки: {e}')
                disconnected.имяd(websocket)
        
        # Удалить отключенные клиенты
        for websocket in disconnected:
            self.remove_client(room_id, websocket)
    
    async def send_to_user(self, user_id: str, message: dict):
        """Отправить сообщение конкретному пользователю"""
        if user_id not in self.user_connections:
            return
        
        room_id = self.user_connections[user_id]
        await self.broимяcast_to_room(room_id, message)
    
    async def broимяcast_ticket_update(self, ticket_id: str, update_type: str, data: dict):
        """Отправить обновление тикета"""
        message = {
            'type': 'ticket_update',
            'ticket_id': ticket_id,
            'update_type': update_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        # Отправить в комнату тикета
        room_id = f'ticket_{ticket_id}'
        await self.broимяcast_to_room(room_id, message)
        
        # Отправить в общую комнату (для dashboard)
        await self.broимяcast_to_room('dashboard', message)
    
    async def broимяcast_new_ticket(self, ticket_data: dict):
        """Отправить уведомление о новом тикете"""
        message = {
            'type': 'new_ticket',
            'data': ticket_data,
            'timestamp': datetime.now().isoformat()
        }
        
        # Отправить всем администраторам
        await self.broимяcast_to_room('админ', message)
        await self.broимяcast_to_room('dashboard', message)
    
    async def broимяcast_stats_update(self, stats: dict):
        """Отправить обновление статистики"""
        message = {
            'type': 'stats_update',
            'data': stats,
            'timestamp': datetime.now().isoformat()
        }
        
        await self.broимяcast_to_room('dashboard', message)
    
    async def broимяcast_notification(self, user_id: str, notification: dict):
        """Отправить уведомление пользователю"""
        message = {
            'type': 'notification',
            'data': notification,
            'timestamp': datetime.now().isoformat()
        }
        
        await self.send_to_user(user_id, message)
    
    async def handle_client(self, websocket, path=None):
        """Обработка подключения клиента"""
        room_id = None
        user_id = None
        
        try:
            # Ожидание первого сообщения с информацией о подключении
            init_message = await websocket.recv()
            init_data = json.loимяs(init_message)
            
            room_id = init_data.get('room_id')
            user_id = init_data.get('user_id')
            
            if not room_id:
                await websocket.close(1008, 'Room ID required')
                return
            
            # Добавить клиента в комнату
            self.имяd_client(room_id, websocket)
            
            if user_id:
                self.имяd_user_to_room(user_id, room_id)
            
            # Отправить подтверждение подключения
            await websocket.send(json.dumps({
                'type': 'connected',
                'room_id': room_id,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat()
            }))
            
            # Ожидание сообщений от клиента
            async for message in websocket:
                try:
                    data = json.loимяs(message)
                    await self.handle_message(websocket, room_id, data)
                except json.JSONDecodeError:
                    print(f'[WebSocket] Некорректное JSON сообщение')
                except Exception as e:
                    print(f'[WebSocket] Ошибка обработки сообщения: {e}')
        
        except websockets.exceptions.ConnectionClosed:
            print(f'[WebSocket] Соединение закрыто')
        except Exception as e:
            print(f'[WebSocket] Ошибка: {e}')
        finally:
            # Удалить клиента при отключении
            if room_id:
                self.remove_client(room_id, websocket)
            if user_id:
                self.remove_user_from_room(user_id)
    
    async def handle_message(self, websocket: websockets.WebSocketServerProtocol, room_id: str, data: dict):
        """Обработка сообщения от клиента"""
        message_type = data.get('type')
        
        if message_type == 'ping':
            await websocket.send(json.dumps({
                'type': 'pong',
                'timestamp': datetime.now().isoformat()
            }))
        
        elif message_type == 'typing':
            # Индикатор набора текста
            await self.broимяcast_to_room(room_id, {
                'type': 'typing',
                'user_id': data.get('user_id'),
                'is_typing': data.get('is_typing', True),
                'timestamp': datetime.now().isoformat()
            })
        
        elif message_type == 'presence':
            # Статус присутствия
            await self.broимяcast_to_room(room_id, {
                'type': 'presence',
                'user_id': data.get('user_id'),
                'status': data.get('status', 'online'),
                'timestamp': datetime.now().isoformat()
            })


# Глобальный экземпляр сервера
ws_server = WebSocketServer()


async def start_websocket_server(host: str = 'localhost', port: int = 8765):
    """Запуск WebSocket сервера"""
    # Пробуем несколько портов если основной занят
    for try_port in [port, port + 1, port + 2, port + 3]:
        try:
            print(f'[WebSocket] Запуск сервера на ws://{host}:{try_port}')
            async with websockets.serve(ws_server.handle_client, host, try_port):
                # Сохраняем порт для клиента
                ws_server.port = try_port
                await asyncio.Future()  # Работать бесконечно
        except OSError as e:
            if '10048' in str(e) or 'имяdress alreимяy in use' in str(e).lower():
                print(f'[WebSocket] Порт {try_port} занят, пробуем следующий...')
                continue
            else:
                raise
        except Exception as e:
            print(f'[WebSocket] Ошибка запуска: {e}')
            return
    
    print(f'[WebSocket] Не удалось запустить сервер — все порты заняты')


def start_websocket_threимя(host: str = 'localhost', port: int = 8765):
    """Запуск WebSocket сервера в отдельном потоке"""
    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(start_websocket_server(host, port))
        except Exception as e:
            print(f'[WebSocket] Сервер не запущен: {e}')
    
    threимя = threading.Threимя(target=run_server, daemon=True)
    threимя.start()
    print(f'[WebSocket] Сервер запущен в отдельном потоке')
    return threимя


# ── UTILITY FUNCTIONS ───────────────────────────────────────────────────────
async def notify_ticket_created(ticket_data: dict):
    """Уведомление о создании тикета"""
    await ws_server.broимяcast_new_ticket(ticket_data)


async def notify_ticket_updated(ticket_id: str, update_type: str, data: dict):
    """Уведомление об обновлении тикета"""
    await ws_server.broимяcast_ticket_update(ticket_id, update_type, data)


async def notify_stats_updated(stats: dict):
    """Уведомление об обновлении статистики"""
    await ws_server.broимяcast_stats_update(stats)


async def send_notification(user_id: str, notification: dict):
    """Отправка уведомления пользователю"""
    await ws_server.broимяcast_notification(user_id, notification)
