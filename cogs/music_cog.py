from typing import Tuple

import nextcord
from nextcord.ext.commands import Cog
from nextcord import Interaction, Embed, VoiceChannel, VoiceClient, Guild, TextChannel, FFmpegPCMAudio, User, Color
from lib.command_decorators import slash_command
from lib.functions import formatDuration, isUrlValid
from queue import Queue
from enum import Enum
from yt_dlp import YoutubeDL
from abc import ABC as ABSTRACT, abstractmethod
import re
import threading
from typing import Optional, Union


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
    Disabled = 0,
    Song = 1,
    Queue = 2


class MediaType(Enum):
    Song = 0,
    Video = 1,
    Playlist = 2,
    Album = 3


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

    # TODO handle exceptions
    def getInfo(self, link):
        with YoutubeDL(self.guildContext.YDL_OPTIONS_FOR_AUDIO) as ydl:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise InvalidLinkException()
            return info

    def getSource(self):
        info = getInfo(self, self.getLink())
        audioSource = info.get("url", "Unknown")
        if audioSource == "Unknown":
            raise InvalidLinkException()
        return audioSource

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

    def getSource(self):
        info = self.getInfo(self.getLink())
        audioSource = info.get("url", "Unknown")
        self.thumbnailUrl = info["thumbnails"][-1]["url"]
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


test = False
if test:
    __links = [
        "https://www.youtube.com/watch?v=8OkpRK2_gVs&list=PLeqaNXpdZ1sV2WkdT5vGflfJFCAK4NFtg&index=3&t=1s"
    ]
    for __link in __links:
        print(YoutubeAudioNode.isYoutubeLink(__link), YoutubeAudioNode.parseYoutubeURL(__link), __link)
if test:
    __links = [
        "https://www.youtube.com/playlist?list=PLeqaNXpdZ1sV2WkdT5vGflfJFCAK4NFtg"
    ]
    for __link in __links:
        print(re.findall(r"^.*?(?:v|list)=(.*?)(?:&|$)", __link))
        print(YoutubeAudioNode.parseYoutubeURL(__link))

'''
with open("cogs/ActiveYouTubeURLFormats.txt", "r+") as f:
    lines = [i for i in "".join(f.readlines()).split("\n") if i != ""]
    # lines += ["youtube.com.pt", "youtube.pt", "youtube.co.pt", "https://www.youtube.pt"]
    lines = [YoutubeAudioNode.parseYoutubeURL(i) for i in lines]
    # lines = [re.findall(r'(?:https?://)?(?:[-\w.]|(?:%[\da-fA-F]{2}))+', i)[0] for i in lines]
    lines = sorted(set(lines))
    for line in lines:
        print(line)

with open("cogs/countryVariants.txt") as f:
    lines = [i for i in "".join(f.readlines()).split("\n") if i != ""]
    l1 = []
    l2 = []
    l3 = []
    for line in lines:
        line = line.split(".")
        assert line[0] == "youtube"
        if len(line) == 2:
            l1.append(line[1])
        elif line[1] == "com":
            l2.append(line[2])
        elif line[1] == "co":
            l3.append(line[2])
        else:
            assert False
    d = {
        k: ("1" if k in l1 else "") + ("2" if k in l2 else "") + ("3" if k in l3 else "")
        for k in sorted(set(l1+l2+l3))
    }
    d2 = {
        dv: [k for k, v in d.items() if v == dv]
        for dv in d.values()
    }
    for k, v in d.items():
        print(k, v)

    for k, v in d2.items():
        print(k, v)
    print(lines)
'''


class SongAddedData:
    def __init__(self, song: Union[AudioNode, list[AudioNode]], image=None):
        self.songs: list[AudioNode] = song if type(song) == list else [song]
        self.image = image

    def getEmbed(self):
        embed = Embed(
            description="\n".join([
                f"\\[[{formatDuration(song.getDuration())}]({song.getLink()})\\] ``{song.getTitle():.50}`` "
                for song in self.songs
            ]),  # TODO maybe fix the getTitle max with "..."
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

    # TODO handle exceptions
    def getInfo(self, link):
        with YoutubeDL(self.guildContext.YDL_OPTIONS_FOR_AUDIO) as ydl:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise InvalidLinkException()
            return info

    def interpretRequest(self, link, requester):
        # TODO check for valid link
        cleanLink = re.findall(r'(?:https?://)?(?:[-\w.]|(?:%[\da-fA-F]{2}))+', link)[0]
        if not isUrlValid(link):  # if text -> yt
            info = YoutubeAudioNode.searchYTFirstResult(link, self.guildContext.YDL_OPTIONS_FOR_AUDIO)
            self.guildContext.queue.put(node := YoutubeAudioNode(
                info["original_url"], requester, self.guildContext,
                duration=info["duration"], title=info["title"], uploader=info["uploader"],
                thumbnailUrl=info["thumbnails"][-1]["url"]
            ))
            return SongAddedData(node)
        elif YoutubeAudioNode.isYoutubeLink(cleanLink):
            mediaType, link = YoutubeAudioNode.parseYoutubeURL(link)
            match mediaType:
                case MediaType.Video:
                    # TODO validate video
                    info = self.getInfo(link)
                    self.guildContext.queue.put(node := YoutubeAudioNode(
                        link, requester, self.guildContext,
                        duration=info["duration"], title=info["title"], uploader=info["uploader"],
                        thumbnailUrl=info["thumbnails"][-1]["url"]
                    ))
                    return SongAddedData(node)

                case MediaType.Playlist:
                    info = YoutubeAudioNode.getInfoPlaylist(link, self.guildContext.cogMain.YDL_OPTIONS_PLAYLIST)

                    # TODO validate videos
                    songsAdded = []
                    for entry in info["entries"]:
                        self.guildContext.queue.put(node := YoutubeAudioNode(
                            entry["url"], requester, self.guildContext,
                            duration=entry["duration"], title=entry["title"], uploader=entry["uploader"],
                            thumbnailUrl=entry["thumbnails"][-1]["url"]
                        ))
                        songsAdded.append(node)
                    return SongAddedData(songsAdded)

        else:  # provider not available
            raise InvalidLinkException()


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
            self.commandQueue.get()()
            self.commandLoopLock.acquire()
        self.inLoop = False
        self.commandLoopLock.release()

    def skip(self):
        self.commandQueue.put(self.__skip)
        self.wakeUpCommandLoop()

    def __skip(self):
        self.guildContextloggerBit = False
        with self.guildContext.lock:
            self.guildContext.getVoiceClient().stop()

    def stop(self):
        self.commandQueue.put(self.__stop)
        self.wakeUpCommandLoop()

    def __stop(self):
        with self.guildContext.lock:
            with self.guildContext.queue.mutex:
                self.guildContext.queue.queue.clear()
            self.guildContext.getVoiceClient().stop()

    def pause(self):
        self.commandQueue.put(self.__stop)
        self.wakeUpCommandLoop()

    def __pause(self):
        with self.guildContext.lock:
            vClient = self.guildContext.getVoiceClient()
            if vClient.is_paused():
                vClient.resume()
            else:
                vClient.pause()


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

        self.YDL_OPTIONS_FOR_AUDIO = cogMain.YDL_OPTIONS_FOR_AUDIO
        self.ffmpegExePath = cogMain.ffmpegExePath
        self.FFMPEG_OPTIONS = cogMain.FFMPEG_OPTIONS

        # TODO add logger

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
                self.getVoiceClient().play(ffmpegAudioSource, after=lambda e: self.playNext())

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
        '''
        sourceEmoji = "🎶"
        desc = f"``{self.nodeBeingPlayed.title}``**``\nBy: {sourceEmoji}{self.nodeBeingPlayed.author}" \
               f"\n```Duration Bar```\n" \
               f"Added By: {self.nodeBeingPlayed.getNameOfAddedBy()}"
        desc = f"{sourceEmoji}``{self.nodeBeingPlayed.title}``"
        desc += f"\n▶ Playing from [{self.nodeBeingPlayed.type.value}]({self.nodeBeingPlayed.link})"

        embed = Embed(
            description=desc,
            colour=Color.blue()
        )
        embed.set_author(name="NOW PLAYING", icon_url=self.nodeBeingPlayed.getImageAddedBy())
        embed.add_field(name="Added By", value=self.nodeBeingPlayed.getPingAddedBy(), inline=True)
        embed.add_field(name="Song By", value=self.nodeBeingPlayed.author, inline=True)
        embed.add_field(name="Duration", value=formatDuration(self.nodeBeingPlayed.duration), inline=True)
        self.lastNowPlayingMessage = await self.currentTextChannel.send(embed=embed)
        '''
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

    def skip(self):
        self.commandHandler.skip()

    def stop(self):
        self.commandHandler.stop()


class MusicCog(Cog):
    def __init__(self, client, botMain):
        self.client = client
        self.botMain = botMain
        self.guildContexts = {}
        self.YDL_OPTIONS_FOR_AUDIO = {
            'format': 'bestaudio/bestaudio*',
            'noplaylist': True,
            'quiet': True,
            'ignoreerrors': True,
            'age_limit': 69
        }
        self.YDL_OPTIONS_PLAYLIST = {
            "extract_flat": "in_playlist",
            'quiet': True,
            'ignoreerrors': True,
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

    @slash_command("test3")
    async def forcePlay(self, inter: Interaction):
        link: str = "https://youtu.be/YTQV48V44Sw?si=__Pql104Xd-6aKKd"
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        with YoutubeDL(self.YDL_OPTIONS_FOR_AUDIO) as ydl:
            info = ydl.extract_info(link, download=False)
            if info is None:
                raise InvalidLinkException()
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
    async def skip(self, inter: Interaction):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        guildContext.skip()
        await inter.send("skipped")

    @slash_command("stop")
    async def stop(self, inter: Interaction):
        await self.guarantee(inter)
        guildContext: GuildVoiceContext = self.getGuildContext(inter.guild)
        guildContext.stop()
        await inter.send("stopped")


def setup(client, botMain):
    client.add_cog(MusicCog(client, botMain))
