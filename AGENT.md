# AGENT.md — Sleep Nutrition & Trp:LNAA Meal Recommender

## 1. Project Overview
Build a diet-and-sleep application grounded in the findings of **St-Onge et al. (2016), *"Effects of Diet on Sleep Quality"* ([PMC5015038](https://pmc.ncbi.nlm.nih.gov/articles/PMC5015038/))**.

### Core Goal
Recommend and evaluate evening food combinations that pair **tryptophan-rich foods** with **low-glycemic-index (low-GI) carbohydrates** to support nocturnal **serotonin** and **melatonin** synthesis and improve sleep quality. Users can:
1. Select or receive recommendations for food combinations.
2. View a calculated **Sleep Score** driven primarily by the **Tryptophan-to-LNAA (Trp:LNAA) ratio** and carbohydrate GI.
3. Log their evening meal and record **subjective sleep quality feedback** the next morning.
4. Track how different dietary combinations, Trp:LNAA ratios, and meal timings correlate with their sleep quality over time.

> **Disclaimer Requirement:** Include a clear, non-intrusive disclaimer in the UI stating that the application is for educational and personal tracking purposes and does not constitute medical advice.

---

## 2. Scientific Model & Domain Rules

### 2.1 Biochemical Mechanism (from PMC5015038)
- **Tryptophan → Serotonin → Melatonin:** Tryptophan (Trp) is an essential dietary amino acid and the sole precursor to serotonin, which is subsequently converted to melatonin in the pineal gland to regulate sleep onset and circadian rhythm.
- **Blood-Brain Barrier (BBB) Competition:** Tryptophan competes with other **Large Neutral Amino Acids (LNAAs)**—specifically **Valine (Val), Leucine (Leu), Isoleucine (Ile), Tyrosine (Tyr), Phenylalanine (Phe)**, and **Methionine (Met)**—for the same L-type amino acid transporter across the BBB.
- **Role of Carbohydrates & Insulin:** Carbohydrate intake triggers insulin release, which promotes uptake of competing LNAAs (especially branched-chain amino acids: Leu, Ile, Val) into skeletal muscle while leaving albumin-bound tryptophan in circulation. This increases the **plasma Trp:LNAA ratio**, facilitating tryptophan entry into the brain.

### 2.2 Product Rules for GI & Timing
- **Primary Pairing Rule:** Favor combinations of **tryptophan-rich foods** + **low-GI carbohydrates** (`GI <= 55`) per the project's core focus on steady nocturnal metabolic support.
- **Scientific Context Note:** PMC5015038 also notes that meal timing relative to bedtime matters (e.g., high-GI meals consumed ~4 hours before bed reduced sleep onset latency in cited studies, whereas eating too close to bedtime, such as ~1 hour before bed, can impair sleep quality). Support logging **hours before bedtime** so users can track both GI and timing effects.

---

## 3. Input Datasets (User-Provided)
The user will provide two datasets (CSV or JSON). Build a flexible ingestion layer in `src/data/` with schema validation, unit normalization (e.g., per `100g` vs. per serving), and clear error reporting for missing values.

### 3.1 Food & Amino Acid Dataset
Expected fields (map column aliases cleanly during import):
- `food_id` / `name` / `category`
- `serving_size_g` (default `100` if not specified)
- `tryptophan_mg` (mg per 100g or per serving)
- Competing LNAAs (mg):
  - `valine_mg`
  - `leucine_mg`
  - `isoleucine_mg`
  - `tyrosine_mg`
  - `phenylalanine_mg`
  - `methionine_mg` *(optional in some nutrient tables; handle gracefully if absent and surface which LNAAs were included)*
- Basic macros (optional but helpful): `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `calories_kcal`

### 3.2 Glycemic Index (GI) Dataset
Expected fields:
- `food_id` or `food_name` (support fuzzy/alias matching to the food dataset)
- `gi_value` (numeric, 0–100+)
- `gi_category` (derived if missing: `Low <= 55`, `Medium 56–69`, `High >= 70`)
- `glycemic_load` *(optional)*

---

## 4. Core Calculation Engine

### 4.1 Trp:LNAA Ratio
For a selected combination of foods $i = 1 \dots n$ with serving weights $w_i$ (in grams):

$$\text{Total Trp} = \sum_{i=1}^{n} \text{Trp}_i(w_i)$$

$$\text{Total LNAA} = \sum_{i=1}^{n} \left(\text{Val}_i(w_i) + \text{Leu}_i(w_i) + \text{Ile}_i(w_i) + \text{Tyr}_i(w_i) + \text{Phe}_i(w_i) + \text{Met}_i(w_i)\right)$$

$$\text{Trp:LNAA Ratio} = \frac{\text{Total Trp}}{\text{Total LNAA}}$$

- Guard against division by zero when `Total LNAA == 0` (e.g., pure sugar/carb items with negligible protein).
- Always display the raw `Total Trp (mg)`, `Total LNAA (mg)`, and `Trp:LNAA Ratio` alongside the score for transparency.

### 4.2 Sleep Score (0–100)
Compute a composite **Sleep Score (0–100)** from configurable weights in a central config module:
1. **Trp:LNAA Component (primary weight, e.g., 60%):** Normalized against a reference target range (configurable, e.g., typical dietary Trp:LNAA ratios ~0.03–0.12+).
2. **GI Suitability Component (e.g., 30%):** Rewards combinations whose carbohydrate-contributing foods are **Low GI (`<= 55`)**; penalizes Medium/High GI unless configured otherwise.
3. **Meal Balance / Practicality Component (e.g., 10%):** Checks that the combination includes meaningful tryptophan (e.g., minimum mg threshold) and carbohydrate presence to trigger the insulin-mediated LNAA clearance mechanism.

> Keep all scoring weights and thresholds in a single configuration file so they can be tuned easily without rewriting logic.

---

## 5. Functional Requirements

### 5.1 Food Combination Builder & Recommender
- **Manual Builder:** Users search/browse foods, add 1+ items to a meal combination, adjust serving sizes (grams or standard servings), and see live updates to:
  - `Total Trp (mg)`
  - `Total Competing LNAAs (mg)`
  - `Trp:LNAA Ratio`
  - `Weighted / Effective GI` and GI category
  - `Sleep Score (0–100)` with a clear breakdown of why it scored that way
- **Smart Recommender:** Given a selected tryptophan-rich food (or a user's dietary preferences/constraints), recommend top-ranked **low-GI carbohydrate pairings** (and vice versa) sorted by Sleep Score.

### 5.2 Sleep Quality Logging & Diet Tracking
- **Log Meal:** Save a selected food combination with date, meal time, and optional planned bedtime / hours before bed.
- **Log Subjective Sleep Quality:** Record next-morning feedback linked to a logged meal (or standalone):
  - Overall Sleep Quality (`1–5` or `1–10` scale)
  - Perceived Sleep Onset Latency (e.g., minutes to fall asleep, or 1–5 ease of falling asleep)
  - Night Awakenings (count or 1–5 scale)
  - Morning Alertness / Restedness (`1–5` scale)
  - Free-text notes (e.g., caffeine, stress, exercise confounders)
- **Progress & Correlation Dashboard:**
  - Time-series view of Sleep Score / Trp:LNAA ratio vs. Subjective Sleep Quality.
  - Summary insights: average sleep quality for Low-GI + High-Trp:LNAA nights vs. other nights, and best-performing food combinations for the individual user.

---

## 6. Suggested Architecture & Project Structure
Use a clean, modular structure (adaptable to Python + Streamlit/FastAPI or TypeScript/Next.js + SQLite):

```text
sleep-nutrition-planner/
├── AGENT.md                  # This specification
├── data/                     # User-provided food & GI datasets + sample fixtures
├── src/
│   ├── config/               # Scoring weights, GI thresholds, LNAA column definitions
│   ├── data/                 # Dataset loaders, schema validation, food-GI matching
│   ├── scoring/              # Trp:LNAA calculator & Sleep Score engine
│   ├── recommender/          # Pairing generator (Trp-rich + Low-GI carb)
│   ├── tracking/             # Persistence (SQLite/JSON) for meal logs & sleep feedback
│   └── ui/                   # Web UI (builder, recommender, logger, analytics)
└── tests/                    # Unit tests for scoring, GI matching, and persistence
```

---

## 7. Implementation Milestones for the Building Agent
1. **Milestone 1 — Data Ingestion & Normalization:**
   - Implement dataset loaders for food/amino-acid data and GI data, plus a small synthetic sample dataset for immediate local testing before the user drops in their full datasets.
2. **Milestone 2 — Scoring & Recommender Engine:**
   - Implement `Trp:LNAA` calculation, `Sleep Score (0–100)` with transparent breakdown, and pairing recommender (`tryptophan-rich + low-GI carb`).
   - Add unit tests covering edge cases (zero LNAA, missing Methionine, high-protein/low-carb vs. balanced Trp+low-GI carb).
3. **Milestone 3 — Meal & Sleep Feedback Persistence:**
   - Implement local storage (e.g., SQLite) for `meal_logs` and `sleep_feedback` with CRUD operations.
4. **Milestone 4 — Interactive UI & Analytics:**
   - Build the Food Combination Builder, Recommender view, Sleep Feedback Logger, and Trend/Correlation Dashboard.
5. **Milestone 5 — Verification:**
   - Run all unit tests, verify end-to-end flow with sample data, and document how to plug in the user's custom datasets.
