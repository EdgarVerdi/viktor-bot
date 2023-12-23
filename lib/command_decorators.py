from typing import Callable
from nextcord import slash_command as nextcord_slash_command, SlashApplicationCommand
from lib.functions import getJson

commandsInfo = getJson("./commands.json")
config = getJson("./config.json")


class UnknownCommandError(Exception):
    def __init__(self, command_id):
        super().__init__(f"There is no command with the id \"{command_id}\" in commands.json")


def slash_command(command_id):
    commandInfo = commandsInfo.get(command_id, {})
    if commandInfo == {}:
        raise UnknownCommandError(command_id)

    def decorator(func: Callable) -> SlashApplicationCommand:
        return nextcord_slash_command(
            name=commandInfo["name"],
            description=commandInfo["description"],
            guild_ids=config["default_guild_ids"]
        )(func)

    return decorator
