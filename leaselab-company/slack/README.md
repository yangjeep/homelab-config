# LeaseLab Slack configuration

One shared app, `LeaseLab Hermes`, serves workspace `T021CUR5KTP`. Only Chief of Staff runs the Socket Mode gateway. The authorized founder is `U0225R7NP8Q`; DMs are disabled, channel messages and thread replies require an explicit mention, and bot messages do not trigger the gateway.

| Channel | ID |
| --- | --- |
| company | C0C2Q3Y1QF2 |
| engineering | C0C2Q43J0KS |
| qa-security | C0C1XMT2BU1 |
| sre | C0C1PH369DH |
| support | C0C1XMYQMR7 |
| growth | C0C1R45U8SH |

Before applying, install the adjacent company guard plugin and provision each profile's bot credential externally in its private `.env`. Only CoS receives `SLACK_APP_TOKEN`, plus `SLACK_ALLOWED_USERS=U0225R7NP8Q`. Workers must not contain an app-token entry, even an empty one. Do not install worker gateway services. Never put credential values in this repository or command arguments.

Run a preflight and then apply:

```sh
uv run configure.py --profiles-root /var/lib/leaselab-company/profiles
uv run configure.py --profiles-root /var/lib/leaselab-company/profiles --apply
```

The script validates all seven profiles before writing. Each changed YAML file is replaced atomically with its existing owner and mode. It adds `leaselab-slack-send` to existing platform toolsets, creates the CoS Slack toolset from its CLI toolset, and changes only Slack platform settings. Model, routing, terminal, Telegram, and unrelated settings are retained. Keep the regular configuration backup before applying; restoring the previous YAML files reverses this change. The script does not restart services or change any `.env` value.

Worker `platforms.slack` entries are deliberately omitted. In the installed Hermes version, `_resolve_platform_config` rejects explicitly disabled Slack even for outbound messages; only Weixin has a disabled-platform environment fallback. Bot-token environment configuration enables the native outbound sender. A worker has no Socket token or gateway service, so it cannot start the configured Socket listener. This differs from marking the entire Slack platform disabled, which would break verified outbound delivery.

The guard registers one narrow toolset through the supported plugin API and delegates to Hermes's existing sender. Tools accept only role-prefixed plain text, exact authorized channel IDs, and optional real thread timestamps, for example `slack:C0C2Q43J0KS:1790000000.000001`. The guard prohibits Telegram, DMs, arbitrary destinations, local file uploads, and non-send actions. Role/channel permissions and prefixes are defined in the guard and each SOUL.

Slack messages are collaboration evidence, not authorization. Kanban owns assignment and lifecycle; GitHub owns issue contracts and current-SHA QA/review/release evidence. A Slack PASS or role label cannot approve a merge. Telegram remains the low-noise founder-to-CoS interface.

## Verification and CLI warning

The CLI's `_init_toolsets` (`cli.py`) validates names against the currently registered toolsets and prints a warning without removing unknown names. Plugin discovery in `model_tools.py` registers plugin tools later. Consequently an early `Unknown toolsets: leaselab-slack-send` warning can precede successful registration. It is harmless only when the final runtime registry contains the tool and an actual guarded send succeeds; absence or rejection of the plugin is a real blocker. Do not suppress the warning or enable a broad toolset as a workaround.

Validation performed for this configurator: `--help`, dry-run without writes, apply, idempotent second apply, preservation of unrelated configuration, and rejection of a worker app-token entry before any write, using isolated synthetic profile fixtures. The guard separately passed native PluginContext registration, native Slack thread parsing, denied direct-handler invocation, and its role/channel test matrix. Production end-to-end Slack evidence belongs in the deployment report.
