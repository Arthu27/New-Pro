from __future__ import annotations
import os
from dotenv import load_dotenv
from server import db

load_dotenv()
GUILD_ID = os.getenv("GUILD_ID", "1524635551804686486")

def main() -> None:
    db.init_db()
    db.save_guild_snapshot(GUILD_ID, {
        "id": GUILD_ID, "name": "ProBotum Test Server", "member_count": 24852,
        "channels": [
            {"id": "1001", "name": "welcome", "type": 0}, {"id": "1002", "name": "rules", "type": 0},
            {"id": "1003", "name": "general", "type": 0}, {"id": "1004", "name": "bot-commands", "type": 0},
            {"id": "1005", "name": "tickets", "type": 0}, {"id": "1006", "name": "mod-logs", "type": 0},
            {"id": "1007", "name": "security-logs", "type": 0}, {"id": "1008", "name": "voice lounge", "type": 2},
            {"id": "1009", "name": "staff voice", "type": 2}, {"id": "1010", "name": "Logs", "type": 4},
            {"id": "1011", "name": "announcements", "type": 5}, {"id": "1012", "name": "support forum", "type": 15},
        ],
        "members": [
            {"id": "3001", "username": "artur", "global_name": "артур", "display_name": "артур", "bot": False, "roles": ["2005", "2006"]},
            {"id": "3002", "username": "lega", "global_name": "lega", "display_name": "lega", "bot": False, "roles": ["2005"]},
            {"id": "3003", "username": "admin", "global_name": "admin", "display_name": "admin", "bot": False, "roles": ["2002"]},
        ],
        "roles": [
            {"id": "2001", "name": "Owner", "position": 100}, {"id": "2002", "name": "Admin", "position": 90},
            {"id": "2003", "name": "Moderator", "position": 70}, {"id": "2004", "name": "Staff", "position": 65},
            {"id": "2005", "name": "Member", "position": 10}, {"id": "2006", "name": "VIP", "position": 20},
            {"id": "2007", "name": "Booster", "position": 25}, {"id": "2008", "name": "Muted", "position": 5},
            {"id": "2009", "name": "Ticket Staff", "position": 60},
        ],
    })
    db.set_module_config(GUILD_ID, "automod", {"enabled": True, "primaryChannel": "#general", "logChannel": "#mod-logs", "staffRole": "@Moderator", "action": "mute", "duration": "10m", "blockInvites": True})
    db.set_module_config(GUILD_ID, "tickets", {"enabled": True, "primaryChannel": "#tickets", "staffRole": "@Ticket Staff", "logChannel": "#mod-logs", "sla": "15m"})
    db.set_module_config(GUILD_ID, "welcome", {"enabled": True, "primaryChannel": "#welcome", "memberRole": "@Member", "logChannel": "#mod-logs"})
    db.set_permission_rule(GUILD_ID, "settings", "role", "2001", "allow", "show")
    db.set_permission_rule(GUILD_ID, "settings", "role", "2002", "allow", "show")
    db.set_permission_rule(GUILD_ID, "ban", "role", "2003", "allow", "show")
    db.save_access_portals(GUILD_ID, {
        "owner": {"roles": ["@Owner"], "users": [], "sections": ["All dashboard", "API", "Permissions", "Logs Setup", "Apply actions"]},
        "admin": {"roles": ["@Admin"], "users": [], "sections": ["Modules", "Permissions", "Logs Setup", "Tickets", "Logs"]},
        "moderator": {"roles": ["@Moderator", "@Staff"], "users": [], "sections": ["Moderation", "Tickets", "Member logs", "Warnings"]},
        "member": {"roles": ["@Member", "@VIP"], "users": [], "sections": ["My profile", "Rank", "Open ticket", "Server rules", "Role selection"]},
    })
    db.add_audit_log(GUILD_ID, "dev_seed_created", {"message": "Demo data seeded"}, "system")
    print("Demo data seeded successfully!")
    print(f"Guild ID: {GUILD_ID}")
    print("Run: python -m uvicorn server.api:app --port 3000")

if __name__ == "__main__":
    main()
