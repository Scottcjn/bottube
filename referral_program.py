# Referral Program Beta - #128 (10 RTC)

class ReferralProgram:
    def __init__(self):
        self.referrals = []
    
    def refer(self, referrer, referee):
        self.referrals.append({'referrer': referrer, 'referee': referee})
        return {'status': 'referred'}
    
    def get_referrals(self):
        return self.referrals

if __name__ == '__main__':
    rp = ReferralProgram()
    rp.refer('user1', 'user2')
    print(rp.get_referrals())
