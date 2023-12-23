import nextcord
from nextcord.ext.commands import Cog
from nextcord import Interaction, Embed
from lib.command_decorators import slash_command


class MusicCog(Cog):
    def __init__(self, client, botMain):
        self.client = client
        self.botMain = botMain

    @slash_command("test")
    async def metroSlash(self, inter: Interaction):
        await inter.send("aa")


def setup(client, botMain):
    client.add_cog(MusicCog(client, botMain))
