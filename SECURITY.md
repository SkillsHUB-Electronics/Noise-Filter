# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub:
**[Report a vulnerability](https://github.com/SkillsHUB-Electronics/Noise-Filter/security/advisories/new)**
(Security tab › Advisories › Report a vulnerability).

Don't open a public issue or pull request for a vulnerability until a fix is released.

Useful to include:
- the Noise Filter version (Settings › About) and your Windows version;
- what an attacker can do, and what they need (a crafted audio file, access to the control pipe,
  a local account, a network position…);
- steps or a sample file that reproduce it.

We'll acknowledge the report, keep you updated while we work on a fix, and credit you in the
advisory unless you'd rather not be named.

## Supported versions

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Older releases | ❌ (please update) |

Fixes go into the default branch and ship in the next release.

## Scope

In scope:
- the desktop app, `nfctl` and the MCP server (for example a way for another Windows user or a
  remote machine to reach the control pipe);
- the installer and the AI model update (for example a way to make the app load an unverified model);
- the sample intake Worker in `cloud/worker/` (for example reading or deleting other users' samples,
  or getting into the review page without the password);
- anything that makes the app send data the [privacy policy](PRIVACY.md) does not list.

Out of scope: VB-CABLE, Windows, Qt and other third-party components (report those upstream),
and denial of service that needs local administrator rights.
