"""
Main bot logic for Discord Voice Call Transcriber.
"""

import discord
from discord.ext import commands
import config
from voice_handler import VoiceHandler
from transcriber import Transcriber

class TranscriberBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.message_content = True

        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)

        self.voice_handler = VoiceHandler(self)
        self.transcriber = Transcriber()

    async def on_ready(self):
        print(f'Bot is ready. Logged in as {self.user}')
        await self.change_presence(activity=discord.Game(name=config.BOT_ACTIVITY))

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        print(f'Command error: {error}')

def main():
    bot = TranscriberBot()

    # Add commands here
    @bot.command(name='join')
    async def join_voice(ctx):
        """Join the voice channel the user is in."""
        # Implementation here
        pass

    @bot.command(name='leave')
    async def leave_voice(ctx):
        """Leave the voice channel."""
        # Implementation here
        pass

    # Run the bot
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        print("Error: DISCORD_TOKEN not found in environment variables.")

if __name__ == '__main__':
    main()