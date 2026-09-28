"""
Einladungs-Tracking.

  - Merkt sich, über welchen Einladungslink jemand beigetreten ist und wer ihn erstellt hat
  - Wer den Server verlässt, zählt nicht mehr
  - Ab config.INVITE_REWARD_COUNT aktiven Einladungen gibt's die Rolle config.INVITE_REWARD_ROLE
  - /invites [mitglied], /invite-leaderboard
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import get_role, log, medal, member_name, now, send_log


def invite_count(user_id: int) -> int:
    return db.scalar("SELECT COUNT(*) FROM invites WHERE inviter_id = ? AND left_guild = 0", (user_id,))


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: dict[str, int] = {}

    async def refresh(self, guild: discord.Guild) -> list[discord.Invite]:
        try:
            invites = await guild.invites()
        except discord.HTTPException as e:
            log.warning("Einladungen können nicht gelesen werden (braucht 'Server verwalten'): %s", e)
            return []
        self.cache = {i.code: i.uses or 0 for i in invites}
        return invites

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        await self.refresh(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        self.cache[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        self.cache.pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != self.bot.guild_id or member.bot:
            return
        old = dict(self.cache)
        invites = await self.refresh(member.guild)
        used = next((i for i in invites if (i.uses or 0) > old.get(i.code, 0)), None)
        if used is None or used.inviter is None:
            await send_log(member.guild, f"🔗 {member.mention} – Einladung nicht erkennbar (Vanity-Link oder abgelaufen).")
            return
        db.execute(
            "INSERT OR REPLACE INTO invites(member_id, inviter_id, code, joined_at, left_guild) VALUES (?, ?, ?, ?, 0)",
            (member.id, used.inviter.id, used.code, now().isoformat()),
        )
        count = invite_count(used.inviter.id)
        await send_log(member.guild,
                       f"🔗 {member.mention} wurde von {used.inviter.mention} eingeladen (`{used.code}`) – "
                       f"{used.inviter.display_name} hat jetzt {count} Einladung(en).")
        inviter = member.guild.get_member(used.inviter.id)
        role = get_role(member.guild, config.INVITE_REWARD_ROLE)
        if inviter and role and count >= config.INVITE_REWARD_COUNT and role not in inviter.roles:
            try:
                await inviter.add_roles(role, reason=f"{count} Einladungen")
                await send_log(member.guild, f"🏅 {inviter.mention} ist jetzt **{role.name}** ({count} Einladungen).")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != self.bot.guild_id:
            return
        db.execute("UPDATE invites SET left_guild = 1 WHERE member_id = ?", (member.id,))
        await send_log(member.guild, f"📤 {member} hat den Server verlassen.")

    @app_commands.command(name="invites", description="Wie viele Leute hast du eingeladen?")
    @app_commands.describe(mitglied="Wessen Einladungen? (leer = deine)")
    @app_commands.guild_only()
    async def invites(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        active = invite_count(member.id)
        left = db.scalar("SELECT COUNT(*) FROM invites WHERE inviter_id = ? AND left_guild = 1", (member.id,))
        text = f"🔗 **{member.display_name}** hat **{active}** aktive Einladung(en)"
        if left:
            text += f" ({left} wieder gegangen)"
        remaining = config.INVITE_REWARD_COUNT - active
        if remaining > 0:
            text += f".\nNoch **{remaining}** bis zur Rolle **{config.INVITE_REWARD_ROLE}**. 🏅"
        else:
            text += f". 🏅 **{config.INVITE_REWARD_ROLE}**!"
        await interaction.response.send_message(text)

    @app_commands.command(name="invite-leaderboard", description="Wer hat die meisten Leute in die Mancave geholt?")
    @app_commands.guild_only()
    async def invite_leaderboard(self, interaction: discord.Interaction):
        rows = db.fetchall(
            "SELECT inviter_id, COUNT(*) AS c FROM invites WHERE left_guild = 0 "
            "GROUP BY inviter_id ORDER BY c DESC LIMIT 10"
        )
        if not rows:
            await interaction.response.send_message("Noch keine Einladungen erfasst. Lad deine Leute ein! 🔗")
            return
        lines = [f"{medal(i)} **{member_name(interaction.guild, r['inviter_id'])}** – {r['c']} Einladung(en)"
                 for i, r in enumerate(rows)]
        embed = discord.Embed(title="🔗 Invite-Leaderboard", description="\n".join(lines), color=0xE91E63)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
