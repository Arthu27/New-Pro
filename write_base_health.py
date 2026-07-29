with open('web/templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# MOD menüsüne add — analytics'ten sonra
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/polls" {% if request.path == '/polls' %}class="active"{% endif %}><i class="fas fa-poll"></i> Опросler</a>
        <a href="/member-notes" {% if request.path == '/member-notes' %}class="active"{% endif %}><i class="fas fa-sticky-note"></i> Uye Notlari</a>''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/server-health" {% if request.path == '/server-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/polls" {% if request.path == '/polls' %}class="active"{% endif %}><i class="fas fa-poll"></i> Опросler</a>
        <a href="/member-notes" {% if request.path == '/member-notes' %}class="active"{% endif %}><i class="fas fa-sticky-note"></i> Uye Notlari</a>''',
    1
)

# ADMIN menüsüne add
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/roles" {% if request.path == '/roles' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Role Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/welcome-editor"''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/server-health" {% if request.path == '/server-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/roles" {% if request.path == '/roles' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Role Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/welcome-editor"''',
    1
)

# OWNER menüsüne add
content = content.replace(
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/roles" {% if request.path == '/roles' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Role Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/welcome-editor" {% if request.path == '/welcome-editor' %}class="active"{% endif %}><i class="fas fa-door-open"></i> Hosgeldin Сообщение</a>
        <a href="/reaction-roles" {% if request.path == '/reaction-roles' %}class="active"{% endif %}><i class="fas fa-smile"></i> Reaksiyon Рольler</a>
        <a href="/giveaway"''',
    '''        <a href="/analytics" {% if request.path == '/analytics' %}class="active"{% endif %}><i class="fas fa-chart-bar"></i> Analitik</a>
        <a href="/server-health" {% if request.path == '/server-health' %}class="active"{% endif %}><i class="fas fa-heartbeat"></i> Сервер Sagligi</a>
        <a href="/roles" {% if request.path == '/roles' %}class="active"{% endif %}><i class="fas fa-user-tag"></i> Role Yonetimi</a>
        <a href="/channels" {% if request.path == '/channels' %}class="active"{% endif %}><i class="fas fa-hashtag"></i> Канал Yonetimi</a>
        <a href="/mod-history" {% if request.path == '/mod-history' %}class="active"{% endif %}><i class="fas fa-history"></i> Mod Gecmisi</a>
        <a href="/welcome-editor" {% if request.path == '/welcome-editor' %}class="active"{% endif %}><i class="fas fa-door-open"></i> Hosgeldin Сообщение</a>
        <a href="/reaction-roles" {% if request.path == '/reaction-roles' %}class="active"{% endif %}><i class="fas fa-smile"></i> Reaksiyon Рольler</a>
        <a href="/giveaway"''',
    1
)

with open('web/templates/base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("OK")
