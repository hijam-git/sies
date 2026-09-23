"""Template + context → one print-ready HTML document (docs/07 §8).

**HTML and CSS print, rendered in the browser. Not a PDF library.** The reason
is the first line of the form: this page carries Bangla *and* Arabic, and
complex-script shaping is the whole problem. Browsers do it correctly and for
free; Python PDF libraries need font configuration and still break ligatures.
Editing a template is also instant feedback in a preview pane, and it adds no
dependency. Server-side PDF is V2, at which point WeasyPrint renders *this same
HTML*.

**Two modes, one template** (§7):

* `blank` — every placeholder and every answer becomes an empty rule. Madrasahs
  print these in a stack at admission season and fill them in by hand.
* `filled` — the same document with the applicant's data on the rules.

They are the same code path with a different context, deliberately: supporting
only the filled case would mean the printed stack came from a different Word
file, and the printed stack is the one the guardian signs.

Everything here works on **plain dictionaries**, never on model instances. That
is what lets `PrintedForm.snapshot` be re-rendered years later by
`render_document()` with no database read at all — the snapshot *is* the
argument list.
"""

from django.utils.html import escape

from .placeholders import resolve

# Self-hosted faces, never a Google Fonts link: a form must print correctly on
# a school computer with no internet (docs/07 §8).
#
# The @font-face rules are NOT optional decoration. An earlier version named
# SolaimanLipi and Kalpurush -- faces nobody had shipped -- and declared no
# @font-face at all, so the browser silently fell back to a system font. The
# one document in this system that MUST look right on paper was the one
# rendering in whatever the machine happened to pick.
#
# The files are real and committed under the SPA's public/fonts, served from
# the same origin as this HTML, so the absolute paths resolve whether the
# form is previewed in an iframe or opened on its own.
FONT_BASE = '/myadmin/fonts'

# One face per weight. The unicode-range slices the SPA uses are deliberately
# NOT used here: a printed form is two pages and fetches everything anyway, and
# leaving the ranges out means a missing slice cannot drop a glyph mid-sentence
# on a document someone is about to sign.
_FACES = [
    ('Hind Siliguri', 400, 'HindSiliguri-400-0.woff2'),
    ('Hind Siliguri', 400, 'HindSiliguri-400-2.woff2'),
    ('Hind Siliguri', 600, 'HindSiliguri-600-0.woff2'),
    ('Hind Siliguri', 600, 'HindSiliguri-600-2.woff2'),
    ('Hind Siliguri', 700, 'HindSiliguri-700-0.woff2'),
    ('Hind Siliguri', 700, 'HindSiliguri-700-2.woff2'),
    ('Amiri', 400, 'Amiri-400-0.woff2'),
    ('Amiri', 400, 'Amiri-400-2.woff2'),
    ('Amiri', 700, 'Amiri-700-0.woff2'),
]

FONT_FACES = '\n'.join(
    "@font-face {{ font-family: '%s'; font-weight: %d; font-style: normal; "
    "font-display: swap; src: url('%s/%s') format('woff2'); }}"
    % (family, weight, FONT_BASE, filename)
    for family, weight, filename in _FACES
)

BANGLA_STACK = "'Hind Siliguri', 'Kohinoor Bangla', 'Noto Sans Bengali', sans-serif"
ARABIC_STACK = "'Amiri', 'Scheherazade New', 'Traditional Arabic', serif"


def _css(paper='A4', margins='12mm 14mm'):
    return f"""
{FONT_FACES}
@page {{ size: {paper}; margin: {margins}; }}
* {{ box-sizing: border-box; }}
body {{
  font-family: {BANGLA_STACK};
  font-size: 12pt; line-height: 1.9; color: #000; background: #fff;
  margin: 0;
}}
.sheet {{ max-width: 190mm; margin: 0 auto; }}
.ar {{ font-family: {ARABIC_STACK}; font-size: 16pt; direction: rtl; }}
.letterhead {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 6px; }}
.letterhead .name {{ font-size: 18pt; font-weight: 700; }}
.letterhead .sub {{ font-size: 11pt; }}
.meta-row {{ display: flex; flex-wrap: wrap; gap: 4mm; margin: 4mm 0; font-size: 11pt; }}
.meta-row .cell {{ flex: 1 1 auto; white-space: nowrap; }}
.prose {{ text-align: justify; margin: 3mm 0; }}
.prose.indent {{ text-indent: 8mm; }}
.grid {{ display: grid; gap: 2mm 6mm; margin: 3mm 0; }}
.grid .cell {{ display: flex; align-items: flex-end; gap: 2mm; }}
.grid .label {{ white-space: nowrap; }}
/* The rule is a line to WRITE on, so it belongs under the blanks and nowhere
   else. A value that has been filled in prints as text: underlining it as well
   reads as emphasis — or worse, as a correction — on a document somebody signs
   and files, and the form is already legible as a form from its labels. */
.rule {{ display: inline-block; min-width: 32mm; flex: 1 1 auto;
        border-bottom: 1px dotted #000; height: 1.25em; vertical-align: baseline; }}
.rule.filled {{ border-bottom: none; font-weight: 600; }}
.line {{ display: block; border-bottom: 1px dotted #000; height: 1.6em; margin-top: 2mm; }}
.section-title {{ font-weight: 700; text-align: center; margin: 4mm 0 2mm; }}
.q {{ margin: 1.5mm 0; }}
.q .choices {{ display: flex; flex-wrap: wrap; gap: 5mm; }}
.box {{ border: 1px solid #000; padding: 3mm; margin: 4mm 0; }}
.box > .title {{ font-weight: 700; text-align: center; margin-bottom: 2mm; }}
.panels {{ display: flex; gap: 4mm; }}
.panels > .panel {{ flex: 1 1 0; border: 1px solid #000; padding: 2mm; }}
.signatures {{ display: flex; justify-content: space-between; gap: 8mm;
              margin-top: 10mm; }}
.signatures .sig {{ flex: 1 1 0; text-align: center; }}
.signatures .sig .space {{ border-bottom: 1px solid #000; height: 12mm; }}
.bullets {{ margin: 2mm 0 2mm 6mm; padding: 0; }}
.bullets li {{ margin-bottom: 1mm; text-align: justify; }}
hr.divider {{ border: none; border-top: 1px solid #000; margin: 3mm 0; }}
.page-break {{ break-before: page; page-break-before: always; }}
@media print {{
  .no-print {{ display: none; }}
  .box, .signatures, .q {{ break-inside: avoid; }}
}}
""".strip()


def _rule(value, *, min_width=None):
    """A value on a rule, or an empty rule of the same width.

    The one function that makes blank mode and filled mode the same template: an
    empty value is not an error and not a gap, it is a line to write on.
    """
    style = f' style="min-width:{min_width}"' if min_width else ''
    if value:
        return f'<span class="rule filled"{style}>{escape(value)}</span>'
    return f'<span class="rule"{style}></span>'


def _resolved(text, context):
    """A prose string with its placeholders turned into rules."""
    out = []
    for part in resolve(text, context):
        if part[0] == 'text':
            out.append(escape(part[1]))
        else:
            out.append(_rule(part[2]))
    return ''.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Blocks
# ─────────────────────────────────────────────────────────────────────────────

def _letterhead(block, context):
    parts = ['<div class="letterhead">']
    for line in block.get('lines_ar', []):
        parts.append(f'<div class="ar">{_resolved(line, context)}</div>')
    lines = block.get('lines') or ['{{branch.name_bn}}', '{{branch.address_bn}}']
    for index, line in enumerate(lines):
        css_class = 'name' if index == 0 else 'sub'
        parts.append(f'<div class="{css_class}">{_resolved(line, context)}</div>')
    parts.append('</div>')
    return ''.join(parts)


def _meta_row(block, context):
    cells = ''.join(
        f'<span class="cell">{escape(field.get("label", ""))} '
        f'{_resolved(field.get("value", ""), context)}</span>'
        for field in block['fields']
    )
    return f'<div class="meta-row">{cells}</div>'


def _prose(block, context):
    # The Bangla text is what prints; the English is the editor's reference and
    # a fallback for a template that has not been translated yet (CLAUDE.md §8
    # rule 9 — both languages, never retrofitted).
    text = block.get('text_bn') or block.get('text', '')
    indent = ' indent' if block.get('indent') else ''
    align = block.get('align')
    style = f' style="text-align:{align}"' if align else ''
    return f'<p class="prose{indent}"{style}>{_resolved(text, context)}</p>'


def _field_grid(block, context):
    columns = block.get('columns', 2)
    cells = ''.join(
        f'<div class="cell"><span class="label">'
        f'{escape(field.get("label_bn") or field.get("label", ""))} :</span>'
        f'{_resolved(field.get("value", ""), context)}</div>'
        for field in block['fields']
    )
    title = block.get('title_bn') or block.get('title')
    heading = f'<div class="section-title">{escape(title)}</div>' if title else ''
    return (f'{heading}<div class="grid" '
            f'style="grid-template-columns:repeat({columns},1fr)">{cells}</div>')


def _checkbox(label, checked):
    return f'{"☑" if checked else "☐"} {escape(label)}'


def _question(question, answer):
    """One question, printed the way its `print_style` says (§5.1)."""
    label = escape(question.get('text_bn') or question.get('text', ''))
    qtype = question.get('type', 'short_text')
    style = question.get('print_style', 'inline')

    if qtype in ('single_choice', 'multi_choice') and style == 'checkbox':
        chosen = answer if isinstance(answer, list) else ([answer] if answer else [])
        boxes = ''.join(
            f'<span>{_checkbox(option.get("label_bn") or option.get("label", ""), option.get("value") in chosen)}</span>'
            for option in question.get('options', [])
        )
        return f'<div class="q">{label} : <span class="choices">{boxes}</span></div>'

    if qtype == 'yes_no':
        return (f'<div class="q">{label} : <span class="choices">'
                f'<span>{_checkbox("হ্যাঁ", answer is True)}</span>'
                f'<span>{_checkbox("না", answer is False)}</span></span></div>')

    if qtype == 'description' or style == 'block':
        lines = ''.join(
            '<span class="line"></span>'
            for _ in range(max(1, int(question.get('answer_lines') or 1)))
        )
        # An answered description prints on the first rule and leaves the rest
        # blank — the guardian may still want to add to it by hand.
        first = f'<div>{_rule(_answer_text(answer))}</div>' if answer else ''
        return f'<div class="q">{label} :{first}{"" if answer else lines}</div>'

    return f'<div class="q">{label} : {_rule(_answer_text(answer))}</div>'


def _answer_text(answer):
    if answer is None or answer is False:
        return ''
    if answer is True:
        return 'হ্যাঁ'
    if isinstance(answer, list):
        return ', '.join(str(item) for item in answer)
    return str(answer)


def _question_set(block, questions, answers):
    section = block['section']
    chosen = [q for q in questions if q.get('section') == section and q.get('is_active', True)]
    title = block.get('title_bn') or block.get('title')
    heading = f'<div class="section-title">{escape(title)}</div>' if title else ''
    body = ''.join(_question(q, answers.get(str(q.get('id')))) for q in chosen)
    return f'{heading}{body}'


def _bullet_list(block, context):
    style = block.get('style', 'bullet')
    tag = 'ol' if style == 'number' else 'ul'
    items = ''.join(f'<li>{_resolved(item, context)}</li>' for item in block['items'])
    title = block.get('title_bn') or block.get('title')
    heading = f'<div class="section-title">{escape(title)}</div>' if title else ''
    return f'{heading}<{tag} class="bullets">{items}</{tag}>'


def _office_box(block, context):
    """The অফিস কর্তৃক পূরণীয় panel — ruled lines, deliberately left empty.

    Filled by hand after the interview, so it prints as blank rules in *both*
    modes. The block still carries its labels, because the person writing on it
    needs to know which line is প্রাপ্ত নম্বর.
    """
    title = escape(block.get('title_bn') or block.get('title', ''))
    panels = ''.join(
        '<div class="panel"><div class="title">'
        f'{escape(panel.get("title_bn") or panel.get("title", ""))}</div>'
        + ''.join(f'<div class="cell">{escape(line)} {_rule("")}</div>'
                  for line in panel.get('lines', []))
        + '</div>'
        for panel in block.get('panels', [])
    )
    panel_html = f'<div class="panels">{panels}</div>' if panels else ''
    lines = ''.join(f'<div class="cell">{escape(line)} {_rule("")}</div>'
                    for line in block.get('lines', []))
    return f'<div class="box"><div class="title">{title}</div>{panel_html}{lines}</div>'


def _signature_row(block, context):
    signatures = ''.join(
        f'<div class="sig"><div class="space"></div>{_resolved(caption, context)}</div>'
        for caption in block['captions']
    )
    return f'<div class="signatures">{signatures}</div>'


def render_block(block, *, context, questions, answers):
    """One block to HTML. Unknown types cannot arrive here — `blocks.validate_blocks`
    refused them when the template was saved."""
    block_type = block['type']

    if block_type == 'letterhead':
        return _letterhead(block, context)
    if block_type == 'meta_row':
        return _meta_row(block, context)
    if block_type == 'prose':
        return _prose(block, context)
    if block_type == 'field_grid':
        return _field_grid(block, context)
    if block_type == 'question_set':
        return _question_set(block, questions, answers)
    if block_type == 'bullet_list':
        return _bullet_list(block, context)
    if block_type == 'office_box':
        return _office_box(block, context)
    if block_type == 'signature_row':
        return _signature_row(block, context)
    if block_type == 'spacer':
        return f'<div style="height:{escape(block.get("height", "6mm"))}"></div>'
    if block_type == 'divider':
        return '<hr class="divider">'
    if block_type == 'page_break':
        return '<div class="page-break"></div>'
    return ''


def render_document(*, blocks, context=None, questions=None, answers=None,
                    paper='A4', margins='12mm 14mm', title='ভর্তি ফরম'):
    """The whole page. Primitive arguments only — this is also the reprint path.

    `PrintedForm.snapshot` stores exactly these arguments, so reprinting a form
    from three years ago is `render_document(**snapshot)` and touches no table.
    That is what makes the reprint show what was signed rather than what the
    record says today (§6).
    """
    context = context or {}
    questions = questions or []
    answers = answers or {}

    body = ''.join(
        render_block(block, context=context, questions=questions, answers=answers)
        for block in blocks
    )
    return (
        '<!DOCTYPE html>\n'
        f'<html lang="bn"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title>'
        f'<style>{_css(paper, margins)}</style></head>'
        f'<body><div class="sheet">{body}</div></body></html>'
    )


def question_payload(question):
    """A `Question` as the plain dict the renderer and the snapshot both use."""
    return {
        'id': question.pk,
        'section': question.section,
        'text': question.text,
        'text_bn': question.text_bn,
        'type': question.type,
        'options': question.options or [],
        'print_style': question.print_style,
        'answer_lines': question.answer_lines,
        'is_active': question.is_active,
        'maps_to': question.maps_to,
    }


def render_form(*, template, context=None, questions=None, answers=None, mode='filled'):
    """Render a `FormTemplate`. `mode='blank'` empties the context and answers.

    Blank mode drops the data rather than using a different template, so the
    stack printed at admission season and the copy printed after data entry are
    the same document, laid out identically. They cannot drift, because there is
    only one of them.
    """
    if mode == 'blank':
        context, answers = {}, {}

    return render_document(
        blocks=template.blocks or [],
        context=context or {},
        questions=[question_payload(q) for q in (questions or [])],
        answers=answers or {},
        paper=template.paper,
        margins=template.margins,
        title=template.name_bn or template.name,
    )
