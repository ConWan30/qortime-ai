"""Generate QorTime AI hero banners (dark/light) in the QorTime brand style. Text is converted to paths."""
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen

BS = '/usr/share/fonts/truetype/sand-box/custom/Big Shoulders Display/BigShouldersDisplay[wght].ttf'
JB = '/usr/share/fonts/truetype/sand-box/google/JetBrains Mono/JetBrainsMono-VariableFont_wght.ttf'

def load(p, w):
    f = TTFont(p); return instantiateVariableFont(f, {'wght': w})

FONTS = {'bs': load(BS, 900), 'jb': load(JB, 500), 'jbb': load(JB, 700)}

def text(font, s, x, y, size, fill, track=0.0, anchor='start'):
    f = FONTS[font]; upm = f['head'].unitsPerEm; gs = f.getGlyphSet(); cmap = f.getBestCmap(); hm = f['hmtx']
    sc = size / upm
    width = sum(hm[cmap[ord(c)]][0] * sc + track for c in s) - track
    if anchor == 'middle': x -= width / 2
    elif anchor == 'end': x -= width
    out = []; cx = x
    for c in s:
        g = cmap[ord(c)]
        if c != ' ':
            pen = SVGPathPen(gs); gs[g].draw(pen); d = pen.getCommands()
            if d: out.append(f'<path transform="translate({cx:.2f},{y:.2f}) scale({sc:.6f},{-sc:.6f})" d="{d}" fill="{fill}"/>')
        cx += hm[g][0] * sc + track
    return ''.join(out), width

PAL = {
 'dark': dict(bg='#04050a', g0='#0c2c34', p0='#0a1640', aqua='#2ef2ff', blue='#4f7cff', ink='#f4f7ff', muted='#7d8796',
              node='#061016', strip='#0a1018', hole='#04050a', pillfill='rgba(46,242,255,0.10)', pillstroke='rgba(46,242,255,0.55)',
              pilltext='#a8fbff', dash='rgba(46,242,255,0.55)', mutedash='rgba(125,135,150,0.55)', brk='rgba(125,135,150,0.75)'),
 'light': dict(bg='#f4f6f8', g0='#d9f4f6', p0='#d5e0fb', aqua='#056775', blue='#1d4ed8', ink='#07111c', muted='#6b7480',
              node='#ffffff', strip='#e4e8ee', hole='#f4f6f8', pillfill='rgba(5,103,117,0.08)', pillstroke='rgba(5,103,117,0.55)',
              pilltext='#044f5a', dash='rgba(5,103,117,0.65)', mutedash='rgba(107,116,128,0.55)', brk='rgba(107,116,128,0.8)'),
}

def hero(mode):
    c = PAL[mode]; o = []
    o.append('<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640" role="img">')
    o.append('<title>QorTime AI</title><desc>QorTime AI. Meta Muse explains the referee\'s result; it never decides it. '
             'Meta Global AI Developer Hackathon, Indie Developer track. Pipeline: receipt and referee (pre-existing), then explain, attack and see (built this week with Meta models).</desc>')
    o.append(f'<defs><radialGradient id="g" cx="0.08" cy="0.0" r="0.9"><stop offset="0" stop-color="{c["g0"]}"/><stop offset="0.62" stop-color="{c["bg"]}"/></radialGradient>'
             f'<radialGradient id="p" cx="1.0" cy="1.1" r="0.6"><stop offset="0" stop-color="{c["p0"]}" stop-opacity="0.85"/><stop offset="1" stop-color="{c["bg"]}" stop-opacity="0"/></radialGradient></defs>')
    o.append(f'<rect width="1280" height="640" fill="{c["bg"]}"/><rect width="1280" height="640" fill="url(#g)"/><rect width="1280" height="640" fill="url(#p)"/><rect width="8" height="640" fill="{c["aqua"]}"/>')
    # clock mark (QorTime brand)
    o.append(f'<g transform="translate(60.0,92.0) scale(4.1500)"><circle cx="32" cy="32" r="27" fill="none" stroke="{c["aqua"]}" stroke-width="5"/>'
             f'<g stroke="{c["aqua"]}" stroke-width="3" stroke-linecap="round" fill="none"><path d="M32 9v5M55 32h-5M32 55v-5M9 32h5"/></g>'
             f'<path d="M32 32V19" stroke="{c["ink"]}" stroke-width="5" stroke-linecap="round"/><g><animateTransform attributeName="transform" type="rotate" from="0 32 32" to="360 32 32" dur="16s" repeatCount="indefinite"/>'
             f'<path d="M32 32l17 17" stroke="{c["blue"]}" stroke-width="6" stroke-linecap="round"/><circle cx="32" cy="32" r="5" fill="{c["blue"]}"/></g></g>')
    x0, base = 360.0, 290.0
    s, w1 = text('bs', 'QOR', x0, base, 196, c['ink'], track=6); o.append(s)
    s, w2 = text('bs', 'TIME', x0 + w1 + 10, base, 196, c['blue'], track=6); o.append(s)
    ax = x0 + w1 + 10 + w2 + 26
    # "AI" chip
    s, wa = text('bs', 'AI', 0, 0, 120, c['aqua'], track=4)
    chip_w = wa + 44
    o.append(f'<rect x="{ax:.1f}" y="{base-130:.1f}" width="{chip_w:.1f}" height="130" rx="18" fill="none" stroke="{c["aqua"]}" stroke-width="5"/>')
    s, _ = text('bs', 'AI', ax + 22, base - 20, 120, c['aqua'], track=4); o.append(s)
    # tagline
    s, wt = text('jb', 'MUSE EXPLAINS.  IT NEVER DECIDES.', x0 + 4, base + 62, 34, c['aqua'], track=1.2); o.append(s)
    # pill
    pill = 'META GLOBAL AI DEVELOPER HACKATHON  ·  INDIE TRACK'
    s, wp = text('jb', pill, x0 + 20, base + 120, 24, c['pilltext'], track=0.8)
    o.append(f'<rect x="{x0+2:.1f}" y="{base+90:.1f}" width="{wp+36:.1f}" height="42" rx="21" fill="{c["pillfill"]}" stroke="{c["pillstroke"]}" stroke-width="1.5"/>'); o.append(s)
    # pipeline
    y = 506.0
    xs = [250.0, 410.0, 610.0, 790.0, 970.0]
    labels = ['RECEIPT', 'REFEREE', 'EXPLAIN', 'ATTACK', 'SEE']
    subs = ['signed', 'deterministic', 'Muse Spark', 'Muse Wonder', 'SAM 3.1']
    o.append(f'<line x1="{xs[0]}" y1="{y}" x2="{xs[1]}" y2="{y}" stroke="{c["mutedash"]}" stroke-width="2" stroke-dasharray="4 8"/>')
    o.append(f'<line x1="{xs[1]}" y1="{y}" x2="{xs[4]}" y2="{y}" stroke="{c["dash"]}" stroke-width="2" stroke-dasharray="4 8"/>')
    for i, (x, lab, sub) in enumerate(zip(xs, labels, subs)):
        col = c['muted'] if i < 2 else c['aqua']
        o.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{c["node"]}" stroke="{col}" stroke-width="2.5"/><circle cx="{x}" cy="{y}" r="3.5" fill="{col}"/>')
        s, _ = text('jbb', lab, x, y + 46, 26, c['ink'] if i >= 2 else c['muted'], track=1.0, anchor='middle'); o.append(s)
        s, _ = text('jb', sub, x, y + 72, 18, col, track=0.3, anchor='middle'); o.append(s)
    # brackets above nodes: pre-existing vs built this week
    def bracket(x1, x2, label, col, tcol):
        yb = y - 34
        o.append(f'<path d="M{x1} {yb+8}V{yb}H{x2}V{yb+8}" fill="none" stroke="{col}" stroke-width="1.5"/>')
        s, _ = text('jb', label, (x1 + x2) / 2, yb - 9, 16, tcol, track=1.2, anchor='middle'); o.append(s)
    bracket(xs[0] - 40, xs[1] + 40, 'PRE-EXISTING', c['brk'], c['muted'])
    bracket(xs[2] - 60, xs[4] + 40, 'BUILT THIS WEEK  ·  META MODELS', c['pillstroke'], c['aqua'])
    vals = ';'.join(f'{x}' for x in xs + [xs[0]])
    o.append(f'<circle cx="{xs[0]}" cy="{y}" r="5.5" fill="{c["blue"]}"><animate attributeName="cx" values="{vals}" dur="7s" repeatCount="indefinite"/></circle>')
    # film strip
    o.append(f'<rect x="0" y="624.0" width="1280" height="26" fill="{c["strip"]}"/>')
    o.append(''.join(f'<circle cx="{18+24*i}" cy="636.0" r="6.5" fill="{c["hole"]}"/>' for i in range(54)))
    o.append('</svg>')
    return ''.join(o)

if __name__ == '__main__':
    import sys
    out = sys.argv[1]
    for m in ('dark', 'light'):
        open(f'{out}/hero-{m}.svg', 'w').write(hero(m))
