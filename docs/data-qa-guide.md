# CORE data QA guide

How to check, by hand, that CORE is using real data and not making anything up.
Written for a non-technical reader. No coding needed.


BEFORE YOU START
----------------
1. Open a Terminal window.
2. Type this and press Enter:

       scripts/start_demo.sh    (run from the repository root)

3. Wait until it says the server is running.
4. Open a browser at:  http://localhost:8000

The bar at the top of every page has a button showing the DATA CONTEXT
(for example "Synthetic validation data" or "Real public data").
Click it at any time to see exactly what CORE is analysing.

## TEST 1 — AER ST37 (the Alberta well list)

 1. Click the map pin icon in the left sidebar (2nd icon down). The Alberta map opens.
 2. Write down the number under "Wells imported" (should be about 475,125).
 3. Click the tab "Data sources & updates".
 4. Find "AER ST37 — List of Wells in Alberta". It should say INSTALLED and show
    a row count and a "retrieved" date.
 5. Press "Refresh".
    EXPECTED: a progress box appears, then the row count and retrieved date update.
    The number of wells should stay in the same ballpark (about 475,000).
 6. Go to the Data hub (database icon in the sidebar) and find the same AER ST37 card.
 7. Press "View schema".
    EXPECTED: a list of REAL column names with data types and how many rows are
    filled in. If you see the words "observed": true, the schema was read from the
    file that was actually imported — not typed in by hand.
 8. Press "View sample".
    EXPECTED: real Alberta rows. Surface locations look like  11-32-040-11W4.
    RED FLAG: any identifier starting with SYN- .
 9. Copy one UWI (a 16-character code like 102162107606W403) from the map's search
    results or from a well you click.
10. Go back to the map, paste it into the search box, press Search, click the result.
    EXPECTED: the map flies to that well and the panel shows the SAME identifier,
    a latitude/longitude, and the operator name.

## TEST 2 — Petrinex production, and checking the maths yourself

 1. On the Alberta map, search for a well that has production
    (try:  102162107606W403 ).
 2. Click the result to open the well panel.
 3. Click the "Production" tab. You will see a list of "Reported months".
 4. Pick the newest month and write down two things:
        - the month            (example: 2026-07)
        - the oil volume in m3 (example: 6,961.5 m3)
 5. Work out the daily average yourself:
        oil volume  ÷  number of days in that month
        Example: 6961.5 ÷ 31 = 224.6 m3 per day
 6. Click the "Calculator" tab in the same panel.
    EXPECTED: "Oil rate" is the same number you just calculated, converted to
    barrels (1 m3 = 6.28981 bbl). Hover the little "CALCULATED" tag: it must show
    the formula and say the source is Petrinex.
    RED FLAG: a number with no formula, or a number you cannot reproduce.

## TEST 3 — Synthetic vs real: proving they are NOT mixed

 1. Click the DATA CONTEXT button in the top bar.
 2. Read the panel. It lists, for the current data set, where Wells / Production /
    Interventions / Costs / Facilities each come from.
 3. Under "SWITCH ANALYTICAL DATA SET", click  alberta_petrinex .
    The page reloads.
 4. Open "Wells" (the house icon in the sidebar).
    EXPECTED: identifiers look like ABWI100010101008W404 (real Alberta wells).
    RED FLAG: anything starting with SYN- .
 5. Open the Overview page (grid icon, top of sidebar).
    EXPECTED (this is correct, not a bug): a message saying the evidence base does
    not match the active data set and must be rebuilt.
    WHY: the analysis was calculated from the other data set. CORE refuses to show
    one data set's results under another data set's name. This is the safety guard.
 6. Click the DATA CONTEXT button again and switch back to  synthetic .
    EXPECTED: the Overview page works again and shows SYN- wells — which is correct,
    because you are now explicitly looking at the synthetic validation data set.

## TEST 4 — Refresh: what should change

 1. Map → "Data sources & updates".
 2. Note the "retrieved" date/time on AER ST37.
 3. Press "Refresh" and wait for it to finish.
    SHOULD CHANGE:  the "retrieved" timestamp.
    SHOULD STAY ROUGHLY THE SAME:  the row count.
    SHOULD NOT CHANGE:  "source last edited" (that is AER's own date, not ours).
 4. On the Petrinex row, change the dropdown from 12 months to 3 months, press Refresh.
    EXPECTED: after it finishes, the row count DROPS and the date range gets shorter.
    This proves the number you choose really controls the data being used.
 5. Set it back to 12 months and Refresh again.

## TEST 5 — Failure test (completely safe, nothing is destroyed)

 Option A — a source with no adapter:
 1. Data hub → find "North Dakota Department of Mineral Resources".
 2. Press "Connect".
    EXPECTED: a red message saying the adapter is not implemented and telling you to
    use the CSV wizard. The card must STAY "Not connected".
    RED FLAG: the card turns green / says Connected.

 Option B — the operator API:
 1. Data hub → "Operator API (SOCAR pilot)" → press "Connect".
    EXPECTED: red message including "SCADA NOT CONNECTED".
    It must never say connected. No SOCAR data exists in this app.

 Option C — turn off your Wi-Fi, then press Refresh on AER ST37.
    EXPECTED: an error message, AND the map keeps working with the data it already
    had. Turn Wi-Fi back on and Refresh again.
    RED FLAG: the map goes blank, or the well count drops to zero.

## TEST 6 — Information ("i") icons: where numbers come from

 1. Go to the Water page (droplet icon).
 2. Find the small round "i" next to a KPI such as "Hidden capacity cost".
 3. Hover it.
    EXPECTED: a card appears ON TOP of everything (never cut off) showing the
    formula, the inputs, and a tag such as PUBLIC ASSUMPTION or CALCULATED.
 4. Click the "i" — the card should stay open ("pinned"). Press Esc to close.
 5. On the Alberta map, open any well → "Calculator" tab → hover the "CALCULATED"
    tag next to Oil rate.
    EXPECTED: formula, the reported volume, the number of days, and "Source: Petrinex".
 6. Same well → "Data sources" tab.
    EXPECTED: every group of values names its dataset, its type (REPORTED /
    CALCULATED) and when it was retrieved. SCADA must say "Not connected".

## TEST 7 — Languages

 1. Use the EN dropdown in the top bar. Switch to RU.
 2. Walk through: Overview → Wells → Water → Portfolio → Data hub → Settings.
    LOOK FOR: menu names, buttons and table headings in Russian.
    These SHOULD stay in English (they are international terms, on purpose):
        UWI, API, SCADA, NPV, AER, Petrinex, bbl/d, and official dataset names.
    RED FLAG: raw keys such as  nav_wells  or  ov_title  appearing on screen.
    RED FLAG: text overflowing outside its box.
 3. Repeat with AZ.
 4. Switch back to EN.
 NOTE: the Alberta map page and the Data-hub source cards are still largely English.
 This is a known gap, listed at the end of this file.

## TEST 8 — Importing your own CSV

 1. Data hub → press "Sample schema" to download an example file.
 2. Open it. It has columns: well_id, month, oil_m3, water_m3, gas_e3m3, hours,
    status, field. Keep the header, keep a few rows, save it as my_test.csv.
 3. Data hub → "Import wizard".
 4. Upload my_test.csv. Step through: preview → map the columns → validate →
    confirm units (m3) → give it a name like  my_test  → ingest.
 5. When it finishes, click the DATA CONTEXT button in the top bar.
 6. Under "SWITCH ANALYTICAL DATA SET" click  my_test .
 7. Open the Wells page.
    EXPECTED: your own well_ids from the CSV — nothing else.
    RED FLAG: SYN- wells, or wells you did not put in the file.

## TEST 9 — Does changing the data set really change the pages?

 1. Note three numbers on the Overview page (oil per day, produced water, idle wells).
 2. Switch the data context to a different data set.
 3. Either the numbers change, or you get the "rebuild the evidence base" message.
    Both are correct answers. What is NOT correct is the numbers staying identical
    while the data set name changes.
 4. The Alberta map is deliberately DIFFERENT: it always shows AER/Petrinex public
    records no matter which analytical data set is selected. The DATA CONTEXT panel
    says so explicitly, under "Alberta public data (map)".

## RED FLAGS — if you see any of these, the feature is fake or broken

 * A source turns green / says "Connected" but shows 0 rows.
 * A source says Connected the instant you press the button, with no import.
 * A real source (AER / Petrinex / your CSV) shows identifiers starting with SYN- .
 * Pressing Disconnect changes nothing.
 * A "last refreshed" time updates but the row count and data never change.
 * The word "undefined" appears where a source name or number should be.
 * A calculated number has no "i" icon, or the icon shows no formula and no source.
 * Choosing a different data set does not change any page and produces no message.
 * Anything labels AER or Petrinex data as "real-time" or "SCADA" or "live telemetry".
   These are monthly, publicly reported figures. They are real, but they are not
   live sensor readings.

## WHAT IS HONESTLY NOT CONNECTED

 * SCADA / live telemetry: NOT CONNECTED. Pressure, temperature, vibration, pump
   and choke values have no public source and are shown as "Not publicly available".
   They are never invented.
 * Operator API (SOCAR): contract only. No operator data is bundled.
 * Intervention/workover history: does not exist in Alberta public data.
 * Costs and facility capacities: illustrative assumptions until operator data is
   connected. They are labelled as assumptions everywhere they are used.
 * Saskatchewan, North Dakota, Kansas, Volve: no automatic adapter. Use the CSV wizard.
