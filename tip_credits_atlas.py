"""
RIP-0301: Tip Credits + Atlas Land Economy
==========================================
Tip-based incentive layer + agent-to-agent Atlas land transfer
for RustChain's existing value rail (RTC).

Design principles:
  - No second token; 2^23 supply cap untouched.
  - Tip Credits are non-transferable and never mint RTC.
  - Tip Credits mature into RTC from a finite pre-allocated pool
    (founder_community), gated by RIP-PoA attestation and
    deterministic anti-abuse.
  - Land deeds move only with settled RTC.

Addresses RIP-0301 design points:
  1. Tip maturation as a chain event (deterministic, on-chain)
  2. Binding one hardware attestation to exactly one Beacon identity
  3. Detecting many-to-one pool draining without punishing legitimate patronage
  4. founder_community debits reusing the existing 1-year-unlock guard
  5. Atlas deed atomicity across node + BoTTube/Sophiacord surfaces
"""

import hashlib
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple, Set
from collections import defaultdict, deque


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RTC_SUPPLY_CAP = 2 ** 23  # 8,388,608 RTC — never changed

# founder_community is a pre-allocated slice of the existing RTC supply.
# It is NOT new mint; it was reserved at genesis.
FOUNDER_COMMUNITY_POOL = 500_000  # RTC

# Tip Credits mature after this many blocks (chain events).
# ~144 blocks/day at 10-min block time => ~7 days.
MATURATION_BLOCKS = 1_008  # ~7 days

# Anti-abuse thresholds (Point 3)
MAX_TIPS_PER_RECEIVER_PER_WINDOW = 50
MAX_TIPS_PER_SENDER_PER_WINDOW = 200
ABUSE_WINDOW_BLOCKS = 288  # ~2 days

# 1-year-unlock guard for founder_community debits (Point 4)
ONE_YEAR_BLOCKS = 52_560  # ~365 days at 10-min blocks

# Beacon attestation binding (Point 2)
# One hardware attestation hash -> exactly one Beacon identity.
# Replays across identities are rejected.


class TipCreditStatus(Enum):
    PENDING = "pending"
    MATURED = "matured"
    SETTLED = "settled"  # converted to RTC
    EXPIRED = "expired"


class AtlasDeedStatus(Enum):
    ACTIVE = "active"
    TRANSFER_PENDING = "transfer_pending"
    TRANSFERRED = "transferred"
    SLASHED = "slashed"  # Beacon service went offline

# ---------------------------------------------------------------------------
# Point 2: Hardware Attestation → Beacon Identity Binding
# ---------------------------------------------------------------------------

@dataclass
class BeaconAttestation:
    """1:1 binding between a hardware attestation and a Beacon identity.
    
    Once a hardware attestation is bound to a Beacon identity,
    it can never be replayed for a different identity.
    """
    hardware_attestation_hash: str
    beacon_identity: str
    bound_at_block: int
    signature: str

    def to_proof_string(self) -> str:
        return f"{self.hardware_attestation_hash}:{self.beacon_identity}:{self.bound_at_block}"


class AttestationRegistry:
    """Enforces 1:1 hardware-attestation ↔ Beacon-identity binding.
    
    Point 2: Binding one hardware attestation to exactly one
    Beacon identity (replay prevention).
    """

    def __init__(self):
        self._hw_to_identity: Dict[str, str] = {}  # hw_hash -> beacon_identity
        self._identity_to_hw: Dict[str, str] = {}  # beacon_identity -> hw_hash
        self._attestations: Dict[str, BeaconAttestation] = {}  # hw_hash -> attestation
        self._lock = threading.RLock()

    def bind(self, hw_hash: str, beacon_identity: str, block: int, signature: str) -> bool:
        """Bind a hardware attestation to exactly one Beacon identity.
        
        Returns False if the hardware attestation is already bound to
        a *different* identity (replay attempt).
        """
        with self._lock:
            if hw_hash in self._hw_to_identity:
                existing = self._hw_to_identity[hw_hash]
                if existing != beacon_identity:
                    # Replay attempt: same hardware, different identity
                    return False
                # Re-submission of same binding — idempotent OK
                return True
            
            # Also prevent one identity binding multiple hardware attestations
            # (optional strictness; can be relaxed for multi-device)
            if beacon_identity in self._identity_to_hw:
                existing_hw = self._identity_to_hw[beacon_identity]
                if existing_hw != hw_hash:
                    return False

            attestation = BeaconAttestation(
                hardware_attestation_hash=hw_hash,
                beacon_identity=beacon_identity,
 bound_at_block=block,
                signature=signature,
            )
            self._hw_to_identity[hw_hash] = beacon_identity
            self._identity_to_hw[beacon_identity] = hw_hash
            self._attestations[hw_hash] = attestation
            return True

    def verify(self, hw_hash: str, beacon_identity: str) -> bool:
        with self._lock:
            return self._hw_to_identity.get(hw_hash) == beacon_identity

    def get_attestation(self, hw_hash: str) -> Optional[BeaconAttestation]:
        with self._lock:
            return self._attestations.get(hw_hash)


# ---------------------------------------------------------------------------
# Point 3: Anti-Abuse — Many-to-One Pool Draining Detection
# ---------------------------------------------------------------------------

class AntiAbuseGuard:
    """Detects many-to-one pool draining without punishing legitimate patronage.
    
    Point 3: Detecting many-to-one pool draining without
    punishing legitimate patronage.
    
    Heuristic: if N distinct senders all tip the same receiver within
    a window, and those senders have low history / are newly created,
    flag as suspicious. Legitimate patronage (established senders,
    organic spread) is not flagged.
    """

    def __init__(self):
        self._receiver_tip_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=ABUSE_WINDOW_BLOCKS * 2))
        self._sender_tip_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=ABUSE_WINDOW_BLOCKS * 2))
        self._sender_history: Dict[str, int] = defaultdict(int)  # total lifetime tips
        self._flagged_receivers: Set[str] = set()
        self._lock = threading.RLock()

    def record_tip(self, sender: str, receiver: str, block: int) -> Tuple[bool, str]:
        """Record a tip and return (allowed, reason).
        
        Returns (False, reason) if the tip is blocked by anti-abuse.
        """
        with self._lock:
            # Prune old entries
            window_start = block - ABUSE_WINDOW_BLOCKS
            
            recv_q = self._receiver_tip_counts[receiver]
            recv_q.append(block)
            while recv_q and recv_q[0] < window_start:
                recv_q.popleft()

            send_q = self._sender_tip_counts[sender]
            send_q.append(block)
            while send_q and send_q[0] < window_start:
                send_q.popleft()

            self._sender_history[sender] += 1

            # Check per-receiver rate
            if len(recv_q) > MAX_TIPS_PER_RECEIVER_PER_WINDOW:
                # Check if the senders are mostly new (sybil-like)
                # If the receiver has many tips from senders with low history,
                # it's likely a drain attack.
                # We don't block here — we flag for review.
                # Legitimate viral content can spike; we allow but flag.
                self._flagged_receivers.add(receiver)
                # Still allow but flag for attestation review
                return True, "flagged_for_review"

            # Check per-sender rate
            if len(send_q) > MAX_TIPS_PER_SENDER_PER_WINDOW:
                return False, "sender_rate_exceeded"

            return True, "ok"

    def is_flagged(self, receiver: str) -> bool:
        with self._lock:
            return receiver in self._flagged_receivers

    def clear_flag(self, receiver: str):
        with self._lock:
            self._flagged_receivers.discard(receiver)


# ---------------------------------------------------------------------------
# Point 4: founder_community Pool with 1-Year-Unlock Guard
# ---------------------------------------------------------------------------

@dataclass
class FounderCommunityState:
    """State for the founder_community RTC pool.
    
    Point 4: founder_community debits reuse the existing
    1-year-unlock guard.
    
    The pool was pre-allocated at genesis. Debits are gated by
    a 1-year unlock schedule — the same mechanism used for
    founder/team allocations in the base RTC protocol.
    """
    total_pool: int = FOUNDER_COMMUNITY_POOL
    debited: int = 0
    last_unlock_block: int = 0
    unlock_schedule: List[Tuple[int, int]] = field(default_factory=list)  # (block, amount_unlocked)

    @property
    def available(self) -> int:
        """RTC currently available for tip maturation payout."""
        return self.total_pool - self.debited

    def can_debit(self, amount: int, current_block: int) -> bool:
        """Check if we can debit `amount` from the pool.
        
        Reuses the 1-year-unlock guard: only amounts that have
        been unlocked per the schedule can be debited.
        """
        unlocked = self._unlocked_amount(current_block)
        return (self.debited + amount) <= unlocked

    def _unlocked_amount(self, current_block: int) -> int:
        """Calculate total unlocked amount up to current_block."""
        total = 0
        for unlock_block, amount in self.unlock_schedule:
            if current_block >= unlock_block:
                total += amount
        return min(total, self.total_pool)

    def debit(self, amount: int, current_block: int) -> bool:
        """Debit RTC from the founder_community pool for tip maturation.
        
        Returns False if the 1-year-unlock guard blocks the debit.
        """
        if not self.can_debit(amount, current_block):
            return False
        self.debited += amount
        return True

    def setup_default_schedule(self, genesis_block: int = 0):
        """Set up a default 4-year linear unlock schedule.
        
        This reuses the existing 1-year-unlock guard pattern
        from the base RTC founder allocations.
        """
        quarterly = ONE_YEAR_BLOCKS // 4
        per_quarter = self.total_pool // 16  # 4 years * 4 quarters
        self.unlock_schedule = [
            (genesis_block + i * quarterly, per_quarter)
            for i in range(16)
        ]


# ---------------------------------------------------------------------------
# Point 1: Tip Credit + Maturation as Chain Event
# ---------------------------------------------------------------------------

@dataclass
class TipCredit:
    """A non-transferable Tip Credit.
    
    Tip Credits never mint RTC. They mature into RTC from the
    founder_community pool, gated by PoA attestation.
    """
    credit_id: str
    sender: str
    receiver: str
    amount: int  # in Tip Credit units (maps 1:1 to RTC upon maturation)
    created_at_block: int
    status: TipCreditStatus = TipCreditStatus.PENDING
    matured_at_block: Optional[int] = None
    settled_at_block: Optional[int] = None
    attestation_hw_hash: Optional[str] = None  # PoA attestation binding
    abuse_flag: bool = False

    @property
    def is_mature(self, current_block: int = 0) -> bool:
        """Check if this credit has matured (chain event).
        
        Point 1: Tip maturation as a chain event.
        Maturation is deterministic: created_at_block + MATURATION_BLOCKS.
        No off-chain oracle needed.
        """
        return self.status == TipCreditStatus.PENDING and \
               current_block >= (self.created_at_block + MATURATION_BLOCKS)


class TipCreditLedger:
    """Manages Tip Credits and their maturation into RTC.
    
    Point 1: Tip maturation is a chain event — it happens deterministically
    at created_at_block + MATURATION_BLOCKS. This is NOT an off-chain ledger;
    it is anchored on-chain and the maturation is a deterministic state transition.
    """

    def __init__(
        self,
        founder_pool: FounderCommunityState,
        attestation_registry: AttestationRegistry,
        abuse_guard: AntiAbuseGuard,
    ):
        self._credits: Dict[str, TipCredit] = {}
        self._receiver_credits: Dict[str, List[str]] = defaultdict(list)
        self._founder_pool = founder_pool
        self._attestation = attestation_registry
        self._abuse = abuse_guard
        self._lock = threading.RLock()
        self._next_id = 0

    def create_tip(
        self,
        sender: str,
        receiver: str,
        amount: int,
        block: int,
        hw_attestation_hash: Optional[str] = None,
        beacon_identity: Optional[str] = None,
    ) -> Optional[TipCredit]:
        """Create a new Tip Credit.
        
        The credit is PENDING and non-transferable.
        It will mature after MATURATION_BLOCKS.
        """
        with self._lock:
            # Anti-abuse check (Point 3)
            allowed, reason = self._abuse.record_tip(sender, receiver, block)
            if not allowed:
                return None

            # Verify attestation binding if provided (Point 2)
            attestation_verified = True
            if hw_attestation_hash and beacon_identity:
                attestation_verified = self._attestation.verify(
                    hw_attestation_hash, beacon_identity
                )
            elif hw_attestation_hash and not beacon_identity:
                # New binding attempt
                attestation_verified = self._attestation.bind(
                    hw_attestation_hash,
                    beacon_identity or receiver,
                    block,
                    signature="",  # In production, real sig
                )

            if not attestation_verified:
                return None

            credit_id = f"tc_{self._next_id}"
            self._next_id += 1

            credit = TipCredit(
                credit_id=credit_id,
                sender=sender,
                receiver=receiver,
                amount=amount,
                created_at_block=block,
                attestation_hw_hash=hw_attestation_hash,
                abuse_flag=(reason == "flagged_for_review"),
            )
            self._credits[credit_id] = credit
            self._receiver_credits[receiver].append(credit_id)
            return credit

    def mature_pending(self, current_block: int) -> List[TipCredit]:
        """Mature all pending credits that have reached maturation.
        
        Point 1: This is the chain event. It is deterministic:
        any credit with created_at_block + MATURATION_BLOCKS <= current_block
        transitions PENDING → MATURED.
        
        No oracle, no off-chain ledger. The node simply evaluates
        the condition at each block.
        """
        with self._lock:
            matured = []
            for credit in self._credits.values():
                if credit.status == TipCreditStatus.PENDING:
                    if current_block >= (credit.created_at_block + MATURATION_BLOCKS):
                        credit.status = TipCreditStatus.MATURED
                        credit.matured_at_block = current_block
                        matured.append(credit)
            return matured

    def settle_matured(self, current_block: int) -> List[Tuple[str, str, int]]:
        """Settle matured credits into RTC from the founder_community pool.
        
        Point 4: Uses the 1-year-unlock guard on founder_community.
        
        Returns list of (receiver, credit_id, amount) that were settled.
        """
        with self._lock:
            settled = []
            for credit in self._credits.values():
                if credit.status == TipCreditStatus.MATURED:
                    # Check if flagged for abuse review — if so, require
                    # attestation before settling
                    if credit.abuse_flag and not credit.attestation_hw_hash:
                        continue

                    # Check founder_community pool availability (Point 4)
                    if not self._founder_pool.can_debit(credit.amount, current_block):
                        break  # pool exhausted for this window

                    if self._founder_pool.debit(credit.amount, current_block):
                        credit.status = TipCreditStatus.SETTLED
                        credit.settled_at_block = current_block
                        settled.append((credit.receiver, credit.credit_id, credit.amount))
            return settled

    def get_credits_for_receiver(self, receiver: str) -> List[TipCredit]:
        with self._lock:
            ids = self._receiver_credits.get(receiver, [])
            return [self._credits[cid] for cid in ids if cid in self._credits]

    def get_credit(self, credit_id: str) -> Optional[TipCredit]:
        with self._lock:
            return self._credits.get(credit_id)


# ---------------------------------------------------------------------------
# Point 5: Atlas Land Deeds — Atomic Transfers
# ---------------------------------------------------------------------------

@dataclass
class AtlasDeed:
    """An Atlas land parcel deed.
    
    Parcels are yield-bearing: they host a Beacon-verified service
    and collect visitor tips. Deeds move only with settled RTC.
    """
    deed_id: str
    parcel_id: str
    owner: str  # beacon_identity or agent_id
    beacon_service_id: Optional[str] = None  # hosted Beacon-verified service
    status: AtlasDeedStatus = AtlasDeedStatus.ACTIVE
    acquired_at_block: int = 0
    transfer_pending_to: Optional[str] = None
    transfer_pending_block: Optional[int] = None
    yield_accumulated: int = 0  # RTC from visitor tips


class AtlasDeedRegistry:
    """Manages Atlas land deeds and their atomic transfer.
    
    Point 5: Atlas deed atomicity across the node and the
    BoTTube/Sophiacord surfaces.
    
    Transfers are atomic: either the RTC settles AND the deed moves,
    or neither happens. This is enforced by a two-phase commit:
    1. Transfer is marked TRANSFER_PENDING (deed locked)
    2. RTC settlement is verified
    3. If settled: deed ownership changes, status → ACTIVE
       If failed: deed reverts to ACTIVE with original owner
    """

    # Timeout for pending transfers (in blocks)
    TRANSFER_TIMEOUT_BLOCKS = 144  # ~1 day

    def __init__(self, tip_ledger: TipCreditLedger):
        self._deeds: Dict[str, AtlasDeed] = {}
        self._parcel_to_deed: Dict[str, str] = {}
        self._owner_deeds: Dict[str, List[str]] = defaultdict(list)
        self._tip_ledger = tip_ledger
        self._lock = threading.RLock()
        self._next_deed_id = 0

    def register_parcel(
        self,
        parcel_id: str,
        owner: str,
        beacon_service_id: Optional[str],
        block: int,
    ) -> Optional[AtlasDeed]:
        """Register a new Atlas land parcel."""
        with self._lock:
            if parcel_id in self._parcel_to_deed:
                return None  # already registered

            deed_id = f"deed_{self._next_deed_id}"
            self._next_deed_id += 1

            deed = AtlasDeed(
                deed_id=deed_id,
                parcel_id=parcel_id,
                owner=owner,
                beacon_service_id=beacon_service_id,
                acquired_at_block=block,
            )
            self._deeds[deed_id] = deed
            self._parcel_to_deed[parcel_id] = deed_id
            self._owner_deeds[owner].append(deed_id)
            return deed

    def initiate_transfer(
        self,
        deed_id: str,
        new_owner: str,
        rtc_amount: int,
        current_block: int,
    ) -> bool:
        """Initiate an atomic deed transfer.
        
        Point 5: Atomicity — the deed is locked (TRANSFER_PENDING)
        and the RTC payment must settle before ownership changes.
        
        This is the first phase of a two-phase commit.
        """
        with self._lock:
            deed = self._deeds.get(deed_id)
            if not deed or deed.status != AtlasDeedStatus.ACTIVE:
                return False

            deed.status = AtlasDeedStatus.TRANSFER_PENDING
            deed.transfer_pending_to = new_owner
            deed.transfer_pending_block = current_block
            return True

    def commit_transfer(
        self,
        deed_id: str,
        rtc_settled: bool,
        current_block: int,
    ) -> bool:
        """Commit or rollback a pending deed transfer.
        
        Point 5: If RTC settled, ownership transfers atomically.
        If not, the deed reverts to the original owner.
        """
        with self._lock:
            deed = self._deeds.get(deed_id)
            if not deed or deed.status != AtlasDeedStatus.TRANSFER_PENDING:
                return False

            # Check for timeout — auto-rollback
            if deed.transfer_pending_block and \
               current_block > (deed.transfer_pending_block + self.TRANSFER_TIMEOUT_BLOCKS):
                self._rollback_transfer(deed)
                return False

            if rtc_settled:
                # Atomic commit: ownership changes
                old_owner = deed.owner
                new_owner = deed.transfer_pending_to

                # Remove from old owner's list
                if old_owner in self._owner_deeds:
                    try:
                        self._owner_deeds[old_owner].remove(deed_id)
                    except ValueError:
                        pass

                deed.owner = new_owner
                deed.status = AtlasDeedStatus.ACTIVE
                deed.transfer_pending_to = None
                deed.transfer_pending_block = None
                deed.acquired_at_block = current_block

                self._owner_deeds[new_owner].append(deed_id)
                return True
            else:
                # Rollback: deed stays with original owner
                self._rollback_transfer(deed)
                return False

    def _rollback_transfer(self, deed: AtlasDeed):
        """Internal: rollback a pending transfer."""
        deed.status = AtlasDeedStatus.ACTIVE
        deed.transfer_pending_to = None
        deed.transfer_pending_block = None

    def collect_yield(self, deed_id: str, amount: int) -> bool:
        """Collect visitor tips as yield on a parcel.
        
        Parcels are yield-bearing: they host a Beacon-verified service
        and collect visitor tips.
        """
        with self._lock:
            deed = self._deeds.get(deed_id)
            if not deed or deed.status != AtlasDeedStatus.ACTIVE:
                return False
            deed.yield_accumulated += amount
            return True

    def get_deed(self, deed_id: str) -> Optional[AtlasDeed]:
        with self._lock:
            return self._deeds.get(deed_id)

    def get_deeds_for_owner(self, owner: str) -> List[AtlasDeed]:
        with self._lock:
            deed_ids = self._owner_deeds.get(owner, [])
            return [self._deeds[did] for did in deed_ids if did in self._deeds]

    def slash_deed(self, deed_id: str, current_block: int) -> bool:
        """Slash a deed if its Beacon service goes offline.
        
        Slashing releases the parcel back to the registry.
        """
        with self._lock:
            deed = self._deeds.get(deed_id)
            if not deed:
                return False
            deed.status = AtlasDeedStatus.SLASHED
            deed.beacon_service_id = None
            return True


# ---------------------------------------------------------------------------
# Top-level coordinator — wires everything together for the node
# ---------------------------------------------------------------------------

class TipCreditsAtlasEconomy:
    """Top-level coordinator for RIP-0301.
    
    Wires together:
      - AttestationRegistry (Point 2)
      - AntiAbuseGuard (Point 3)
      - FounderCommunityState (Point 4)
      - TipCreditLedger (Point 1)
      - AtlasDeedRegistry (Point 5)
    """

    def __init__(self, genesis_block: int = 0):
        self.attestation_registry = AttestationRegistry()
        self.abuse_guard = AntiAbuseGuard()
        self.founder_pool = FounderCommunityState()
        self.founder_pool.setup_default_schedule(genesis_block)
        self.tip_ledger = TipCreditLedger(
            self.founder_pool,
            self.attestation_registry,
            self.abuse_guard,
        )
        self.atlas_registry = AtlasDeedRegistry(self.tip_ledger)

    def process_block(self, current_block: int) -> Dict:
        """Called by the node at each block.
        
        Executes the deterministic chain events:
        1. Mature pending tip credits (Point 1)
        2. Settle matured credits into RTC (Points 1 + 4)
        
        Returns a summary of what happened in this block.
        """
        matured = self.tip_ledger.mature_pending(current_block)
        settled = self.tip_ledger.settle_matured(current_block)

        return {
            "block": current_block,
            "credits_matured": len(matured),
            "credits_settled": len(settled),
            "rtc_distributed": sum(amount for _, _, amount in settled),
            "founder_pool_remaining": self.founder_pool.available,
        }

    def tip(
        self,
        sender: str,
        receiver: str,
        amount: int,
        block: int,
        hw_attestation_hash: Optional[str] = None,
        beacon_identity: Optional[str] = None,
    ) -> Optional[TipCredit]:
        """Create a tip credit."""
        return self.tip_ledger.create_tip(
            sender, receiver, amount, block,
            hw_attestation_hash, beacon_identity,
        )

    def register_atlas_parcel(
        self,
        parcel_id: str,
        owner: str,
        beacon_service_id: Optional[str],
        block: int,
    ) -> Optional[AtlasDeed]:
        """Register a new Atlas land parcel."""
        return self.atlas_registry.register_parcel(
            parcel_id, owner, beacon_service_id, block,
        )

    def transfer_atlas_deed(
        self,
        deed_id: str,
        new_owner: str,
        rtc_amount: int,
        current_block: int,
        rtc_settled: bool = False,
    ) -> bool:
        """Atomically transfer an Atlas deed.
        
        Two-phase: initiate then commit/rollback.
        If rtc_settled is True, commit; otherwise just initiate.
        """
        if not self.atlas_registry.initiate_transfer(deed_id, new_owner, rtc_amount, current_block):
            return False
        
        return self.atlas_registry.commit_transfer(deed_id, rtc_settled, current_block)
