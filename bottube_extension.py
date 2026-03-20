# BoTTube Chrome Extension - #535 (50 RTC)
# Browse, View, Upload Videos

class BoTTubeExtension:
    def __init__(self):
        self.name = "BoTTube Extension"
    def browse(self): return {'status': 'browsing'}
    def view(self, video_id): return {'video_id': video_id}
    def upload(self, file): return {'file': file, 'status': 'uploaded'}
