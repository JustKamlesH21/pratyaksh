# Pratyaksh: the business case

**Team Omnitrons** · FET Aavishkar 2026 · #F1BBBA03 "Voice-clone consent verification protocol"

Draft of Oct 27, 2026, for the pitch and for what we build after the finale. Figures carry their source and date; anything we could not confirm is marked as such. Terms such as Caller, Challenge, Verdict and Verification Receipt are defined in [`CONTEXT.md`](../CONTEXT.md).

## 1. The problem a bank pays to solve

A scammer needs seconds of a Customer's voice to clone it. They then call the bank as that Customer and ask for the things that move money: a new payee, a SIM swap or password reset, a high-value transfer.

- **The losses are large and growing.** Indians lost about **₹22,846 crore to cyber fraud in 2024**, roughly three times 2023's ₹7,465 crore, across 22.68 lakh incidents (MHA reply in Parliament, I4C data, 22 Jul 2025, [PTI via The Week](https://www.theweek.in/wire-updates/business/2025/07/22/del23-lsq-cyber-fraud.html)).¹ RBI counted **₹36,014 crore of bank fraud in FY25** ([Business Standard, May 2025](https://www.business-standard.com/finance/news/bank-fraud-amount-triples-in-fy25-despite-drop-in-number-of-cases-rbi-125052900696_1.html)).
- **Cloned voices already work on people.** In McAfee's 2023 survey, 47% of Indian adults had experienced an AI voice scam or knew someone who had. 69% could not tell a cloned voice from a real one, and 83% of Indian victims lost money ([BusinessWorld, May 2023](https://businessworld.in/article/ai-voice-scams-more-prevalent-in-india-affects-almost-50-indians-mcafee-report-475192)). Indian police have reported cases such as a ₹44,500 loss in Lucknow to a cloned relative's voice ([Gulf News, Dec 2023](https://gulfnews.com/world/asia/india/india-lucknow-reports-first-ai-generated-voice-fraud-case-1.1702870783452)).
- **Cloned voices already beat bank voice ID.** In 2023 a journalist got into his own Lloyds Bank account by playing an AI clone of his voice to its Voice ID ([IT Brew, Mar 2023](https://www.itbrew.com/stories/2023/03/31/voice-generation-ai-blows-through-bank-s-voice-id-security)). In 2025 the OpenAI CEO called accepting a voiceprint as authentication "a crazy thing to still be doing" ([Axios, 22 Jul 2025](https://www.axios.com/2025/07/22/openai-chatgpt-sam-altman-ai-fraud)).
- **Attacks on call centres are rising fastest.** Pindrop, a voice-security vendor, reports synthetic-voice attacks up 149% at banks and 475% at insurers in 2024, from its own call data (Pindrop's 2025 Voice Intelligence and Security Report, Jun 2025, [pindrop.com](https://www.pindrop.com/); vendor data, and its figures vary between publications).

¹ A separate DoT reply gives ₹22,812 crore and 19.18 lakh complaints for 2024 ([PIB](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2117716&reg=48&lang=2)). We quote the MHA figure.

## 2. Why the usual answers fail

| Today's check on a bank call | Why a Clone gets through |
|---|---|
| Voice biometrics (a stored voiceprint) | A good Clone *is* the Customer's voice. And a leaked voiceprint can never be reset, unlike a password |
| Knowledge questions (date of birth, last transaction) | Found in leaks and on social media, or phished in the same call |
| OTP read out on the call | The scam script talks the victim into reading it out ("digital arrest", fake KYC) |
| Deepfake-detection models | They chase the latest generator. On our laptop the open wav2vec2 detector scored Indic Parler-TTS speech as 0.0 synthetic: it simply did not recognise it |

## 3. What Pratyaksh does differently

Pratyaksh never asks whether a voice *sounds like* the Customer. It asks whether a **live human holding the Registered Device** is on the line, using Challenges a Clone pipeline cannot pass in real time:

- **A Whisper Phrase**: a random phrase mixing Kannada, Hindi and English (1,344 equally likely), to be *whispered*. Text-to-speech and voice-cloning models speak; they do not whisper on demand. In our first runs a synthetic Caller said the right words (Task Match 0.92) but scored 0.01–0.25 on whispering, against the 0.60 needed, and was BLOCKed.
- **A Possession Code**: a one-time code that appears only on the Customer's paired Bank App, read aloud. A remote attacker does not have the phone.
- **Reply Latency**, and a spoof score as one Signal among several (advisory, not the gate).

The result is a Verdict (PASS, STEP-UP or BLOCK) with a plain-language Reason a bank officer, an auditor or the Customer can read. Around it:
- A **Security Alert** on the Customer's phone after every BLOCK, and a **Voice Pause**, so the impostor cannot simply call again.
- An **Attack Wave** alarm when several Customers are targeted within minutes.
- A **hash-chained Audit Trail**, and **Ed25519-signed Verification Receipts** that core banking checks and redeems once before acting.
- **No voiceprint is ever stored** (ADR-0003). There is nothing biometric to leak, and nothing to enrol.
- **Added Time** for a genuine Caller is designed to stay under 20 s on the riskiest Request. Balance enquiries are not slowed at all.

## 4. Why now: regulation is moving our way

- **RBI's Digital Payment Authentication Directions (25 Sep 2025)** require at least two factors, plus **risk-based checks on top**. Factors other than SMS OTP are allowed, and compliance was due by 1 Apr 2026 ([RBI press release](https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=61282)). A Possession Code on the Registered Device plus a live Challenge is that kind of risk-based check.
- **RBI's circular on voice-call and SMS fraud (17 Jan 2025)** asks regulated entities to have procedures for changing a registered mobile number "after due verification" ([MediaNama](https://www.medianama.com/2025/01/223-rbi-transactional-calls-financial-fraud/)). SIM-swap and number-change requests are exactly where Pratyaksh sits.
- **CERT-In's deepfake advisory (Nov 2024)** recommends call-back verification for sensitive transactions (secondary summary: [Khaitan & Co](https://khaitanco.com/thought-leadership/Growing-Concern-over-Deepfakes-CERT-In-Issues-Advisory)).
- **The DPDP Rules (notified 13 Nov 2025)** phase in by about May 2027, with penalties up to ₹250 crore for failing to keep reasonable security safeguards ([PIB](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf)). Holding voiceprints of millions of Customers is a large, permanent breach exposure; Pratyaksh holds none.

## 5. Who buys it

| Buyer | Where Pratyaksh sits | What pushes them |
|---|---|---|
| Banks' phone banking and contact centres (first target) | In front of add-payee, SIM or number change, password reset, high-value transfers | RBI authentication directions; fraud losses; liability for unauthorised transactions |
| NBFCs, housing finance companies, small finance banks | Loan disbursal account changes, contact-detail updates | RBI fraud-risk directions for NBFCs; the same voice/SMS circular |
| Payment apps and issuers | Account recovery, device change, limit increases | The 2025 directions apply to all payment issuers |
| Telecom SIM-swap desks | SIM replacement requests by phone | TRAI already blocks porting for 7 days after a SIM swap because of fraud ([Benzinga, 2024](https://in.benzinga.com/content/37774947/trai-tightens-mobile-number-portability-rules-to-prevent-fraud-heres-whats-new)) |
| Insurers | Claim payout account changes, policy surrender | Fastest-growing synthetic-voice attacks in Pindrop's data |
| Government helplines | Any call that changes records | Opportunity only; no specific mandate found |

We found no credible figure for India's call-centre authentication market, so we do not quote one. The size of the problem is the fraud loss above.

## 6. How it is sold and integrated

**Product.** A verification service the bank runs on its own infrastructure (on-premises or its own cloud), because Customer calls and audit data cannot leave the bank. It has four parts:
- the Verifier API;
- the Voice Agent;
- the Bank App module, delivered as an SDK in the bank's existing app;
- the Console for the fraud team.

**Integration path, already designed in:**
1. **The phone line.** Today Calls arrive over WebRTC through a self-hosted LiveKit server. A bank adds a SIP trunk from its telephony to LiveKit; Verification does not change (ADR-0005).
2. **The Bank App.** Pairing and the Device Inbox become a small module in the bank's existing app, with push notifications instead of polling.
3. **Core banking.** It acts only on a valid, unredeemed Verification Receipt: a standard JWT that any bank system can verify with an off-the-shelf library.
4. **Policy.** Each bank sets its own Risk Tiers, thresholds and Voice Pause in `policy.yaml`, tuned from its own Eval Runs, with no code change.

**Pricing (hypotheses to test with pilot banks, not validated):**
- Per Verification on risky Requests, since balance enquiries are free and unchallenged.
- An annual platform fee per contact centre, covering the Console, the Audit Trail and Eval Runs.
- A pilot priced on fraud prevented in its first quarter.

## 7. Plan after the hackathon

| Stage | Goal | Proof we need |
|---|---|---|
| 0–3 months | Pilot-ready | Eval Runs on 500+ consented real and Clone recordings across Kannada, Hindi and English, with Catch Rate and False Reject Rate per language. Then the SIP trunk, and the Bank App as an SDK |
| 3–6 months | First pilot (a cooperative or small finance bank) | Added Time and drop-off on real Customers; zero voiceprints stored; a fraud team's verdict on the Reasons |
| 6–12 months | More languages and buyers | Tamil, Telugu and Marathi phrase banks; a SIM-swap desk pilot; an independent security audit; hardware-backed signing keys |

**Metrics we will report:** Catch Rate, False Reject Rate and Added Time (all already measured by Eval Runs), plus hearing time per Response and the share of Callers who choose App Approval.

## 8. Risks and how we answer them

| Risk | Answer |
|---|---|
| Clone generators learn to whisper | The Whisper Phrase is one Challenge of several, and the Possession Code needs the physical phone. New Challenge types plug into the same Policy |
| A human scammer reads a code the victim was tricked into sharing | The code is shown only in the Customer's own app, next to a warning, and every BLOCK alerts them. Agent Review holds high-value Requests for a person |
| Accessibility (elderly or speech-impaired Customers) | App Approval on the Registered Device replaces voice Challenges entirely |
| False rejects annoy genuine Customers | STEP-UP before BLOCK; thresholds tuned from each bank's Eval Runs; App Approval as the fallback |
| Speech models are weak on Indian languages | Script-agnostic matching; Task Match is one Signal among several; per-language Eval Runs |

## Sources still to check before quoting on stage

- The original Vice article on the Lloyds Voice ID bypass (we cite IT Brew's summary).
- The direct link to Pindrop's 2025 report (the link we had returns 404) and which of its growth figures to use.
- McAfee's own 2023 release (we cite BusinessWorld's report of it).
- The exact text of the RBI 2025 directions on a dynamic factor and on compensating customers (law-firm commentary only so far).
- Whether the DPDP Act treats a voiceprint differently from other personal data (our reading: it has no separate "sensitive" tier, unlike the old IT Rules 2011).
