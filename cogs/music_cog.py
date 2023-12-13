import nextcord
from nextcord.ext.commands import Cog
from nextcord import slash_command, Interaction, Embed

guild_ids = [
    356482115161948171, 875478001687609375,
    517442949064425472, 722785171580912168, 673824125965565962,
    737744084348960849, 714199096730320956
]


class MusicCog(Cog):
    def __init__(self, client, botMain):
        self.botMain = botMain
        self.client = client

    @slash_command(name="test", description="test", guild_ids=guild_ids)
    async def metroSlash(self, inter: Interaction):
        await inter.send("aa")


def setup(client, botMain):
    client.add_cog(MusicCog(client, botMain))
