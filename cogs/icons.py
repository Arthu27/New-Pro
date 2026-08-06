"""Aether — фирменные иконки (assets/icons/) — помощник embed-миниатюр"""
import os 
import discord 

ICONS_DIR =os .path .join (os .path .dirname (os .path .dirname (__file__ )),'assets','icons')

# Имя файла, к которому привяжется иконка в embed (256px — баланс видимости/скорости)
def icon_attach (name :str ):
    """Embed'e bağlanacak (dosya adı, discord.File) döndürür. Yoksa (None, None).

    Kullanım:
        fname, f = icon_attach('welcome')
        if f:
            embed.set_thumbnail(url=f'attachment://{fname}')
            await channel.send(embed=embed, file=f)
        else:
            await channel.send(embed=embed)
    """
    for cand in (f'{name}_256.png',f'{name}.png'):
        path =os .path .join (ICONS_DIR ,cand )
        if os .path .exists (path ):
            return cand ,discord .File (path ,filename =cand )
    return None ,None 


async def send_with_icon (target ,embed ,name :str ,**kwargs ):
    """embed'i simgesiyle (varsa) gönderir. target: .send(...) metodu olan nesne."""
    if os .path .isdir (ICONS_DIR ):
        fname ,f =icon_attach (name )
        if f :
            embed .set_thumbnail (url =f'attachment://{fname}')
            return await target .send (embed =embed ,file =f ,**kwargs )
    return await target .send (embed =embed ,**kwargs )


async def respond_with_icon (interaction ,embed ,name :str ,**kwargs ):
    """interaction.response.send_message için simgeli gönderim."""
    if os .path .isdir (ICONS_DIR ):
        fname ,f =icon_attach (name )
        if f :
            embed .set_thumbnail (url =f'attachment://{fname}')
            return await interaction .response .send_message (embed =embed ,file =f ,**kwargs )
    return await interaction .response .send_message (embed =embed ,**kwargs )
