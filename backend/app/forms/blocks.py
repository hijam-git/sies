"""The block schema, and the validator that keeps a malformed one out of the
renderer (docs/07 §3, §6.1).

`FormTemplate.blocks` is an ordered JSON list rather than a `FormBlock` table:
blocks are only ever read as a whole document, always in order, and never
queried individually, so a table would buy joins and reordering pain for
nothing (§6.1). The price of that choice is that the database cannot check the
shape — so this module does, **on save**, and the model calls it there.

Validating at save rather than at render is the entire point. A renderer that
tolerates a bad block prints a page with a section silently missing, and the
first person to see it is holding the printed stack. A save that refuses tells
the administrator who typed it, while they are looking at what they typed.

Each entry below is `(required, optional)` where the value is the Python type
the key must hold. Unknown keys are refused too: `{"type": "prose", "txt": …}`
is a typo, and a schema that ignored it would render an empty paragraph.
"""

from django.core.exceptions import ValidationError

from .placeholders import validate_text

STR = str
BOOL = bool
INT = int
LIST = list

BLOCK_SCHEMA = {
    # Logo, Arabic / English / Bangla names, established year, address. The
    # lines come from Branch through placeholders, so a template needs no copy
    # of the institution's name — and a renamed institution reprints correctly.
    'letterhead': ({}, {'show_logo': BOOL, 'lines': LIST, 'lines_ar': LIST}),
    # ফরম নং · নতুন/পুরাতন · ভর্তি নং · তারিখ · ☑ আবাসিক
    'meta_row': ({'fields': LIST}, {}),
    'prose': ({'text': STR}, {'text_bn': STR, 'align': STR, 'indent': BOOL}),
    'field_grid': ({'fields': LIST}, {'columns': INT, 'title': STR, 'title_bn': STR}),
    'question_set': ({'section': STR}, {'title': STR, 'title_bn': STR}),
    'bullet_list': ({'items': LIST}, {'title': STR, 'title_bn': STR, 'style': STR}),
    'office_box': ({'title': STR}, {'title_bn': STR, 'panels': LIST, 'lines': LIST}),
    'signature_row': ({'captions': LIST}, {'align': STR}),
    'spacer': ({}, {'height': STR}),
    'divider': ({}, {}),
    'page_break': ({}, {}),
}

BLOCK_TYPES = sorted(BLOCK_SCHEMA)

BULLET_STYLES = {'bullet', 'number', 'none'}


def _fail(message):
    raise ValidationError(f'{message} · ফরম টেমপ্লেটের ব্লক ত্রুটিপূর্ণ।')


def _check_labelled_pairs(items, *, where):
    """`[{'label': …, 'value': …}]` — the shape a meta row and a field grid use.

    `value` carries placeholders and is validated as prose; `label` is printed
    text and may carry them too — the reference form's grid labels are fixed
    Bangla, but a template that wanted `{{class.name_bn}}` in a label is not
    wrong, and refusing it would be an arbitrary rule.
    """
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            _fail(f'{where}[{index}] must be an object with a label and a value')
        unknown = set(item) - {'label', 'label_bn', 'value', 'width'}
        if unknown:
            _fail(f'{where}[{index}] has unknown key(s) {", ".join(sorted(unknown))}')
        for key in ('label', 'label_bn', 'value'):
            if key in item:
                if not isinstance(item[key], str):
                    _fail(f'{where}[{index}].{key} must be text')
                validate_text(item[key], where=f'{where}[{index}].{key}')


def validate_block(block, *, index):
    """One block, or a `ValidationError` naming exactly what is wrong with it."""
    where = f'blocks[{index}]'

    if not isinstance(block, dict):
        _fail(f'{where} must be an object')

    block_type = block.get('type')
    if block_type not in BLOCK_SCHEMA:
        _fail(f'{where}: unknown block type {block_type!r}. '
              f'Allowed: {", ".join(BLOCK_TYPES)}')

    required, optional = BLOCK_SCHEMA[block_type]
    allowed = {'type', *required, *optional}

    unknown = set(block) - allowed
    if unknown:
        _fail(f'{where} ({block_type}) has unknown key(s) '
              f'{", ".join(sorted(unknown))}. Allowed: {", ".join(sorted(allowed))}')

    missing = set(required) - set(block)
    if missing:
        _fail(f'{where} ({block_type}) is missing {", ".join(sorted(missing))}')

    for key, expected in {**required, **optional}.items():
        if key in block and not isinstance(block[key], expected):
            _fail(f'{where}.{key} must be {expected.__name__}')

    if block_type == 'prose':
        validate_text(block['text'], where=f'{where}.text')
        validate_text(block.get('text_bn', ''), where=f'{where}.text_bn')

    elif block_type in ('meta_row', 'field_grid'):
        _check_labelled_pairs(block['fields'], where=f'{where}.fields')

    elif block_type == 'bullet_list':
        style = block.get('style', 'bullet')
        if style not in BULLET_STYLES:
            _fail(f'{where}.style must be one of {", ".join(sorted(BULLET_STYLES))}')
        for position, item in enumerate(block['items']):
            if not isinstance(item, str):
                _fail(f'{where}.items[{position}] must be text')
            validate_text(item, where=f'{where}.items[{position}]')

    elif block_type == 'signature_row':
        for position, caption in enumerate(block['captions']):
            if not isinstance(caption, str):
                _fail(f'{where}.captions[{position}] must be text')
            validate_text(caption, where=f'{where}.captions[{position}]')

    elif block_type == 'office_box':
        for position, line in enumerate(block.get('lines', [])):
            if not isinstance(line, str):
                _fail(f'{where}.lines[{position}] must be text')
        for position, panel in enumerate(block.get('panels', [])):
            if not isinstance(panel, dict):
                _fail(f'{where}.panels[{position}] must be an object')
            unknown = set(panel) - {'title', 'title_bn', 'lines'}
            if unknown:
                _fail(f'{where}.panels[{position}] has unknown key(s) '
                      f'{", ".join(sorted(unknown))}')
            if not isinstance(panel.get('lines', []), list):
                _fail(f'{where}.panels[{position}].lines must be a list')

    elif block_type == 'letterhead':
        for key in ('lines', 'lines_ar'):
            for position, line in enumerate(block.get(key, [])):
                if not isinstance(line, str):
                    _fail(f'{where}.{key}[{position}] must be text')
                validate_text(line, where=f'{where}.{key}[{position}]')

    return block


def validate_blocks(blocks):
    """The whole ordered list. Called from `FormTemplate.save()`."""
    if not isinstance(blocks, list):
        _fail('blocks must be an ordered list of block objects')
    for index, block in enumerate(blocks):
        validate_block(block, index=index)
    return blocks
