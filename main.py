import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
import asyncio
import threading

import database
import config
from cogs.verification import VerificationButton
from cogs.reporting import ReportTriggerView
from web_server import run_server # <-- Import the new function

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)-8s] %(name)-12s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)

class MyBot(commands.Bot):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # --- NEW: Start the web server in a background thread ---
        server_thread = threading.Thread(target=run_server)
        server_thread.daemon = True # Allows the bot to exit gracefully
        server_thread.start()
        log.info("Started background web server.")

        await database.initialize_database()
        
        self.add_view(ReportTriggerView(bot=self))
        self.add_view(VerificationButton(bot=self))
        
        log.info("Registered persistent UI views.")

        cogs_to_load = [
            "cogs.settings", "cogs.events", "cogs.moderation",
            "cogs.verification", "cogs.reaction_roles", "cogs.reporting",
            "cogs.temp_vc", "cogs.submissions", "cogs.tasks", "cogs.ranking",
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                log.info(f"Successfully loaded extension: {cog}")
            except Exception as e:
                log.error(f"Failed to load extension {cog}: {e}", exc_info=True)
        
        log.info("Syncing application commands...")
        synced = await self.tree.sync()
        log.info(f"Synced {len(synced)} commands globally.")

    # --- (The on_ready and if __name__ == "__main__" parts are unchanged) ---
    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info("Bot is ready! 🚀")
        # ... (activity setting logic)

if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.voice_states = True
    
    bot = MyBot(intents=intents)
    bot.run(TOKEN)