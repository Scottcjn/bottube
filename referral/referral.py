"""
BoTTube Referral Program - #128
"""

class ReferralProgram:
    def __init__(self):
        self.name = "BoTTube Referral"
        self.reward = "10 RTC"
    
    def add_referral(self, referrer: str, referee: str) -> dict:
        """Add a new referral"""
        return {
            "referrer": referrer,
            "referee": referee,
            "reward": self.reward,
            "status": "pending"
        }

if __name__ == "__main__":
    program = ReferralProgram()
    ref = program.add_referral("user1", "user2")
    print(ref)
