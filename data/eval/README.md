# Eval Run data

An Eval Run replays labelled recordings through the same Signals and Policy as live Calls and reports **Catch Rate**, **False Reject Rate** and **Added Time** on the Eval page.

## Collect (with consent)

1. Set `RETAIN_AUDIO=true` in `.env` and restart the verifier. Response audio is saved under `data/recordings/<call_id>/`.
2. Place **real** Calls: teammates and volunteers who agreed, answering normally. Aim for about 80 across the three risky Requests, on the mics you will use at the finale.
3. Export them: `pratyaksh-eval export --label real --since 2026-10-29T10:00`
4. Place **Clone** Calls with the attacker tools (`attacker/README.md`), then `pratyaksh-eval export --label clone --since <start of the clone session>`.
5. Set `RETAIN_AUDIO=false` again.

Rows are appended to `data/eval/manifest.csv` (git-ignored). See `manifest.example.csv` for the columns.

## Run

```bash
pratyaksh-eval run data/eval/manifest.csv --label "lab mics, Oct 29"
pratyaksh-eval run data/eval/manifest.csv --policy tuned-policy.yaml --no-save   # try thresholds
pratyaksh-eval run data/eval/manifest.csv --speech scripted                      # use stored transcripts, no GPU
```

Tune `policy.yaml` (weights, `pass_at`, `block_at`, Reply Latency bounds) until Catch Rate is high without raising False Reject Rate, then point `POLICY_PATH` at the tuned file.
