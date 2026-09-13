# Grafana Cloud consolidation

These configurations supplement the existing local homelab dashboards using native Cloud data sources. They do not install another collector or duplicate all local telemetry.

## OpenRouter

Generate the importable dashboard with:

```sh
jq -n -f openrouter-dashboard.jq > openrouter-dashboard.json
```

Replace `${DS_TEMPO}` with the actual existing Cloud Tempo datasource UID at deployment. Credentials are never part of the dashboard.

The dashboard counts only native `LLM Generation` spans. Child provider attempts must not be added to request, token, or cost totals. Application identity comes from `span.trace.metadata.openrouter.api_key_name`; serving provider comes from `span.trace.metadata.openrouter.provider_name`, not the model vendor in `gen_ai.provider.name`.

Native TraceQL metrics avoids a polling exporter and a second copy of inference data. Queries are bounded by a default 24-hour window, five-minute steps, and five-minute refresh. Percentiles are approximate Tempo estimates. First-token float quantiles returned no series on this tenant; the dashboard uses an honestly labeled mean for that field.

The stat reducer explicitly selects the five configured application names. The live Tempo datasource returned exemplar frames even when requested with `exemplars: 0`; their numeric `Value` fields must never contribute to request/cost/token totals. Zero-based provider-attempt indices greater than zero count additional attempts.

Latency queries filter positive values after aggregation: this tenant fills idle quantile intervals with zero, which would otherwise display a false zero-latency reading. Usage counters have neutral colors rather than Grafana's default numeric alert thresholds.

Additional provider attempts are distinct from affected requests and from application-level cross-model fallback. The latter can be validated using an isolated Hermes invocation and its actual GLM response trace, but a GLM trace by itself does not establish why the application selected it.

Privacy Mode is OFF under the user's explicit override. OpenRouter's separate Input/Output Logging remains OFF. Raw contents may reach Cloud Tempo and are excluded from repository artifacts and operational reports. The earlier metadata-only byte estimate is not a valid forecast for full-content trace ingestion; measure actual Cloud usage before changing sampling or retention.

## Cloudflare

`cloudflare-workers.graphql` is a bounded native Workers Analytics query for the six discovered LeaseLab Workers. `cloudflare-datasource.json` is the nonsecret Infinity datasource definition. Inject its account-scoped Analytics Read token into the datasource's protected bearer-token field at deployment. Preserve the allowed-host restriction.

This path queries existing analytics rather than ingesting full access logs. CPU quantiles are CPU time, not request wall duration. Free website zones do not satisfy the official zone integration's Pro-or-better prerequisite; that does not prevent the separate Workers Analytics path.

## Verification and lifecycle

`business-alert-rules.json` contains three native warning rules: at least three root OpenRouter errors in 15 minutes, Hermes estimated spend above USD 0.25 in one hour, and at least five production Worker errors in 15 minutes, each sustained for five minutes. These are explicit initial operational thresholds, not learned baselines. Idle/no-data windows remain OK; datasource failures remain Error. Apps Script rules live in the adjacent collector directory. Contact points and severity routing belong to the separate Hermes integration.

Deployment is complete only after live datasource health/query and rendered-dashboard checks. Source files alone are not a pass. Safe query results and deployment receipts belong in the task's evidence directory, not raw API responses containing credentials or content.

Cloud write policy `homelab-alloy-write` has only `metrics:write` and `logs:write`. Its 90-day token must be renewed before expiry. Existing Alloy handles the Apps Script forwarding configuration maintained beside its collector. No token value is tracked here.
