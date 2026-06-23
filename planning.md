# Provenance Guard Planning Spec

## Architecture Narrative

A single piece of text-based content submitted to Provenance Guard passes through the following path:
1. **Submission**: The creative platform sends a POST request with the content and `creator_id` to `/submit`.
2. **Rate Limiting Check**: `Flask-Limiter` inspects the request IP. If the threshold is exceeded, a 429 error is returned.
3. **Pipeline Processing**:
   - **Signal 1 (LLM Analysis)**: The text is analyzed using the Groq API (`llama-3.3-70b-versatile`) to evaluate semantic and logical structure.
   - **Signal 2 (Stylometric Heuristics)**: A pure-Python module calculates vocabulary richness, sentence length variance, and punctuation density.
4. **Scoring Combination & Calibration**: The scores from both signals are combined using a weighted formula. The combined probability of AI authorship maps to a categorical verdict (`likely_ai`, `likely_human`, or `uncertain`) and a calibrated confidence score.
5. **Transparency Label Generation**: A label is selected from the design system matching the classification and confidence.
6. **Persistence & Auditing**: The submission, individual scores, confidence, label, and status (`classified`) are stored in an SQLite database.
7. **Response**: The API returns a structured JSON payload to the sharing platform.

### Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                  Client / Platform                                |
+-----------------+------------------------------------------------+----------------+
                  |                                                ^
                  | POST /submit                                   | JSON Response
                  v                                                |
+-----------------+------------------------------------------------+----------------+
|                                Flask Web Service                                  |
|                                                                                   |
|  [ Rate Limiter (Flask-Limiter) ]                                                 |
|          |                                                                        |
|          v                                                                        |
|  +-------+-------------------------+                                              |
|  | Multi-Signal Detection Engine   |                                              |
|  |                                 |                                              |
|  |  +---------------------------+  |                                              |
|  |  | Signal 1: LLM (Groq)      |  |                                              |
|  |  +-------------+-------------+  |                                              |
|  |                | llm_score      |                                              |
|  |                v                |                                              |
|  |  +---------------------------+  |                                              |
|  |  | Signal 2: Stylometrics    |  |                                              |
|  |  +-------------+-------------+  |                                              |
|  |                | styl_score     |                                              |
|  |                v                |                                              |
|  |  +---------------------------+  |                                              |
|  |  | Confidence Calibration    |  |                                              |
|  |  +-------------+-------------+  |                                              |
|  |                | verdict, conf  |                                              |
|  |                v                |                                              |
|  |  +---------------------------+  |                                              |
|  |  | Transparency Label Gen    |  |                                              |
|  |  +---------------------------+  |                                              |
|  +-------+-------------------------+                                              |
|          |                                                                        |
|          v                                                                        |
|  +-------+-------------------------+                                              |
|  | Database & Audit Log (SQLite)   |<----+ POST /appeal (content_id, reasoning)    |
|  +---------------------------------+     | (updates status to 'under_review')     |
+------------------------------------------+----------------------------------------+
```

---

## 1. Detection Signals

We use two distinct, independent signals:
1. **Signal 1: LLM semantic coherence (Groq API)**
   - **What it measures**: Semantic homogeneity, transition patterns, vocabulary predictability, and structured framing common to modern LLMs.
   - **Why it differs**: AI models generate text optimizing for the most probable next token, resulting in highly clean, expected transition patterns. Humans use non-sequiturs, nuanced analogies, and inconsistent logic.
   - **Output**: A float from `0.0` (clearly human) to `1.0` (clearly AI).
   - **Blind spot**: Highly polished human academic writing or business reports can be falsely flagged as AI due to their formal, predictable nature.
2. **Signal 2: Stylometric heuristics (Pure Python)**
   - **What it measures**: Sentence length variance, Type-Token Ratio (TTR) for vocabulary diversity, and punctuation density.
   - **Why it differs**: LLM writing is highly uniform, with average sentence lengths hovering around 15–20 words with low variance, and uniform punctuation. Humans exhibit high sentence length variability (burstiness) and unique vocabulary distribution.
   - **Output**: A float from `0.0` (highly diverse/human) to `1.0` (highly uniform/AI).
   - **Blind spot**: Short texts (under 100 words) where TTR is naturally high or sentence length variance cannot be calculated reliably.

### Combined Score Formula
We compute the combined AI probability ($P_{AI}$) as a weighted average:
$$P_{AI} = 0.70 \times S_{LLM} + 0.30 \times S_{Stylometric}$$
*Reasoning*: The LLM is a more comprehensive detector of semantic styles, while the stylometric heuristic acts as a sanity check. Since false positives (human classified as AI) are highly damaging, the weights favor the semantic richness of the LLM while allowing structural uniformity to adjust the score.

---

## 2. Uncertainty Representation

A confidence score should represent the system's certainty in its verdict.
- **Calibrated Verdicts**:
  - $P_{AI} \ge 0.75 \implies$ Verdict: `likely_ai`
  - $P_{AI} \le 0.30 \implies$ Verdict: `likely_human`
  - $0.30 < P_{AI} < 0.75 \implies$ Verdict: `uncertain`
- **Calibrated Confidence**:
  - For `likely_ai`: $\text{Confidence} = P_{AI}$ (ranges from $0.75$ to $1.0$)
  - For `likely_human`: $\text{Confidence} = 1.0 - P_{AI}$ (ranges from $0.70$ to $1.0$)
  - For `uncertain`: We calculate how close the probability is to absolute neutrality ($0.525$, the midpoint of $[0.30, 0.75]$):
    $$\text{Uncertainty} = 1.0 - \frac{|P_{AI} - 0.525|}{0.225}$$
    We map confidence to: $\text{Confidence} = 1.0 - \text{Uncertainty}$ (scaled between $0.0$ and $1.0$). Therefore, a score near $0.525$ returns a confidence of $0.0$ (complete uncertainty), while a score near the boundary returns higher confidence of being uncertain.

---

## 3. Transparency Label Design

### Variant A: High-Confidence Human (Confidence >= 0.85, Verdict: likely_human)
- **Header**: `Verified Human-Written`
- **Detailed Text**: `Provenance Guard: Verified Human-Written. This content shows strong indicators of human authorship, exhibiting rich sentence structure and organic stylistic variance. Confidence: High (Calibrated at {confidence_pct}%).`

### Variant B: High-Confidence AI (Confidence >= 0.85, Verdict: likely_ai)
- **Header**: `AI-Generated Content`
- **Detailed Text**: `Provenance Guard: AI-Generated Content. This content matches patterns commonly associated with AI models. Confidence: High (Calibrated at {confidence_pct}%). This classification is based on stylistic and semantic analysis. If you are the creator and believe this is an error, you may file an appeal.`

### Variant C: Uncertain (Verdict: uncertain OR Confidence < 0.85)
- **Header**: `Indeterminate / Mixed Style`
- **Detailed Text**: `Provenance Guard: Indeterminate/Mixed Signals. Our analysis did not find clear evidence to classify this content as either fully human-written or AI-generated. This often occurs when writing is highly structured or contains a blend of styles. Confidence: Low/Uncertain. If you are the creator and wish to clarify your process, you may submit an appeal.`

---

## 4. Appeals Workflow

- **Submission**: Any creator who receives an `uncertain` or `likely_ai` classification can submit an appeal via `POST /appeal`.
- **Payload**:
  ```json
  {
    "content_id": "UUID-string",
    "creator_reasoning": "Detailed explanation of writing process"
  }
  ```
- **System Actions**:
  1. The database checks if the `content_id` exists.
  2. The status is updated from `classified` to `under_review`.
  3. The `creator_reasoning` is appended to the submission record.
  4. An audit log entry is added reflecting the appeal filing.
- **Reviewer Queue**: Human reviewers query `GET /log` (or a specific filter) to view all entries where `status = 'under_review'`. They see the original text, the AI/stylometric scores, and the creator's explanation.

---

## 5. Anticipated Edge Cases

1. **Academic/Formal Writing**: Papers, documentation, or legal text have high structure and low variance, mimicking AI stylometrics. To address this, the LLM signal uses a specific prompt instructing it not to flag formal language alone as AI.
2. **Experimental Poetry**: Poetry with heavy repetition, single-word lines, or unusual punctuation density will break stylometric heuristics, showing extreme variance. The system relies on the LLM's semantic comprehension to balance this.

---

## AI Tool Plan

### Milestone 3: Submission Endpoint & LLM Signal
- **Spec Sections**: Detection Signals (Signal 1), Architecture Diagram.
- **Prompt Plan**: Generate Flask setup with SQLite initial configuration, a POST `/submit` route returning dummy values, and the Groq client integration wrapper scoring text from `0.0` to `1.0`.
- **Verification**: Test endpoint using curl with standard human/AI text and inspect SQLite file.

### Milestone 4: Heuristics & Combined Scoring
- **Spec Sections**: Detection Signals (Signal 2), Uncertainty Representation.
- **Prompt Plan**: Create python stylometric metrics (TTR, sentence length variance) and a scaling function to return a combined `0.0` to `1.0` AI score.
- **Verification**: Test using 4 specified baseline inputs: clear AI, clear human, formal human, edited AI.

### Milestone 5: Production Layer
- **Spec Sections**: Transparency Label Design, Appeals Workflow.
- **Prompt Plan**: Write label mapper, Flask-Limiter integration, and POST `/appeal` endpoint.
- **Verification**: Verify rate limiting returns 429 after 10 requests/minute, and filing an appeal updates database status to `under_review`.
