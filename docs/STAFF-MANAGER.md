# Staff Manager

## Как работает

1. Конфиг `data/staff_manager.json` — единственный источник ID ролей и веток.
2. Лестница одинаковая во всех ветках: Master → Assistant → Curator → Admin (ранги из конфига).
3. Над ветками: **Стафф админ** и **владелец**.
4. **Ответственный за ветку** (`responsible_role_id`) управляет только своей веткой и только ролями из `responsible_can_manage` (по умолчанию master/assistant/curator). **Admin не выдаёт.**
5. Куратор/ассистент/мастер по умолчанию **не** управляют ролями — только заявка.
6. Все проверки — `can_manage_staff`; смена ролей — `apply_staff_change`.
7. Discord: `/staff panel @user` (Components V2). Веб: `/api/staff-manager/allowed`.

## Настройка

```bash
cp data/staff_manager.example.json data/staff_manager.json
# заполни role ID всех веток + responsible + staff_admin_role_id
systemctl restart hakumo
# или /staff reload
```

## Команды

- `/staff panel member:` — панель
- `/staff reload` — перечитать JSON
