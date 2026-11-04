# Reading notes (step 0)

Read on 4 Nov 2026. Full literature review: /Users/Ali/career/METROPT-LITERATURE-REVIEW.md.

## The data itself (CSV + Data Description_Metro.pdf)

- **Sampling.** The CSV holds 1,516,948 rows, one every **10 s**, from 2020-02-01 00:00:00 to 2020-09-01 03:59:50, in UTC. The first, unnamed column is the original 1 Hz row index (0, 10, 20, …), which is why the description says 15,169,480 points "at 1 Hz": the original was 1 Hz, and the published CSV keeps every 10th row.
- **Columns:** `timestamp, TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature, Motor_current, COMP, DV_eletric (sic), Towers, MPG, LPS, Pressure_switch, Oil_level, Caudal_impulses`.
- **What the signals mean** (from the description):
  - MPG starts loading when pressure falls below 8.2 bar.
  - LPS turns on below 7 bar; this is the operator's low-pressure alarm.
  - Motor current is about 0 A when off, about 4 A idling and about 7 A loaded (raw transducer values; the scaled data show 0.04 / 3.78 / 5.92 A).
  - `DV_eletric` = 1 means loaded.
- **Failures (UCI table):** four air leaks: 18 Apr 00:00–23:59; 29 May 23:30–30 May 06:00; 5 Jun 10:00–7 Jun 14:30; 15 Jul 14:30–19:00. The table has typos (two rows numbered #1, a maintenance date of 30 Apr before failure 2).
- **MetroPT-3's introductory paper:** Davari et al., DSAA 2021, doi:10.1109/DSAA53316.2021.9564181. Another early paper on the same unit: Barros et al. 2020, "Failure detection of an APU in the operational context", doi:10.1007/978-3-030-66770-2_5.

## Troshin, Komakhidze, Abakarov (2026): physics model of the APU (Zenodo, open, read in full to p. 23)

doi:10.5281/zenodo.23737435. A preprint, not peer reviewed, but pre-registered and careful.

- **Failure times from the maintenance log** (report time T_f, when the car was declared unavailable):
  1. 18 Apr 07:05
  2. 30 May 01:10
  3. 5 Jun 18:00
  4. 15 Jul 18:25 (pressure below 7 bar)
  5. **17 Jul 05:46, a fifth air leak not in the UCI table**

  Three other log entries (12 Mar, 27 Mar, 20 Apr) are not APU failures; treat them as exclusion zones (± 24 h).
- **Normal operation, Feb–Mar:**
  - load starts at 8.09 bar and stops at 10.18 bar;
  - pressure rises 1.08 bar/min loaded and falls 0.069 bar/min idle;
  - the motor stops 416 s after unloading;
  - load phases last about 2 min.
- **Data problems to handle in the pipeline:**
  - recording gaps, mostly at night, when the car is off;
  - **TP3 sometimes freezes for hours while the compressor works**: 7 times for more than 1 h between April and August, the longest 62 h on 22–25 June;
  - the compressor is loaded 97–100% of the time inside failure windows.
- **Their evaluation protocol** (reuse it and cite it, so our numbers are comparable):
  - warning zone = T_f − 7 days … T_f − 2 h;
  - late zone = T_f − 2 h … T_f + 24 h;
  - an alarm *episode* merges alarms less than 1 h apart;
  - a failure is "warned" if an episode starts in its warning zone;
  - false episodes are counted per 1000 h outside all zones.
- **Baselines to beat** (Table 9, failures 1–4):

  | Rule | Warned | Lead (h) | False per 1000 h |
  |---|---|---|---|
  | L1, duty rule (loaded more than half of the last hour) | 4 of 4 | 139, 159, 162, 40 | 5.73 |
  | LPS (below 7 bar) | 4 of 4 | 146, 120, 133, 165 | 30.9 (useless as a warning) |
  | Their consumption-share predictor: a = u − S_p/(d_m·R) over the last hour, threshold 0.835, 30 min hold, frozen-sensor guard | 3 of 4 | 138, late, 161, 3.0 | 0.88 |

  The consumption-share indicator reads about 0.07 in normal operation and above 1 during a leak.
- **Leak sizes 24 h before each failure** (Table 8, l/min of free air; normal consumption is about 10.7):
  1. 0
  2. 3.9
  3. 1.3
  4. 15.3
  5. 4.9

  So failure 1 is invisible in the last 24 h, while failures 2–5 show a leak.
- **Blind test on the 2022 units:** two of their leaks were sudden (pressure collapsed within an hour) and one was invisible in pressure.
- **Synthetic leaks** (Kalman filter on the model): leaks growing linearly to 1.2× delivery over 72, 24 or 6 h, or a step. Leaks growing over 24–72 h were warned 10–43 h before the 7 bar alarm. They used **one clean week, 29 Jun – 6 Jul 2020**, as the base for injection; reuse that idea.

**What this means for our paper:**
- **The drop-the-paper rule cannot trigger.** Its second condition was "every real leak is sudden". Here, failures 1–3 were flagged about 6 days ahead by simple physics rules, so at least some leaks build up over days, which is slow enough for daily or weekly retraining to absorb.
- **Adopt their zones and episode counting** as our evaluation protocol.
- **Include L1 (the duty rule) as a baseline.** It is simple and catches all four failures.
- **Use the consumption share as the physics health indicator** for the guard, and its slope before each failure as the fault rate v for RQ2.
- **Our pipeline needs a frozen-sensor check**, and retraining must never train on frozen periods.
- **Summer consumption sits slightly higher than February's** (their Fig. 9a). That is benign drift, the kind retraining should follow.

## Davari et al. (2021), DSAA: closed access

What the abstract and citing papers give:
- a sparse autoencoder on the analog sensors, compared with a variational autoencoder (SAE better by 14% recall, 77% precision, 37% F1);
- air-leak failures predicted from analog data, other failure types from digital data;
- a later paper by the group reports detection up to two hours before failure.

The labelling and detection definitions need the full text.

## Wang, Kruger & Irwin (2005): closed access

Abstract: fast moving-window PCA plus an **N-step-ahead horizon** (the model from N steps earlier judges the current sample), which "improves the ability to detect slowly developing drifts". **Not verified:** whether they give a rule for choosing N. This no longer affects the go/no-go decision (see above). It only affects how we word the related work.

## Sullivan & Jones (2002), Technometrics: closed access

A self-starting chart for multivariate individual observations: the in-control parameters are estimated as data arrive, which avoids degradation from estimated parameters. **Not verified:** whether it treats trends. Wording only.

## To get the three closed papers

Use the INPT or UCA library portal, or request them from the authors (ResearchGate or email). Put the PDFs in `paper/refs/`, which is git-ignored if you add it to `.gitignore`.
