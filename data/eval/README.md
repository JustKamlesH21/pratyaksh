# Eval Run data

An Eval Run replays labelled recordings through the same Signals and Policy as live Calls and reports **Catch Rate**, **False Reject Rate** and **Added Time** on the Eval page. Rates are shown as x/n with a Wilson 95% confidence interval: with 20 Calls, 20/20 still only says "at least 84%".

## Calibrate the Whisper Score first (Oct 28)

Record short WAVs from the calibration speakers into one folder per class, e.g.

```
data/eval/calibration/whisper/  normal/  soft/  silence/  noise/  clone/
```

```bash
pratyaksh-eval calibrate data/eval/calibration/                    # per-class n, min, median, max + suggested range
pratyaksh-eval calibrate data/eval/calibration/ --exclude noise    # leave a class out of the threshold
pratyaksh-eval calibrate data/eval/manifest.csv                    # or an exported manifest (real phrase = whisper,
                                                                   # real code readout = normal, Clone = clone)
```

Put each speaker's WAVs in their own folder under the class (`whisper/kamlesh/1.wav`) so the calibration speakers are recorded. It writes `calibration.html` (a dot plot, no internet needed) next to the source and suggests a `whisper_score.min` with zero false accepts where the data allow it. It never changes `policy.yaml`: agree the number with the team lead, then change it with a test. The Eval Run speakers should be different people from the calibration speakers: export with `--speaker <name>` and run with `--calibration data/eval/calibration/`, which warns (and shows it on the Eval page) when a speaker appears in both.

## Collect (with consent)

1. Set `RETAIN_AUDIO=true` in `.env` and restart the verifier. Response audio is saved under `data/recordings/<call_id>/`.
2. Place **real** Calls: teammates and volunteers who agreed, answering normally. Target 20 (at least 10) across the risky Requests, on the mics you will use at the finale.
3. Export them: `pratyaksh-eval export --label real --since 2026-10-29T10:00 --language kn`
   Replay about 5 of them through the virtual cable and export those with `--channel cable`: a channel control for the Clone Calls, which also arrive through the cable.
4. Place **Clone** Calls with the attacker tools (`attacker/README.md`), target 20 (at least 10), then
   `pratyaksh-eval export --label clone --since <start> --condition code_withheld` (attacker has no phone) or
   `--condition code_supplied` (attacker read the right Possession Code, so the voice Signals are measured on their own).
5. Set `RETAIN_AUDIO=false` again.

Rows are appended to `data/eval/manifest.csv` (git-ignored). See `manifest.example.csv` for the columns. Optional columns `condition` (code_withheld | code_supplied; blank = inferred from Code Match), `channel` (mic | cable; blank = mic), `language` and `hearing_ms` can be added to older manifests by hand.

## Run

```bash
pratyaksh-eval run data/eval/manifest.csv --label "lab mics, Oct 29"
pratyaksh-eval run data/eval/manifest.csv --policy tuned-policy.yaml --no-save   # try thresholds
pratyaksh-eval run data/eval/manifest.csv --speech scripted                      # use stored transcripts, no GPU
```

The report gives Catch Rate per condition, False Reject and Catch Rate per channel and language, which Signals caught each Clone BLOCK, Added Time per real Call (median, p95, max) and hearing time per Response.

Tune `policy.yaml` (weights, `pass_at`, `block_at`, Reply Latency bounds) until Catch Rate is high without raising False Reject Rate, then point `POLICY_PATH` at the tuned file.
