import nextcord
import os
from nextcord.ext import commands
import json
import logging

def getJson(path):
    if os.path.exists(path):
        with open(path, "r+", encoding='utf8') as f:
            return json.load(f)
    else:
        return {}


class BotMain:
    def __init__(self):
        beta = True
        prefixes = ['b!', 'B!'] if beta else ['v!', 'V!']
        token_key = "viktor-beta" if beta else "viktor"
        self.path = os.path.dirname(os.path.abspath(__file__))

        intents = nextcord.Intents.all()
        self.description = "Testing out the waters"
        self.client = commands.Bot(command_prefix=prefixes, intents=intents)
        self.client.remove_command("help")
        self.client.event(self.on_ready)
        self.__addCogs()

        token = getJson(self.path+"/cred/dicord_tokens.json").get(token_key, None)
        self.client.run(token)

        logger = logging.getLogger('nextcord')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(filename='nextcord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

    def __addCogs(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        cogs_path = "./cogs"
        for filename in os.listdir(dir_path + "/ "[:-1] + cogs_path):
            if filename.endswith(".py"):
                self.client.load_extension(f"cogs.{filename[:-3]}", extras={"botMain": self})

    # EVENTS
    async def on_ready(self):
        # description = "The Spauzu System has just been released :D"
        await self.client.change_presence(
            status=nextcord.Status.online,
            activity=nextcord.Game(name=self.description, type=3)
        )
        print('The BOTty is reacting!')


botmain = BotMain()
