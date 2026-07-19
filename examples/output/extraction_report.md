# Reg-to-Evidence — LLM rule-extraction validation

An extractor proposes a typed rule from each manifest excerpt; each proposal is gated by schema validation, source-span/hash validation, and a gold diff before it is accepted. The LLM output never feeds a compliance judgment — the checker reads only the human-authored `rules.yaml`.

> The shipped extractor replays a committed cached response (no live model call is bundled). Swap it for a provider adapter to go live; the gates are unchanged.

- Candidates validated: **2**; accepted: **2/2**

| rule | schema | clause | span hash | gold diff | accepted |
|---|---|---|---|---|---|
| R2_finished_height | ok | ok | ok | — | **yes** |
| R1_glazing_ratio | ok | ok | ok | — | **yes** |

