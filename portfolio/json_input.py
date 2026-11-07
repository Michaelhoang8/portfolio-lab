"""Strict JSON decoding shared by local and versioned HTTP APIs."""
import json
import math


def decode(raw):
    """Reject ambiguous keys, non-finite numbers, and invalid/deep JSON."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON fields')
            result[key] = value
        return result

    def finite(raw_number):
        value = float(raw_number)
        if not math.isfinite(value):
            raise ValueError('Non-finite JSON number')
        return value

    def reject_constant(_):
        raise ValueError('Non-finite JSON number')

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_float=finite,
                          parse_constant=reject_constant)
        pending = [(value, 0)]
        while pending:
            node, depth = pending.pop()
            if isinstance(node, (dict, list)):
                if depth >= 64:
                    raise ValueError('JSON nesting limit exceeded')
                children = node.values() if isinstance(node, dict) else node
                pending.extend((child, depth + 1) for child in children)
        return value
    except (ValueError, UnicodeError, RecursionError):
        # Never reflect submitted content (which may contain secrets) in errors.
        raise ValueError('Malformed JSON body') from None


def read_exact(stream, length):
    raw = stream.read(length)
    if len(raw) != length:
        raise ValueError('Incomplete request body')
    return raw
