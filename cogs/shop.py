import discord
from discord import app_commands
from discord.ext import commands
import logging
import re

import database
import config
import utils

log = logging.getLogger(__name__)

# --- Modal for creating/editing the custom role ---
class CustomRoleModal(discord.ui.Modal):
    def __init__(self, title: str, current_name: str = "", current_color: str = "#99aab5"):
        super().__init__(title=title)
        self.role_name = discord.ui.TextInput(
            label="Role Name",
            placeholder="Enter a name for your role.",
            default=current_name,
            max_length=50,
            required=True
        )
        self.role_color = discord.ui.TextInput(
            label="Role Color (Hex Code)",
            placeholder="e.g., #ff00ff or ff00ff",
            default=current_color,
            max_length=7,
            required=True
        )
        self.add_item(self.role_name)
        self.add_item(self.role_color)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # --- Validate Hex Color ---
        hex_color_pattern = re.compile(r'^#?([A-Fa-f0-9]{6})$')
        match = hex_color_pattern.match(self.role_color.value)
        if not match:
            await interaction.followup.send("❌ Invalid hex color code. Please use a format like `#RRGGBB` (e.g., `#5865F2`).", ephemeral=True)
            return
        
        color_value = int(match.group(1), 16)
        color = discord.Color(color_value)

        # --- Validate Name ---
        bad_words = await database.get_bad_words(interaction.guild.id)
        if any(word in self.role_name.value.lower() for word in bad_words):
            await interaction.followup.send("❌ Your chosen role name contains a forbidden word.", ephemeral=True)
            return

        # --- Logic for editing an existing role ---
        existing_role_id = await database.get_user_custom_role(interaction.guild.id, interaction.user.id)
        if existing_role_id:
            role = interaction.guild.get_role(existing_role_id)
            if role:
                try:
                    await role.edit(name=self.role_name.value, color=color, reason=f"User {interaction.user.id} edited their custom role.")
                    await interaction.followup.send(f"✅ Your custom role has been updated to **{self.role_name.value}**.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send("❌ I don't have permission to edit roles.", ephemeral=True)
            else:
                await interaction.followup.send("Could not find your role to edit. It may have been deleted.", ephemeral=True)
            return

        # --- Logic for buying a new role ---
        cost = await database.get_setting(interaction.guild.id, 'custom_role_cost') or 100
        balance = await database.get_koth_points(interaction.guild.id, interaction.user.id)
        if balance < cost:
            await interaction.followup.send(f"You don't have enough points. You need {cost} but only have {balance}.", ephemeral=True)
            return

        divider_role_id = await database.get_setting(interaction.guild.id, 'custom_role_divider_role_id')
        divider_role = interaction.guild.get_role(divider_role_id) if divider_role_id else None
        
        try:
            new_role = await interaction.guild.create_role(
                name=self.role_name.value,
                color=color,
                reason=f"Custom role purchased by {interaction.user.id}"
            )
            if divider_role:
                await new_role.edit(position=divider_role.position)

            await interaction.user.add_roles(new_role)
            await database.set_user_custom_role(interaction.guild.id, interaction.user.id, new_role.id)
            await database.adjust_koth_points(interaction.guild.id, interaction.user.id, -cost)
            await interaction.followup.send(f"🎉 Congratulations! You have successfully purchased and equipped your custom role: **{new_role.name}**.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create or assign roles. Please contact a server admin.", ephemeral=True)
        except Exception as e:
            log.error(f"Error creating custom role: {e}")
            await interaction.followup.send("An unexpected error occurred while creating your role.", ephemeral=True)

# --- Views for the Shop and Role Management ---
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Buy Custom Role", style=discord.ButtonStyle.success, emoji="🎨")
    async def buy_custom_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await database.get_user_custom_role(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("You already own a custom role! Use the `/myrole` command to edit or delete it.", ephemeral=True)
            return
        
        await interaction.response.send_modal(CustomRoleModal(title="Purchase a Custom Role"))

class ManageRoleView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.original_interaction = original_interaction

    @discord.ui.button(label="Edit Name & Color", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_id = await database.get_user_custom_role(interaction.guild.id, interaction.user.id)
        role = interaction.guild.get_role(role_id)
        if role:
            await interaction.response.send_modal(CustomRoleModal(title="Edit Your Custom Role", current_name=role.name, current_color=str(role.color)))
        else:
            await interaction.response.send_message("Could not find your role. It might have been deleted.", ephemeral=True)

    @discord.ui.button(label="Delete Role", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfirmDeleteView(self.original_interaction)
        await interaction.response.send_message("Are you sure you want to delete your custom role? This action cannot be undone and your points will **not** be refunded.", view=view, ephemeral=True)

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.original_interaction = original_interaction

    @discord.ui.button(label="Yes, Delete It", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_id = await database.get_user_custom_role(interaction.guild.id, interaction.user.id)
        role = interaction.guild.get_role(role_id)
        if role:
            try:
                await role.delete(reason=f"Custom role deleted by user {interaction.user.id}")
            except discord.Forbidden:
                await interaction.response.edit_message(content="❌ I don't have permission to delete roles.", view=None)
                return
        
        await database.delete_user_custom_role(interaction.guild.id, interaction.user.id)
        await interaction.response.edit_message(content="✅ Your custom role has been deleted.", view=None)

    @discord.ui.button(label="No, Keep It", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)

# --- Main Cog ---
class ShopCog(commands.Cog, name="Shop"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, interaction: discord.Interaction) -> bool:
        is_enabled = await database.get_setting(interaction.guild.id, 'ranking_system_enabled')
        if not is_enabled:
            await interaction.response.send_message("The KOTH / Points system is disabled on this server.", ephemeral=True)
            return False
        return True

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Cleans up a user's custom role if they leave the server."""
        role_id = await database.get_user_custom_role(member.guild.id, member.id)
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await role.delete(reason=f"Owner left the server.")
                    log.info(f"Deleted custom role for user {member.id} who left guild {member.guild.id}")
                except discord.Forbidden:
                    log.error(f"Failed to delete role for user {member.id} in guild {member.guild.id}")
            await database.delete_user_custom_role(member.guild.id, member.id)


    @app_commands.command(name="shop", description="View items you can purchase with your KOTH points.")
    async def shop(self, interaction: discord.Interaction):
        cost = await database.get_setting(interaction.guild.id, 'custom_role_cost') or 100
        balance = await database.get_koth_points(interaction.guild.id, interaction.user.id)

        embed = discord.Embed(
            title="⚔️ KOTH Points Shop",
            description="Spend your hard-earned points on unique perks!",
            color=config.BOT_CONFIG["EMBED_COLORS"]["INFO"]
        )
        embed.add_field(
            name=f"🎨 Custom Role - {cost} Points",
            value="Purchase a unique role with a custom name and color that you control! A true sign of a champion.",
            inline=False
        )
        embed.set_footer(text=f"You currently have {balance} points.")

        view = ShopView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="myrole", description="Manage your purchased custom role.")
    async def myrole(self, interaction: discord.Interaction):
        role_id = await database.get_user_custom_role(interaction.guild.id, interaction.user.id)
        if not role_id:
            await interaction.response.send_message("You don't own a custom role yet. Purchase one from the `/shop`!", ephemeral=True)
            return
        
        role = interaction.guild.get_role(role_id)
        if not role:
            await database.delete_user_custom_role(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message("It seems your custom role was deleted. You can purchase a new one from the `/shop`.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🎨 Manage Your Custom Role",
            description=f"You are managing the role: {role.mention}",
            color=role.color
        )
        embed.add_field(name="Current Name", value=role.name, inline=True)
        embed.add_field(name="Current Color", value=str(role.color), inline=True)
        
        view = ManageRoleView(interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))
