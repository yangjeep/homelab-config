# LeaseLab GitHub App bootstrap inventory

These registrations are not proof of runtime authority enforcement. Private keys
are retained in 1Password and six service-only broker PEM files; none is installed
in a role profile. The broker is live and six role repository reads passed. CoS,
Reviewer, QA and Growth ordinary broker tokens have no Contents-write permission.
The Reviewer App grant now includes service-only Contents/Checks write. Engineer
must remain uninstalled/unprovisioned until main/prod actor restrictions and
QA/review gates are enforced. Reviewer merge authority requires a trusted gated
service; the ordinary broker token never includes that authority.

| Role | App ID | Slug | Installation (only yangjeep/leaselab) | Private document in 1Password | Evidence |
| --- | --- | --- | --- | --- | --- |
| chief-of-staff | 4948371 | leaselab-chief-of-staff | 161803163 | 7af6mr2enu4jvu5jfrimhe5yqa | Live broker read passed; Contents/Metadata read, Issues/PR write |
| engineer | 4948533 | leaselab-engineer | NOT INSTALLED | No key generated | Registered only; branch-policy dependency unresolved |
| qa-security | 4948555 | leaselab-qa-security | 161806533 | 6brdaafo5253bfp6rx32btlnvq | Live broker read passed; CI/Contents read and Issues/PR write; App Checks write reserved service-side |
| reviewer | 4948588 | leaselab-reviewer | 161807039 | m4lgwpovo4blf6wt464q2avjhu | Live broker read passed; Actions/Checks/Statuses/Contents read, Issues/PR write; no merge token; App Contents/Checks write reserved for trusted services |
| growth | 4948599 | leaselab-growth | 161807370 | foa72lsg3t7dptmcaf7nr423aa | Live broker read passed; actual issue779 created by leaselab-growth[bot]; Contents/PR/Metadata read, Issues write; temporary token revoked |
| support | 4948622 | leaselab-support | 161807858 | vccaztp2y5mhwtuil2hsjiog4q | Live broker read passed; Contents/PR/Metadata read, Issues write |
| sre | 4948651 | leaselab-sre | 161808475 | 727civh35u3k7sd74n42x3onhi | Browser install confirmed; Actions/Checks/Statuses/Contents/Deployments/Issues/PR/Metadata read only |

All registered Apps have inactive webhooks and personal-account-only visibility.
No founder GitHub token was copied into an agent. Installation tokens used for
bootstrap validation were revoked immediately after the test.

For key rotation, generate a replacement private key in the exact App settings,
store it as an independent version/document in 1Password, cut over the trusted
credential service and validate exact repository/permissions, then delete the old
private key. Uninstall the individual App to revoke that identity's repository
access. Do not add all repositories or install Engineer as a shortcut around the
unfinished gates.

QA/Security update, September 15, 2026: Actions and Commit statuses read plus
Checks write were accepted on installation 161806533. The broker always requests
Checks **read**, regardless of the App's elevated grant. The trusted QA publisher
is not implemented; no QA check-write credential is available to the role shell.

Broker: `leaselab-github-broker.service`, socket `/run/leaselab-github/broker.sock`;
PEMs `/etc/leaselab-company/github/<role>.pem`, broker-owned 0600. Peer Unix UID
selects the fixed role; callers cannot request arbitrary scopes or another role.
All six enabled roles read the repository through this service; Engineer was
denied. Linux tests passed (36). Diagnostic tokens were revoked. Main/prod actor
rules, current-SHA QA/review and merge/release controllers remain incomplete.

Reviewer update, September 15, 2026: installation 161807039 now accepts App-level
Contents write and Checks write for the planned trusted merge/review services.
The ordinary Reviewer broker still requests **Contents read and Checks read**;
a freshly minted token was checked after the permission update, used for a
repository read, and revoked. The merge controller is implemented and tested
offline but remains disabled pending trusted publishers and branch rules.
