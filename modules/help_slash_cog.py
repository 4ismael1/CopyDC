import discord
from discord import app_commands
from discord.ext import commands

from modules.help_cog import HelpView, resolve_help_language


class HelpSlashCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Muestra el menu de ayuda")
    async def slash_help(self, interaction: discord.Interaction):
        locale = interaction.guild_locale or interaction.locale
        view = HelpView(lang=resolve_help_language(locale), current_index=0)
        await interaction.response.send_message(embed=view.embeds[0], view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpSlashCog(bot))
