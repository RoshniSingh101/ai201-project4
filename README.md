# Provenance Guard

Provenance Guard is a backend system designed for creative sharing platforms to classify text-based submissions (poems, blog posts, short stories), assign attribution verdicts and confidence scores, present user-facing transparency labels, and manage creator appeals.

---

## 1. System Architecture

A single piece of text-based content submitted to Provenance Guard passes through the following path:
1. **Submission**: A creative sharing platform makes a POST request to `/submit` containing the text and the creator's ID.
2. **Rate Limiting**: `Flask-Limiter` checks the request count. If the client has sent more than 10 requests within a rolling 60-second window, the request is rejected with a `429 Too Many Requests` error.
3. **Pipeline Processing**:
   - **Signal 1 (LLM Semantic Coherence)**: The text is analyzed using the Groq API running `llama-3.3-70b-versatile`. It parses structural coherence, transitions, and predictability, returning a probability score between `0.0` and `1.0`.
   - **Signal 2 (Stylometric Heuristics)**: A Python module evaluates statistical features of the text, specifically:
     - Sentence length variance (burstiness).
     - Vocabulary diversity (Type-Token Ratio, adjusted for length).
     - Punctuation density.
4. **Scoring Combination & Calibration**: Individual signal scores are blended into a combined probability of AI authorship:
   $$P_{AI} = 0.70 \times S_{LLM} + 0.30 \times S_{Stylometric}$$
   This combined probability is mapped to one of three verdicts (`likely_human`, `likely_ai`, or `uncertain`) and a calibrated confidence score.
5. **Transparency Label Generation**: Based on the verdict and confidence, the system generates a tailored user-facing transparency label.
6. **Auditing & DB Persistence**: The entire payload—including the submission text, individual signal scores, combined score, confidence, label text, and status (`classified`)—is committed as a structured row to an SQLite database.
7. **Response**: A JSON payload is returned to the client containing the categorization details.

---

## 2. Detection Signals & Calibration

We use two distinct, independent signals to capture semantic and structural features of the text:

### Signal 1: LLM Semantic Coherence (Groq LLaMA 3.3 70B)
- **Why we chose it**: Modern LLMs write using standard transition phrases, logical consistency, and homogeneous sentence flows. Human writing contains logical jumps, colloquialisms, and structural irregularities.
- **Blind spots**: Highly structured human writing (like technical specifications, legal contracts, or formal academic articles) often matches the predictable structural flow of LLM generations.

### Signal 2: Stylometric Heuristics (Pure Python)
- **Why we chose it**: Computes statistical patterns. Humans write with high variance in sentence length (combining very short sentences with long compound structures) and show variable vocabulary richness. AI outputs exhibit a highly uniform sentence length distribution.
- **Blind spots**: Short text submissions (under 30–50 words). For short text, TTR is naturally close to 1.0, and sentence length variance is highly volatile, making heuristics statistically unreliable.

### Calibrated Thresholds
- **Likely Human**: Combined score $P_{AI} \le 0.30$
  - Confidence = $1.0 - P_{AI}$ (Ranges from 70% to 100%)
- **Likely AI**: Combined score $P_{AI} \ge 0.75$
  - Confidence = $P_{AI}$ (Ranges from 75% to 100%)
- **Uncertain**: Combined score $0.30 < P_{AI} < 0.75$
  - Confidence = $0.70 \times (\text{distance from midpoint } 0.525 / \text{max distance } 0.225)$

---

## 3. Transparency Label Design

### Variant A: High-Confidence Human (Verdict: likely_human, Confidence >= 75%)
- **Header**: `Verified Human-Written`
- **Exact Text**: `Provenance Guard: Verified Human-Written. This content shows strong indicators of human authorship, exhibiting rich sentence structure and organic stylistic variance. Confidence: High (Calibrated at {confidence}%).`

### Variant B: High-Confidence AI (Verdict: likely_ai, Confidence >= 75%)
- **Header**: `AI-Generated Content`
- **Exact Text**: `Provenance Guard: AI-Generated Content. This content matches patterns commonly associated with AI models. Confidence: High (Calibrated at {confidence}%). This classification is based on stylistic and semantic analysis. If you are the creator and believe this is an error, you may file an appeal.`

### Variant C: Uncertain / Indeterminate (Verdict: uncertain OR Confidence < 75%)
- **Header**: `Indeterminate / Mixed Style`
- **Exact Text**: `Provenance Guard: Indeterminate/Mixed Signals. Our analysis did not find clear evidence to classify this content as either fully human-written or AI-generated. This often occurs when writing is highly structured or contains a blend of styles. Confidence: Low/Uncertain. If you are the creator and wish to clarify your process, you may submit an appeal.`

---

## 4. Appeals Workflow

When a submission is classified as `uncertain` or `likely_ai`, creators can file an appeal:
1. **Endpoint**: `POST /appeal` with `content_id` and `creator_reasoning`.
2. **Operations**: The SQLite database updates the submission status from `classified` to `under_review` and stores the creator's explanation.
3. **Audit Log**: An audit log entry is inserted recording the appeal filing event alongside the original score data.
4. **Queue View**: A reviewer can inspect `GET /log` and easily isolate entries with `status: "under_review"` to view the submitted text, the AI/Stylometric scores, and the creator's reasoning.

---

## 5. Rate Limiting Decisions

We enforce **10 requests per minute** and **100 requests per day** per client IP.
- **Reasoning**: Creative platforms generally have human authors writing or editing content before publishing. A single human writer rarely submits more than a few stories or posts per hour. A limit of 10 requests per minute easily accommodates active posting and editing while successfully preventing adversarial scripts from flooding the API, scraping endpoints, or performing bulk AI detection evasion testing.

---

## 6. Known Limitations

- **Volatile Short-Text Stylometrics**: Short texts (e.g. poems or social media updates under 50 words) possess too few sentences to compute variance accurately. For example, a three-sentence paragraph where sentence lengths are 10, 22, and 11 words yields a mathematical variance of 44.33 (which maps to 0.0 AI-likeness, human-like), even if generated by AI.
- **Non-Native English Formal Writing**: Non-native English writers often use highly structured sentences, formal transitions, and a limited set of vocabulary, which can mimic AI patterns and lead to a false `uncertain` classification.

---

## 7. Spec Reflection

- **How the spec helped**: Writing out the exact formula for combining scores and scaling confidence in `planning.md` made implementation trivial. It kept us from guessing thresholds during code development.
- **Divergence and why**: In our planning spec, we set the High-Confidence threshold to `0.85`. During testing, we realized that highly variable human writing obtained a combined score around `0.20`, resulting in a confidence score of `0.80`. Under the `0.85` rule, this would be labeled `Indeterminate / Mixed Style`, which is too strict. We calibrated the threshold to `0.75` so that human writing is correctly marked as `Verified Human-Written` while keeping the false-positive risk low.

---

## 8. AI Usage Notes

During development:
1. **Flask App Skeleton**: We directed the agent to output the Flask app shell including custom error handlers. It generated an `@app.errorhandler(444)` which is not a recognized HTTP code in Flask. We revised this to a standard `404` handler to enable correct execution.
2. **SQLite Database Helpers**: We instructed the agent to generate database helpers with default paths. The agent bound `DEFAULT_DB_PATH` in the function definitions (e.g., `def save_submission(..., db_path=DEFAULT_DB_PATH)`), which caused python to evaluate the path at import time, rather than dynamically. This caused test database isolation to break. We modified this to default to `db_path=None` and resolve the path dynamically during call time.
