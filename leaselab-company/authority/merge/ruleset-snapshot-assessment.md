# Ruleset snapshot assessment — 2026-09-15

Decision: do not implement or wire a reduced-visibility snapshot validator as merge authorization. Runtime remains disabled. A snapshot comparison can provide useful drift detection, but the inspected GitHub contract does not establish that unchanged visible fields plus unchanged timestamp prove an unchanged hidden bypass list. No Python module or tests were added for an unsupported guarantee; existing merge policy/models/server are unchanged.

## Documented facts

GitHub intentionally omits `bypass_actors` unless the requester has write access to the ruleset. Repository ruleset reads require Metadata read; omission is not an empty bypass list. The collection supports pagination and `includes_parents=true`; target filters can narrow the inventory. Repository ruleset history and historical-version reads require Administration write. [REST rules API](https://docs.github.com/en/rest/repos/rules?apiVersion=2026-03-10#get-a-repository-ruleset).

GraphQL describes `updatedAt` as the last-update time. It also exposes a nullable, paginated bypass-actor connection, but the reference does not establish an unprivileged complete-view guarantee. [RepositoryRuleset reference](https://docs.github.com/en/graphql/reference/repos#repositoryruleset).

REST pagination uses response links to traverse additional pages. A first page alone is not complete inventory. [Pagination documentation](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api).

## Empirical evidence and its boundary

The parent-produced `outputs/leaselab-company/ruleset-drift-probe.json` records disabled ruleset 23416864 with bypass counts 0 → 1 → 0. Both credential views returned matching timestamps at each sample: `02:31:13.170`, `02:31:16.621`, and `02:31:20.063` (UTC−04:00). The reduced view omitted bypass actors throughout, and its `current_user_can_bypass` stayed `never`. The probe records deletion of the temporary rule.

This establishes successful detection of those two spaced bypass-only updates. It does not establish collision-free timestamps, a monotonic revision counter, atomicity between bypass writes and timestamp visibility, consistency across list/detail/projection endpoints, or complete visibility for future inherited rulesets. These are missing guarantees, not demonstrated GitHub defects. `current_user_can_bypass` also cannot identify whether another actor was added.

## Why the proposed authorization inference is unsupported

A root-owned administrative snapshot protects local integrity. Exact comparison of ID, source, enforcement, conditions, rules, creation/update timestamps and every visible semantic field improves drift detection. Complete inventory comparison catches additional/deleted IDs and new inherited policies. None of those checks reconstruct a currently hidden field.

The critical implication would be: visible projection and timestamp equal baseline ⇒ hidden bypass actors equal baseline. The sources reviewed do not specify that implication. Synthetic tests that assert an increment on every hidden mutation would encode the assumption, not verify GitHub's behavior. Repeating the probe more times would strengthen empirical confidence without turning a timestamp into a documented authorization revision.

An admin snapshot is consequently acceptable as evidence of bootstrap state, or as a fail-on-observed-change monitor. It is not sufficient to reopen a gate whose required bypass evidence is currently missing. Do not substitute `[]`, a cached bypass list, or the caller's bypass capability for the missing live actor list.

## Requirements if this direction is revisited

A defensible solution needs authoritative current bypass evidence, or a documented provider contract binding an observable revision to the entire ruleset state. The latter contract has not been found. An on-demand privileged observer might reduce credential lifetime relative to a continuously running observer, but it still requires a separately designed, constrained privileged trust boundary; no such service is introduced here.

Any future snapshot implementation must acquire a complete administrative inventory including parents and all pages, pin the exact expected ruleset IDs and repository identity, compare full visible semantic payloads without dropping unknown fields, fail on missing/ambiguous/paginated evidence, preserve role-dependent fields separately, protect snapshot ownership and update paths, and re-check before mutation. Multi-request inventory coherence and the final policy-check-to-merge race need explicit treatment. These requirements are necessary, not sufficient to cure hidden bypass uncertainty.

No live GitHub settings, rules, credentials, merges, service state or commits were touched by this assessment. Public documentation was read. No runtime or deployment safety claim is made.
