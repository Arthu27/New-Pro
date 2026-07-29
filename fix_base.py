with open('web/templates/base.html', 'w', encoding='utf-8') as f:
    f.write("""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Bot Panel{% endblock %}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="sidebar">
        <h2>🤖 ПАНЕЛЬ AETHER</h2>

        {% if role == 'uye' %}
        <a href="/member-apply" {% if request.path == '/member-apply' %}class="active"{% endif %}><i class="fas fa-user-shield"></i> Администратор Basvurusu</a>

        {% elif role == 'mod' %}
        <a href="/" {% if request.path == '/' %}class="active"{% endif %}><i class="fas fa-home"></i> Panel управление</a>
        <a href="/logs" {% if request.path == '/logs' %}class="active"{% endif %}><i class="fas fa-clipboard-list"></i> Логи модерации</a>
        <a href="/warnings" {% if request.path == '/warnings' %}class="active"{% endif %}><i class="fas fa-exclamation-triangle"></i> Предупреждения</a>

        {% elif role == 'admin' %}
        <a href="/" {% if request.path == '/' %}class="active"{% endif %}><i class="fas fa-home"></i> Panel управление</a>
        <a href="/users" {% if request.path == '/users' %}class="active"{% endif %}><i class="fas fa-users"></i> Пользователи</a>
        <a href="/logs" {% if request.path == '/logs' %}class="active"{% endif %}><i class="fas fa-clipboard-list"></i> Логи модерации</a>
        <a href="/warnings" {% if request.path == '/warnings' %}class="active"{% endif %}><i class="fas fa-exclamation-triangle"></i> Предупреждения</a>
        <a href="/commands" {% if request.path == '/commands' %}class="active"{% endif %}><i class="fas fa-terminal"></i> Команды</a>
        <a href="/staff-apps" {% if request.path == '/staff-apps' %}class="active"{% endif %}><i class="fas fa-user-shield"></i> Администратор Basvurulari</a>

        {% elif role == 'owner' %}
        <a href="/" {% if request.path == '/' %}class="active"{% endif %}><i class="fas fa-home"></i> Panel управление</a>
        <a href="/guilds" {% if request.path == '/guilds' %}class="active"{% endif %}><i class="fas fa-сервер"></i> Сервера</a>
        <a href="/users" {% if request.path == '/users' %}class="active"{% endif %}><i class="fas fa-users"></i> Пользователи</a>
        <a href="/logs" {% if request.path == '/logs' %}class="active"{% endif %}><i class="fas fa-clipboard-list"></i> Логи модерации</a>
        <a href="/warnings" {% if request.path == '/warnings' %}class="active"{% endif %}><i class="fas fa-exclamation-triangle"></i> Предупреждения</a>
        <a href="/commands" {% if request.path == '/commands' %}class="active"{% endif %}><i class="fas fa-terminal"></i> Команды</a>
        <a href="/send-command" {% if request.path == '/send-command' %}class="active"{% endif %}><i class="fas fa-paper-plane"></i> Команда Gonder</a>
        <a href="/staff-apps" {% if request.path == '/staff-apps' %}class="active"{% endif %}><i class="fas fa-user-shield"></i> Администратор Basvurulari</a>
        <a href="/settings" {% if request.path == '/settings' %}class="active"{% endif %}><i class="fas fa-cog"></i> Настройки</a>
        {% endif %}
    </div>

    <div class="main-content">
        <div class="navbar">
            <h1>{% block page_title %}Bot Контроль Paneli{% endblock %}</h1>
            <div class="user-info">
                <span>{{ username }}</span>
                <span class="role-badge">{{ роли }}</span>
                <a href="/logout" class="logout-btn"><i class="fas fa-sign-out-alt"></i> Cikis</a>
            </div>
        </div>

        {% block content %}{% endblock %}
    </div>
</body>
</html>
""")
print("OK")
