# [ch2370] Fork Talon and improve signature removal.
# [ch14047] improve talon signature extraction
from __future__ import absolute_import

import logging

import regex

from talon.signature.constants import TOO_LONG_SIGNATURE_LINE
from talon.utils import get_delimiter

log = logging.getLogger(__name__)

# regex to fetch signature based on common signature words
ENG_GER_CHARS_SPACES = '[a-z\u00E4\u00F6\u00FC\u00C4\u00D6\u00DC\u00df\s]'


RE_SIGNATURE = regex.compile(rf'''
               (
                   (?:
                       ^[\s]*--*[\s]*[a-z \.]*$
                       |
                       ^[\s]*—+[\s]*$
                       |
                       ^thanks?\s?(?:you?\s*)?[a-z]*[\s,!]*$
                       |
                       ^regards\s?[a-z]*[\s,!]*$
                       |
                       ^(?:with?\s*)?kind\sregards[\sa-z]*[\s,!]*$
                       |
                       ^take\scare\s?[a-z]*[\s,!]*$
                       |
                       ^cheers\s?[a-z]*[\s,!]*$
                       |
                       ^sincerely[\s,!]*$
                       |
                       ^best[ a-z]*[\s,!]*$
                       |
                       ^ihre?[\s,!]*$
                       |
                       ^deine?[\s,!]*$
                       |
                       ^{ENG_GER_CHARS_SPACES}*grüße{ENG_GER_CHARS_SPACES}*[\s,!]*$
                       |
                       ^vielen?\sdank[\s,!]*$
                       |
                       die\sbesten\swünsche[\s,!]*$
                       |
                       ^danke{ENG_GER_CHARS_SPACES}*[\s,!]*$
                       |
                       ^[a-z\s]+\ ?\/\ ?mit\ freundlichen\ grüßen[\n,!]+$
                       |
                       ^mit\ freundlichen\ grüßen\ ?\/\ ?[a-z\s]+[\n,!]+$
                   )
                   .*
               )
               ''', regex.I | regex.X | regex.M | regex.S)


# signatures appended by phone email clients
RE_PHONE_SIGNATURE = regex.compile(r'''
               (
                   (?:
                       ^sent[ ]{1}from[ ]{1}my[\s,!\w]*$
                       |
                       ^sent[ ]from[ ]Mailbox[ ]for[ ]iPhone.*$
                       |
                       ^sent[ ]([\S]*[ ])?from[ ]my[ ]BlackBerry.*$
                       |
                       ^Enviado[ ]desde[ ]mi[ ]([\S]+[ ]){0,2}BlackBerry.*$
                   )
                   .*
               )
               ''', regex.I | regex.X | regex.M | regex.S)

# see _mark_candidate_indexes() for details
# c - could be signature line
# d - line starts with dashes (could be signature or list item)
# l - long line
RE_SIGNATURE_CANDIDATE = regex.compile(r'''
    (?P<candidate>c+d)[^d]
    |
    (?P<candidate>c+d)$
    |
    (?P<candidate>c+)
    |
    (?P<candidate>d)[^d]
    |
    (?P<candidate>d)$
''', regex.I | regex.X | regex.M | regex.S)


def extract_signature(msg_body):
    '''
    Analyzes message for a presence of signature block (by common patterns)
    and returns tuple with two elements: message text without signature block
    and the signature itself.

    >>> extract_signature('Hey man! How r u?\n\n--\nRegards,\nRoman')
    ('Hey man! How r u?', '--\nRegards,\nRoman')

    >>> extract_signature('Hey man!')
    ('Hey man!', None)
    '''
    try:
        # identify line delimiter first
        delimiter = get_delimiter(msg_body)

        # make an assumption
        stripped_body = msg_body.strip()
        phone_signature = None

        # strip off phone signature
        phone_signature = RE_PHONE_SIGNATURE.search(msg_body)
        if phone_signature:
            stripped_body = stripped_body[:phone_signature.start()]
            phone_signature = phone_signature.group()

        # decide on signature candidate
        lines = stripped_body.splitlines()
        candidate = get_signature_candidate(lines)
        candidate = delimiter.join(candidate)

        # try to extract signature
        signature = RE_SIGNATURE.search(candidate)
        if not signature:
            return (stripped_body.strip(), phone_signature)
        else:
            signature = signature.group()
            # when we splitlines() and then join them
            # we can lose a new line at the end
            # we did it when identifying a candidate
            # so we had to do it for stripped_body now
            stripped_body = delimiter.join(lines)
            stripped_body = stripped_body[:-len(signature)]

            if phone_signature:
                signature = delimiter.join([signature, phone_signature])

            return (stripped_body.strip(),
                    signature.strip())
    except Exception:
        log.exception('ERROR extracting signature')
        return (msg_body, None)


def get_signature_candidate(lines):
    """Return lines that could hold signature

    The lines should:

    * be among last SIGNATURE_MAX_LINES non-empty lines.
    * not include first line
    * be shorter than TOO_LONG_SIGNATURE_LINE
    * not include more than one line that starts with dashes
    """
    # non empty lines indexes
    non_empty = [i for i, line in enumerate(lines) if line.strip()]

    # if message is empty or just one line then there is no signature
    if len(non_empty) <= 1:
        return []

    # we don't expect signature to start at the 1st line
    candidate = [i for i in non_empty if i > 0]

    markers = _mark_candidate_indexes(lines, candidate)
    candidate = _process_marked_candidate_indexes(candidate, markers)

    # get actual lines for the candidate instead of indexes
    if candidate:
        candidate = lines[candidate[0]:]
        return candidate

    return []


def _mark_candidate_indexes(lines, candidate):
    """Mark candidate indexes with markers

    Markers:

    * c - line that could be a signature line
    * l - long line
    * d - line that starts with dashes but has other chars as well

    >>> _mark_candidate_lines(['Some text', '', '-', 'Bob'], [0, 2, 3])
    'cdc'
    """
    # at first consider everything to be potential signature lines
    markers = list('c' * len(candidate))
    # mark lines starting from bottom up
    for i, line_idx in reversed(list(enumerate(candidate))):
        if len(lines[line_idx].strip()) > TOO_LONG_SIGNATURE_LINE:
            markers[i] = 'l'
        else:
            line = lines[line_idx].strip()
            if line.startswith('-') and line.strip("-"):
                markers[i] = 'd'
    return "".join(markers)


def _process_marked_candidate_indexes(candidate, markers):
    """
    Run regexes against candidate's marked indexes to strip
    signature candidate.

    >>> _process_marked_candidate_indexes([9, 12, 14, 15, 17], 'clddc')
    [15, 17]
    """
    match = RE_SIGNATURE_CANDIDATE.search(markers)
    return candidate[match.start('candidate'):match.end('candidate')+1] if match else []
