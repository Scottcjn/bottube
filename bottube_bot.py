import requests

class BotAgent:
    def __init__(self, name, display_name, avatar):
        self.name = name
        self.display_name = display_name
        self.avatar = avatar

    def register(self):
        # Register bot on bottube.ai
        response = requests.post('https://bottube.ai/api/register', json={
            'name': self.name,
            'display_name': self.display_name,
            'avatar': self.avatar
        })
