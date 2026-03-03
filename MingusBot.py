import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque

load_dotenv()
TOKEN = os.getenv('TOKEN')

SONG_QUEUE = {}
CURRENT_SONG = {}  # Tracks the currently playing song per guild

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='ming', intents=intents)

@bot.event
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="Mingus"
    ))
    print(f"{bot.user} is online!")

#TODO: Allow specific link entries with search query fallback
#TODO: Add playlist support
#TODO: Messages send twice when playing a song from an empty queue because the play command sends a message and then play_next sends another message. Need to consolidate these into one message or edit the original message instead of sending a new one in play_next.
#TODO: Add file (mp3, wav, etc) support
@bot.tree.command(name="play", description="Play a song or add to queue")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()  # Defer the response to allow time for processing

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("You need to be in a voice channel to play music.")
        return
    
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    ydl_options = {
        # 'format': 'bestaudio[abr<=96]/bestaudio',
        'format': 'bestaudio/best',  # More flexible format selection
        'noplaylist': True,
        'youtube_include_dash_manifest': False,
        'youtube_include_hls_manifest': False,
        'quiet': True,  # Suppress yt-dlp output
    }

    query = "ytsearch1: " + song_query
    try:
        results = await search_ytdlp_async(query, ydl_options)
        tracks = results.get('entries', [])
    except Exception as e:
        await interaction.followup.send(f'Error searching for "{song_query}": {str(e)}')
        return

    if not tracks or len(tracks) == 0:
        await interaction.followup.send(f'No results found for "{song_query}"')
        return
    
    first_track = tracks[0]
    audio_url = first_track['url']
    title = first_track.get('title', 'Untitled')

    guild_id = str(interaction.guild_id)
    if SONG_QUEUE.get(guild_id) is None:
        SONG_QUEUE[guild_id] = deque()

    SONG_QUEUE[guild_id].append((audio_url, title))

    queue_message = f'Added to queue: **{title}**'
    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(queue_message)
    else:
        await interaction.followup.send(queue_message)
        await play_next(voice_client, guild_id, interaction.channel)

@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.followup.send("Skipped the current song.")
    else:
        await interaction.followup.send("No song is currently playing.")

@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    await interaction.response.defer()
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.followup.send("I'm not connected to a voice channel.")
        return

    if not voice_client.is_playing():
        await interaction.followup.send("Nothing is currently playing.")
        return

    voice_client.pause()
    await interaction.followup.send("Paused the current song.")

@bot.tree.command(name="resume", description="Resume the current song")
async def resume(interaction: discord.Interaction):
    await interaction.response.defer()
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.followup.send("I'm not connected to a voice channel.")
        return

    if not voice_client.is_paused():
        await interaction.followup.send("Nothing is currently paused.")
        return

    voice_client.resume()
    await interaction.followup.send("Resumed the current song.")

@bot.tree.command(name="stop", description="Stop the music and clear the queue")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer the response to allow time for processing
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        await interaction.followup.send("I'm not connected to a voice channel.")
        return
    
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUE:
        SONG_QUEUE[guild_id_str].clear()  # Clear the queue
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    await interaction.followup.send("Stopped the current song and cleared the queue.")

    await asyncio.sleep(300)
    try:
        if voice_client.is_connected() and not voice_client.is_playing() and not voice_client.is_paused():
            await interaction.channel.send("Disconnecting due to inactivity.")
            await voice_client.disconnect()
    except Exception:
        pass  # Already disconnected, nothing to do

#TODO: Add a command to remove a specific song from the queue
#TODO: Add loop command

@bot.tree.command(name="clear", description="Clear the song queue without stopping the current song")
async def clear_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id_str = str(interaction.guild_id)

    if guild_id_str in SONG_QUEUE:
        SONG_QUEUE[guild_id_str].clear()
        await interaction.followup.send("Cleared the song queue.")
    else:
        await interaction.followup.send("The song queue is already empty.")

@bot.tree.command(name="queue", description="Show the current song queue")
async def show_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id_str = str(interaction.guild_id)

    current = CURRENT_SONG.get(guild_id_str)
    queue = SONG_QUEUE.get(guild_id_str)

    if not current and (not queue or len(queue) == 0):
        await interaction.followup.send("Nothing is currently playing and the queue is empty.")
        return

    message = ""
    if current:
        message += f":musical_note: Now Playing: **{current}**\n\n"

    if queue and len(queue) > 0:
        queue_list = [f"{idx + 1}. {title}" for idx, (_, title) in enumerate(queue)]
        message += "**Up Next:**\n" + "\n".join(queue_list)
    else:
        message += "No songs in queue."

    await interaction.followup.send(message)

# @bot.tree.command(name="remove", description="Remove a specific song from the queue by its position")

@bot.tree.command(name="leave", description="Stops music, clears queue, and disconnects")
async def leave(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer the response to allow time for processing
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        await interaction.followup.send("I'm not connected to a voice channel.")
        return
    
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUE:
        SONG_QUEUE[guild_id_str].clear()  # Clear the queue
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    await interaction.followup.send("Disconnecting :wave:")

    await voice_client.disconnect()  # Disconnect from the voice channel

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):

    embed = discord.Embed(
        title="Mingus Commands",
        color=discord.Color.blurple()
    )
    embed.add_field(name="/play [song]", value="Play a song or add it to the queue (search query)", inline=False)
    embed.add_field(name="/pause", value="Pause the current song", inline=False)
    embed.add_field(name="/resume", value="Resume the current song", inline=False)
    embed.add_field(name="/skip", value="Skip the current song", inline=False)
    embed.add_field(name="/stop", value="Stop the music and clear the queue", inline=False)
    embed.add_field(name="/queue", value="Show the current song queue", inline=False)
    embed.add_field(name="/clear", value="Clear the song queue without stopping the current song", inline=False)
    embed.add_field(name="/leave", value="Stops music, clears queue, and disconnects", inline=False)
    embed.add_field(name="/remove", value="Remove a specific song from the queue by its position (Coming soon)", inline=False)
    embed.add_field(name="/loop", value="Loop the current song (Coming soon)", inline=False)

    await interaction.response.send_message(embed=embed)

async def play_next(voice_client, guild_id, channel):
    if SONG_QUEUE[guild_id]:
        audio_url, title = SONG_QUEUE[guild_id].popleft()
        CURRENT_SONG[guild_id] = title  # Track the currently playing song
        
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -c:a libopus -b:a 96k',
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options, executable='bin\\ffmpeg\\ffmpeg.exe')    

        def after_playing(error):
            if error:
                print(f"Error playing {title}: {error}")
            CURRENT_SONG.pop(guild_id, None)  # Clear the current song when done
            asyncio.run_coroutine_threadsafe(play_next(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_playing)
        asyncio.create_task(channel.send(f':musical_note: Now playing: **{title}**'))

    else:
        CURRENT_SONG.pop(guild_id, None)  # Clear the current song when queue is empty    
        SONG_QUEUE[guild_id] = deque()

        # Wait 5 minutes, then disconnect if still idle
        await asyncio.sleep(300)

        # Check if something started playing again during the wait
        if voice_client.is_connected() and not voice_client.is_playing() and not voice_client.is_paused():
            await channel.send("Disconnecting due to inactivity.")
            await voice_client.disconnect()

bot.run(TOKEN)