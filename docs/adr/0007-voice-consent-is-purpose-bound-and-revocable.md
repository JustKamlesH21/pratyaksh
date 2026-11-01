# Voice Consent is purpose-bound, revocable, and checked on every use

Our problem statement is a voice-clone *consent* protocol, and until now consent was a `--i-have-consent` flag: a person's word, checked by nothing. Now the owner of a voice decides who may use it, for which purpose, for how long and how many times. They agree on their Registered Device by reading a statement with a fresh random number, the same two proofs as a risky Request (Possession Code: the device; Whisper Phrase: a live person and a number that cannot be replayed).

That produces a signed Consent Pass, but a signature alone cannot be withdrawn, so a pass is never enough by itself: every Voice Use asks the verifier, which checks the live record for revocation, expiry, requester, purpose and remaining uses. Allowed or refused, each use goes on the owner's Voice Ledger, an Audit Trail chain of its own.

- **A separate signing key.** A Consent Pass has the same format as a Verification Receipt. Under one key it would verify as a receipt, because it names no Call whose chain could disagree.
- **No speaker comparison, for now.** Azure's personal voice uses the consent recording to confirm the speaker matches the training audio. We do not: ADR-0003 rules out voiceprints, so the statement proves that the phone's holder agreed, not that the recording to be cloned is theirs. Binding the two is the next step, and the honest gap until then.
- **Only a hash of the statement is kept**, so ADR-0003 still holds: no voice is stored to give consent.
- **A closed list of purposes.** A purpose is only worth signing if everyone reads it the same way.

Consent binds those who honour it. Someone with an open-source model and no scruples never asks, which is why Verification stays: consent governs lawful use of a voice, and the Possession Code stops the rest.
