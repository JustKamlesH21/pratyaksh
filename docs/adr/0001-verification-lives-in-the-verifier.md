# Verification state lives in the verifier, not the voice agent

The LiveKit voice agent only moves audio: it plays the prompt it is given, records the Caller's Response, measures Reply Latency and sends both to the verifier. The verifier owns the Call state machine, Challenge planning, Signals, Policy and the Audit Trail, and returns the next prompt each time. We chose this over the usual "logic inside the agent" LiveKit pattern so that one process holds the GPU models, the Console and Bank App see one source of truth, and the whole Verification flow can be tested without LiveKit.
