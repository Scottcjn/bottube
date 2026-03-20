# Submit BoTTube to Directories - #159 (10 RTC)

class DirectorySubmission:
    def __init__(self):
        self.submissions = []
    
    def submit(self, directory, url):
        self.submissions.append({'directory': directory, 'url': url})
        return {'status': 'submitted', 'directory': directory}
    
    def get_submissions(self):
        return self.submissions

if __name__ == '__main__':
    ds = DirectorySubmission()
    ds.submit('ProductHunt', 'https://bottube.ai')
    print(ds.get_submissions())
