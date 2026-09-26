# Mnemo Email Ingestion

Mnemo-owned plugin code and documentation are proprietary: Copyright © 2026
Atharv Patil. All rights reserved. See the [distribution policy](../../docs/governance/active/proprietary_distribution_policy.md).

Optional, deterministic `ParserInterfaceV1` plugin implementing the ADR-0016
Email ingestion semantic boundary.

Supported inputs are `.eml`/`message/rfc822` and
`.mbox`/`application/mbox`. Outlook `.msg` is not supported.

The parser operates only on supplied bytes. It performs no remote acquisition,
filesystem access, storage access, UUID generation, or clock access.
