"""
Main bot logic for Discord Voice Call Transcriber.
"""

import discord
import config
import os
import json
import subprocess
import requests
import asyncio
import logging
import platform
import uuid
from datetime import datetime
from voice_handler import VoiceHandler
from transcriber import Transcriber
from utils import export_training_data, save_transcript_for_training
from vector_store import SessionVectorStore

# Configure logging
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
logger = logging.getLogger(__name__)

# File paths constants
CHARACTER_MAP_FILE = "character_map.json"
NOTES_CHANNEL_MAP_FILE = "notes_channel_map.json"
TRANSCRIPTIONS_DIR = "transcriptions"
OBSIDIAN_NOTES_DIR = "obsidian_notes"
OLLAMA_TIMEOUT = 2
OLLAMA_URL = "http://localhost:11434/api/tags"


class TranscriberBot:
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.message_content = True

        self.bot = discord.Bot(intents=intents)
        self.voice_handler = VoiceHandler(self)
        self.transcriber = Transcriber()
        self.vector_store = SessionVectorStore()
        self.current_voice_client = None
        self.character_map = self.load_character_map()
        self.notes_channel_map = self.load_notes_channel_map()

        self.ensure_opus_loaded()

        for directory in [OBSIDIAN_NOTES_DIR, TRANSCRIPTIONS_DIR]:
            os.makedirs(directory, exist_ok=True)

        self.bot.event(self.on_ready)
        self.bot.event(self.on_app_command_error)
        self.register_commands()

    def run(self, token: str):
        self.bot.run(token)

    def ensure_opus_loaded(self) -> bool:
        """Ensure the Opus library is loaded for voice support."""
        if discord.opus.is_loaded():
            return True

        for lib_name in ("libopus-0.dll", "opus.dll", "libopus.dll"):
            try:
                discord.opus.load_opus(lib_name)
                logger.info(f"Loaded Opus library: {lib_name}")
                return True
            except Exception as exc:
                logger.debug(f"Failed to load Opus library {lib_name}: {exc}")

        discord_root = os.path.dirname(discord.__file__)
        dll_paths = [
            os.path.join(discord_root, "bin", "libopus-0.x64.dll"),
            os.path.join(discord_root, "bin", "libopus-0.x86.dll"),
        ]
        for dll_path in dll_paths:
            if not os.path.exists(dll_path):
                continue
            try:
                discord.opus.load_opus(dll_path)
                logger.info(f"Loaded Opus library from path: {dll_path}")
                return True
            except Exception as exc:
                logger.debug(f"Failed to load Opus library {dll_path}: {exc}")

        logger.warning(
            "Opus library is not loaded. Voice support will not work until Opus is installed or available via the py-cord DLL path."
        )
        return False

    def load_character_map(self):
        """Load character map from file."""
        try:
            with open(CHARACTER_MAP_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse {CHARACTER_MAP_FILE}, starting with empty map")
            return {}
        except Exception as e:
            logger.error(f"Error loading character map: {e}")
            return {}

    def save_character_map(self):
        """Save character map to file."""
        try:
            with open(CHARACTER_MAP_FILE, "w") as f:
                json.dump(self.character_map, f, indent=2)
            return True
        except IOError as e:
            logger.error(f"Failed to save character map: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving character map: {e}")
            return False

    def load_notes_channel_map(self):
        """Load notes channel map from file (guild_id -> channel_id)."""
        try:
            with open(NOTES_CHANNEL_MAP_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse {NOTES_CHANNEL_MAP_FILE}, starting with empty map")
            return {}
        except Exception as e:
            logger.error(f"Error loading notes channel map: {e}")
            return {}

    def save_notes_channel_map(self):
        """Save notes channel map to file."""
        try:
            with open(NOTES_CHANNEL_MAP_FILE, "w") as f:
                json.dump(self.notes_channel_map, f, indent=2)
            return True
        except IOError as e:
            logger.error(f"Failed to save notes channel map: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving notes channel map: {e}")
            return False

    async def on_ready(self):
        logger.info(f"Bot is ready. Logged in as {self.bot.user}")
        await self.bot.change_presence(activity=discord.Game(name=config.BOT_ACTIVITY))

        for guild in self.bot.guilds:
            if guild.me is None:
                logger.warning(f"Cannot edit bot member in guild {guild.id}: guild.me is None")
                continue

            if guild.me.nick is None or guild.me.nick == self.bot.user.name:
                try:
                    await guild.me.edit(nick="Fly Scribe")
                except discord.Forbidden:
                    logger.debug(f"No permission to change nickname in guild {guild.id}")
                except Exception as e:
                    logger.error(f"Error changing nickname in guild {guild.id}: {e}")

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.DiscordException):
        """Handle errors in slash commands."""
        command_name = getattr(interaction.command, "name", "unknown")
        logger.error(f"Slash command error in {command_name}: {error}", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    async def close(self):
        """Clean up voice clients before closing."""
        try:
            for guild_id in list(self.voice_handler.voice_clients.keys()):
                try:
                    await self.voice_handler.leave_voice_channel(guild_id)
                except Exception as e:
                    logger.error(f"Error disconnecting voice client for guild {guild_id}: {e}")
            if self.current_voice_client and self.current_voice_client.is_connected():
                try:
                    await self.current_voice_client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting current voice client: {e}")
        except Exception as e:
            logger.error(f"Error closing voice clients: {e}")
        finally:
            await self.bot.close()

    def _build_prior_context(self, guild_id, transcription, n_results=3):
        """
        Retrieve related past session summaries for this guild to give the
        summarizer continuity across sessions. Returns None (not an empty
        string) when nothing relevant is found, so the prompt template can
        omit the context block entirely rather than injecting an empty one.
        """
        query_text = transcription[:4000]
        results = self.vector_store.query(guild_id, query_text, n_results=n_results)
        if not results:
            return None

        return "\n\n".join(
            f"[{meta.get('timestamp', 'unknown date')}] {doc}" for doc, meta in results
        )

    async def process_recording(self, user_files: dict, channel: discord.TextChannel):
        """Handle transcription and summary generation for a saved recording."""
        try:
            loop = asyncio.get_running_loop()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            unique_id = str(uuid.uuid4())[:8]
            transcription_filename = os.path.join(TRANSCRIPTIONS_DIR, f"transcription_{timestamp}_{unique_id}.txt")

            await channel.send("Recording stopped. Preparing transcription...")

            enhanced_transcription = await loop.run_in_executor(
                None, self.transcriber.transcribe_speakers, user_files, self.character_map
            )

            if not enhanced_transcription.strip():
                await channel.send("No speech was detected in the recording.")
                return

            try:
                with open(transcription_filename, "w", encoding="utf-8") as f:
                    f.write(f"Session Timestamp: {timestamp}\n\n")
                    f.write(f"Enhanced Transcription:\n{enhanced_transcription}\n\n")
            except IOError as e:
                logger.error(f"Failed to write transcription file: {e}")
                await channel.send(f"Error: Could not save transcription file: {e}")
                return

            if not await is_ollama_running():
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

            guild = channel.guild
            prior_context = await loop.run_in_executor(
                None, self._build_prior_context, guild.id, enhanced_transcription
            )

            await channel.send("Generating summary with LLM...")
            summary = await loop.run_in_executor(
                None,
                self.transcriber.summarize_with_llm,
                enhanced_transcription,
                self.character_map,
                prior_context,
            )

            try:
                with open(transcription_filename, "a", encoding="utf-8") as f:
                    f.write(f"Summary:\n{summary}\n")
            except IOError as e:
                logger.error(f"Failed to append summary to file: {e}")
                await channel.send(f"Warning: Could not save summary to file: {e}")

            try:
                save_transcript_for_training(
                    enhanced_transcription, summary, unique_id, channel.name
                )
            except Exception as e:
                logger.error(f"Failed to save training data: {e}")

            characters = [info["name"] for info in self.character_map.values()]
            await loop.run_in_executor(
                None,
                self.vector_store.add_session,
                guild.id,
                unique_id,
                timestamp,
                channel.name,
                characters,
                summary,
            )

            note_file = await loop.run_in_executor(
                None, self.transcriber.save_obsidian_note, summary, self.character_map
            )
            if note_file:
                await channel.send(f"📝 Session notes saved to: `{note_file}`")

            guild_id = str(guild.id)
            if guild_id in self.notes_channel_map:
                channel_id = self.notes_channel_map[guild_id]
                notes_channel = guild.get_channel(channel_id)
                if notes_channel:
                    embed = discord.Embed(
                        title="📖 D&D Session Summary",
                        description=summary,
                        color=discord.Color.blue(),
                        timestamp=datetime.now(),
                    )
                    if self.character_map:
                        chars = ", ".join([info["name"] for info in self.character_map.values()])
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
                f"🎙️ Recorded {len(user_files)} speaker track(s)\n"
                f"📄 Transcription saved to: `{transcription_filename}`\n\n"
                f"**Transcription:**\n{enhanced_transcription[:1000]}...\n\n"
                f"**Summary:**\n{summary}"
            )

        except Exception as e:
            logger.error(f"Error processing recording: {e}", exc_info=e)
            await channel.send(f"❌ Error during transcription: {e}")

    def register_commands(self):
        @self.bot.slash_command(
            name="name_me",
            description=("Set the bot's nickname in this server "
                         "(used in transcriptions and join messages)."),
        )
        async def name_me(ctx: discord.ApplicationContext, name: str):
            try:
                await ctx.guild.me.edit(nick=name) # type: ignore
                await ctx.respond(f"Bot name changed to '{name}'!")
            except discord.Forbidden:
                await ctx.respond("I don't have permission to change my nickname here.")
            except Exception as e:
                await ctx.respond(f"Failed to change name: {e}")

        @self.bot.slash_command(name="join", description="Join the voice channel you are in.")
        async def join(ctx: discord.ApplicationContext):
            if not self.ensure_opus_loaded():
                await ctx.respond(
                    "Voice cannot connect because the Opus library is not loaded. "
                    "Install a compatible Opus library and restart the bot."
                )
                return

            member = getattr(ctx, "author", None) or getattr(ctx, "user", None)
            voice = getattr(member, "voice", None)

            if not voice or not getattr(voice, "channel", None):
                await ctx.respond("Buzz-Buzz, You aren't in a voice channel!")
                return

            guild = ctx.guild
            if guild is None:
                await ctx.respond("This command must be used in a server.")
                return

            if self.voice_handler.get_voice_client(guild.id) and self.voice_handler.get_voice_client(guild.id).is_connected():
                await ctx.respond("I'm already connected to a voice channel in this server.")
                return

            try:
                voice_client = await self.voice_handler.join_voice_channel(voice.channel)
                self.current_voice_client = voice_client
                bot_name = guild.me.display_name if guild.me else "Fly Scribe"
                await ctx.respond(f"{bot_name} joined {voice.channel.name}!")
            except discord.errors.ConnectionClosed as e:
                logger.exception("Failed to join voice channel")
                if getattr(e, 'code', None) == 4017:
                    await ctx.respond(
                        "Failed to join voice: voice websocket closed with code 4017. "
                        "This often means the voice server accepted the handshake but "
                        "the voice session could not be established. "
                        "Check that the bot has CONNECT/SPEAK permissions and that "
                        "outbound UDP to Discord voice servers is allowed."
                    )
                else:
                    await ctx.respond(f"Failed to join the voice channel: {e}")
            except Exception as e:
                logger.exception("Failed to join voice channel")
                await ctx.respond(f"Failed to join the voice channel: {e}")

        @self.bot.slash_command(name="leave", description="Leave the voice channel.")
        async def leave(ctx: discord.ApplicationContext):
            if not ctx.guild:
                await ctx.respond("This command must be used in a guild.")
                return
            voice_client = self.current_voice_client or self.voice_handler.get_voice_client(ctx.guild.id)
            if voice_client and voice_client.is_connected():
                await self.voice_handler.leave_voice_channel(ctx.guild.id)
                self.current_voice_client = None
                await ctx.respond("Left the voice channel.")
            else:
                await ctx.respond("I'm not currently in a voice channel.")

        @self.bot.slash_command(name="inscribe", description="Start recording the current voice channel.")
        async def inscribe(ctx: discord.ApplicationContext):
            if not ctx.guild:
                await ctx.respond("This command must be used in a guild.")
                return

            voice_client = self.current_voice_client or self.voice_handler.get_voice_client(ctx.guild.id)
            if voice_client is None or not voice_client.is_connected():
                await ctx.respond("I need to join a voice channel first. Use /join.")
                return

            if self.voice_handler.start_recording(voice_client):
                bot_name = ctx.guild.me.display_name if ctx.guild and ctx.guild.me else "Fly Scribe"
                channel_name = voice_client.channel.name if voice_client.channel else "unknown channel"
                await ctx.respond(f"{bot_name} is now inscribing {channel_name}.")
            else:
                await ctx.respond("Already recording.")

        @self.bot.slash_command(name="stop", description="Stop recording and transcribe the session.")
        async def stop(ctx: discord.ApplicationContext):
            if not ctx.guild:
                await ctx.respond("This command must be used in a guild.")
                return

            await ctx.defer()
            voice_client = self.current_voice_client or self.voice_handler.get_voice_client(ctx.guild.id)

            if voice_client and self.voice_handler.is_recording(ctx.guild.id):
                user_files = await self.voice_handler.stop_recording(ctx.guild.id)
                if user_files:
                    await ctx.followup.send(
                        f"Recording stopped. Captured {len(user_files)} speaker track(s)."
                    )
                    if isinstance(ctx.channel, discord.TextChannel):
                        await self.process_recording(user_files, ctx.channel)
                    else:
                        await ctx.followup.send(
                            "Unable to transcribe because this command was not issued from a text channel."
                        )
                else:
                    await ctx.followup.send("Failed to save recording (no audio captured).")
            else:
                await ctx.followup.send("I am not currently recording in this voice channel.")

        @self.bot.slash_command(
            name="assign_dm",
            description="Assign a Discord user as the DM for better transcription context.",
        )
        async def assign_dm(ctx: discord.ApplicationContext, user: discord.User):
            user_id = str(user.id)
            self.character_map[user_id] = {
                "user_id": user_id,
                "username": user.name,
                "name": user.name,
                "class": "Dungeon Master",
                "species": "N/A",
                "gender": "N/A",
                "age": "N/A",
            }
            if self.save_character_map():
                await ctx.respond(f"Assigned {user.mention} as DM.")
            else:
                await ctx.respond(
                    "Assigned DM in memory, but failed to persist the character map."
                )

        @self.bot.slash_command(
            name="assign_character",
            description="Assign a character name to a Discord user for transcription enhancement.",
        )
        @discord.option("character_name", description="Character name")
        @discord.option("character_class", description="Character class")
        @discord.option("character_species", description="Character species")
        @discord.option("character_gender", description="Character gender")
        @discord.option("character_age", description="Character age", required=False)
        async def assign_character(
            ctx: discord.ApplicationContext,
            user: discord.User,
            character_name: str,
            character_class: str,
            character_species: str,
            character_gender: str,
            character_age: int = 0,
        ):
            user_id = str(user.id)
            self.character_map[user_id] = {
                "user_id": user_id,
                "username": user.name,
                "name": character_name,
                "class": character_class,
                "species": character_species,
                "gender": character_gender,
                "age": character_age,
            }
            if self.save_character_map():
                await ctx.respond(f"Assigned '{character_name}' to {user.mention}.")
            else:
                await ctx.respond(
                    "Assigned the character in memory, but failed to persist the character map."
                )

        @self.bot.slash_command(
            name="remove_character",
            description="Remove a user's assigned character name.",
        )
        async def remove_character(ctx: discord.ApplicationContext, user: discord.User):
            user_key = str(user.id)
            deleted = False
            if user_key in self.character_map:
                del self.character_map[user_key]
                deleted = True
            else:
                legacy_key = next(
                    (
                        key
                        for key, value in self.character_map.items()
                        if value.get("user_id") == user_key or key == user.name
                    ),
                    None,
                )
                if legacy_key:
                    del self.character_map[legacy_key]
                    deleted = True

            if deleted:
                if self.save_character_map():
                    await ctx.respond(f"Removed character assignment for {user.mention}.")
                else:
                    await ctx.respond(
                        "Removed the character assignment in memory, but failed to persist changes."
                    )
            else:
                await ctx.respond(f"No character assigned to {user.mention}.")

        @self.bot.slash_command(
            name="remove_all_characters",
            description="Reset entire character map.",
        )
        async def remove_all_characters(ctx: discord.ApplicationContext):
            self.character_map = {}
            if self.save_character_map():
                await ctx.respond("All character assignments have been removed.")
            else:
                await ctx.respond(
                    "Cleared all character assignments in memory, but failed to persist the character map."
                )

        @self.bot.slash_command(
            name="export_data",
            description=(
                "Export collected session transcripts+summaries as instruction/response "
                "training pairs for LLM fine-tuning (admin only)."
            ),
        )
        async def export_data(ctx: discord.ApplicationContext):
            if not ctx.user.guild_permissions.administrator:
                await ctx.respond("You need administrator permissions to export training data.")
                return

            await ctx.defer(ephemeral=True)
            loop = asyncio.get_running_loop()
            try:
                output_path = await loop.run_in_executor(None, export_training_data)
            except Exception as e:
                logger.error(f"Failed to export training data: {e}")
                await ctx.followup.send(f"Failed to export training data: {e}", ephemeral=True)
                return

            if output_path:
                await ctx.followup.send(
                    f"Training data exported to `{output_path}`. "
                    "See DND_LLM_GUIDE.md for how to use it with train_llm.py.",
                    ephemeral=True,
                )
            else:
                await ctx.followup.send(
                    "No training data found yet — run a few sessions with /stop first.",
                    ephemeral=True,
                )

        @self.bot.slash_command(
            name="sync_commands",
            description="Sync slash commands (admin only).",
        )
        async def sync_commands(ctx: discord.ApplicationContext):
            if not ctx.user.guild_permissions.administrator:
                await ctx.respond("You need administrator permissions to sync commands.")
                return

            try:
                await ctx.defer()
            except Exception as e:
                logger.error(f"Failed to defer sync_commands: {e}")
                await ctx.respond(
                    "Failed to start command sync. Please try again.", ephemeral=True
                )
                return

            try:
                await self.bot.sync_commands()
                await ctx.followup.send("Commands synced successfully!")
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")
                await ctx.followup.send(f"Failed to sync commands: {e}")

        @self.bot.slash_command(
            name="list_characters",
            description="List all assigned character names.",
        )
        async def list_characters(ctx: discord.ApplicationContext):
            if not self.character_map:
                await ctx.respond("No characters assigned yet.")
                return

            entries = []
            for info in self.character_map.values():
                user_id = info.get("user_id")
                character_name = info.get("name", "Unknown")
                character_class = info.get("class", "N/A")
                character_species = info.get("species", "N/A")
                character_gender = info.get("gender", "N/A")
                username = info.get("username") or "Unknown"

                try:
                    user = await self.bot.fetch_user(int(user_id)) if user_id else None
                    display_name = user.mention if user else f"@{username}"
                except (ValueError, discord.NotFound):
                    display_name = f"@{username}"

                entries.append(
                    f"**{display_name}** - {character_name} \n"
                    f"Class: {character_class} | Species: {character_species} | Gender: {character_gender}"
                )

            chunks = []
            current_chunk = ""
            for entry in entries:
                entry_text = f"{entry}\n\n"
                if len(current_chunk) + len(entry_text) > 1900:
                    chunks.append(current_chunk)
                    current_chunk = entry_text
                else:
                    current_chunk += entry_text
            if current_chunk:
                chunks.append(current_chunk)

            await ctx.respond(f"**Assigned Characters:**\n{chunks[0]}")
            for remaining in chunks[1:]:
                await ctx.followup.send(remaining)

        @self.bot.slash_command(
            name="set_notes_channel",
            description="Set the Discord channel where session notes will be posted (admin only).",
        )
        async def set_notes_channel(ctx: discord.ApplicationContext, channel: discord.TextChannel):
            if not ctx.user.guild_permissions.administrator:
                await ctx.respond("You need administrator permissions to set the notes channel.")
                return
            guild_id = str(ctx.guild.id)
            self.notes_channel_map[guild_id] = channel.id
            if self.save_notes_channel_map():
                await ctx.respond(f"Notes will now be posted to {channel.mention}")
            else:
                await ctx.respond(
                    "Notes channel updated in memory, but failed to persist the notes channel map."
                )

        @self.bot.slash_command(
            name="get_notes_channel",
            description="Get the current notes channel for this server.",
        )
        async def get_notes_channel(ctx: discord.ApplicationContext):
            guild_id = str(ctx.guild.id)
            if guild_id in self.notes_channel_map:
                channel = ctx.guild.get_channel(self.notes_channel_map[guild_id])
                if channel:
                    await ctx.respond(f"Notes channel: {channel.mention}")
                else:
                    await ctx.respond(
                        "Notes channel is set but no longer exists."
                    )
            else:
                await ctx.respond(
                    ("No notes channel set for this server. "
                    "Use `/set_notes_channel #channel` to set one.")
                )

        @self.bot.slash_command(
            name="recall",
            description="Semantically search past session summaries for this server.",
        )
        @discord.option("query", description="What are you trying to remember?")
        async def recall(ctx: discord.ApplicationContext, query: str):
            await ctx.defer()
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, self.vector_store.query, ctx.guild.id, query, 5
            )

            if not results:
                await ctx.followup.send(
                    "No matching sessions found (or the vector store/Ollama isn't reachable)."
                )
                return

            chunks = []
            for doc, meta in results:
                timestamp = meta.get("timestamp", "unknown date")
                characters = meta.get("characters") or "unknown characters"
                chunks.append(f"**{timestamp}** ({characters})\n{doc[:500]}")

            await ctx.followup.send(
                f"**Sessions matching '{query}':**\n\n" + "\n\n---\n\n".join(chunks)
            )

        @self.bot.slash_command(name="help", description="Show the help message for Fly Scribe.")
        async def help_command(ctx: discord.ApplicationContext):
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
                "- /recall [query] - Semantically search past session summaries\n"
                "- /export_data - Export session data as LLM fine-tuning pairs (admin only)\n"
                "- /sync_commands - Sync slash commands (admin only)\n"
                "- /help - Show this help message\n"
            )
            await ctx.respond(help_message)


def is_ollama_running():
    """Check if Ollama server is running without blocking event loop."""
    def _check_ollama():
        try:
            response = requests.get(OLLAMA_URL, timeout=OLLAMA_TIMEOUT)
            return response.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False
        except Exception as e:
            logger.error(f"Error checking Ollama status: {e}")
            return False

    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, _check_ollama)


async def start_ollama_server():
    """Start the Ollama server in the background."""
    try:
        if platform.system() == "Windows":
            subprocess.Popen(
                ["ollama", "serve"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )

        for _ in range(10):
            await asyncio.sleep(1)
            if await is_ollama_running():
                return True
        return False
    except FileNotFoundError:
        logger.error("Ollama not found in PATH. Please install Ollama.")
        return False
    except Exception as e:
        logger.error(f"Error starting Ollama: {e}")
        return False

def main():
    bot = TranscriberBot()
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.error("DISCORD_TOKEN not found in environment variables.")

if __name__ == "__main__":
    main()
