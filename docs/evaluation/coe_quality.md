# CoE Quality — Chain-of-Explanation Quality Metric (HELIOS)

## Definition
**CoE (Chain-of-Explanation)** measures the quality, actionability, and trustworthiness of the natural-language root cause explanation + remediation recommendation produced by HELIOS (primarily from the L-pipe + P4 cognitive layer).

It evaluates how well the explanation helps a Site Reliability Engineer (SRE) understand, trust, and act on the RCA output.

## Formal Scoring Rubric (0–4 Scale)

| Score | Label              | Description                                                                 | Example Characteristics |
|-------|--------------------|-----------------------------------------------------------------------------|-------------------------|
| 4     | Excellent          | Clear, complete, actionable, causally accurate, high confidence, SRE-ready | Step-by-step causal chain, confidence scores, exact file/function/line, remediation steps with commands, no hallucinations |
| 3     | Good               | Mostly clear and actionable with minor gaps                                 | Good causal narrative but missing one remediation command or confidence value |
| 2     | Acceptable         | Understandable but incomplete or partially misleading                       | Identifies root cause but weak causal link or vague remediation |
| 1     | Poor               | Confusing, hallucinated, or not actionable                                  | Generic explanation, wrong service blamed, no remediation |
| 0     | Invalid            | Completely wrong, contradictory, or no explanation                          | Hallucinated components, breaks causality |

**Scoring is done at the incident level.** Average across all evaluated incidents becomes the final CoE Quality score.

## Evaluation Protocol (DSR-Compliant)

1. **Annotation Process**
   - Two independent human raters (SREs or researchers)
   - Blind scoring (raters do not see each other’s scores)
   - Adjudication by third rater (or AblationCoordinatorAgent + human) when |score difference| ≥ 2

2. **Inter-rater Reliability Target**
   - Cohen’s Kappa ≥ 0.75 (substantial agreement)
   - Report both raw agreement and Kappa in every ablation run

3. **Inputs Required for Scoring**
   - Ground-truth root cause (from fault injection oracle)
   - HELIOS-generated explanation + remediation suggestion
   - Trace / log / metric context (for verification)

4. **Tie Handling & Edge Cases**
   - Partial credit for identifying correct service but wrong sub-component
   - Penalty for hallucinations (even if overall root cause is correct)
   - Bonus for including uncertainty quantification / confidence intervals

5. **Integration with MAHC**
   - CoE score is one of the votes in Multi-Agent Hierarchical Consensus
   - LLMReasoningAgent, GraphPipelineAgent, and StatisticalPipelineAgent each contribute a sub-score
   - Final CoE uses hierarchical weighted aggregation with entropy regularization

## Automated Heuristics (for fast iteration)
While human scoring is the gold standard, the following automated signals are used for pre-filtering and regression detection:

- Presence of actionable commands (kubectl, restart, scale, etc.)
- Mention of exact file/function/line/class
- Causal language strength (“because”, “triggered by”, “root cause”)
- Confidence score calibration (predicted vs actual accuracy)
- Length and readability (Flesch-Kincaid + entity density)

## Usage in HELIOS Evaluation Pipeline

```python
# Example in metrics-evaluator
coe_score = evaluate_coe(
    explanation=llm_output,
    ground_truth=oracle_root_cause,
    raters=["rater1", "rater2"]
)

# Record in ablation_matrix.csv
row["coe_quality"] = coe_score
row["coe_kappa"] = kappa