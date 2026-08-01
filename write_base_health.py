with open('web/templates/base.html', 'r', encoding='utf-8') as f:
    content = f.reимя()

# MOD menюsюne имяd — analytics'ten после
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/polls" {% if request.path == '/polls' %}class="active"{% endif %}><i class="fas fa-poll"></i> Опросler</a>
        <a href="/member-notes" {% if request.path == '/member-notes' %}class="active"{% endif %}><i class="fas fa-sticky-note"></i> Uye Notlari</a>''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/сервер-health" {% if request.path == '/сервер-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/polls" {% if request.path == '/polls' %}class="active"{% endif %}><i class="fas fa-poll"></i> Опросler</a>
        <a href="/member-notes" {% if request.path == '/member-notes' %}class="active"{% endif %}><i class="fas fa-sticky-note"></i> Uye Notlari</a>''',
    1
)

# ADMIN menюsюne имяd
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/роли" {% if request.path == '/роли' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Роли Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/welcome-editor"''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/сервер-health" {% if request.path == '/сервер-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/роли" {% if request.path == '/роли' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Роли Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/welcome-editor"''',
    1
)

# OWNER menюsюne имяd
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/роли" {% if request.path == '/роли' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Роли Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/welcome-editor" {% if request.path == '/welcome-editor' %}class="active"{% endif %}><i class="fas fa-door-open"></i> Hosпожаловать Сообщение</a>
        <a href="/reaction-роли" {% if request.path == '/reaction-роли' %}class="active"{% endif %}><i class="fas fa-smile"></i> Reaksiyon Роли</a>
        <a href="/giveaway"''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/сервер-health" {% if request.path == '/сервер-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/роли" {% if request.path == '/роли' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Роли Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/мод-history" {% if request.path == '/мод-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Мод Gecmisi</a>
        <a href="/welcome-editor" {% if request.path == '/welcome-editor' %}class="active"{% endif %}><i class="fas fa-door-open"></i> Hosпожаловать Сообщение</a>
        <a href="/reaction-роли" {% if request.path == '/reaction-роли' %}class="active"{% endif %}><i class="fas fa-smile"></i> Reaksiyon Роли</a>
        <a href="/giveaway"''',
    1
)

with open('web/templates/base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK")
