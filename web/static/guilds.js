fetch('/api/guilds', { credentials: 'same-origin' })
    .then(function(r) { return r.json(); })
    .then(function(guilds) {
        if (!guilds || guilds.length === 0) {
            document.getElementById('guilds-container').innerHTML = '<p style="color: #aaa;">Пока сервер yok</p>';
            return;
        }
        
        var html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px;">';
        
        guilds.forEach(function(g) {
            var icon = g.icon || 'https://cdn.discordapp.com/embed/avatars/0.png';
            html += '<div style="background: linear-gradient(135deg, #dc143c 0%, #ff1744 100%); padding: 25px; border-radius: 15px; box-shadow: 0 8px 20px rgba(220, 20, 60, 0.4); border: 2px solid rgba(255, 215, 0, 0.3);">';
            html += '<img src="' + icon + '" style="width: 80px; height: 80px; border-radius: 50%; display: block; margin: 0 auto 15px; border: 4px solid rgba(255, 255, 255, 0.3);">';
            html += '<h3 style="text-align: center; color: white; margin-bottom: 10px; font-size: 20px; font-weight: 700;">' + g.name + '</h3>';
            html += '<div style="text-align: center; color: white; padding-top: 15px; border-top: 1px solid rgba(255, 255, 255, 0.2);">';
            html += '<i class="fas fa-users"></i> ' + g.members + ' участник';
            html += '</div></div>';
        });
        
        html += '</div>';
        document.getElementById('guilds-container').innerHTML = html;
    })
    .catch(function(error) {
        console.error('Ошибка:', error);
        document.getElementById('guilds-container').innerHTML = '<p style="color: #e74c3c;">Сервера загруз ошибка: ' + error.message + '</p>';
    });
