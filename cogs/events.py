import discord
from discord.ext import commands
import logging
import database
import config 

log = logging.getLogger(__name__)

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _check_milestones(self, guild: discord.Guild):
        # Fetch the last announced milestone. Default to 0 if never set.
        # We are reusing the 'milestone_100_announced' field to store the last number.
        last_announced_milestone = await database.get_setting(guild.id, 'milestone_100_announced') or 0

        increment = 50
        
        # The first milestone is 100, subsequent ones are in increments of 50.
        if last_announced_milestone < 100:
            next_milestone = 100
        else:
            next_milestone = last_announced_milestone + increment

        # Get the list of IDs to exclude from the config file
        excluded_ids = set(config.BOT_CONFIG.get("MILESTONE_EXCLUDED_IDS", []))
        
        # Calculate the current eligible member count
        eligible_member_count = 0
        for member in guild.members:
            if not member.bot and member.id not in excluded_ids:
                eligible_member_count += 1
        
        # If the count has reached or passed the next milestone, make the announcement
        if eligible_member_count >= next_milestone:
            announcement_channel_id = await database.get_setting(guild.id, 'announcement_channel_id')
            if not announcement_channel_id:
                log.warning(f"Guild {guild.id} reached {next_milestone} members, but no announcement channel is set.")
                return

            announcement_channel = guild.get_channel(announcement_channel_id)
            if announcement_channel:
                log.info(f"Guild {guild.id} reached {next_milestone} member milestone. Announcing.")
                embed = discord.Embed(
                    title="🎉 Server Milestone Reached! 🎉",
                    description=f"**Congratulations!** Our community has just reached **{next_milestone}** members!\n\nThank you to everyone for being a part of our journey. Here's to many more milestones to come! 🚀",
                    color=config.BOT_CONFIG["EMBED_COLORS"]["SUCCESS"]
                )
                embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
                
                try:
                    await announcement_channel.send(embed=embed)
                    # Update the database with the new milestone number we just announced
                    await database.update_setting(guild.id, 'milestone_100_announced', next_milestone)
                except discord.Forbidden:
                    log.error(f"Failed to send milestone announcement in guild {guild.id}. Missing permissions.")
            else:
                log.error(f"Could not find announcement channel {announcement_channel_id} in guild {guild.id}.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot: return
        unverified_role_id = await database.get_setting(member.guild.id, 'unverified_role_id')
        if unverified_role_id:
            unverified_role = member.guild.get_role(unverified_role_id)
            if unverified_role:
                try:
                    await member.add_roles(unverified_role, reason="New member join")
                    log.info(f"Assigned unverified role to {member} in guild {member.guild.id}.")
                except discord.Forbidden:
                    log.error(f"Failed to assign unverified role to {member} in guild {member.guild.id}. Missing permissions.")
            else:
                log.error(f"Could not find the configured unverified role ({unverified_role_id}) in guild {member.guild.id}.")

        await self._check_milestones(member.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))