"""
Main bot logic for Discord Voice Call Transcriber.
"""

import discord
from discord.ext import commands
from discord import option
import config
import os
import json
import subprocess
import requests
import asyncio
from datetime import datetime
from voice_handler import VoiceHandler
from transcriber import Transcriber


class TranscriberBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.message_content = True

        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

        self.voice_handler = VoiceHandler(self)
        self.transcriber = Transcriber()
        self.current_voice_client = None
        self.character_map = self.load_character_map()
        self.notes_channel_map = self.load_notes_channel_map()

        # Ensure notes directory exists
        if not os.path.exists("obsidian_notes"):
            os.makedirs("obsidian_notes")

    async def setup_hook(self):
        await self.tree.sync()

    def load_character_map(self):
        """Load character map from file."""
        try:
            with open("character_map.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_character_map(self):
        """Save character map to file."""
        with open("character_map.json", "w") as f:
            json.dump(self.character_map, f)

    def load_notes_channel_map(self):
        """Load notes channel map from file (guild_id -> channel_id)."""
        try:
            with open("notes_channel_map.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_notes_channel_map(self):
        """Save notes channel map to file."""
        with open("notes_channel_map.json", "w") as f:
            json.dump(self.notes_channel_map, f)

    async def on_ready(self):
        print(f"Bot is ready. Logged in as {self.user}")
        await self.change_presence(activity=discord.Game(name=config.BOT_ACTIVITY))

        # Set default nickname to 'Fly Scribe' in all guilds if not already set
        for guild in self.guilds:
            if guild.me.nick is None or guild.me.nick == self.user.name:
                try:
                    await guild.me.edit(nick="Fly Scribe")
                except discord.Forbidden:
                    pass  # Skip if no permission

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        print(f"Command error: {error}")


def is_ollama_running():
    """Check if Ollama server is running."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False


async def start_ollama_server():
    """Start the Ollama server in the background."""
    try:
        # Platform-specific startup
        import platform

        if platform.system() == "Windows":
            # On Windows, start ollama serve in background
            subprocess.Popen(
                ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            # On macOS/Linux
            subprocess.Popen(
                ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        # Wait for server to start (give it up to 10 seconds)
        for i in range(10):
            await asyncio.sleep(1)
            if is_ollama_running():
                return True
        return False
    except Exception as e:
        print(f"Error starting Ollama: {e}")
        return False

async def process_recording(filename: str, channel: discord.TextChannel, bot: TranscriberBot):
    """Handle transcription and summary generation for a saved recording."""
    try:
        if not os.path.exists("transcriptions"):
            os.makedirs("transcriptions")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        transcription_filename = f"transcriptions/transcription_{timestamp}.txt"

        await channel.send("Recording stopped. Preparing transcription...")

        transcription = bot.transcriber.transcribe_audio(filename)
        enhanced_transcription = bot.transcriber.enhance_transcription(
            transcription, bot.character_map
        )

        with open(transcription_filename, "w", encoding="utf-8") as f:
            f.write(f"Session Timestamp: {timestamp}\n\n")
            f.write(f"Enhanced Transcription:\n{enhanced_transcription}\n\n")

        if not is_ollama_running():
            await channel.send(
                "Ollama server not running. Starting it now (this may take a moment)..."
            )
            if await start_ollama_server():
                await channel.send("Ollama server started successfully!")
            else:
                await channel.send(
                    "Failed to start Ollama server. Ensure Ollama is installed and try again."
                )
                return

        await channel.send("Generating summary with LLM...")
        summary = bot.transcriber.summarize_with_llm(
            enhanced_transcription, bot.character_map
        )

        with open(transcription_filename, "a", encoding="utf-8") as f:
            f.write(f"Summary:\n{summary}\n")

        note_file = bot.transcriber.save_obsidian_note(summary, bot.character_map)
        if note_file:
            await channel.send(f"📝 Session notes saved to: `{note_file}`")

        guild = channel.guild
        guild_id = str(guild.id)
        if guild_id in bot.notes_channel_map:
            channel_id = bot.notes_channel_map[guild_id]
            notes_channel = guild.get_channel(channel_id)
            if notes_channel:
                embed = discord.Embed(
                    title="📖 D&D Session Summary",
                    description=summary,
                    color=discord.Color.blue(),
                    timestamp=datetime.now(),
                )
                if bot.character_map:
                    chars = ", ".join([info["name"] for info in bot.character_map.values()])
                    embed.add_field(name="Characters", value=chars, inline=False)
                embed.set_footer(text="Generated by Fly Scribe Bot")
                try:
                    await notes_channel.send(embed=embed)
                except discord.Forbidden:
                    await channel.send(
                        f"⚠️ Cannot post to {notes_channel.mention} (permission denied)"
                    )

        await channel.send(
            f"✅ Session complete!\n\n"
            f"📁 Recording saved to: `{filename}`\n"
            f"📄 Transcription saved to: `{transcription_filename}`\n\n"
            f"**Transcription:**\n{enhanced_transcription}\n\n"
            f"**Summary:**\n{summary}"
        )

    except Exception as e:
        await channel.send(f"❌ Error during transcription: {e}")
        print(f"Error processing recording: {e}")


def main():
    bot = TranscriberBot()

    @bot.slash_command(
        name="name_me",
        description=("Set the bot's nickname in this server "
                        "(used in transcriptions and join messages).")
    )
    async def name_me(interaction: discord.Interaction, name: str):
        try:
            await interaction.guild.me.edit(nick=name)
            await interaction.response.send_message(f"Bot name changed to '{name}'!")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to change my nickname here."
            )
        except Exception as e:
            await interaction.response.send_message(f"Failed to change name: {e}")

    @bot.slash_command(name="join", description="Join the voice channel you are in.")
    async def join_voice(interaction: discord.Interaction):
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.response.send_message(
                "You need to be in a voice channel to use this command."
            )
            return

        channel = interaction.user.voice.channel
        voice_client = await bot.voice_handler.join_voice_channel(channel)
        bot.current_voice_client = voice_client

        bot_name = interaction.guild.me.display_name

        if voice_client:
            await interaction.response.send_message(f"{bot_name} joined {channel.name}!")
        else:
            await interaction.response.send_message("Failed to join the voice channel.")

    @bot.slash_command(name="leave", description="Leave the voice channel.")
    async def leave_voice(interaction: discord.Interaction):
        voice_client = bot.current_voice_client or bot.voice_handler.get_voice_client(
            interaction.guild.id
        )
        if voice_client and voice_client.is_connected():
            await bot.voice_handler.leave_voice_channel(interaction.guild.id)
            bot.current_voice_client = None
            await interaction.response.send_message("Left the voice channel.")
        else:
            await interaction.response.send_message("I'm not currently in a voice channel.")

    @bot.slash_command(name="inscribe", description="Start recording the current voice channel.")
    async def inscribe(interaction: discord.Interaction):
        voice_client = bot.current_voice_client or bot.voice_handler.get_voice_client(
            interaction.guild.id
        )

        if voice_client is None or not voice_client.is_connected():
            await interaction.response.send_message(
                "I need to join a voice channel first. Use /join."
            )
            return

        if bot.voice_handler.start_recording(voice_client):
            bot_name = interaction.guild.me.display_name
            channel_name = voice_client.channel.name if voice_client.channel else "unknown channel"
            await interaction.response.send_message(f"{bot_name} is now inscribing {channel_name}.")
        else:
            await interaction.response.send_message("Already recording.")

    @bot.slash_command(name="stop", description="Stop recording and transcribe the session.")
    async def stop(interaction: discord.Interaction):
        await interaction.response.defer()
        voice_client = bot.current_voice_client or bot.voice_handler.get_voice_client(
            interaction.guild.id
        )

        if voice_client and bot.voice_handler.recording:
            filename = bot.voice_handler.stop_recording()
            if filename:
                await interaction.followup.send(f"Recording stopped. File saved as: {filename}")
                await process_recording(filename, interaction.channel, bot)
            else:
                await interaction.followup.send("Failed to save recording.")
        else:
            await interaction.followup.send("I am not currently recording in this voice channel.")
        

    @bot.slash_command(
        name="assign_dm",
        description="Assign a Discord user as the DM for better transcription context.",
    )
    async def assign_dm(interaction: discord.Interaction, user: discord.User):
        bot.character_map[str(user.id)] = {
            "name": "DM",
            "class": "Dungeon Master",
            "species": "N/A",
        }
        bot.save_character_map()
        await interaction.response.send_message(f"Assigned {user.mention} as DM.")

    @bot.slash_command(
        name="assign_character",
        description="Assign a character name to a Discord user for transcription enhancement.",
    )
    @option("user", description="Discord user to assign")
    @option("character_name", description="Character name")
    @option("character_class", description="Character class", required=False)
    @option("character_species", description="Character species", required=False)
    @option("character_gender", description="Character gender", required=False)

    async def assign_character(
        interaction: discord.Interaction,
        user: discord.User,
        character_name: str,
        character_class: str = None,
        character_species: str = None,
        character_gender: str = None,
    ):
        bot.character_map[str(user.id)] = {
            "name": character_name,
            "class": character_class,
            "species": character_species,
            "gender": character_gender,
        }
        bot.save_character_map()
        await interaction.response.send_message(f"Assigned '{character_name}' to {user.mention}.")

    @bot.slash_command(
        name="remove_character", description="Remove a user's assigned character name."
    )
    async def remove_character(interaction: discord.Interaction, user: discord.User):
        if str(user.id) in bot.character_map:
            del bot.character_map[str(user.id)]
            bot.save_character_map()
            await interaction.response.send_message(
                f"Removed character assignment for {user.mention}."
            )
        else:
            await interaction.response.send_message(f"No character assigned to {user.mention}.")

    @bot.slash_command(name="remove_all_characters", description="Reset entire character map.")
    async def remove_all_characters(interaction: discord.Interaction):
        bot.character_map = {}
        bot.save_character_map()
        await interaction.response.send_message("All character assignments have been removed.")

    @bot.slash_command(name="sync_commands", description="Sync slash commands (admin only).")
    async def sync_commands(
        interaction: discord.Interaction,
        global_sync: bool = False,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to sync commands."
            )
            return

        await interaction.response.defer()
        try:
            if global_sync:
                synced = await bot.tree.sync()
                await interaction.followup.send(
                    f"Globally synced {len(synced)} commands."
                )
            else:
                synced = await bot.tree.sync(guild=interaction.guild)
                await interaction.followup.send(
                    f"Synced {len(synced)} commands for this guild."
                )
        except Exception as e:
            await interaction.followup.send(f"Failed to sync commands: {e}")

    @bot.slash_command(name="list_characters", description="List all assigned character names.")
    async def list_characters(interaction: discord.Interaction):
        if bot.character_map:
            char_list = []
            for handle, info in bot.character_map.items():
                user = bot.get_user(int(handle)) if handle.isdigit() else None
                display_name = user.mention if user else handle
                char_list.append(
                    f"""{display_name}:
                            {info['name']} (
                                {info.get('class', 'N/A')},
                                {info.get('species', 'N/A')},
                                {info.get('gender', 'N/A')})
                    """
                )
            await interaction.response.send_message(
                f"Assigned characters:\n{chr(10).join(char_list)}"
            )
        else:
            await interaction.response.send_message("No characters assigned yet.")

    @bot.slash_command(
        name="set_notes_channel",
        description="Set the Discord channel where session notes will be posted (admin only).",
    )
    async def set_notes_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to set the notes channel."
            )
            return
        guild_id = str(interaction.guild.id)
        bot.notes_channel_map[guild_id] = channel.id
        bot.save_notes_channel_map()
        await interaction.response.send_message(f"Notes will now be posted to {channel.mention}")

    @bot.slash_command(
        name="get_notes_channel", description="Get the current notes channel for this server."
    )
    async def get_notes_channel(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if guild_id in bot.notes_channel_map:
            channel = interaction.guild.get_channel(bot.notes_channel_map[guild_id])
            if channel:
                await interaction.response.send_message(f"Notes channel: {channel.mention}")
            else:
                await interaction.response.send_message(
                    "Notes channel is set but no longer exists."
                )
        else:
            await interaction.response.send_message(
                ("No notes channel set for this server. "
                "Use `/set_notes_channel #channel` to set one.")
            )

    @bot.slash_command(name="help", description="Show the help message for Fly Scribe.")
    async def help_command(interaction: discord.Interaction):
        help_message = (
            "**Fly Scribe is a fly-on-the-wall voice transcriber for D&D sessions.**\n"
            "Available commands:\n"
            "- /name_me [name] - Set the bot's nickname\n"
            "- /join - Join the voice channel you're in\n"
            "- /leave - Leave the voice channel\n"
            "- /inscribe - Start recording the voice channel\n"
            "- /stop - Stop recording and get transcription + summary\n"
            "- /assign_character [user] [character_name] [class] [species] [gender] "
            "Assign a character name, class, species, and gender\n"
            "- /assign_dm [user] - Assign a Discord user as the DM\n"
            "- /remove_character [user] - Remove a character assignment\n"
            "- /remove_all_characters - Reset entire character map\n"
            "- /list_characters - List all assigned characters\n"
            "- /set_notes_channel [#channel] - Set where session notes are posted (admin only)\n"
            "- /get_notes_channel - Show the current notes channel\n"
            "- /sync_commands - Sync slash commands (admin only)\n"
            "- /help - Show this help message\n"
        )
        await interaction.response.send_message(help_message)

    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        print("Error: DISCORD_TOKEN not found in environment variables.")


if __name__ == "__main__":
    main()
