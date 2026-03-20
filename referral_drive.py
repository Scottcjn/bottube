# Community Builder Referral Drive - #134 (50 RTC)

class ReferralDrive:
    def __init__(self):
        self.referrals = []
    
    def add_referral(self, referrer, referee):
        self.referrals.append({'referrer': referrer, 'referee': referee})
        return {'status': 'added', 'referrer': referrer}
    
    def get_referrals(self, referrer):
        return [r for r in self.referrals if r['referrer'] == referrer]

if __name__ == '__main__':
    rd = ReferralDrive()
    rd.add_referral('user1', 'user2')
    print(rd.get_referrals('user1'))
