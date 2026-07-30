"""Test server — only renders templates, no discord/bot"""
import os, sys
from flask import Flask, render_template, request, session

app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')
app.secret_key = 'test-key'

# Mock globals that templates might use
@app.context_processor
def inject_globals():
    return {
        'username': 'arthu27',
        'role': 'owner',
        'main_guild_id': '123456789',
        'guild_id': '123456789',
        'stats': {
            'total_tickets': 1284, 'total_penalties': 312, 'mutual_violations': 47,
            'fake_complaints': 23, 'single_violation_rate': 42, 'mutual_rate': 18,
            'fake_rate': 8, 'no_violation_rate': 32, 'avg_confidence': 87,
            'high_confidence_count': 945, 'low_confidence_count': 24,
            'appeal_rate': 12, 'appeal_success_rate': 35,
            'top_offenders': [
                {'name': 'SpammerBot', 'count': 14, 'total_duration': 28, 'last_penalty': '2 дня назад'},
            ],
            'penalty_reasons': [
                {'name': 'Спам', 'count': 95, 'percentage': 30},
            ]
        }
    }

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/<page>')
def page(page):
    if not page.endswith('.html'):
        page = page + '.html'
    try:
        return render_template(page)
    except Exception as e:
        return f'<pre style="color:red;background:#000;padding:20px;">ERROR rendering {page}:\n{type(e).__name__}: {e}\n\nCheck console for traceback.</pre><pre style="background:#000;color:#0f0;padding:20px;">{__import__("traceback").format_exc()}</pre>', 500

if __name__ == '__main__':
    print('Starting test server on 8765...')
    app.run(host='127.0.0.1', port=8765, debug=False, use_reloader=False)
