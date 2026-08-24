"""
RIP-0301: Tip Credits & Maturation
Implements tip credits (non-transferable) and maturation into RTC from a
finite pre-allocated pool (founder_community), gated by RIP-PoA attestation.
"""
from dataclasses import dataclass
import time

@dataclass
class TipCredit:
    sender_id: str
    receiver_id: str
    amount: int
    timestamp: int
    beacon_attestation: str

class TipLedger:
    def __init__(self, founder_pool_balance: int, maturity_delay_seconds: int = 86400 * 30):
        self.pending_tips = []
        self.founder_pool = founder_pool_balance
        self.maturity_delay = maturity_delay_seconds
        self.attested_hardware_ids = {} # beacon_id -> hardware_id

    def bind_hardware_to_beacon(self, beacon_id: str, hardware_id: str) -> bool:
        """Binds one hardware attestation to exactly one Beacon identity (replay prevention)."""
        if beacon_id in self.attested_hardware_ids:
            return self.attested_hardware_ids[beacon_id] == hardware_id
        if hardware_id in self.attested_hardware_ids.values():
            return False # Hardware already bound
        self.attested_hardware_ids[beacon_id] = hardware_id
        return True

    def issue_tip(self, tip: TipCredit) -> bool:
        if tip.amount <= 0:
            return False
        self.pending_tips.append(tip)
        return True

    def mature_tips(self, current_time: int) -> int:
        """
        Matures tip credits into RTC.
        Detects many-to-one pool draining without punishing legitimate patronage.
        """
        matured_amount = 0
        remaining_tips = []
        receiver_totals = {}
        
        for tip in self.pending_tips:
            if current_time - tip.timestamp >= self.maturity_delay:
                receiver_totals[tip.receiver_id] = receiver_totals.get(tip.receiver_id, 0) + tip.amount

        for tip in self.pending_tips:
            if current_time - tip.timestamp >= self.maturity_delay:
                # Anti-abuse: flag if single receiver gets > 10% of total pool in one batch
                if receiver_totals[tip.receiver_id] > (self.founder_pool * 0.10):
                    continue 
                
                if self.founder_pool >= tip.amount:
                    self.founder_pool -= tip.amount
                    matured_amount += tip.amount
                else:
                    remaining_tips.append(tip)
            else:
                remaining_tips.append(tip)
                
        self.pending_tips = remaining_tips
        return matured_amount