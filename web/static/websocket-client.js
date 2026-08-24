/**
 * WebSocket клиент для real-time обновлений
 * Автоматически определяет URL на основе текущего хоста
 */

class WebSocketClient {
    constructor(options = {}) {
        // Автоопределение URL
        this.url = options.url || this._getDefaultUrl();
        this.roomId = options.roomId || null;
        this.userId = options.userId || null;
        this.reconnectInterval = options.reconnectInterval || 5000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.enabled = options.enabled !== false;
        
        this.ws = null;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.listeners = {};
        this.messageQueue = [];
        this._disposed = false;
        
        // Автоматическое подключение
        if (this.enabled && options.autoConnect !== false && this.url) {
            this.connect();
        }
    }
    
    /**
     * Определить WebSocket URL автоматически
     */
    _getDefaultUrl() {
        try {
            const host = window.location.hostname || '';
            const isLocal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(host) || host === '';
            if (!isLocal) {
                // Панель открыта через домен/туннель: ws-порт наружу не проброшен.
                // Молча живём на polling-API — без спама реконнектами в консоль.
                return null;
            }
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${host}:8765`;
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Подключение к WebSocket серверу
     */
    connect() {
        if (this._disposed || !this.url) return;
        
        try {
            this.ws = new WebSocket(this.url);
            
            this.ws.onopen = this.onOpen.bind(this);
            this.ws.onmessage = this.onMessage.bind(this);
            this.ws.onerror = this.onError.bind(this);
            this.ws.onclose = this.onClose.bind(this);
        } catch (error) {
            this.scheduleReconnect();
        }
    }
    
    onOpen(event) {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        this.send({
            type: 'init',
            room_id: this.roomId,
            user_id: this.userId
        });
        
        this.flushMessageQueue();
        this.emit('connected', event);
    }
    
    onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
                case 'ticket_update': this.emit('ticket_update', data); break;
                case 'new_ticket': this.emit('new_ticket', data); break;
                case 'stats_update': this.emit('stats_update', data); break;
                case 'notification': this.emit('notification', data); break;
                case 'typing': this.emit('typing', data); break;
                case 'presence': this.emit('presence', data); break;
                case 'pong': this.emit('pong', data); break;
            }
            
            this.emit('message', data);
        } catch (error) {
            // Silent ignore parse errors
        }
    }
    
    onError(event) {
        this.emit('error', event);
    }
    
    onClose(event) {
        this.isConnected = false;
        this.emit('disconnected', event);
        
        if (event.code !== 1000) {
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this._disposed || !this.url) return;
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            // Тихо прекращаем попытки — WebSocket сервер может быть не запущен
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectInterval * this.reconnectAttempts;
        
        setTimeout(() => {
            if (!this._disposed) this.connect();
        }, delay);
    }
    
    send(data) {
        if (!this.isConnected) {
            this.messageQueue.push(data);
            return false;
        }
        
        try {
            this.ws.send(JSON.stringify(data));
            return true;
        } catch (error) {
            return false;
        }
    }
    
    flushMessageQueue() {
        while (this.messageQueue.length > 0) {
            const data = this.messageQueue.shift();
            this.send(data);
        }
    }
    
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
        return this;
    }
    
    off(event, callback) {
        if (!this.listeners[event]) return this;
        if (callback) {
            this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
        } else {
            delete this.listeners[event];
        }
        return this;
    }
    
    emit(event, data) {
        if (!this.listeners[event]) return;
        this.listeners[event].forEach(callback => {
            try { callback(data); } catch (e) {}
        });
    }
    
    close() {
        this._disposed = true;
        if (this.ws) {
            this.ws.close(1000, 'Client closing');
        }
    }
    
    changeRoom(newRoomId) {
        this.roomId = newRoomId;
        if (this.isConnected) {
            this.send({ type: 'change_room', room_id: newRoomId, user_id: this.userId });
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketClient;
}
