import os
import json
from django.core.validators import URLValidator, ValidationError


def getJson(path):
    if os.path.exists(path):
        with open(path, "r+", encoding='utf8') as f:
            return json.load(f)
    else:
        return {}


def formatDuration(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    if minutes >= 60:
        return f"{minutes // 60}:{minutes % 60 : 02}:{seconds:02}"
    else:
        return f"{minutes}:{seconds:02}"


validator = URLValidator()


def isUrlValid(url: str) -> bool:
    try:
        validator(url)
        return True
    except ValidationError:
        return False
