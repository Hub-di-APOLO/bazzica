"""Genera i medaglioni SVG degli scienziati che danno il nome alle varianti (sfondo del gioco).

Uso: python tools/disegna_scienziati.py  -> bazzica/web/img/scienziati/*.svg
Disegni originali e stilizzati (nessuna foto o opera esistente).
"""
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "bazzica", "web", "img", "scienziati")
LINEA = "#3a1d0b"
PELLE = "#f6c9a0"


def medaglione(nome, sfondo, dietro="", vestito="", davanti="", extra_sfondo="", pelle=PELLE, bocca=None):
    bocca = bocca or '<path d="M88 113 Q100 123 112 113" fill="none" stroke="#3a1d0b" stroke-width="4" stroke-linecap="round"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 236">
<defs><clipPath id="c"><circle cx="100" cy="100" r="88"/></clipPath></defs>
<circle cx="100" cy="100" r="92" fill="{sfondo}" stroke="{LINEA}" stroke-width="7"/>
<g clip-path="url(#c)">
{extra_sfondo}
{dietro}
<rect x="87" y="126" width="26" height="28" fill="{pelle}" stroke="{LINEA}" stroke-width="4"/>
{vestito}
<ellipse cx="61" cy="96" rx="8" ry="12" fill="{pelle}" stroke="{LINEA}" stroke-width="4"/>
<ellipse cx="139" cy="96" rx="8" ry="12" fill="{pelle}" stroke="{LINEA}" stroke-width="4"/>
<ellipse cx="100" cy="92" rx="39" ry="45" fill="{pelle}" stroke="{LINEA}" stroke-width="4"/>
<ellipse cx="79" cy="107" rx="7" ry="4.5" fill="#ff8f8f" opacity=".55"/>
<ellipse cx="121" cy="107" rx="7" ry="4.5" fill="#ff8f8f" opacity=".55"/>
<circle cx="86" cy="93" r="5" fill="{LINEA}"/><circle cx="114" cy="93" r="5" fill="{LINEA}"/>
<circle cx="87.5" cy="91.5" r="1.6" fill="#fff"/><circle cx="115.5" cy="91.5" r="1.6" fill="#fff"/>
{bocca}
{davanti}
</g>
<circle cx="100" cy="100" r="92" fill="none" stroke="{LINEA}" stroke-width="7"/>
<path d="M18 196 L40 186 L160 186 L182 196 L160 206 L172 218 L100 214 L28 218 L40 206 Z" fill="#fff3c4" stroke="{LINEA}" stroke-width="5" stroke-linejoin="round"/>
<text x="100" y="205" text-anchor="middle" font-family="Fredoka, 'Baloo 2', Nunito, Arial, sans-serif" font-weight="700" font-size="{20 if len(nome) < 12 else 16}" fill="{LINEA}">{nome}</text>
</svg>'''


def giacca(colore, camicia="#ffffff", cravatta=None):
    s = f'<path d="M20 240 C25 175 60 150 100 150 C140 150 175 175 180 240 Z" fill="{colore}" stroke="{LINEA}" stroke-width="4"/>'
    s += f'<path d="M84 150 L100 178 L116 150 Z" fill="{camicia}" stroke="{LINEA}" stroke-width="3"/>'
    if cravatta:
        s += f'<path d="M96 156 L104 156 L107 182 L100 192 L93 182 Z" fill="{cravatta}" stroke="{LINEA}" stroke-width="3"/>'
    return s


SCIENZIATI = {
    "einstein": medaglione(
        "Einstein", "#8fd3ff",
        dietro='<path d="M44 96 C24 70 40 36 66 42 C72 18 98 22 104 34 C112 16 146 24 142 46 C168 42 178 80 156 96 C172 108 160 132 146 122 L140 82 Q100 60 60 82 L54 122 C40 132 28 108 44 96 Z" fill="#f4f4f4" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>',
        vestito=giacca("#8c8f99", "#d9d9d9"),
        davanti='<path d="M78 108 Q90 100 100 104 Q110 100 122 108 Q114 118 100 112 Q86 118 78 108 Z" fill="#f4f4f4" stroke="#3a1d0b" stroke-width="3.5"/>'
                '<path d="M76 80 l10 -3 M114 77 l10 3" stroke="#3a1d0b" stroke-width="4" stroke-linecap="round"/>',
        bocca='<path d="M92 120 Q100 125 108 120" fill="none" stroke="#3a1d0b" stroke-width="3.5" stroke-linecap="round"/>'),
    "curie": medaglione(
        "Marie Curie", "#d8b8ff",
        dietro='<circle cx="100" cy="40" r="17" fill="#5a3a22" stroke="#3a1d0b" stroke-width="4"/>'
               '<path d="M58 100 C50 52 150 52 142 100 C138 72 62 72 58 100 Z" fill="#5a3a22" stroke="#3a1d0b" stroke-width="4"/>',
        vestito='<path d="M20 240 C25 175 60 150 100 150 C140 150 175 175 180 240 Z" fill="#2f2f3a" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M84 150 Q100 166 116 150" fill="none" stroke="#fff" stroke-width="6"/>',
        davanti='<path d="M62 80 C70 54 98 50 100 62 C102 50 130 54 138 80 C124 66 106 64 100 70 C94 64 76 66 62 80 Z" fill="#5a3a22" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<circle cx="155" cy="150" r="9" fill="#9cff7a" stroke="#3a1d0b" stroke-width="3"/>'),
    "fermi": medaglione(
        "Fermi", "#9be3a8",
        vestito=giacca("#3b4252", "#ffffff", "#c0392b"),
        davanti='<path d="M62 84 C64 56 136 56 138 84 C130 70 116 66 100 68 C84 66 70 70 62 84 Z" fill="#2b2118" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'),
    "pascal": medaglione(
        "Pascal", "#ffc48a",
        dietro='<path d="M52 100 C36 46 164 46 148 100 C164 136 158 168 140 176 C128 178 132 140 136 112 Q100 66 64 112 C68 140 72 178 60 176 C42 168 36 136 52 100 Z" fill="#7a4b2a" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>',
        vestito='<path d="M20 240 C25 175 60 150 100 150 C140 150 175 175 180 240 Z" fill="#1f1f24" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M80 148 L120 148 L116 172 L100 166 L84 172 Z" fill="#fff" stroke="#3a1d0b" stroke-width="3"/>',
        davanti='<path d="M62 84 C66 52 134 52 138 84 C126 68 112 64 100 70 C88 64 74 68 62 84 Z" fill="#7a4b2a" stroke="#3a1d0b" stroke-width="4"/>'
                '<circle cx="58" cy="128" r="8" fill="#8a5a36" stroke="#3a1d0b" stroke-width="3"/><circle cx="142" cy="128" r="8" fill="#8a5a36" stroke="#3a1d0b" stroke-width="3"/>'),
    "heisenberg": medaglione(
        "Heisenberg", "#7fe0d6",
        vestito=giacca("#4a5a6a", "#ffffff", "#2d6cdf"),
        davanti='<path d="M58 86 C52 46 146 42 142 82 C130 64 104 58 84 66 C74 70 64 78 58 86 Z" fill="#e8c06a" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<path d="M84 66 C96 54 120 54 132 64" fill="none" stroke="#3a1d0b" stroke-width="3"/>'),
    "avogadro": medaglione(
        "Avogadro", "#ffe27a",
        vestito='<path d="M20 240 C25 175 60 150 100 150 C140 150 175 175 180 240 Z" fill="#2a2a40" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M80 144 L120 144 L118 164 L82 164 Z" fill="#fff" stroke="#3a1d0b" stroke-width="3"/>'
                '<path d="M88 160 L112 160 L106 172 L94 172 Z" fill="#111" stroke="#3a1d0b" stroke-width="3"/>',
        davanti='<path d="M60 88 C52 50 76 40 86 50 C92 38 112 38 116 50 C128 40 150 52 140 88 C134 70 118 62 100 64 C82 62 66 70 60 88 Z" fill="#2e2219" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<path d="M62 86 L66 118 L74 118 L72 88 Z M138 86 L134 118 L126 118 L128 88 Z" fill="#2e2219" stroke="#3a1d0b" stroke-width="3"/>'),
    "federico": medaglione(
        "Federico II", "#c9a8ff",
        vestito='<path d="M20 240 C25 175 60 150 100 150 C140 150 175 175 180 240 Z" fill="#b3263a" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M40 190 C60 176 140 176 160 190" fill="none" stroke="#fff3c4" stroke-width="8"/>',
        davanti='<path d="M60 84 C62 58 138 58 140 84 C126 72 74 72 60 84 Z" fill="#b5482a" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M62 102 Q64 142 100 144 Q136 142 138 102 Q128 128 100 130 Q72 128 62 102 Z" fill="#b5482a" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<path d="M66 64 L66 36 L80 50 L92 28 L100 46 L108 28 L120 50 L134 36 L134 64 Z" fill="#ffd23f" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<circle cx="100" cy="56" r="5" fill="#ff4fa3" stroke="#3a1d0b" stroke-width="2.5"/>',
        bocca='<path d="M90 120 Q100 127 110 120" fill="none" stroke="#3a1d0b" stroke-width="3.5" stroke-linecap="round"/>'),
    "hack": medaglione(
        "Margherita Hack", "#27335f",
        extra_sfondo=''.join(f'<path d="M{x} {y} l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3 z" fill="#ffe27a"/>'
                             for x, y in [(40, 40), (160, 52), (150, 150), (34, 140), (120, 22)]),
        vestito=giacca("#3d7bff", "#ffffff"),
        davanti='<path d="M58 94 C50 48 150 48 142 94 C138 70 120 62 100 64 C80 62 62 70 58 94 Z" fill="#e3e3e3" stroke="#3a1d0b" stroke-width="4" stroke-linejoin="round"/>'
                '<circle cx="86" cy="93" r="12" fill="none" stroke="#3a1d0b" stroke-width="4"/>'
                '<circle cx="114" cy="93" r="12" fill="none" stroke="#3a1d0b" stroke-width="4"/>'
                '<path d="M98 92 L102 92" stroke="#3a1d0b" stroke-width="4"/>'),
}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for k, svg in SCIENZIATI.items():
        with open(os.path.join(OUT, k + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    print(f"{len(SCIENZIATI)} medaglioni in {os.path.abspath(OUT)}")
