---
version: 2
name: Pratyaksh
description: >
  Voice-clone-resistant verification for bank Calls. A calm, evidence-first banking surface: deep bank navy
  and white, tonal depth, pill controls, one accent, and Verdict colours that mean only PASS, STEP-UP, BLOCK.
colors:
  light:
    canvas: "#f2f4f7"
    surface: "#fbfcfd"
    sunken: "#ebeff2"
    line: "#dce0e5"
    line-strong: "#858d96"
    ink: "#14191e"
    ink-soft: "#535c66"
    accent: "#174a92"
    on-accent: "#fbfcfd"
    brand: "#173a76"
    brand-red: "#f84c41"
    on-fill: "#f9fafc"
    pass: "#14744d"
    stepup: "#8b570f"
    block: "#bc2e27"
    pass-fill: "#01663e"
    stepup-fill: "#824c11"
    block-fill: "#a72724"
    bezel: "#171a1d"
  dark:
    canvas: "#0a0d10"
    surface: "#13161a"
    sunken: "#1a1f24"
    line: "#272d34"
    line-strong: "#616a73"
    ink: "#ebeff2"
    ink-soft: "#a1aab4"
    accent: "#91c2fa"
    on-accent: "#0a0d10"
    brand: "#173a76"
    brand-red: "#f84c41"
    on-fill: "#f9fafc"
    pass: "#51d39c"
    stepup: "#edb755"
    block: "#f87f73"
    pass-fill: "#14764a"
    stepup-fill: "#90561a"
    block-fill: "#b3332e"
typography:
  display: { fontFamily: "Bricolage Grotesque", fontWeight: 600, letterSpacing: "-0.02em", fontVariation: "opsz auto" }
  display-numeral: { fontFamily: "Bricolage Grotesque", fontWeight: 500, letterSpacing: "-0.035em" }
  h1-page: { fontFamily: "Bricolage Grotesque", fontSize: "36px", fontWeight: 600, lineHeight: 1.1, letterSpacing: "-0.02em" }
  h2-section: { fontFamily: "Bricolage Grotesque", fontSize: "48px", fontWeight: 600, lineHeight: 1.08, letterSpacing: "-0.02em" }
  body: { fontFamily: "Geist", fontSize: "16px", fontWeight: 400, lineHeight: 1.6 }
  ui: { fontFamily: "Geist", fontSize: "14px", fontWeight: 600, lineHeight: 1 }
  eyebrow: { fontFamily: "Geist Mono", fontSize: "12px", fontWeight: 500, letterSpacing: "0.08em", textTransform: uppercase }
  mono: { fontFamily: "Geist Mono", fontFeature: "tnum" }
  verdict-stage: { fontFamily: "Bricolage Grotesque", fontSize: "clamp(6rem, 8vw, 9rem)", fontWeight: 700, lineHeight: 0.95 }
rounded:
  pill: 9999px
  card: 16px
  well: 12px
  phone: 2.2rem
spacing:
  base: 4px
  gutter: 16px
  card-padding: 20px
  section: 80px to 112px
  container: 1280px
components:
  btn-primary: { background: accent, color: on-accent, rounded: pill, height: 40px, padding: "0 18px" }
  btn-quiet: { background: surface, color: ink, border: "1px line (inset)", rounded: pill }
  btn-danger: { background: surface, color: block, border: "1px block/45 (inset)", rounded: pill }
  btn-strong: { background: ink, color: canvas, rounded: pill }
  field: { background: surface, border: "1px line-strong", rounded: well, height: 44px }
  card: { background: surface, border: "1px line", rounded: card, padding: 20px, elevation: 1 }
  brand-band: { background: brand, color: on-fill }
---

# Pratyaksh design system

What the web app looks and moves like, and why. For engineers changing a screen and for presenters on the projector. Tokens live in `frontend/src/index.css`; this file explains them. The YAML above follows the [DESIGN.md format](https://github.com/google-labs-code/design.md) so a design or coding agent can read the system directly.

## Overview

**Design read:** a trust-first banking product shown to judges and bank decision-makers. Calm and exact, not "command centre". It leans on fintech references and stays restrained: one accent, tonal depth, evidence over decoration.

The demo is remembered for one beat. The Clone ticks green for the whisper, then flips to a full-width red BLOCK because the Possession Code is missing, while the real phone shows the Security Alert. Every choice here serves that beat and the honesty behind it.

1. **One thing is large at a time.** On the projector that is the latest Verdict, at the top of the screen. Everything else steps back.
2. **Evidence, not decoration.** A Verdict is a word, a plain Reason, the Signals that landed and what decided it. No hooded hackers, matrix rain or pulsing alerts.
3. **Name the weakness.** The UI never implies the whisper proves identity, and the advisory Spoof Score never looks as if it decided anything.
4. **Colour means one thing.** Green, amber and red mean PASS, STEP-UP and BLOCK. Every state also has an icon shape and a word.
5. **Motion explains a change.** Nothing moves for decoration.

### What we took from the references (Oct 30)

| From | Element | Where it shows |
|---|---|---|
| Kotak Mahindra Bank's app and brand (navy, red and white) | Deep **bank navy** as the accent, and a navy **brand band** on the bank's own surfaces | Bank App header, phone frames, every action |
| [Mercury DESIGN.md](https://getdesign.md/mercury/design-md) | Depth by colour step rather than shadow; **eyebrow labels**; **stat blocks** (big light numeral, small caption); only one solid primary per group; secondaries as quiet pills | Cards, section indexes, landing and Eval numbers, button groups |
| [Stripe DESIGN.md](https://getdesign.md/stripe/design-md) | Two **tinted shadow** levels (never pure black); **all buttons are pills**; tabular figures on every number; input focus border in the accent | `.elev-1` / `.elev-2`, `.btn`, `.field` |
| [Fintech trust patterns](https://phenomenonstudio.com/article/fintech-ux-design-patterns-that-build-trust-and-credibility/), [banking UI 2026](https://lollypop.design/blog/2026/june/banking-app-ui-design/) | Show the reason for every decision; consistent layout across screens; plain security cues instead of fear | Reasons on every Verdict, PageHeader on every staff page |

**Kept from Kotak, changed on purpose:** Kotak uses red for its actions. Here red means BLOCK, so actions are navy, and Kotak's red lives on as `brand-red`: a thin line in the logo, the eyebrows and the timeline, never something you press or read as a result. A red Approve button beside a red BLOCK would blur the one beat the demo depends on. We use no Kotak name, logo or wordmark (see Copy rules); the palette is an inspiration, not an imitation.

## Colors

Tokens are defined once in `frontend/src/index.css` (`@theme static` for light, `:root[data-theme="dark"]` and the `prefers-color-scheme` block for dark). Dark is the default theme. The header toggle cycles dark, light and system, and a change in one tab reaches the others, so the projector follows the laptop. Neutrals sit on one cool hue (250).

| Token | Dark | Light | Use |
|---|---|---|---|
| `canvas` / `surface` / `sunken` | #0a0d10 / #13161a / #1a1f24 | #f2f4f7 / #fbfcfd / #ebeff2 | Page, cards, wells. One tonal step apart: this is the main depth cue |
| `line` / `line-strong` | #272d34 / #616a73 | #dce0e5 / #858d96 | Hairlines (decorative) / control borders (3:1) |
| `ink` / `ink-soft` | #ebeff2 / #a1aab4 | #14191e / #535c66 | Text / secondary text |
| `accent` | `oklch(0.8 0.095 252)` #91c2fa | `oklch(0.42 0.13 258)` #174a92 | Bank navy: actions, focus, selection, the bank's voice. Dark uses a light navy because deep navy disappears on a dark canvas |
| `brand` | #173a76 (both) | #173a76 | The bank's own band, under `on-fill` text: Bank App header, phone frames, the landing page's navy sections, the logo tile. Deep navy in both themes, like a real bank app |
| `brand-red` | `oklch(0.66 0.21 28)` #f84c41 (both) | same | Kotak-style brand red, **for marks only**: the logo's centre line, the rule in every eyebrow, the How it works timeline, the stroke under "voice". 3.1:1 on canvas and 3.2:1 on navy: enough for a mark, not for text. Never text, never a button, never a state |
| `pass` / `stepup` / `block` | #51d39c / #edb755 / #f87f73 | #14744d / #8b570f / #bc2e27 | Verdict text, icons, thin marks, tinted chips |
| `*-fill` | #14764a / #90561a / #b3332e | #01663e / #824c11 / #a72724 | Solid Verdict surfaces (Ribbon, end screen) under `on-fill` |
| `bezel` | #171a1d | same | The phone frame, dark in both themes |

Role tokens point at the palette: `advisory` → `ink-soft` (Spoof Score, never pass or block), `turn-bank` → `accent`, `turn-you` → `ink`, `turn-wait` → `ink-soft`.

**Where Verdict colours may appear:** Verdicts and Outcomes, Signal ticks on the Ribbon, the deciding Signal on the Console, Voice Pause and Security Alerts, and system checks that are pass/fail by nature (Ready, Audit Trail intact, signature valid). **Never** for turn cues, live indicators (accent), the Spoof Score, Approve buttons (an action, so accent) or handing a Call to an officer (neutral). Errors and Hang up stay red by convention.

### Contrast (WCAG 2.x)

`node frontend/scripts/contrast.mjs` reads the values from `index.css` and checks every pair the UI uses in both themes. It exits 1 if any pair falls below AA (4.5:1 text, 3:1 controls and large text); `--md` prints the full table. Results on Oct 30, after the navy change:

| Pair | Dark | Light |
|---|---|---|
| `ink` on `canvas` / `surface` / `sunken` | 16.89 / 15.64 / 14.40 | 16.10 / 17.26 / 15.31 |
| `ink-soft` on `canvas` / `surface` / `sunken` | 8.33 / 7.72 / 7.11 | 6.19 / 6.64 / 5.89 |
| `accent` on `canvas` / `surface` / `sunken` | 10.50 / 9.73 / 8.96 | 7.81 / 8.37 / 7.42 |
| `accent` on `accent/12` (selected chips) | 8.04 | 6.83 |
| `on-accent` on `accent` | 10.50 | 8.37 |
| `on-fill` on `brand` / on `on-fill/15` over `brand` | 10.55 / 7.06 | 10.55 / 7.06 |
| `pass` / `stepup` / `block` on their own 12% tint | 7.93 / 8.16 / 6.06 | 4.77 / 4.93 / 4.85 |
| `on-fill` on `pass-fill` / `stepup-fill` / `block-fill` | 5.44 / 5.68 / 5.86 | 6.76 / 6.73 / 6.82 |
| `line-strong` on `surface` / `canvas` (3:1) | 3.29 / 3.55 | 3.27 / 3.05 |

The tightest margins are the light tinted Verdict chips (4.77) and light `line-strong` on `canvas` (3.05). Re-run the script after any colour change. The projector may wash colours out, so do the greyscale and back-row check at rehearsal.

## Typography

| Face | Use | Rules |
|---|---|---|
| Bricolage Grotesque (`font-display`) | Headlines, the Verdict word, the Whisper Phrase, big numerals | 24 px and up only. Headings 600 to 700, tracking -0.02 to -0.03em. **Display numerals** (landing stats, Eval stats) at 500 with -0.035em: lighter and calmer, after Mercury's stat blocks. The Verdict word stays 700. |
| Geist (`font-sans`) | All UI text | 15 to 16 px body; the Console mostly 13 to 15 px. Buttons 14 px / 600. |
| Geist Mono (`font-mono`) | Scores, codes, timers, IDs, hashes, **eyebrows** | Tabular figures everywhere (set on `body`), so live numbers do not jitter. |
| Noto Sans Devanagari / Kannada | Hindi and Kannada, by fallback | Regular families, bundled offline. |

**Eyebrow** (`.eyebrow`): 12 px Geist Mono, 500, uppercase, +0.08em, `ink-soft`, with an optional `<b>` index in the accent and a 24 px rule (`01`, a short rule, `THE THREAT`). It sits above every landing section heading and every staff page title. It is Latin only: never put Hindi or Kannada in an eyebrow.

Scale: Tailwind's `text-xs` 12, `sm` 14, `base` 16, `lg` 18, `2xl` 24, `3xl` 30, `4xl` 36, `5xl` 48, `7xl` 72, plus `text-phrase` (`clamp(2rem, 9vw, 2.5rem)`), `--text-ribbon` (`clamp(6rem, 8vw, 9rem)`) and `--text-ribbon-compact` (`clamp(2.75rem, 5vw, 4rem)`).

### Indic rules

- **Every element that shows Hindi or Kannada carries `lang="hi"` or `lang="kn"`.** For dynamic text use `scriptLang(text)` from `components.tsx`.
- `[lang="hi"]` gets line-height 1.65 and `[lang="kn"]` 1.75. Headings inside them get 1.3 / 1.35 at weight 700 (Bricolage has no Indic glyphs).
- `:lang(hi), :lang(kn)`: no letter-spacing, no italics, no text-transform. Links get a bottom border instead of an underline.
- An inline Indic run inside Latin text is set 10% larger (Kannada 5%).
- Use international digits. Format money with `Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", numberingSystem: "latn" })`.
- Clipping traps: `truncate`, `line-clamp`, `overflow: hidden`, fixed-height chips, `background-clip: text`. Test with the tallest strings.
- Hindi and Kannada product copy is written or checked by a native speaker, never machine-translated.

## Layout

- Tailwind's 4 px spacing scale. Page gutter 16 px, `max-w-7xl` content, full width in stage mode.
- **Staff pages** (Demo, Deepfake, Console, Eval) open with `PageHeader`: eyebrow (what kind of page), title, one line on what it is for, actions on the right with at most one solid button. A hairline separates it from the content.
- **Landing** sections are numbered 01 to 06 with eyebrows so the page reads as one argument: threat, how it works, the honest limit, safeguards, evidence, adoption. Sections breathe 80 to 112 px apart.
- **Phone screens** (`/call`, `/bank`) own the whole viewport, with no site header: `100dvh`, safe areas padded, the main action in a bottom dock in the thumb zone.
- The app header is 64 px. Navigation is a **segmented pill track** (`bg-sunken`, ring hairline). The current page is an `accent/15` pill with a filled icon; the others are `ink-soft`.

## Elevation & Depth

Depth is **tonal first**: canvas, surface and sunken are one colour step apart, so a card lifts off the page by fill and hairline. Shadows appear only where a layer really floats, and are tinted to the neutral hue (never pure black on light).

| Level | Light | Dark | Use |
|---|---|---|---|
| 0 | flat | flat | Page sections, wells |
| 1 (`.elev-1`) | `0 1px 2px` + `0 1px 3px`, hue-250 ink at 6 to 8% | 1 px top highlight, white at 4% | Cards, the idle Verdict Ribbon, Eval stats |
| 2 (`.elev-2`) | `0 2px 6px -2px` + `0 24px 48px -20px`, ink at 8 to 22% | top highlight + deep tinted drop | Floating things: the decided Ribbon, the landing hero's Verdict card, toasts |

`.elev-*` and Tailwind's `ring-*` both set `box-shadow`, so the later one wins. Pair elevation with `border`, not `ring`. z-index is used only for the sticky header (`z-30`) and the Reset note (`z-10`).

## Shapes

One rule, used everywhere:

| Shape | Radius | What |
|---|---|---|
| Pill | full | Everything you press: buttons, nav and tab pills, chips, badges, live pills, compact fields inside wells |
| Card | 16 px (`rounded-2xl`) | Cards, hub tiles, the Ribbon, Bank App messages |
| Well / field | 12 px (`rounded-xl`) | Wells inside cards, form fields, error notes, list rows |
| Phone | `2.2rem` | The drawn phone frame; the Bank App's navy band rounds its bottom at `1.75rem` |
| Logo tile | 30% | The waveform mark |

## Components

| Component | Where | Notes |
|---|---|---|
| `.btn` + `.btn-primary` / `-quiet` / `-ghost` / `-strong` / `-danger`, sizes `-sm` (32) / default (40) / `-lg` (48) | `index.css` components layer | Pills. Hover crossfades colour only (150 ms); press scales to 0.98. `.btn-primary` hover mixes the accent toward `ink`, so `on-accent` text only gains contrast. **One `.btn-primary` per group.** `.btn-strong` is for operator actions that are not the bank's voice (Reset, Lift Voice Pause). `.btn-danger` is Decline and Dismiss. |
| `.field` | `index.css` | 44 px, 12 px radius, `line-strong` border; focus gives an accent outline and border. |
| `.eyebrow` | `index.css` | See Typography. |
| `PageHeader`, `LivePill`, `Card` | `components.tsx` | Staff page top; the connection pill (accent with a live dot, `block` when reconnecting); card = surface, hairline, 16 px, `.elev-1`, 20 px padding. |
| `Logo` ("Aksha") | `components.tsx` | प्रत्यक्ष is "before the eye": an eye whose pupil is a voice waveform, on a navy tile, with the centre line in `brand-red`. Five bars from 40 px, three in the header, one at favicon size. Concepts A, B and C are on the Claude Design canvas. |
| Hero replay (`HeroReel`) | `LandingHero.tsx` | A scripted replay of a blocked Clone Call, labelled as one. The waveform follows who speaks (Caller ink, Voice Agent accent, whisper at a third); captions arrive word by word; three Signals land; BLOCK sweeps a red line across the card; Rahul's real phone beside it goes idle, then code, then Security Alert. Shows "meets" and "not read", never numbers it did not measure. |
| Navy sections | `LandingPage.tsx` | "The honest limit" and the final call to action sit on `bg-brand` with `on-fill` text, a red rule, a large faint logo watermark, `.btn-on-brand` (white pill) and `.btn-outline-on-brand`. |
| AI voice check | `ConsolePage.tsx`, `DemoPage.tsx` Ribbon | Live on every Call once a spoken turn is measured: Likely human, Unsure or Likely AI with a score, from pitch movement on the Request and the code readout (not whispers). Advisory: dashed outline, neutral colours, never pass or block, never part of a Verdict. |
| Brand band | `BankAppPage.tsx`, `LandingParts.tsx` | `bg-brand text-on-fill`: the Bank App header (rounded bottom on a phone, flat in a frame). It says "this is your bank" in both themes. |
| `VerdictBadge` | `components.tsx` | Tinted pill, icon + word (PASS, STEP-UP, BLOCK). Pops in once. |
| `Meter` | `components.tsx` | One Signal against its threshold. A missed threshold is `block`; a met one stays neutral. `advisory`: neutral bar, no threshold, tagged "advisory". `value={null}` draws a hatched "not measured" track. |
| Verdict Ribbon | `DemoPage.tsx` | Idle "Waiting for a Call" (`.elev-1`). Live: Request, current Challenge, Signal ticks in order. Verdict: solid fill sweeps in (`.elev-2`), PASS / STEP-UP / BLOCKED at ribbon size, one sentence, "Decided by", Liveness. `aria-live="polite"`. |
| Conclusion block | `ConsolePage.tsx` | Verdict word, one sentence, Decided by, authentication factors, "Aligned to RBI Authentication Directions 2025". BLOCK rows in the Calls list get a 2 px `block` left edge. |
| Console tabs | `ConsolePage.tsx` | The same segmented pill track as the nav. |
| Bank App | `BankAppPage.tsx` | Possession Code card (digits in Geist Mono 2.25rem, 3 + 3, the anti-relay line); masked on the projector; Security Alert with a full-width Dismiss (`.btn-danger`); Approve `.btn-primary`, Decline `.btn-danger`. |
| Call screen | `CallerPage.tsx` | Full-screen in-call layout: header, turn orb, Challenge card, scrolling captions, bottom dock (mic sheet, 72 px Hang up, mic meter). |
| Voice Pause row | `DemoPage.tsx` | Closed lock in `block` with scrim fade and shackle drop when on; open and neutral when off. |

## Motion

All keyframes and motion classes live in `index.css`. Keyframes animate only `transform` and `opacity`; hover may crossfade colour. Expressive motion is reserved for the Verdict and the Security Alert.

Tokens: `--dur-press` 100 ms, `--dur-fast` 150, `--dur-quick` 200, `--dur-normal` 280, `--dur-emphasis` 400, `--dur-ring` 600, `--dur-glow` 700, `--dur-loop` 900, `--dur-sweep` (280, or 400 in stage mode), `--stagger` 50.
Easing: `arrive` cubic-bezier(0.05, 0.7, 0.1, 1), `leave` (0.3, 0, 0.8, 0.15), `std` (0.2, 0, 0, 1), `firm` (0, 0, 0.3, 1), `loop` (0.33, 0, 0.67, 1), `spring` (a `linear()` curve, scale only).

| Name (class) | Duration · easing | Purpose | Reduced motion |
|---|---|---|---|
| `enter` (`.motion-enter`) | 280 ms · arrive, 45 ms stagger | Something arrived | 1 ms |
| `pop` (`.motion-pop`) | 280 ms · arrive | A badge appears | 1 ms |
| `grow` (`.motion-grow`) | 600 ms · arrive | A Signal meter fills | 1 ms |
| Ribbon sweep (`.ribbon[data-verdict]::before`, `.ribbon-word`) | 280 / 400 ms · firm | The Verdict fill sweeps in; the word rises 8 px. No bounce, no shake | 150 ms crossfade |
| PASS icon (`.ribbon-icon-spring`) | 400 ms · spring | Scales from 0.6 with 5% overshoot | 150 ms crossfade |
| `tick` (`.tick`, `.tick-mark`) | 150 / 200 ms · std | A Signal landed. Stage dwell 450 ms between ticks | 1 ms, no dwell |
| `ring-once` | 600 ms · arrive, once | The active hub tile's Call starts or is decided | none |
| `alert-in` + `glow` | 400 ms; glow 700 ms × 2 | The Security Alert drops in, then glows twice | 150 ms crossfade |
| Voice Pause scrim + `shackle` | 700 ms; 150 ms | Voice Pause turns on | 1 ms |
| `word` (`.word`) | 280 ms each, 80 ms stagger · arrive, rises 0.32em | Whisper Phrase, word by word (five words settle in under 700 ms) | 1 ms |
| `caption-word` (`.caption-word`, `Spoken`) | 200 ms each, stagger spread over about 1 s · arrive | The Bank's newest caption appears as it is spoken; words hold their space, so nothing reflows; the conversation box scrolls smoothly to it | 1 ms, instant scroll |
| `fade` (`.motion-fade`, `LiveNumber`) | 150 ms · std | A live number changed (never roll digits) | 1 ms |
| `voice`, `breathe`, `live`, `spin`, `typing`, `shimmer` | loops | Real live states only | Stop |
| `.press`, `.btn:active` | 100 ms · std | scale(0.98) while pressed | 1 ms |
| Hero replay (`.hero-wave`, `.hero-card`, `.hero-phone`) | beats of 1.3 to 6.2 s, about 21 s a round; bars `wave` 620 to 1000 ms alternate | The landing hero replays a Call. **The one loop that is not a live state**: allowed because it is labelled a replay, and it pauses whenever it is off screen | Last frame (BLOCK and the alert), no loop |
| How it works numerals (`.lp-numeral`) and red timeline (`.lp-rail-fill`) | 400 / 700 ms | The step being read fills in its numeral and the red thread grows to it | 1 ms |
| Landing `lp-line`, `lp-digit`, `lp-underline`, `.reveal` | 360 to 900 ms · arrive | Previews arrive line by line; the red stroke under "voice" draws in once; sections reveal as they scroll in | Shown at once |

**Reduced motion** (OS setting, or `localStorage.motion = "reduce"`): every animation and transition is shortened to 1 ms with one iteration, so it ends in its final state. The Ribbon and the Security Alert keep a 150 ms crossfade.

**Never:** shake on BLOCK, infinite pulses on alerts, odometer rolls, `filter: blur()` reveals, animated `box-shadow`, colour or opacity overshoot, more than three flashes per second.

## Stage mode

`/demo?stage=1` on the projector and `/console?stage=1` for the Console beat (`?stage=small` for a 1280x800 projector at 112.5%).

- `html[data-stage]` sets `font-size: 125%`; the nav and page headers are hidden and the page runs full width.
- Hub: the Verdict Ribbon fills the top third; the Customer on the latest Call keeps a ring in its tone and the others fade to 55%; Possession Codes on mirrored Bank Apps are masked.
- Console: opens the newest decided Call by itself, Conclusion block on top.
- Dark is the default; switch to light if the hall is bright (light shows the navy at its most "bank").

## Copy rules

- Use `CONTEXT.md` words exactly: Customer, Caller, Call, Request, Whisper Phrase, Possession Code, Signal, Verdict, Reason, Security Alert, Voice Pause, Registered Device, Bank Agent, Audit Trail. Never "OTP" for the Possession Code, "user", "session" or "lockout" in the UI.
- **No em-dashes or en-dashes** in visible text, including ranges. A middle dot (`·`) at most once per line.
- Show only Reasons that actually fired, in the Policy's own words.
- Never claim more than the data: no "secure line" before a PASS, no "the whisper proves identity", no "100%", no "certified", and **no real bank, RBI or NPCI names or logos in the product UI**. The navy palette is inspired by Kotak; the app never says Kotak or shows its mark.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Add a token to `index.css`, then use the utility | Hard-code a hex, `zinc-*`, `white` or `black` in a page |
| Use `.btn` variants for every button, one primary per group | Hand-roll `rounded-lg bg-accent px-3 ...` buttons, or put two solid buttons side by side |
| Lift cards by fill and hairline; use `.elev-2` only for things that float | Add strong or black drop shadows, or combine `.elev-*` with `ring-*` |
| Open staff pages with `PageHeader`, landing sections with an eyebrow | Put Hindi or Kannada in an eyebrow |
| Keep red for BLOCK, errors and Hang up | Make an action red because a brand does |
| Pair every state colour with an icon shape and a word | Use green, amber or red for turns, live states or the Spoof Score |
| Re-run `node frontend/scripts/contrast.mjs` after a colour change | Lighten `ink-soft` or the light Verdict colours by eye |
| Check every screen in both themes and with Reduce motion on | Ship a screen you have only seen in one theme |
| Keep Hang up alone in the thumb zone | Put "Call again" where Hang up was |
