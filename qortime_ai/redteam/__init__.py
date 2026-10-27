"""Red-Team the Referee (Meta AI Developer Hackathon, built Oct 27 2026, in the event window).

Muse Wonder proposes receipt tampering attacks as structured JSON mutations (cached in ``fixtures/``). The harness
applies each one to a synthetic receipt signed by freshly generated TEST keys and runs the pre-existing, unmodified
``qor_receipt.receipt.verify_receipt``. Code, not a model, records whether each attack was accepted.

Muse Spark then explains the result. Every sentence must cite the fields it relies on, and a deterministic checker plus
a banned-word filter decide whether the text may be shown. AI never decides the verdict.
"""
