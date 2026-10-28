"""Challenge Echo (built Oct 27 2026, Meta AI Developer Hackathon, Oct 26 - Nov 4 2026). INFO-ONLY, LOWER-ONLY.

During a pause challenge the player presses OPTIONS, enters a D-pad pattern on the pause menu, then selects Resume.
Challenge Echo tracks the pause-menu highlight in the video (Meta SAM 3.1, box prompt) and checks that every logged
D-pad press is followed by the matching on-screen highlight move. It reports per-press press-to-pixel latency,
directions matched, and whether the menu appeared after the OPTIONS press. It never raises a status; at most it
suggests lowering VERIFIED to PARTIAL. It is not a referee input and does not touch the live referee.
"""
