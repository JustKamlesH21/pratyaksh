# Pratyaksh design system

What the web app looks and moves like, and why. For engineers changing a screen and for presenters on the projector. The live version is the style guide at **`/design`** (in the nav after Demo): every token, state, component and animation below, rendered from the same CSS, with replay buttons. The source of truth is `web/src/index.css`; this file explains it.

The direction comes from `reports/Pratyaksh demo design brief.md`: the demo is remembered for one beat (the clone ticks green for the whisper, then flips to a full-width red BLOCK because the Possession Code is missing, while the real phone shows the Security Alert). Every choice here serves that beat and the honesty behind it.

## Principles

1. **One thing is large at a time.** On the projector that is the latest Verdict, at the top of the screen. Everything else steps back.
2. **Evidence, not decoration.** A Verdict is a word, a plain Reason, the Signals that landed and what decided it. No hooded hackers, matrix rain, or pulsing "command centre" alerts.
3. **Name the weakness.** The UI never implies the whisper proves identity, and the advisory Spoof Score never looks as if it decided anything.
4. **Colour means one thing.** Green, amber and red mean PASS, STEP-UP and BLOCK. Every state also has an icon shape and a word, so colour is never the only cue.
5. **Motion explains a change.** Something arrived, a decision was made, a measurement came in, something is pending, or a connection is live. Nothing moves for decoration.

## Colour

Defined once in `web/src/index.css` (`@theme static` for light values, `:root[data-theme="dark"]` and the `prefers-color-scheme` block for dark). Dark is the default theme; the header toggle cycles dark, light and system, and a change in one tab reaches the others (the projector window follows the laptop). Cool neutrals sit on one hue (265). Borders are hairlines; there are no drop shadows except one tinted shadow under the landing hero card.

| Token | Dark | Light | Use |
|---|---|---|---|
| `canvas` | `oklch(0.155 0.008 265)` #0b0c10 | `oklch(0.967 0.004 265)` #f3f4f7 | Page |
| `surface` | `oklch(0.2 0.01 265)` #14161b | `oklch(0.991 0.002 265)` #fbfcfd | Cards, panels |
| `sunken` | `oklch(0.235 0.012 265)` #1b1e24 | `oklch(0.95 0.006 265)` #eceef3 | Wells, tracks, chips |
| `line` | `oklch(0.295 0.015 265)` #292d34 | `oklch(0.905 0.008 265)` #dde0e5 | Hairline borders (decorative) |
| `line-strong` | `oklch(0.52 0.018 265)` #646974 | `oklch(0.64 0.016 265)` #878c96 | Input and select borders (3:1) |
| `ink` | `oklch(0.95 0.006 265)` #eceef3 | `oklch(0.21 0.012 265)` #16181e | Text |
| `ink-soft` | `oklch(0.735 0.018 265)` #a4a9b5 | `oklch(0.47 0.02 265)` #555b66 | Secondary text |
| `accent` | `oklch(0.72 0.13 268)` #82a1f6 | `oklch(0.49 0.19 265)` #2954ca | Actions, focus, selection, the bank's voice |
| `on-accent` | `oklch(0.155 0.008 265)` | `oklch(0.991 0.002 265)` | Text on accent (and on pass / block used as a button fill) |
| `pass` / `stepup` / `block` | `oklch(0.78 0.14 162)` #51d39c, `oklch(0.81 0.13 80)` #edb755, `oklch(0.73 0.15 27)` #f87f73 | `oklch(0.495 0.105 160)` #14744d, `oklch(0.505 0.105 68)` #8b570f, `oklch(0.525 0.18 28)` #bc2e27 | Verdict text, icons, thin marks, tinted chips (`bg-pass/12`) |
| `pass-fill` / `stepup-fill` / `block-fill` | `oklch(0.5 0.11 158)` #14764a, `oklch(0.51 0.105 62)` #90561a, `oklch(0.515 0.165 27)` #b3332e | `oklch(0.45 0.105 158)` #01663e, `oklch(0.47 0.1 62)` #824c11, `oklch(0.48 0.165 27)` #a72724 | Solid Verdict surfaces: Verdict Ribbon, call end screen |
| `on-fill` | `oklch(0.985 0.003 265)` #f9fafc | same | Text on the solid fills |
| `bezel` | `oklch(0.215 0.008 265)` #18191d | same | The Bank App phone frame (dark in both themes) |

Role tokens point at the palette so a role can move without a hunt through pages:

| Role | Points at | Rule |
|---|---|---|
| `advisory` | `ink-soft` | The Spoof Score. Never pass or block, never "ok/low". |
| `turn-bank` | `accent` | Call screen: the Voice Agent is speaking. |
| `turn-you` | `ink` | Call screen: your turn, with a solid microphone icon. |
| `turn-wait` | `ink-soft` | Call screen: connecting or checking, with a spinner. |

**Where Verdict colours may appear:** Verdicts and Outcomes (badges, Ribbon, end screen), Signal ticks on the Ribbon (a met Signal is green, a missed one red, as the brief's beat needs), the deciding Signal on the Console, Voice Pause and Security Alerts (consequences of a BLOCK), and system checks that are pass/fail by nature (Ready, Audit Trail intact, signature valid). **Never** for turn cues, live indicators (accent), the advisory Spoof Score, Approve buttons (an action, so accent), or handing a Call to an officer (neutral). Errors and the 72 px Hang up stay red as universal conventions.

### Contrast (WCAG 2.x)

`node web/scripts/contrast.mjs` reads the values straight from `index.css` and checks every pair the UI uses in both themes; it exits 1 if any falls below AA (4.5:1 text, 3:1 controls and large text). `--md` prints the full 72-row table. Tints are mixed in OKLab as Tailwind's `color-mix(in oklab, ...)` does. Results on Oct 28:

| Pair | Dark | Light |
|---|---|---|
| `ink` on `canvas` / `surface` / `sunken` | 16.89 / 15.65 / 14.41 | 16.11 / 17.27 / 15.31 |
| `ink-soft` on `canvas` / `surface` / `sunken` | 8.32 / 7.71 / 7.10 | 6.21 / 6.66 / 5.90 |
| `accent` on `canvas` / `surface` / `sunken` | 7.76 / 7.19 / 6.62 | 5.96 / 6.39 / 5.66 |
| `pass` on `canvas` / `surface` / `sunken` | 10.36 / 9.59 / 8.84 | 5.28 / 5.66 / 5.02 |
| `stepup` on `canvas` / `surface` / `sunken` | 10.70 / 9.91 / 9.13 | 5.47 / 5.87 / 5.20 |
| `block` on `canvas` / `surface` / `sunken` | 7.67 / 7.11 / 6.55 | 5.37 / 5.76 / 5.11 |
| `pass` / `stepup` / `block` on their own 12% tint | 7.94 / 8.17 / 6.07 | 4.77 / 4.93 / 4.85 |
| `accent` on `accent/12` (selected nav, chips) | 6.13 | 5.35 |
| `on-accent` on `accent` / `pass` / `block` | 7.76 / 10.36 / 7.67 | 6.39 / 5.66 / 5.76 |
| `on-fill` on `pass-fill` / `stepup-fill` / `block-fill` | 5.44 / 5.67 / 5.86 | 6.76 / 6.73 / 6.82 |
| `line-strong` on `surface` / `canvas` (controls, 3:1) | 3.29 / 3.55 | 3.28 / 3.06 |
| `accent` focus ring on `canvas` (3:1) | 7.76 | 5.96 |

Lowest margins are the light tinted chips (4.77) and light `line-strong` on `canvas` (3.06). Don't lighten those tokens without re-running the script. The projector may wash colours out: run the greyscale and back-row check at rehearsal before changing values.

## Typography

| Face | Use | Rules |
|---|---|---|
| Bricolage Grotesque (display, `font-display`) | Headlines, the Verdict word, the Whisper Phrase | 24 px and up only; weight 600 to 700; tracking -0.02 to -0.03em. Nothing at 300 or lighter on the projector. |
| Geist (`font-sans`) | All UI text | 15 to 16 px body; Console mostly 13 to 15 px. |
| Geist Mono (`font-mono`) | Scores, codes, timers, IDs, hashes | Tabular figures (set globally on `body`, and on `.font-mono`), so live numbers do not jitter. |
| Noto Sans Devanagari / Kannada | Hindi and Kannada, by fallback | The regular families, not the "UI" cuts. Bundled offline. |

Scale: Tailwind's `text-xs` 12, `sm` 14, `base` 16, `lg` 18, `2xl` 24, `3xl` 30, `5xl` 48, `7xl` 72, plus three tokens: `text-phrase` (`clamp(2rem, 9vw, 2.5rem)`, the Whisper Phrase on the phone), `--text-ribbon` (`clamp(6rem, 8vw, 9rem)`, the Verdict word on stage) and `--text-ribbon-compact` (`clamp(2.75rem, 5vw, 4rem)`, on a laptop).

### Indic rules

- **Every element that shows Hindi or Kannada carries `lang="hi"` or `lang="kn"`.** For dynamic text use `scriptLang(text)` from `components.tsx` (it detects Devanagari or Kannada letters; mixed Hindi and English counts as Hindi). Done today for: call captions, the Whisper Phrase (call screen, hub, Ribbon, Console), Console Transcript lines and chips, language chips, landing examples and the footer.
- `[lang="hi"]` gets line-height 1.65, `[lang="kn"]` 1.75; headings and `.font-display` inside them 1.3 / 1.35 at weight 700 (Bricolage has no Indic glyphs, so Noto at 700 carries the display weight).
- `:lang(hi), :lang(kn)`: no letter-spacing (tracking breaks the shirorekha), no italics, no text-transform; links get a bottom border instead of an underline.
- An inline Indic run inside Latin text (`<span lang="hi">`) is set 10% larger (Kannada 5%) so its body matches Geist. This rule is in the base layer, so an explicit `text-*` on the same span wins.
- Use international digits inside Indic text. Format money with `Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", numberingSystem: "latn" })`.
- Clipping traps: `truncate`, `line-clamp`, `overflow: hidden`, fixed-height chips and `background-clip: text` cut matras and Kannada subscripts. Test any new Indic surface with the tallest strings (ि / ी with ु / ृ; Kannada conjuncts such as ಸ್ತ್ರೀ).
- Product copy in Hindi or Kannada is written or checked by a native-speaker teammate, never machine-translated.

## Spacing, radius, layers

- Tailwind's 4 px spacing scale. Page gutter 16 px (`px-4`), `max-w-7xl` content width except in stage mode (full width).
- Radius: cards `rounded-xl`, landing tiles and the Ribbon `rounded-2xl`, controls `rounded-lg`, badges and chips `rounded-full`, the phone frame `rounded-[2.2rem]`.
- Hairline `border-line` separates; `ring-2` in the tone colour marks the active hub tile. z-index only for the sticky header (`z-30`) and the Reset note (`z-10`).

## Components

| Component | Where | Notes |
|---|---|---|
| `VerdictBadge` | `components.tsx` | Tinted chip, icon + word (PASS, STEP-UP, BLOCK). Pops in once. |
| `Meter` | `components.tsx` | One Signal against its threshold. A missed threshold is `block`, a met one stays neutral. `advisory` (Spoof Score): neutral bar, no threshold mark, no ok/low, tagged "advisory · flags some real whispers, not used in the Verdict". `value={null}` draws a hatched "not measured" track, never a silent zero. |
| Verdict Ribbon | `DemoPage.tsx` `VerdictRibbon` | The hub's top band. Idle: "Waiting for a Call". Live: neutral surface, the Request, the current Challenge (Whisper Phrase shown; Possession Code "on Meera's phone"). Signal ticks land in order (Task Match, Whisper Score, Reply Latency, Code Match), the Spoof Score set apart with a dashed outline and "advisory". Verdict: solid fill, PASS / STEP-UP / BLOCKED at the ribbon size with a fill icon, one plain sentence, "Decided by", Liveness. Holds the last Verdict until the next Call starts. `aria-live="polite"`. |
| Verdict logic | `verdict.ts` | `decidedBy`, `headline`, `signalTicks`, `isVoicePauseRefusal`. Built only from the Policy's own Reasons and the measured Signals, so the screen shows only what fired. |
| Conclusion block | `ConsolePage.tsx` `Conclusion` | Top of a decided Call: Verdict word (text-3xl), one plain sentence, Decided by, authentication factors (Possession, Inherence/liveness) tagged "Aligned to RBI Authentication Directions 2025". Never "certified", no logos. BLOCK rows in the Calls list get a 2 px `block` left edge, not a red fill. |
| Bank App | `BankAppPage.tsx` | Phone frame in `bezel`. Possession Code card: "Code for your call with the bank", the Request, digits in Geist Mono 2.25rem grouped 3 + 3, the anti-relay line ("Read it aloud only if *you* are on this call right now. If someone asks you for this code, it's a scam."). `maskCodes` (stage mode) renders "••• •••, Shown only on Meera's phone" and never puts the digits in the page. Security Alert: no "never share codes" line (it contradicted reading the code out); adds "If a caller says this check is 'not working', hang up." Approve is accent, Decline is block-outlined. |
| Call screen | `CallerPage.tsx` | Header status: "Your bank · verifying you" (ink-soft) until a Verdict, then "Verified call" (pass) or "Not verified" (block). Turn orb uses the turn tokens and changes shape: voice bars + mic-slash "Bank is speaking, please wait"; solid microphone "Your turn"; spinner "Checking…". Whisper Phrase at `text-phrase`, word-by-word reveal, tag "Speak softly, close to the phone". Captions 18 px with a Bank / You speaker chip and icon on every line. End screen: 96 px icon whose shape differs per outcome (check, X circle, headset) on a solid fill, then a single Done (no "Call again" where the thumb just pressed Hang up). Hang up stays alone, 72 px, padded `calc(1rem + env(safe-area-inset-bottom))`. One stable hidden audio host sits outside the per-status trees so the agent's `<audio>` never remounts. |
| Voice Pause row | `DemoPage.tsx` `VoicePause` | Lock icon (closed, block) with scrim fade and shackle drop when on; open lock, neutral when off. "Lift Voice Pause" (strong neutral button) hidden on stage. |

## Motion

All keyframes and motion classes live in `index.css`. Only `transform` and `opacity` animate. Expressive motion is reserved for the Verdict and the Security Alert; everything else is productive.

Tokens: `--dur-press` 100 ms, `--dur-fast` 150, `--dur-quick` 200, `--dur-normal` 280, `--dur-emphasis` 400, `--dur-ring` 600, `--dur-glow` 700, `--dur-loop` 900, `--dur-sweep` (280, or 400 in stage mode), `--stagger` 50.
Easing (`ease-*` utilities): `arrive` cubic-bezier(0.05, 0.7, 0.1, 1) (M3 emphasized decelerate), `leave` (0.3, 0, 0.8, 0.15), `std` (0.2, 0, 0, 1), `firm` (0, 0, 0.3, 1) (Carbon expressive entrance), `loop` (0.33, 0, 0.67, 1), `spring` = `linear(0, 0.22 8%, 0.6 18%, 0.9 30%, 1.04 42%, 1.05 50%, 1.01 65%, 0.995 80%, 1)` for scale only.

| Name (class) | Duration · easing | Purpose | Reduced motion |
|---|---|---|---|
| `enter` (`.motion-enter`) | 280 ms · arrive, 45 ms stagger | A list item, panel or Transcript line arrived | 1 ms |
| `pop` (`.motion-pop`) | 280 ms · arrive | A badge appears | 1 ms |
| `grow` (`.motion-grow`) | 600 ms · arrive | A Signal meter fills (scaleX) | 1 ms |
| Ribbon sweep, BLOCK (`.ribbon[data-verdict]::before`, `.ribbon-word`) | 280 ms laptop / 400 ms stage · firm | Fill sweeps in from the left; word rises 8 px. No bounce, no shake | 150 ms opacity crossfade |
| Ribbon sweep, PASS (`.ribbon-icon-spring`) | sweep · arrive; icon 400 ms · spring | Icon scales from 0.6 with 5% overshoot; opacity never overshoots | 150 ms crossfade |
| `tick` (`.tick`, `.tick-mark`) | 150 ms · std; mark 200 ms after 150 ms | A Signal landed on the Ribbon. Stage dwell: at least 450 ms between ticks (the Console keeps true timestamps); the Verdict waits for the last tick | 1 ms, no dwell |
| `ring-once` (`.ring-once`) | 600 ms · arrive, once | The active hub tile when its Call starts or gets its Verdict ("Meera's tile flashes red once") | none |
| `alert-in` + `glow` (`.alert-in`) | 400 ms · arrive; glow 700 ms × 2 after 400 ms | The Security Alert drops in, then a pseudo-element ring glows twice | 150 ms crossfade |
| Voice Pause scrim + `shackle` (`.pause-scrim`, `.shackle`) | 700 ms; 150 ms · std | Voice Pause turns on | 1 ms |
| `word` (`.word`) | 200 ms each, 50 ms stagger · arrive | Whisper Phrase word by word, under 800 ms | 1 ms |
| `fade` (`.motion-fade`, `LiveNumber`) | 150 ms · std | A live number changed: crossfade, never roll digits | 1 ms |
| Tile dim (`.tile.is-dim`) | 400 ms · std (transition) | Stage: the other Customers step back to 55% | 1 ms |
| `voice`, `breathe` (`.voice-bars.is-active`, `.speaking-ring.is-active`) | 900 ms alternate · loop | Someone is speaking right now | Loops stop; static bars at mid height |
| `live` (`.live-dot`) | 2 s · arrive, infinite | A live connection or Call | Stops |
| `spin` (`.spinner`) | 900 ms per turn · linear | Checking a Response | Stops |
| `typing` (`.typing`) | 1.2 s · loop | The Voice Agent is about to speak (Console) | Stops |
| `shimmer` (`.skeleton::after`) | 1.4 s · loop | Loading | Stops |
| `.press` | 100 ms · std (transition) | scale(0.98) while pressed | 1 ms |
| Landing `lp-rise`, `lp-slide`, `lp-line`, `lp-digit`, `.reveal` | 360 to 900 ms · arrive | Hero plays a blocked Call; steps reveal as they scroll in | Content shown at once |

**Reduced motion** (OS setting, or `html[data-motion="reduce"]` from the switch on `/design`, remembered in `localStorage` and applied before first paint): every animation and transition is shortened to 1 ms with one iteration, rather than removed, so it ends in its final state and `animationend` still fires. The Verdict Ribbon and the Security Alert keep a 150 ms opacity crossfade. Hidden start states (scroll reveals) exist only when motion is allowed. JS checks `prefersReducedMotion()` (both sources) to skip the Ribbon's tick dwell.

**Never:** shake on BLOCK, infinite pulses on alerts, odometer number rolls, `filter: blur()` reveals, animated `box-shadow`, colour or opacity overshoot, anything over three flashes per second.

## Stage mode

`/demo?stage=1` on the projector and `/console?stage=1` for the Console beat (`?stage=small` for a 1280x800 projector at 112.5%).

- `html[data-stage]` sets `font-size: 125%`, so every rem scales; the nav header is hidden and the page runs full width with a 16 px gutter.
- Hub: no page intro, pairing links, "Call as" buttons, Reset or Lift Voice Pause. The Verdict Ribbon fills the top third (min-height 15rem, footer "Live: Calls, Verdicts, phones / Pre-generated: clone audio (IndicF5, consented reference)"). The Customer on the latest Call keeps a 2 px ring in its tone; the others fade to 55%. Per-tile CallState is folded into the Ribbon. Possession Codes on the mirrored Bank Apps are masked.
- Console: opens the newest decided Call by itself, Conclusion block on top.
- Theme: changing it on the laptop tab changes the projector window too (shared storage). Dark is the default; switch to light if the hall is bright.
- Set Windows to Extend: the projector shows `/demo?stage=1`, the laptop keeps the attacker tab, the non-stage hub (Reset) and the backup video.

## Copy rules

- Use `CONTEXT.md` words exactly: Customer, Caller, Call, Request, Whisper Phrase, Possession Code, Signal, Verdict, Reason, Security Alert, Voice Pause, Registered Device, Bank Agent, Audit Trail. Never "OTP" for the Possession Code, "check" for a Signal, "user", "session", "lockout" or "deepfake" in the UI.
- **No em-dashes or en-dashes** in visible text, including ranges ("60% to 98%"). Use a period, comma, colon or parentheses. A middle dot (`·`) at most once per line.
- Show only Reasons that actually fired, in the Policy's own words (`verdict.ts` strips the "Challenge 2 (Possession Code):" label and names the Customer).
- Never claim more than the data: no "secure line" or "verified" before a PASS, no "the whisper proves identity", no "voice clones cannot whisper", no "100%", no "certified", no real bank, RBI or NPCI names or logos, no numbers not read from the running backend or labelled with their sample and date.
- Hindi and Kannada product copy comes from a native speaker.

## Do and don't

| Do | Don't |
|---|---|
| Add a token to `index.css`, then use the utility | Hard-code a hex, `zinc-*`, `white` or `black` in a page |
| Pair every state colour with an icon shape and a word | Use green, amber or red for turns, live states or the Spoof Score |
| Put `lang` on Indic text (`scriptLang`) | Track, italicise, uppercase or truncate Indic text |
| Animate `transform` and `opacity`, with a named keyframe | Add a loop that is not a real live state |
| Re-run `node web/scripts/contrast.mjs` after a colour change | Lighten `ink-soft` or the light Verdict colours by eye |
| Check `/design` in both themes and with Reduce motion on | Ship a screen you have only seen in one theme |
| Keep Hang up alone in the thumb zone | Put "Call again" where Hang up was |
