# Data sources and value types

CORE distinguishes five kinds of number, and every value that reaches the UI is tagged
with one. This is what makes the product defensible in front of an operator.

| Tag | Meaning | Example in the Alberta map |
|---|---|---|
| `REPORTED` | A value a regulator or operator formally declared | Petrinex monthly oil volume; AER well category |
| `MEASURED` | An instrument reading | none in public mode — requires a SCADA connector |
| `CALCULATED` | Deterministic arithmetic on values above | average daily rate, water cut, 3-month decline |
| `PREDICTED` | Model output | intervention success probability (synthetic data set only) |
| `NOT AVAILABLE` | No source exists; nothing is substituted | tubing pressure, vibration, bottom-hole location |

Two further data modes exist at the application level and are badged in the header:

* `REAL PUBLIC DATA` — the Alberta map. Public regulatory and volumetric records plus
  calculated derivatives. No simulated value appears anywhere in this mode.
* `SYNTHETIC — FOR METHOD VALIDATION` — the bundled 180-well data set used to validate
  the causal method. It is generated, labelled as generated, and never mixed with
  Alberta data.

## Where each Alberta value comes from

| Value | Source | Type |
|---|---|---|
| Latitude / longitude | AER ST37 (WGS84 as served) | REPORTED |
| Surface legal location | AER ST37 | REPORTED |
| AER well category | AER ST37 | REPORTED |
| Status, fluid | derived from the AER category by a documented rule | CALCULATED |
| ATS legal cell | parsed from the AER location string | CALCULATED |
| UWI | Petrinex, linked by legal location | REPORTED |
| Operator / licensee | Petrinex reporting operator | REPORTED |
| Reporting facility | Petrinex; facility identity from AER ST102 | REPORTED |
| Monthly oil / gas / water / injection | Petrinex conventional volumetrics | REPORTED |
| Producing hours | Petrinex | REPORTED |
| Average daily rate | reported monthly volume ÷ days in that month | CALCULATED |
| Water cut | reported water ÷ (reported water + reported oil) | CALCULATED |
| Production trend | last 3 reported months vs the earlier reported months | CALCULATED |
| Casing failure / vent flow | AER integrity reports, when imported | REPORTED |
| Pressures, temperatures, vibration, ESP, choke | — | NOT AVAILABLE |
| Netback, NPV, payback | CORE economics engine on illustrative price assumptions | CALCULATED |

## Precision and wording

* Absence from a public report is stated as **"No matching public record"** — never as
  "no casing failure exists". A dataset not listing something does not prove anything.
* Monthly reported volumes are never described as real-time, live, or measured.
* Regulatory data is never described as SCADA.
* Economic assumptions (price, royalty, lifting cost, water component costs,
  intervention costs) are illustrative public assumptions, editable in Settings and
  labelled wherever they influence a number.
