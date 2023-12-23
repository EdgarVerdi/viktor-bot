import os
import json


def getJson(path):
    if os.path.exists(path):
        with open(path, "r+", encoding='utf8') as f:
            return json.load(f)
    else:
        return {}
