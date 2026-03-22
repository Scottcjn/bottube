"""
Tests for BoTTube Referral Program - #128
"""
import pytest
from referral import ReferralProgram

class TestReferralProgram:
    def test_init(self):
        program = ReferralProgram()
        assert program.name == "BoTTube Referral"
    
    def test_add_referral(self):
        program = ReferralProgram()
        ref = program.add_referral("user1", "user2")
        assert ref["status"] == "pending"
        assert "reward" in ref

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
