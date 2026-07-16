# Meridian governed workflow design artifacts

**Status:** design research artifact; not P0/P3 implementation.

## Research inputs

- `PRD.md`: human control, evidence, permission, answer/citation, and review requirements.
- `ROADMAP.md`: P0 remains blocked by R13; a static prototype must not be called a product.
- Supplied `Meridian Dashboard.dc.html`: board-workspace shell, low-noise typography, source
  badges, persistent Ask Meridian framing, and preparation context.

The supplied prototype depicts broad dashboard and meeting workflows. This artifact narrows
the scope to trust-critical moments: evidence in an answer, approval of a proposal, and
citation disclosure.

## Artifact

[Open the static governed-workflow prototype](../../design/meridian-governed-workflows.html)

The demo uses fabricated local content and browser-local state. That is deliberate: no
mockup should imply that AI can approve a fact, mutate memory, assign an owner, or send an
external message.

| Surface | Required visible state | Prohibited implication |
|---|---|---|
| Grounded chat | Approved graph fact, readable citation, explicit gap, aggregate withheld count | A citation/title/quote/entity hint for unreadable content; unsupported claim |
| Approval review | Exact quote, source, span, confidence, review policy, individual disposition | Silent graph write, sensitive bulk approval, discarded rejection |
| Citation drawer | Exact quote, document, chunk/span, access basis, provenance status | Paraphrase as evidence; disclosure of withheld content |

## Design decisions

1. **Separate claim layers.** Approved graph facts and source text have different visual
   treatments so a fluent answer cannot blur proposal, evidence, and approved fact.
2. **Citation is inspection.** The drawer makes document, exact quote, span, access basis,
   and provenance auditable together.
3. **Withholding is boring.** The UI may show an aggregate count but never source titles,
   entity names, quotes, or descriptions that form a side channel.
4. **Approval is consequential.** There is no approve-all control. Confirmation is visible
   even in the local simulation; product code would also require authorization and audit
   persistence before replay-safe graph writing.
5. **Accessible primitives first.** Native buttons/inputs, labels, visible focus, live
   answer output, and a labelled drawer close control are built in. Production still needs a
   WCAG audit.

## Requirement traceability

| PRD requirement | Design evidence |
|---|---|
| FR-LIVE-04 / FR-LIVE-05 | Consequential fields remain proposed until explicit human review; no silent inference. |
| FR-DEC-01 / FR-DEC-03 | Chat separates decision facts, evidence, stakeholders, ownership, and source passage. |
| FR-DEC-04 | Each proposal exposes an individual quote, confidence, source, and review disposition. |
| FR-DEC-06 | Answers expose readable source-backed decision context. |
| AI governance / quality | Opaque withholding, source-backed citation, and no represented AI write path. |
| NFR accessibility / explainability | Semantic controls, focus styling, live response, and inspectable provenance. |

## Questions for P0/P3 (not answered by this artifact)

- Which roles may approve which proposal types, and when is re-authentication required?
- How does future object-level policy avoid leaking titles or existence through the UI?
- How are return-for-revision reasons, conflicts, and superseded decisions represented?
- Which citation fields are safe under the current clearance-only model?

## Validation

`tests/test_design_artifacts.py` checks the static governance contract and confirms no network
or API surface is introduced. Manually follow `design/README.md` for interaction review. This
does not change the R8-R13 gate or authorize P0.
