# Phase 7 evaluation — stratified, hybrid vs vector-only

_Run: 2026-07-18 02:36 · ollama · gpt-oss:120b-cloud_

## Score by stratum

Read this table by row, not by total. The claim lives in the *shape*: lookup ties, multi-hop separates.

| Stratum | n | Vector-only correct | Hybrid correct | Graph-fact recall (hybrid) |
|---|---|---|---|---|
| lookup | 2 | 1/2 | 1/2 | — |
| relational | 3 | 3/3 | 3/3 | 100% |
| multi_hop | 2 | 2/2 | 2/2 | 100% |
| temporal | 4 | 3/4 | 3/4 | 100% |
| aliases | 4 | 2/4 | 1/4 | 100% |
| conflict | 2 | 2/2 | 1/2 | 100% |
| coreference | 2 | 0/2 | 1/2 | 0% |
| messy_email | 2 | 2/2 | 2/2 | 100% |
| grounding_adv | 4 | 3/4 | 4/4 | 100% |
| grounding_neg | 2 | 2/2 | 2/2 | — |
| rbac | 2 | 2/2 | 2/2 | — |

## Entity grounding vs traversal (graph-dependent questions)

The multi-hop bottleneck is a Named Entity Linking problem, not a graph one. This split shows which stage fails: the traversal engine vs the linking of the question's words to a node name.

| Stage | Accuracy (of retrieved) |
|---|---|
| Candidate recall (right entity offered) | 100% (21/21) |
| Linker (given the entity was offered) | 76% |
| Entity grounding (correct seed) | 76% (16/21) |
| Grounding Error Rate (GER) | 24% |
| Grounding precision — abstention negatives | 50% (1/2) |
| Coreference negatives resolved (separate capability) | 0/1 |
| Traversal (given grounding) | 100% |

Grounding is scored for CORRECTNESS (right seed), not mere presence. Traversal is measured only on questions that grounded, so it isolates the graph engine from the linking stage upstream. The `grounding_adv` stratum is adversarial — paraphrases sharing no tokens with the node name ("metered billing", "pay-per-use") — so grounding here tests generalisation, not one lucky synonym. `grounding_neg` questions have no referent in the graph; a good linker abstains (precision). Coreference negatives ("the prior motion") are unresolved references, a different capability (M16) — their misses are reported separately, not folded into linker precision.


### Where grounding loss comes from (R12)

| Attribution | Share of 21 retrieved graph questions |
|---|---|
| Lost — entity never offered to the planner | 0% |
| Lost — entity offered, linker chose wrong | 24% |
| Grounded correctly | 76% |

The planner may only return names the candidate stage surfaced (`retrieve.plan` drops the rest), so candidate recall is a hard ceiling on grounding — the rows above split the GER into the stage that caused it. Only *linker* loss is an abstention or prompting problem; *candidate* loss needs a wider or better candidate stage, and tightening the linker would make it worse. Distractor load: 36.5 candidates per question on average, 38 at most — precision is a function of this, so it is not comparable across corpora of different size.

Stage latency: candidate 368 ms (embedding + store lookup) · planner 4568 ms (LLM). Both are per question and exclude synthesis.


## Ablation — grounding on vs off (identical graph engine)

| Configuration | Graph-fact recall (graph questions) |
|---|---|
| Exact match only (no grounding) | 38% |
| Planner grounding | 95% |

Same traversal code, same corpus, same questions — the only variable is whether the planner grounds the mention to a canonical node name. The delta is the measured contribution of the grounding stage.


## Per-question detail

| id | stratum | sources | as | grounded | grounded to | vector | hybrid | graph facts | recall | question |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | lookup | board_meeting_12_transcript | Raj | — | — | ERR | ERR | — | — | What was decided about Pricing Model B? (errored: Ollama error 500: {"error":"Post \"https://ollama.com:443/ap) |
| L2 | lookup | board_meeting_12_transcript | Raj | — | — | ✓ | ✓ | 29 | — | What did the margin analysis say gross margin would drop to under Model B? |
| L3 | lookup | board_meeting_12_transcript | Raj | — | — | ✗ | ✗ | 0 | — | How many months of runway does the company have? |
| R1 | relational | board_meeting_12_transcript | Raj | ✓ | Reject Pricing Model B, Pricing Model B | ✓ | ✓ | 56 | 100% | Who opposed rejecting Pricing Model B? |
| R2 | relational | board_meeting_12_transcript | Raj | ✓ | Pricing Model B, Reject Pricing Model B | ✓ | ✓ | 56 | 100% | Who made the final call to reject Pricing Model B? |
| R3 | relational | board_meeting_12_transcript | Raj | ✓ | Reject Pricing Model B, Pricing Model B | ✓ | ✓ | 56 | 100% | Who supported the rejection of Pricing Model B? |
| M1 | multi_hop | board_meeting_12_transcript | Raj | ✗ | Adopt Usage-Based Pricing | ✓ | ✓ | 43 | 100% | Which board members took a position when the board rejected the usage-based pricing proposal, and what were their positions? |
| M2 | multi_hop | board_meeting_12_transcript | Raj | ✗ | Adopt Usage-Based Pricing | ✓ | ✓ | 43 | 100% | What action item came out of the board's rejection of the usage-based pricing proposal, and who owns it? |
| T1 | temporal | board_meeting_12_transcript, board_meeting_13_transcript | Raj | ✓ | Pricing Model B, Reject Pricing Model B | ✓ | ✓ | 56 | 100% | Is Pricing Model B currently rejected, or has that changed? |
| T2 | temporal | board_meeting_12_transcript, board_meeting_13_transcript | Raj | ✓ | Reject Pricing Model B, Adopt Usage-Based Pricing | ✓ | ✓ | 63 | 100% | What decision reversed the earlier pricing rejection, and who made the call? |
| T3 | temporal | board_meeting_12_transcript, board_meeting_13_transcript | Raj | ✓ | Reject Pricing Model B, Pricing Model B | ✓ | ✓ | 56 | 100% | Why was the pricing decision reversed? |
| T4 | temporal | board_meeting_12_transcript, board_meeting_13_transcript | Raj | ✓ | Adopt Usage-Based Pricing | ✗ | ✗ | 43 | 100% | Who changed their position on usage-based pricing between the two board meetings? |
| E1 | aliases | board_meeting_14_transcript | Raj | ✓ | R. Malhotra, Board Meeting 14 | ✗ | ✗ | 29 | 100% | Who is R. Malhotra in the Meeting 14 record? |
| E2 | aliases | board_meeting_14_transcript | Raj | ✓ | R. Kumar, Board Meeting 14 | ✓ | ✓ | 28 | 100% | Who is R. Kumar in the Meeting 14 record? |
| E3 | aliases | board_meeting_14_transcript | Raj | — | — | ✓ | ✗ | 33 | — | In Meeting 14, is R. Malhotra the same person as R. Kumar? |
| E4 | aliases | board_meeting_14_transcript | Raj | ✓ | Board Meeting 14, Approve billing pipeline deploy | ✗ | ✗ | 31 | 100% | In Meeting 14, who approved the billing pipeline deploy? |
| C1 | conflict | finance_fy27_forecast, sales_fy27_forecast, board_meeting_15_transcript | Raj | ✓ | Finance FY27 ARR forecast, Finance FY27 Forecast, Sales FY27 ARR forecast, Sales FY27 Forecast | ✓ | ✓ | 14 | 100% | What FY27 ARR forecasts conflict, and which source reported each? |
| C2 | conflict | finance_fy27_forecast, sales_fy27_forecast, board_meeting_15_transcript | Raj | ✓ | FY27 ARR forecast | ✓ | ✗ | 10 | 100% | Which FY27 ARR forecast should the board treat as the winner? |
| K1 | coreference | board_meeting_16_transcript | Raj | ✗ | Board Meeting 16 | ✗ | ✓ | 1 | 0% | What does “that proposal” refer to in Meeting 16, and who owns it? |
| K2 | coreference | board_meeting_16_transcript | Raj | — | — | ✗ | ✗ | 1 | — | What does “the prior motion” refer to in Meeting 16? |
| A1 | grounding_adv | board_meeting_12_transcript | Raj | ✓ | Pricing Model B, Reject Pricing Model B | ✗ | ✓ | 56 | 100% | Who argued against the consumption-pricing model the board rejected? |
| A2 | grounding_adv | board_meeting_12_transcript | Raj | ✗ | Adopt Usage-Based Pricing | ✓ | ✓ | 43 | 100% | In the original board vote, who rejected the pay-per-use proposal? |
| A3 | grounding_adv | board_meeting_12_transcript | Raj | ✓ | Pricing Model B | ✓ | ✓ | 28 | 100% | Who backed dropping the metered-billing plan? |
| A4 | grounding_adv | board_meeting_12_transcript | Raj | ✗ | Adopt Usage-Based Pricing | ✓ | ✓ | 43 | 100% | Which board members weighed in on the usage-billing proposal the board turned down? |
| N1 | grounding_neg | board_meeting_12_transcript | Raj | — | — | ✓ | ✓ | 56 | — | Why was the dynamic pricing engine rejected? |
| N2 | grounding_neg | board_meeting_12_transcript | Raj | — | — | ✓ | ✓ | 0 | — | Who owns the customer churn dashboard? |
| X1 | rbac | compensation_review_CONFIDENTIAL | Marcus | — | — | ✓ | ✓ | 0 | — | What is Priya's base compensation? |
| X2 | rbac | compensation_review_CONFIDENTIAL | Raj | — | — | ✓ | ✓ | 0 | — | What is Priya's base compensation? |
| D1 | messy_email | messy_board_followup_email | Raj | ✓ | Vendor security questionnaire | ✓ | ✓ | 11 | 100% | Who owns the vendor-security questionnaire in the board follow-up email? |
| D2 | messy_email | messy_audit_followup_email | Raj | ✓ | SOC 2 evidence request | ✓ | ✓ | 1 | 100% | Who owns the SOC 2 evidence request in the forwarded audit email? |

## How to read this

- **graph facts** is how many facts the hybrid arm actually received. When it is 0 and the plan is shared, hybrid and vector-only see *identical* context — so any difference in their answers is model sampling noise (gpt-oss cloud ignores `temperature`), NOT the graph helping or hurting. Treat those rows as ties.
- **Vector-only correct vs Hybrid correct**: equal on `lookup` is the expected tie; hybrid > vector on `relational`/`multi_hop` is the graph earning its keep.
- **Graph-fact recall** is the mechanism check: it is the fraction of the question's required edges that reached the context. It is only meaningful for hybrid — vector-only has no graph context, so this column is graph-exclusive by construction.
- **`rbac` rows** are pass/fail on the guardrail, not retrieval quality: X1 (investor) passes only if the secret never appears; X2 (founder) passes only if the authorised answer does.

