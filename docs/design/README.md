# FinLit design documents

## Approved colour and typography reference

[Design System v1.3](design-system-v1.3.md) is the repository snapshot of the supplied [Google design document](https://docs.google.com/document/d/1Rz1CdPwluvpsZkYp_60xEtR4PgymB0ukOj_zI6MQwkw/edit?tab=t.ltp1jxuuxcp6), dated 27 October 2026 and read on 1 November 2026. It covers colour, light and dark themes, typography, financial numbers, components and accessibility. Preserve its FINAL, PROPOSED, CANDIDATE and TO DESIGN distinctions.

The Google document is the maintained source. This snapshot makes the specification available to repository readers; it is not automatically synchronised. If that source changes, update the snapshot and record the date and differences here.

## Latest direction

[Minimalism and motion](minimalism-and-motion.md) records the 1 November Mehman reference review, the product-and-services emphasis, the opening introduction, the demo implementation and the wider UI rollout. This supersedes the earlier homepage emphasis while preserving the colour/type reference and report-data requirements.

## Website review and implementation

[Landing page review](landing-page-review.md) expands the 1 November website review with the proposed public landing page, section order, content to move or remove, and acceptance checks. The user approved implementation on 1 November 2026 for the evening demo. See [implementation and demo checks](demo-implementation.md) for the delivered scope and verification.

The companion **FinLit Website Design Review.docx** contains the broader desktop and mobile review with screenshots. It remains the original review deliverable; implementation status is tracked separately so the findings and their resolution are distinguishable.

## Existing implementation references

- `frontend/src/styles/design-system.css` contains the v1.3 semantic foundation. Its presence does not mean all components follow the specification.
- `frontend/src/styles/finlit.css` and other page styles still contain earlier treatments. Compare rendered components with the specification during implementation.
- `design/tokens.json` and `design/build_tokens.py` are an earlier Carbon-based token pipeline. They have not been migrated to v1.3 in this documentation pass. Do not regenerate application styles from them on the assumption that they represent the approved specification.
- [brand-palette.md](../brand-palette.md) points to the current specification; its earlier ivory/black palette is superseded.
- [Layout and overlay guards](../LAYOUT-GUARD.md) document checks to retain during future redesign work.

## Continuing design review

The approved first pass leads with company search, a real Reliance sample and three research tasks. Use the demo to validate that emphasis and the default detail level with the team. Design cleanup must preserve model calculations, financial terminology, sources, disclosures and access controls.

## Workspace implementation

[Workspace UI pass](workspace-ui.md) records the signed-in page improvements, the financial-table CSS collision fix, and the light/dark and phone verification results.
