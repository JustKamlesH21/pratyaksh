# Pratyaksh

Pratyaksh decides whether the person on a bank call is a live human holding the customer's registered phone, rather than an AI voice clone. It does this without storing anyone's voice.

## Language

### People and devices

**Customer**:
A person who holds an account with the bank and has a Registered Device on file.
_Avoid_: user, account holder, client

**Caller**:
Whoever is speaking on a Call and claims to be a Customer. A Caller may be the Customer or an impostor using a Clone.
_Avoid_: user, speaker, customer (until verified)

**Registered Device**:
The Customer's phone where the Bank App runs. It is the only place a Possession Code or App Approval prompt is delivered.
_Avoid_: phone, mobile, device

**Device Pairing**:
Linking the Bank App on a Customer's Registered Device to that Customer with a secret link, so Possession Codes and App Approval prompts reach only that phone.
_Avoid_: login, registration

**Bank Agent**:
The human contact-centre employee who watches Calls on the Console and handles Agent Review.
_Avoid_: operator, executive, admin

**Voice Agent**:
The automated voice on the bank's side of a Call that speaks prompts and listens to the Caller.
_Avoid_: bot, assistant, IVR

### The call

**Call**:
One live voice conversation between a Caller and the Voice Agent, from greeting to close.
_Avoid_: session, conversation, room

**Request**:
The thing the Caller asks the bank to do on a Call: a balance enquiry, adding a payee, a SIM swap or password reset, or a high-value transfer.
_Avoid_: intent, action, transaction

**Risk Tier**:
The level a Request is assigned. It sets which Challenges the Caller must pass and whether Agent Review is needed.
_Avoid_: risk level, priority

**Verification**:
The process of deciding, from the Caller's Responses, whether the Caller is a live human holding the Registered Device.
_Avoid_: authentication, KYC, login

### Challenges and evidence

**Challenge**:
One task the Voice Agent asks the Caller to perform during Verification.
_Avoid_: question, CAPTCHA, test

**Whisper Phrase**:
A Challenge where the Caller must whisper a randomly chosen phrase that mixes Kannada, Hindi and English words.
_Avoid_: passphrase, code-mix test

**Possession Code**:
A Challenge where a one-time code is sent to the Registered Device and the Caller must read it aloud.
_Avoid_: OTP, PIN

**Response**:
The Caller's spoken reply to one Challenge, together with how long the Caller took to start speaking.
_Avoid_: answer, turn, utterance

**Signal**:
One measurement taken from a Response: Task Match, Whisper Score, Reply Latency, Spoof Score or Code Match.
_Avoid_: check, feature, metric

**Liveness Score**:
The single number, between 0 and 1, that the Policy derives from all Signals of a Response. Higher means more likely a live human.
_Avoid_: confidence, trust score

### Outcomes

**Verdict**:
The Policy's decision after the Challenges of a Call: PASS, STEP-UP or BLOCK. STEP-UP is never final; it adds one more Challenge or hands over to App Approval.
_Avoid_: result, decision, outcome

**Reason**:
A plain-language sentence attached to a Verdict saying which Signal drove it.
_Avoid_: explanation, log message

**App Approval**:
The fallback where the Caller approves the Request by tapping a prompt on the Registered Device instead of completing voice Challenges.
_Avoid_: in-app confirm, push approval

**Agent Review**:
A hold placed on a PASSed high-value Request until a Bank Agent confirms it.
_Avoid_: manual check, escalation

**Policy**:
The bank-configurable rules that map Requests to Risk Tiers and Signals to a Verdict.
_Avoid_: config, rules engine

**Audit Trail**:
The insert-only, ordered record of everything that happened on a Call.
_Avoid_: log, history

### Attack and measurement

**Clone**:
A synthetic voice generated to imitate a specific Customer.
_Avoid_: deepfake, fake voice

**Eval Run**:
A replay of labelled real and Clone recordings through Verification that measures Catch Rate, False Reject Rate and Added Time.
_Avoid_: benchmark, test run

**Catch Rate**:
The share of Clone Calls that ended in BLOCK.
_Avoid_: accuracy, detection rate

**False Reject Rate**:
The share of real-Customer Calls that did not end in PASS.
_Avoid_: error rate, FRR (in prose)
