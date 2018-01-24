import click
import re
import edlib
import os
import json

from collections import Counter


def make_mapping(sequences):
    too_many_strange_characters = False
    replacement = u'@'

    # make char -> int mapping
    temp = {}
    multiple_chars = Counter()

    for sequence in sequences:
        for c in sequence:
            length = len(c.encode('utf-8'))
            if length > 1:
                multiple_chars[c] += 1
            else:
                temp[ord(c)] = c

    if len(temp.keys()) + len(set(multiple_chars)) > 127:
        too_many_strange_characters = True

    # find unused integers for characters encoded with multiple characters
    # if there are too many of these strange characters, the least frequent
    # are ignored
    for c, _freq in multiple_chars.most_common():
        for i in range(128):
            if i not in temp.keys():
                temp[i] = c
                replacement = c
                break

    # reverse the int -> char mapping
    mapping = {}
    for k, v in temp.items():
        mapping[v] = k

    return mapping, too_many_strange_characters, replacement


def translate(mapping, sequence, default_replacement_character):
    seq = []
    for i, c in enumerate(sequence):
        seq.append(chr(mapping.get(c, ord(default_replacement_character))))
    return ''.join(seq)


@click.command()
@click.argument('file1', type=click.Path(exists=True))
@click.argument('file2', type=click.Path(exists=True))
@click.option('--out_dir', '-o', default=os.getcwd(), type=click.Path())
def align(file1, file2, out_dir):
    err_msg = 'File "{}" does not contain a string that can be aligned.'
    with open(file1, encoding='utf-8') as f:
        seq1 = f.read()
        if len(seq1) == 0:
            raise ValueError(err_msg.format(file1))
    with open(file2, encoding='utf-8') as f:
        seq2 = f.read()
        if len(seq2) == 0:
            raise ValueError(err_msg.format(file2))

    # map characters encoded with multiple characters to single characters
    # disable_sanity_check is True if the total number of different characters
    # in the texts is > 127 (this means these characters can't be encoded with
    # single byte characters and will be replaced with a default single byte
    # character)
    mapping, disable_check, replacement_character = make_mapping([seq1, seq2])
    sequence1 = translate(mapping, seq1, replacement_character)
    sequence2 = translate(mapping, seq2, replacement_character)

    aligment = edlib.align(sequence1, sequence2, task='path')
    edit_distance = aligment['editDistance']
    cigar = aligment['cigar']

    matches = re.findall(r'(\d+)(.)', cigar)
    offset1 = 0
    offset2 = 0

    changes_from = []
    changes_to = []
    changes = Counter()

    for m in matches:
        n = int(m[0])
        typ = m[1]

        if typ == '=':
            # sanity check - strings should be equal
            try:
                assert(seq1[offset1:offset1+n] == seq2[offset2:offset2+n])
            except AssertionError as e:
                if not disable_check:
                    raise(e)

            if changes_from != [] and changes_to != []:
                changes[(''.join(changes_from), ''.join(changes_to))] += 1

            changes_from = []
            changes_to = []

            offset1 += n
            offset2 += n
        elif typ == 'D':  # Inserted
            changes_from.append('')
            changes_to.append(seq2[offset2:offset2+n])

            offset2 += n
        elif typ == 'X':
            changes_from.append(seq1[offset1:offset1+n])
            changes_to.append(seq2[offset2:offset2+n])

            offset1 += n
            offset2 += n
        elif typ == 'I':  # Deleted
            changes_from.append(seq1[offset1:offset1+n])
            changes_to.append('')

            offset1 += n

    doc_id = os.path.basename(file1).split('-')[0]
    result = {'doc_id': doc_id,
              'edit_distance': edit_distance,
              'seq1_length': len(sequence1),
              'seq2_length': len(sequence2),
              'cigar': cigar}

    out_file = os.path.join(out_dir, '{}-metadata.json'.format(doc_id))
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    changes_list = []
    for (c_from, c_to), freq in changes.items():
        changes_list.append({'doc_id': doc_id,
                             'from': c_from,
                             'to': c_to,
                             'num': freq,
                             'df': 1})
    out_file = os.path.join(out_dir, '{}-changes.json'.format(doc_id))
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(changes_list, f, indent=2)


if __name__ == '__main__':
    align()
