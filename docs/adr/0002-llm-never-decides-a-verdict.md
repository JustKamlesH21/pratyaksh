# The LLM never decides a Verdict

Challenges are chosen by a scripted state machine and Verdicts come only from the Policy over measured Signals. The LLM (Ollama) is used for two narrow jobs: classifying a Request when keyword rules don't recognise it, and phrasing a short clarifying reply. An LLM-driven conversation would sound more natural, but its Verdicts could not be explained with Reasons, reproduced in an Eval Run, or defended to a bank, so we gave that up.
