from flask import Flask
import json
import discord
from web.app import bot_instance as bot
from cogs.giveaway import GiveawayView
import asyncio
from datetime import timedelta, datetime

app = Flask(__name__)

@app.route('/fix-giveaway', methods=['POST'])
def fix():
    guild_id = request.json['guild_id']
    channel_id = request.json['channel_id']
    prize = request.json['prize']
    winners = request.json['winners']
    duration = request.json['duration']
    
    gw_id = str(int(datetime.utcnow().timestamp()))
    ends_at = (datetime.utcnow() + timedelta(minutes=duration)).isoformat()
    
    f = f'data/giveaways_{guild_id}.json'
    gws = {}
    if os.path.exists(f):
        with open(f, 'r') as fp: gws = json.load(fp)
    
    gws[gw_id] = {'id': gw_id, 'prize': prize, 'winners': winners, 'ends_at': ends_at, 'status': 'active', 'channel_id': channel_id, 'participants': [], 'message_id': None}
    with open(f, 'w') as fp: json.dump(gws, fp, indent=2)
    
    async def send():
        ch = bot.get_channel(int(channel_id))
        embed = discord.Embed(title=f'🎉 {prize}', description='**Присоединитьсяmak для butona bas!**', color=0xffd700)
        embed.add_field(name='Kazanan', value=winners, inline=True)
        embed.add_field(name='Участник', value='0/{}'.format(winners), inline=True)
        embed.add_field(name='Bitiш', value=f'<t:{int(datetime.utcnow().timestamp())+duration*60}:R>', inline=True)
        embed.set_footer(text=f'{gw_id}')
        view = GiveawayView(gw_id, guild_id)
        msg = await ch.send(embed=embed, view=view)
        gws[gw_id]['message_id'] = str(msg.id)
        with open(f, 'w') as fp: json.dump(gws, fp)
    
    asyncio.run_coroutine_threadsafe(send(), bot.loop)
    return 'FIXED! 🎉'

if __name__ == '__main__':
    app.run(port=5002)

