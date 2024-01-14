import queue
from typing import Tuple

import nextcord
from nextcord.ext.commands import Cog
from nextcord import Interaction, Embed, VoiceChannel, VoiceClient, Guild, TextChannel, FFmpegPCMAudio, User, Color, \
    SlashOption
from lib.command_decorators import slash_command
from lib.functions import formatDuration, isUrlValid, getJson
from queue import Queue
from enum import Enum
from yt_dlp import YoutubeDL
from abc import ABC as ABSTRACT, abstractmethod
import re
import threading
from typing import Optional, Union
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class UserNotInVoiceChannel(Exception):
    pass


class WrongVoiceChannel(Exception):
    pass


class InvalidLinkException(Exception):
    pass


class NoSearchResultsException(Exception):
    pass


class UnavailableSourceException(Exception):
    pass


class LoopMode(Enum):
    Disabled = 0
    Song = 1
    Queue = 2


class MediaType(Enum):
    Song = 0
    Video = 1
    Playlist = 2
    Album = 3
    Artist = 4
    Episode = 5


class AudioNode(ABSTRACT):
    def __init__(self, link: str, requester: User, guildContext: "GuildVoiceContext", duration: int, title: str):
        self.link: str = link
        self.requester: User = requester
        self.guildContext: "GuildVoiceContext" = guildContext
        self.duration: int = duration  # in seconds
        self.title: str = title

    def getDuration(self):
        return self.duration

    def getTitle(self):
        return self.title

    def getLink(self):
        return self.link

    def getImageUrl(self) -> Optional[str]:
        return None

    @abstractmethod
    def getSource(self):
        raise InvalidLinkException

    @abstractmethod
    def makeEmbed(self) -> Embed:
        pass


class YoutubeAudioNode(AudioNode):
    def __init__(self, link: str, requester: User, guildContext: "GuildVoiceContext",
                 duration: int, title: str, uploader: str, thumbnailUrl: str):
        super().__init__(link, requester, guildContext, duration, title)
        self.uploader: str = uploader
        self.thumbnailUrl = thumbnailUrl

    def getImageUrl(self) -> Optional[str]:
        return self.thumbnailUrl

    # TODO handle exceptions
    @staticmethod
    def getInfo(link, YDL_OPTIONS):
        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise InvalidLinkException()
            return info

    def getSource(self):
        info = self.getInfo(self.getLink(), self.guildContext.YDL_OPTIONS_FOR_AUDIO)
        audioSource = info.get("url", "Unknown")
        try:
            self.thumbnailUrl = info["thumbnails"][-1]["url"]
        except KeyError:
            self.thumbnailUrl = None
        if audioSource == "Unknown":
            raise InvalidLinkException()
        return audioSource

    def makeEmbed(self) -> Embed:
        sourceEmoji = "🎶"
        desc = f"{sourceEmoji} ``{self.getTitle()}``"
        desc += f"\n▶ Playing from [YouTube]({self.getLink()})"
        embed = Embed(
            description=desc,
            colour=Color.blue()
        )
        embed.set_thumbnail(self.thumbnailUrl)
        embed.set_author(name="NOW PLAYING")  # , icon_url=self.nodeBeingPlayed.getImageAddedBy())
        embed.add_field(name="Added By", value=f"<@{self.requester.id}>", inline=True)
        embed.add_field(name="Duration", value=formatDuration(self.duration), inline=True)
        embed.add_field(name="Song By", value=self.uploader, inline=True)
        return embed

    # TODO handle exceptions
    @staticmethod
    def getInfoPlaylist(link, YDL_OPTIONS):
        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise InvalidLinkException()
            return info

    @staticmethod
    def isYoutubeLink(link):
        link = re.findall(r'(?:https?://)?(?:[-\w.]|(?:%[\da-fA-F]{2}))+', link)[0]  # simplify link
        return any(option in link for option in ["youtube", "youtu.be"])

    @staticmethod
    def parseYoutubeURL(url: str) -> tuple[MediaType, str]:
        # validated from https://gist.githubusercontent.com/rodrigoborgesdeoliveira/987683cfbfcc8d800192da1e73adc486
        if "attribution" in url:
            url = url.replace("attribution", "attr")
            url = url.replace("watch%3Fv%3D", "watch?v=")
        if "oembed" in url:
            url = url.replace("watch?v%3D", "watch?v=")

        data = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if data:
            return MediaType.Video, f"https://youtu.be/{data[0]}"

        data = re.findall(r"^.*?(?:v|list)=(.*?)(?:&|$)", url)
        if data:
            return MediaType.Playlist, f"https://youtube.com/playlist?list={data[0]}"

        raise InvalidLinkException()

    @staticmethod
    def searchYTFirstResult(query, YDL_OPTIONS):
        try:
            with YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info("ytsearch:%s" % query, download=False)
                return info['entries'][0]
        except IndexError:
            raise NoSearchResultsException


class SpotifyAudioNode(AudioNode):

    def __init__(self, spotifyId: str, requester: User, guildContext: "GuildVoiceContext",
                 duration: int, title: str, uploader: str, thumbnailUrl, albumName: str):
        super().__init__(f"https://open.spotify.com/track/{spotifyId}", requester, guildContext, duration, title)
        self.uploader: str = uploader
        self.thumbnailUrl = thumbnailUrl
        self.albumName = albumName
        self.spotifyId = spotifyId

    def getImageUrl(self) -> Optional[str]:
        return self.thumbnailUrl

    def makeEmbed(self) -> Embed:
        sourceEmoji = "🎶"
        desc = f"{sourceEmoji} ``{self.getTitle()}``"
        desc += f"\n▶ Playing from [Spotify]({self.getLink()})"
        embed = Embed(
            description=desc,
            colour=Color.blue()
        )
        embed.set_thumbnail(self.thumbnailUrl)
        embed.set_author(name="NOW PLAYING")  # , icon_url=self.nodeBeingPlayed.getImageAddedBy())
        embed.add_field(name="Added By", value=f"<@{self.requester.id}>", inline=True)
        embed.add_field(name="Duration", value=formatDuration(self.duration), inline=True)
        embed.add_field(name="Song By", value=self.uploader, inline=True)
        return embed

    def getYoutubeInfo(self):
        q = "{}, {}, {}".format(
            self.title,
            self.uploader,
            self.albumName
        )
        return YoutubeAudioNode.searchYTFirstResult(q, self.guildContext.YDL_OPTIONS_FOR_AUDIO)

    def getSource(self):
        info = self.getYoutubeInfo()
        audioSource = info.get("url", "Unknown")
        if audioSource == "Unknown":
            raise InvalidLinkException()
        return audioSource

    @staticmethod
    def isSpotifyLink(link):
        # return bool(re.findall(r"^(?:https?://)?open.spotify.com/(?:album|track|playlist)/(?:\d|[a-z]|[A-Z]){22}",
        # link))
        return bool(re.findall(r"^(?:https?://)?open.spotify.com", link))

    @staticmethod
    def parseSpotifyURL(url: str) -> tuple[MediaType, str] | tuple[None, None]:
        results = re.findall(
            r"^(?:https?://)?open.spotify.com/(album|track|playlist|artist)/((?:\d|[a-z]|[A-Z]){22})"
            , url)
        if len(results) <= 0 or len(results[0]) < 2 or len(results[0][1]) != 22:
            return None, None
        match results[0][0]:
            case "album":
                return MediaType.Album, results[0][1]
            case "playlist":
                return MediaType.Playlist, results[0][1]
            case "track":
                return MediaType.Song, results[0][1]
            case "artist":
                return MediaType.Artist, results[0][1]
            case _:
                return None, None


test = False
if test:
    uLink = "https://open.spotify.com/playlist/7hGG8g2WqzRN0fcc1fg2T9"
    print(SpotifyAudioNode.isSpotifyLink(uLink))
    print(SpotifyAudioNode.parseSpotifyURL(uLink))


class SongAddedData:
    def __init__(self, song: Union[AudioNode, list[AudioNode]], image=None):
        self.songs: list[AudioNode] = song if type(song) == list else [song]
        self.image = image

    def getEmbed(self):

        desc = "\n".join([
            f"\\[[{formatDuration(song.getDuration())}]({song.getLink()})\\] ``{song.getTitle():.50}`` "
            for song in self.songs[:15]])
        if (remSongs := len(self.songs[15:])) > 0:
            desc += f"\n...and other {remSongs} songs."
        embed = Embed(
            description=desc,
            colour=Color.blue()
        )
        embed.set_author(name="Added to Queue")

        image = self.image or next(
            (item for item in map(lambda song: song.getImageUrl(), self.songs)
             if item is not None), None
        )
        if image is not None:
            embed.set_thumbnail(image)
        return embed


class NodePseudoFactory:
    def __init__(self, guildContext):
        self.guildContext: "GuildVoiceContext" = guildContext

    def interpretRequest(self, link, requester):
        # DONE check for valid link
        cleanLink = re.findall(r'(?:https?://)?(?:[-\w.]|(?:%[\da-fA-F]{2}))+', link)[0]
        if YoutubeAudioNode.isYoutubeLink(cleanLink):
            mediaType, link = YoutubeAudioNode.parseYoutubeURL(link)
            match mediaType:
                case MediaType.Video:
                    # DONE validate video: getInfo returns InvalidLinkException!
                    info = YoutubeAudioNode.getInfo(link, self.guildContext.YDL_OPTIONS_FOR_AUDIO)
                    self.guildContext.queue.put(node := YoutubeAudioNode(
                        link, requester, self.guildContext,
                        duration=info["duration"], title=info["title"], uploader=info["uploader"],
                        thumbnailUrl=info["thumbnails"][-1]["url"]
                    ))
                    return SongAddedData(node)

                case MediaType.Playlist:
                    info = YoutubeAudioNode.getInfoPlaylist(link, self.guildContext.YDL_OPTIONS_PLAYLIST)

                    # DONE validate videos: if duration is None then the video wouldn't play!
                    songsAdded = []
                    for entry in info["entries"]:
                        if entry.get("duration", None) is None:
                            # TODO tell skipped videos
                            continue
                        self.guildContext.queue.put(node := YoutubeAudioNode(
                            entry["url"], requester, self.guildContext,
                            duration=entry["duration"], title=entry["title"], uploader=entry["uploader"],
                            thumbnailUrl=entry["thumbnails"][-1]["url"]
                        ))
                        songsAdded.append(node)
                    return SongAddedData(songsAdded)
        elif SpotifyAudioNode.isSpotifyLink(cleanLink):
            mediaType, spotify_id = SpotifyAudioNode.parseSpotifyURL(link)
            if mediaType is None or spotify_id is None:
                InvalidLinkException()
            if mediaType == MediaType.Song:
                track = self.guildContext.cogMain.spotifyClient.track(track_id=spotify_id)
                self.guildContext.queue.put(node := SpotifyAudioNode(
                    f"open.spotify.com/track/{track['id']}", requester, self.guildContext,
                    duration=round(track["duration_ms"] / 1000), title=track["name"],
                    uploader=track["artists"][0]["name"],
                    thumbnailUrl=track["album"]["images"][0]["url"], albumName=track['album']['name']
                ))
                return SongAddedData(node)
            elif mediaType == MediaType.Album:
                album_tracks_response = self.guildContext.cogMain.spotifyClient.album_tracks(album_id=spotify_id)
                album_response = self.guildContext.cogMain.spotifyClient.album(album_id=spotify_id)
                image = album_response["images"][0]["url"]
                album_items = album_tracks_response['items']
                addedNodes = []
                for item in album_items:
                    track = item
                    self.guildContext.queue.put(node := SpotifyAudioNode(
                        f"open.spotify.com/track/{track['id']}", requester, self.guildContext,
                        duration=round(track["duration_ms"] / 1000), title=track["name"],
                        uploader=track["artists"][0]["name"],
                        thumbnailUrl=image, albumName=album_response['name']
                    ))
                    addedNodes.append(node)
                return SongAddedData(addedNodes, image)
            elif mediaType == MediaType.Playlist:
                playlist_response = self.guildContext.cogMain.spotifyClient.playlist(playlist_id=spotify_id)
                image = playlist_response["images"][0]["url"]
                playlist_items = playlist_response['tracks']['items']
                addedNodes = []
                for item in playlist_items:
                    track = item.get("track", None)
                    if track is None:
                        continue
                    self.guildContext.queue.put(node := SpotifyAudioNode(
                        f"open.spotify.com/track/{track['id']}", requester, self.guildContext,
                        duration=round(track["duration_ms"] / 1000), title=track["name"],
                        uploader=track["artists"][0]["name"],
                        thumbnailUrl=track["album"]["images"][0]["url"], albumName=track['album']['name']
                    ))
                    addedNodes.append(node)
                return SongAddedData(addedNodes, image=image)
            elif mediaType == MediaType.Artist:
                artist_response = self.guildContext.cogMain.spotifyClient.artist_top_tracks(artist_id=spotify_id)
                artist = self.guildContext.cogMain.spotifyClient.artist(artist_id=spotify_id)
                addedNodes = []
                for track in artist_response['tracks']:
                    self.guildContext.queue.put(node := SpotifyAudioNode(
                        f"open.spotify.com/track/{track['id']}", requester, self.guildContext,
                        duration=round(track["duration_ms"] / 1000), title=track["name"],
                        uploader=track["artists"][0]["name"],
                        thumbnailUrl=track["album"]["images"][0]["url"], albumName=track['album']['name']
                    ))
                    addedNodes.append(node)
                return SongAddedData(addedNodes, image=artist["images"][0]["url"])
        elif not isUrlValid(link):  # if text -> yt
            info = YoutubeAudioNode.searchYTFirstResult(link, self.guildContext.YDL_OPTIONS_FOR_AUDIO)
            self.guildContext.queue.put(node := YoutubeAudioNode(
                info["original_url"], requester, self.guildContext,
                duration=info["duration"], title=info["title"], uploader=info["uploader"],
                thumbnailUrl=info["thumbnails"][-1]["url"]
            ))
            return SongAddedData(node)
        raise InvalidLinkException()  # provider not available


class LoggerOutputs:
    def __init__(self):
        pass

    def error(self, msg):
        pass
        # print("Captured Error: " + msg)

    def warning(self, msg):
        pass
        # print("Captured Warning: " + msg)

    def debug(self, msg):
        pass
        # print("Captured Log: " + msg)


class EmptyLoggerOutputs:
    def __init__(self):
        self.error = self.nothing
        self.warning = self.nothing
        self.debug = self.nothing

    def nothing(self, msg):
        pass


class CommandQueueHandler:
    def __init__(self, guildContext):
        self.commandQueue = Queue()
        self.guildContext: "GuildVoiceContext" = guildContext

        self.inLoop = False
        self.commandLoopLock = threading.Lock()
        # TODO make play also part of the command handler

    def wakeUpCommandLoop(self):
        self.commandLoopLock.acquire()
        if not self.inLoop:
            threading.Thread(target=self.commandLoop).start()
        self.commandLoopLock.release()

    def commandLoop(self):
        self.commandLoopLock.acquire()
        self.inLoop = True
        while not self.commandQueue.empty():
            self.commandLoopLock.release()
            func, args, kwargs = self.commandQueue.get()
            func(*args, **kwargs)
            self.commandLoopLock.acquire()
        self.inLoop = False
        self.commandLoopLock.release()

    def skip(self, count=1):
        self.commandQueue.put((self.__skip, [], {"count": count}))
        self.wakeUpCommandLoop()

    def __skip(self, count=1):
        with self.guildContext.lock:
            if count > 1:
                for _ in range(0, count - 1):
                    self.guildContext.queue.get()
            if count >= 1:
                self.guildContext.getVoiceClient().stop()

    def stop(self):
        self.commandQueue.put((self.__stop, [], {}))
        self.wakeUpCommandLoop()

    def __stop(self):
        with self.guildContext.lock:
            with self.guildContext.queue.mutex:
                self.guildContext.queue.queue.clear()
            self.guildContext.getVoiceClient().stop()

    def pause(self):
        self.commandQueue.put((self.__pause, [], {}))
        self.wakeUpCommandLoop()

    def __pause(self):
        with self.guildContext.lock:
            vClient = self.guildContext.getVoiceClient()
            if vClient.is_paused():
                vClient.resume()
            else:
                vClient.pause()

    def setLoopMode(self, loopMode: LoopMode):
        self.commandQueue.put((self.__setLoopMode, [], {"loopMode": loopMode}))
        self.wakeUpCommandLoop()

    def __setLoopMode(self, loopMode: LoopMode):
        self.guildContext.loopMode = loopMode


class GuildVoiceContext:
    def __init__(self, guild, cogMain: "MusicCog"):
        self.guild: Guild = guild
        self.cogMain: "MusicCog" = cogMain
        self.replyChannel: Optional[TextChannel] = None
        self.queue = Queue()
        self.nodePlaying: Optional[AudioNode] = None
        self.loopMode: LoopMode = LoopMode.Disabled
        self.lastNowPlayingMessage = None

        self.nodePseudoFactory = NodePseudoFactory(self)
        self.commandHandler = CommandQueueHandler(self)
        self.lock = threading.Lock()

        # TODO add autodisconnect after some other time of inactivity
        # TODO add *functional* logger
        # TODO fix sequential /play (probably result of put play in commandQueue)
        self.logger = EmptyLoggerOutputs()  # DONE add logger
        self.logger = LoggerOutputs()
        self.YDL_OPTIONS_FOR_AUDIO = cogMain.YDL_OPTIONS_FOR_AUDIO.copy()
        self.YDL_OPTIONS_FOR_AUDIO['logger'] = self.logger
        self.YDL_OPTIONS_PLAYLIST = cogMain.YDL_OPTIONS_PLAYLIST.copy()
        self.YDL_OPTIONS_PLAYLIST['logger'] = self.logger
        self.ffmpegExePath = cogMain.ffmpegExePath
        self.FFMPEG_OPTIONS = cogMain.FFMPEG_OPTIONS

    def calculateQueueDuration(self):  # in seconds
        return sum([node.getDuration() for node in self.queue.queue])

    def hasNextNode(self):
        return (
                not self.queue.empty()
                or
                self.loopMode in [LoopMode.Queue, LoopMode.Song] and self.nodePlaying is not None
        )

    async def playNext(self):
        with self.lock:
            while self.hasNextNode():  # interpret as an if that can be repeated
                if self.loopMode == LoopMode.Queue:
                    self.queue.put(self.nodePlaying)
                    self.nodePlaying: AudioNode = self.queue.get()
                elif self.loopMode == LoopMode.Disabled:
                    self.nodePlaying: AudioNode = self.queue.get()

                # play audio and recursively call this function
                # get source
                try:
                    audioSource = self.nodePlaying.getSource()
                except InvalidLinkException:
                    # TODO notify song was skipped
                    continue

                ffmpegAudioSource: AudioSource = FFmpegPCMAudio(
                    executable=self.ffmpegExePath, source=audioSource, **self.FFMPEG_OPTIONS
                )
                self.getVoiceClient().play(
                    ffmpegAudioSource, after=lambda e: self.playNext(),

                )

                await self.deletePreviousNowPlayingMessage()
                await self.sendNowPlayingMessage()
                return

            # if condition fails
            await self.deletePreviousNowPlayingMessage()
            self.nodePlaying = None

    async def deletePreviousNowPlayingMessage(self):
        if self.lastNowPlayingMessage is not None:
            await self.lastNowPlayingMessage.delete()
            self.lastNowPlayingMessage = None

    async def sendNowPlayingMessage(self):
        self.nodePlaying: AudioNode
        self.lastNowPlayingMessage = await self.replyChannel.send(embed=self.nodePlaying.makeEmbed())

    def getVoiceClient(self) -> VoiceClient:
        return self.guild.voice_client

    def addToQueue(self, requestInput, requester) -> SongAddedData:  # will return info about what was added
        return self.nodePseudoFactory.interpretRequest(requestInput, requester)

    async def wakeUp(self):
        vCl = self.getVoiceClient()

        if not vCl.is_playing() and not vCl.is_paused():
            await self.playNext()

    def isPaused(self):
        return self.getVoiceClient().is_paused()

    def pause(self):
        self.commandHandler.pause()

    def skip(self, jumpTo):
        self.commandHandler.skip(jumpTo)

    def stop(self):
        self.commandHandler.stop()

    def setLoopMode(self, loopMode: LoopMode):
        self.commandHandler.setLoopMode(loopMode)

    def getQueue(self, n: int) -> (list[dict], int):
        if n < 0:
            n = 0
        if n * 15 > len(self.queue.queue):
            n = len(self.queue.queue) // 15
        return [{
            "duration": node.getDuration(),
            "url": node.getLink(),
            "title": node.getTitle()
        } for node in list(self.queue.queue)[n * 15: (n + 1) * 15]], n


class ComponentsView(nextcord.ui.View):

    def __init__(self, components):
        super().__init__()
        for comp in components:
            self.add_item(comp)


class QueueButton(nextcord.ui.Button):
    def __init__(self, guildContext: GuildVoiceContext, page: int, isRight: bool, **kwargs):
        super().__init__(emoji="➡" if isRight else "⬅", **kwargs)
        self.guildContext = guildContext
        self.page = page

    async def callback(self, interaction: nextcord.Interaction):
        songList, page = self.guildContext.getQueue(self.page)
        embed, view = MusicCog.makeQueueEmbed(songList, page, self.guildContext)
        await interaction.message.edit(embed=embed, view=view)


class MusicCog(Cog):

    def __init__(self, client, botMain):
        self.client = client
        self.botMain = botMain
        self.guildContexts = {}
        cred = getJson(path=botMain.path + "/cred/spotify_dev.json")
        self.spotifyClient = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=cred["client_id"], client_secret=cred["client_secret"]
            ))
        self.YDL_OPTIONS_FOR_AUDIO = {
            'format': 'bestaudio/bestaudio*',
            'noplaylist': True,
            'quiet': True,
            'ignore_errors': True,
            'age_limit': 69
        }
        self.YDL_OPTIONS_PLAYLIST = {
            "extract_flat": "in_playlist",
            'quiet': True,
            'ignore_errors': True,
            'skip_download': True,
            'age_limit': 69,
            'hls-prefer-ffmpeg': True,
            'reject_title': '[Deleted video]'
        }
        self.ffmpegExePath = "C:/ffmpeg/ffmpeg.exe"
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

    @staticmethod
    async def getSendingRequestMessage(inter):
        return await inter.send(embed=Embed(
            description="Sending Request",
            colour=Color.blue()
        ))

    def getGuildContext(self, guild: Guild):
        gc = self.guildContexts.get(guild.id, {})
        if gc == {}:
            gc = GuildVoiceContext(guild, self)
            self.guildContexts[guild.id] = gc
        return gc

    @staticmethod
    async def guarantee(inter: Interaction) -> VoiceChannel:
        vc = MusicCog.getUserVc(inter)
        if inter.guild.voice_client is None or not inter.guild.voice_client.is_connected():
            await vc.connect()
        elif inter.guild.voice_client.channel != vc:
            raise WrongVoiceChannel

    @staticmethod
    def getUserVc(inter: Interaction) -> VoiceChannel:
        for vc in inter.guild.voice_channels:
            if inter.user in vc.members:
                return vc
        raise UserNotInVoiceChannel

    @slash_command("test")
    async def joinCall(self, inter: Interaction):
        vc = self.getUserVc(inter)
        voiceClient = await vc.connect()
        await inter.send("aa")

    @slash_command("test4")
    async def moveHere(self, inter: Interaction):
        vc = self.getUserVc(inter)
        if inter.guild.voice_client is not None and inter.guild.voice_client.is_connected():
            if inter.guild.voice_client.channel == vc:
                await inter.send("nothing to do")
                return
            await inter.guild.voice_client.disconnect(force=True)
        voiceClient = await vc.connect()
        await inter.send("aa")

    @slash_command("play")
    async def play(self, inter: Interaction, link: str):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        if guildContext.replyChannel is None:
            guildContext.replyChannel = inter.channel
        msg = await self.getSendingRequestMessage(inter)
        try:
            addedData = guildContext.addToQueue(link, inter.user)
            await guildContext.wakeUp()
            await msg.edit(embed=addedData.getEmbed())
        except InvalidLinkException:
            await msg.edit("Invalid Link Exception")
        except NoSearchResultsException:
            await msg.edit("No results were found for the given query.")

    @slash_command("test2")
    async def forcePlay2(self, inter: Interaction):
        link: str = "https://youtu.be/YTQV48V44Sw?si=__Pql104Xd-6aKKd"
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)

        # link: str = "https://open.spotify.com/track/5SGesS47gTWra708Z5LhVe?si=428c2591ce7b4a83"

        pl_id = '6ZkwfPHoQFEvxtuXf6dUnr'
        pl_id = '1lfVSnY49aGFPkiSXaWR6T'
        sp = self.spotifyClient
        playlist_response = sp.playlist(playlist_id=pl_id)
        name = playlist_response['name']
        playlist_items = playlist_response['tracks']['items']

        q = [
            "{} {} {}".format(
                item['track']['name'],
                item['track']['artists'][0]['name'],
                item['track']['album']['name']
            )
            for item in playlist_items
        ]

        info = YoutubeAudioNode.searchYTFirstResult(q[0], self.YDL_OPTIONS_FOR_AUDIO)
        audioSource = info.get("url", "Unknown")

        ffmpegAudioSource: AudioSource = FFmpegPCMAudio(
            executable=self.ffmpegExePath, source=audioSource, **self.FFMPEG_OPTIONS
        )
        guildContext.getVoiceClient().play(ffmpegAudioSource, after=lambda e: self.playNext())
        await inter.send("aa")

    @slash_command("pause")
    async def pause(self, inter: Interaction):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        guildContext.pause()
        await inter.send("paused" if guildContext.isPaused() else "resumed")

    @slash_command("skip")
    async def skip(self, inter: Interaction, jump_to: int = SlashOption(
        required=False, min_value=1, max_value=500, default=1,
        name="jump_to", description="the number of song the you wish to skip to"
    )):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        await inter.send("skipped")
        guildContext.skip(jump_to)

    @slash_command("stop")
    async def stop(self, inter: Interaction):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        await inter.send("stopped")
        guildContext.stop()

    @staticmethod
    def makeQueueEmbed(songList, page, guildContext):
        desc = "\n".join([f"**Page {page + 1}:**"] + [
            f"``[{1 + i + page * 15:02}]``\\[[{formatDuration(song['duration'])}]({song['url']})\\] ``{song['title']:.50}``"
            for i, song in enumerate(songList)
        ])
        embed = Embed(
            description=desc,
            colour=Color.blue()
        )
        embed.set_author(name="QUEUE")
        view = ComponentsView([
            QueueButton(guildContext, page - 1, False),
            QueueButton(guildContext, page + 1, True),

        ])
        return embed, view

    @slash_command("queue")
    async def queue(self, inter: Interaction, page: int = SlashOption(
        required=False, min_value=1, max_value=50, default=1,
        name="page", description="the page of 15 songs in the queue"
    )):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        msg = await self.getSendingRequestMessage(inter)
        # TODO don't allow if there are no songs
        songList, page = guildContext.getQueue(page - 1)
        embed, view = self.makeQueueEmbed(songList, page, guildContext)
        await msg.edit(embed=embed, view=view)

    @slash_command("loop")
    async def loop(self, inter: Interaction, loopMode: int = SlashOption(
        required=True, choices={
            "Song": 1,
            "Queue": 2,
            "Disabled": 0
        },
        name="loop_mode", description="The loop mode you want to change the bot to"
    )):
        await self.guarantee(inter)
        # TODO loop ain't working whatsever :skull:
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        await inter.send("loop mode changed")
        guildContext.setLoopMode(LoopMode(loopMode))

    @slash_command("test3")
    async def choose_a_number(
            self,
            interaction: nextcord.Interaction,
            number: int = SlashOption(
                name="picker",
                choices={
                    "one": 1,
                    "two": 2,
                    "three": 3},
            ),
    ):
        """Repeats your number that you choose from a list

        Parameters
        ----------
        interaction: Interaction
            The interaction object
        number: int
            The chosen number.
        """
        await interaction.response.send_message(f"You chose {number}!")


def setup(client, botMain):
    client.add_cog(MusicCog(client, botMain))
