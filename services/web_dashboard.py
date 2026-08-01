"""
Web Dashboard
Flask web arayüzü
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
from functools import wraps
import os
import json
from datetime import datetime, timedelta


class WebDashboard:
    """Web Dashboard"""
    
    def __init__(self, bot):
        self.bot = bot
        self.app = Flask(__name__)
        self.app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
        
        self.setup_routes()
    
    def login_required(self, f):
        """Login required decorator"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Basit authentication
            # Gerçek uygulamada session использовать
            return f(*args, **kwargs)
        return decorated_function
    
    def setup_routes(self):
        """Routes настроить"""
        
        @self.app.route('/')
        @self.login_required
        def dashboard():
            """Dashboard"""
            return render_template('dashboard.html')
        
        @self.app.route('/tickets')
        @self.login_required
        def tickets():
            """Tickets"""
            return render_template('tickets.html')
        
        @self.app.route('/users')
        @self.login_required
        def users():
            """Users"""
            return render_template('users.html')
        
        @self.app.route('/stats')
        @self.login_required
        def stats():
            """Stats"""
            return render_template('stats.html')
        
        @self.app.route('/logs')
        @self.login_required
        def logs():
            """Logs"""
            return render_template('logs.html')
        
        @self.app.route('/settings')
        @self.login_required
        def settings():
            """Settings"""
            return render_template('settings.html')
        
        # API Routes
        @self.app.route('/api/stats')
        def api_stats():
            """API stats"""
            stats = {
                'total_tickets': len(self.bot.get_cog('TicketCog').tickets if self.bot.get_cog('TicketCog') else []),
                'total_users': len(self.bot.users),
                'total_guilds': len(self.bot.guilds),
                'uptime': '24h'
            }
            return jsonify(stats)
        
        @self.app.route('/api/tickets')
        def api_tickets():
            """API tickets"""
            tickets = []
            if self.bot.get_cog('TicketCog'):
                tickets = list(self.bot.get_cog('TicketCog').tickets.values())
            return jsonify(tickets)
        
        @self.app.route('/api/users')
        def api_users():
            """API users"""
            users = [{'id': u.id, 'name': u.name, 'discriminator': u.discriminator} 
                    for u in self.bot.users]
            return jsonify(users)
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Dashboard'u запустить"""
        self.app.run(host=host, port=port, debug=debug)


def create_dashboard(bot):
    """Dashboard создать"""
    return WebDashboard(bot)
