"""Stick Echo (built Oct 28 2026, Meta AI Developer Hackathon, Oct 26 - Nov 4 2026). INFO-ONLY, LOWER-ONLY.

Meta SAM 3.1 tracks the player the gamer controls (seeded on the game's own controlled-player marker) and the
on-screen movement of that player is compared with the left-stick log, at a lag fixed beforehand from the same
game's pause challenges (Challenge Echo). Agreement is the mean angle cosine against swapped-log nulls. The result
goes in a separate ``stickecho.sidecar.json``; ``receipt.v0.json`` is never touched. It never raises a status and
never makes the call: at most it suggests lowering VERIFIED to PARTIAL.
"""
