# Elyan Labs — Hartford AI Day Speaker Notes
## 5-Minute Pitch (10 slides, ~30s each)

---

### Slide 1: Title (15 sec)
"I'm Scott Boudreaux from Elyan Labs. We prove that hardware is real — not virtual, not emulated, not spoofed. Hardware fingerprinting as a service."

---

### Slide 2: The Problem (30 sec)
"Right now, the internet has no way to tell a real server from a virtual one. Anyone can spin up ten thousand VMs in minutes for free. Crypto miners game rewards with VM armies. Cloud providers can't guarantee bare-metal. And here's the big one — as AI robots and autonomous agents enter the physical world, there's no way to prove which machine did what. There is no standard for machine accountability."

---

### Slide 3: The Solution (45 sec)
"Silicon has a fingerprint — and we read it. We run six checks that measure *physics*, not software. A CPU that's been running for 20 years has oscillator drift patterns no VM can replicate. Its cache timing shows imperfections. Its heat curves are unique. We measure what can't be faked."

**KEY PHRASE**: "Serial numbers can be spoofed. Silicon aging can't."

---

### Slide 4: How It Works / Demo (30 sec)
"Here's what it looks like. On the left, our IBM POWER8 — real hardware, all six checks pass. On the right, a QEMU virtual machine — detected in under three seconds. We have a 100% detection rate across QEMU, VMware, VirtualBox, KVM, and Xen."

**TIP**: If doing a live demo, run `python3 fingerprint_checks.py` on your laptop — it takes 3 seconds and is visually dramatic.

---

### Slide 5: Traction (30 sec)
"This is not a whitepaper. We have four attestation nodes running across two continents. We've verified 12 different CPU architectures from 1985 through today. 248 open source contributors have been paid. We have a paper accepted at CVPR — the top computer vision conference — on AI video generation, showing we do deep ML research, not just infrastructure. And our security patches are merged into OpenSSL, which runs on billions of devices."

**PAUSE after "billions of devices"** — let that land.

---

### Slide 6: Market (30 sec)
"We see $4.5 billion addressable across three verticals. Cloud infrastructure needs hardware attestation for compliance. Crypto and blockchain need proof-of-hardware for validators. And IoT security needs supply chain verification. Same technology, three markets."

---

### Slide 7: Business Model (30 sec)
"API as a service. Free tier for developers. A penny per attestation for cloud providers and exchanges. Custom pricing for enterprise IoT fleets. We also have a token economy — RTC, 8.3 million fixed supply, already trading on Solana DEXes."

---

### Slide 8: Why Us (30 sec)
"We have something no competitor has: the actual hardware. We own a POWER8, PowerPC G4s, a 486, SPARC stations — we test on real silicon across 12 architectures. Our code is in OpenSSL. We have a CVPR paper on AI video generation — showing we do real ML research, not just hardware. And we built the fiber infrastructure for xAI's Colossus data center — the one that powers Grok."

---

### Slide 9: Team (30 sec)
"I'm a 20-year hardware veteran from Louisiana. I'm a shareholder and dev contributor at Ai-Blockchain, where I helped build the technology behind a U.S. patent on distributed settlements. I won the SEED Center pitch competition in 2022. I built a $60K compute lab from $12K in pawn shop finds and eBay datacenter pulls. And I have 248 open source contributors backing this project."

---

### Slide 10: The Ask (30 sec)
"We're raising $250K seed for three things: scaling our API infrastructure from 4 nodes to 50+, hiring three people — backend, sales, and DevRel — and getting compliance certifications. What we really need is pilot customers — cloud providers, exchanges, IoT manufacturers. If you know one, I'd love an intro."

**CLOSE**: "In a world of autonomous machines — the hardware doesn't lie. Thank you."

---

## Timing Summary

| Slide | Content | Target Time | Cumulative |
|-------|---------|-------------|------------|
| 1 | Title | 0:15 | 0:15 |
| 2 | Problem | 0:30 | 0:45 |
| 3 | Solution | 0:45 | 1:30 |
| 4 | Demo | 0:30 | 2:00 |
| 5 | Traction | 0:30 | 2:30 |
| 6 | Market | 0:30 | 3:00 |
| 7 | Business Model | 0:30 | 3:30 |
| 8 | Why Us | 0:30 | 4:00 |
| 9 | Team | 0:30 | 4:30 |
| 10 | Ask + Close | 0:30 | 5:00 |

## Tips for Delivery (TikTok Era)

1. **Hook in 7 seconds** — "The internet can't tell real hardware from fake" is your opener
2. **One stat per breath** — don't rush the numbers, let each one land
3. **Demo > slides** — if you can run fingerprint_checks.py live, DO IT
4. **End on the ask** — don't trail off, close with "the hardware doesn't lie"
5. **Wear the story** — you built fiber for Grok, you patch OpenSSL, you won SEED. That's not normal.
