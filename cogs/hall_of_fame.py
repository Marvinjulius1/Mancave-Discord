"""
Wins-Board / Hall of Fame.

Beiträge in #erfolge-feiern, die genug 🔥-Reaktionen bekommen (config.HALL_OF_FAME_THRESHOLD,
ohne die Reaktion des Autors), werden automatisch in #hall-of-fame gepostet. Der Autor bekommt Bonus-XP.
"""

import discord
from discord.ext import commands

import config
import db
from cogs.leveling import grant_xp
from utils import get_text_channel, log, now, send_log


class HallOfFame(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id != self.bot.guild_id or str(payload.emoji) != config.HALL_OF_FAME_EMOJI:
            return
        guild = self.bot.get_guild(payload.guild_id)
        source = guild.get_channel(payload.channel_id) if guild else None
        if source is None or source.name != config.WINS_CHANNEL:
            return
        if db.fetchone("SELECT 1 FROM hall_of_fame WHERE message_id = ?", (payload.message_id,)):
            return

        try:
            message = await source.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        reaction = discord.utils.find(lambda r: str(r.emoji) == config.HALL_OF_FAME_EMOJI, message.reactions)
        if reaction is None or reaction.count < config.HALL_OF_FAME_THRESHOLD:
            return
        count = 0
        async for user in reaction.users():
            if not user.bot and user.id != message.author.id:
                count += 1
        if count < config.HALL_OF_FAME_THRESHOLD:
            return

        target = get_text_channel(guild, config.HALL_OF_FAME_CHANNEL)
        if target is None:
            return
        # Erst eintragen, dann posten -> bei gleichzeitigen Reaktionen kein Doppelpost
        db.execute(
            "INSERT OR IGNORE INTO hall_of_fame(message_id, author_id, content, reactions, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (message.id, message.author.id, message.content[:1000], count, now().isoformat()),
        )

        embed = discord.Embed(
            description=message.content[:4000] or "*(Bild/Anhang)*",
            color=0xF1C40F,
            timestamp=message.created_at,
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        image = next((a for a in message.attachments if (a.content_type or "").startswith("image/")), None)
        if image:
            embed.set_image(url=image.url)
        embed.add_field(name="Original", value=f"[Zum Beitrag springen]({message.jump_url})")
        try:
            hof_msg = await target.send(
                content=f"🏆 **Neuer Eintrag in der Hall of Fame!** {config.HALL_OF_FAME_EMOJI} × {count} · {message.author.mention}",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException as e:
            log.warning("Hall of Fame Post fehlgeschlagen: %s", e)
            return
        db.execute("UPDATE hall_of_fame SET hof_message_id = ? WHERE message_id = ?", (hof_msg.id, message.id))
        await send_log(guild, f"🏆 Win von {message.author.mention} ist in der Hall of Fame.")
        if isinstance(message.author, discord.Member):
            await grant_xp(message.author, config.XP_HALL_OF_FAME)


async def setup(bot: commands.Bot):
    await bot.add_cog(HallOfFame(bot))
