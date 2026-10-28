"""Draws docs/stick-echo/totals.png from the TOTALS below (offline re-score of two private practice games, Oct 28 2026).
Totals only: lowest z over the three swapped-log nulls and frames scored. Needs matplotlib (not a repo dependency)."""
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np
# totals only (min z over the three null sources, frames scored); from the offline re-score of Oct 28 2026
G = {'Practice game A (first test)': [('SAM only\npre-registered', 2.68, 222, True), ('Hybrid\nselection', 2.02, 189, False), ('Hybrid +\nheld-out offset', 2.81, 191, False)],
     'Practice game B': [('SAM only\npre-registered', 3.11, 543, True), ('Hybrid\nselection', 3.67, 519, False), ('Hybrid +\nheld-out offset', 4.45, 514, False)]}
bg, fg, acc, mut = '#04050a', '#e8eef6', '#2ef2ff', '#7d8796'
fig, axs = plt.subplots(1, 2, figsize=(11, 4.6), facecolor=bg, sharey=True)
for ax, (title, rows) in zip(axs, G.items()):
    ax.set_facecolor(bg)
    x = np.arange(len(rows))
    for xi, (lab, z, n, pre) in zip(x, rows):
        ax.bar(xi, z, 0.6, color=acc if pre else 'none', edgecolor=acc if pre else mut, hatch=None if pre else '//', lw=1.5)
        ax.text(xi, z + 0.08, f'min z {z:.2f}\n{n} frames', ha='center', va='bottom', color=fg, fontsize=9, bbox=dict(facecolor=bg, edgecolor='none', pad=1.5))
    ax.axhline(3, color='#ff4d5e', ls='--', lw=1.2)
    ax.text(-0.4, 5.2, '- - -  bar: z ≥ 3 against every null', color='#ff4d5e', fontsize=8, ha='left', va='top')
    ax.set_xticks(x); ax.set_xticklabels([r[0] for r in rows], color=fg, fontsize=9)
    ax.set_title(title, color=fg, fontsize=11)
    ax.tick_params(colors=fg); [s.set_color(mut) for s in ax.spines.values()]
    ax.set_ylim(0, 5.4)
axs[0].set_ylabel('lowest z over 3 swapped-log nulls', color=fg)
fig.suptitle('Stick Echo: controller and video agreement, totals only (solid = pre-registered, hatched = exploratory)', color=fg, fontsize=11)
fig.text(0.5, 0.01, 'Two private offline practice games, never submitted. Info only, lower-only, capped at PARTIAL. Built Oct 28 2026.', ha='center', color=mut, fontsize=8)
fig.tight_layout(rect=(0, 0.04, 1, 0.94))
fig.savefig(__import__('pathlib').Path(__file__).with_name('totals.png'), dpi=110, facecolor=bg)
