"""Public, read-only "agent verify" API for QorTime matches.

Built Wed Oct 28 2026, during the Meta Global AI Developer Hackathon (Oct 26 - Nov 4 2026).

Any AI agent (for example a personal agent with a custom connector) can list the published QorTime matches, read one,
and re-check its signed receipt with the pre-existing deterministic verifier (``qor_receipt.receipt.verify_receipt``)
against the pinned referee key, plus the referee's public transparency log.

Rule for agents: only announce or record a result as VERIFIED when ``verified`` is true. The API never decides a
verdict itself; it re-runs the pre-existing verifier and reports what it returns. GET only, no auth, nothing is ever
written to the referee.
"""
