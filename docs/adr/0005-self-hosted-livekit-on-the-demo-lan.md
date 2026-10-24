# Self-hosted LiveKit on the demo LAN

Calls run over WebRTC through a LiveKit server in Docker on the GPU laptop, reached over a phone hotspot or local Wi-Fi, instead of LiveKit Cloud or a real phone number. Venue internet is unreliable and telephony needs paperwork and gives 8 kHz audio; a self-hosted server keeps the demo working offline. Moving to a SIP phone line later needs no change to Verification, only a SIP trunk on the LiveKit side (see ADR-0001).
