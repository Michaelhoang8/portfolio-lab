import unittest
from portfolio.json_input import decode


class UnicodeJSONTests(unittest.TestCase):
    def test_unpaired_surrogates_are_rejected_in_keys_values_and_nested_arrays(self):
        for raw in (r'{"secret":"PRIVATE_PREFIX_\ud800"}',r'{"\udfff":1}',
                    r'{"rows":[{"name":"\udc00"}]}',r'["\ud800x\udfff"]'):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'^Malformed JSON body$'):
                decode(raw)

    def test_valid_surrogate_pairs_and_unicode_round_trip(self):
        value=decode(r'{"name":"\ud83d\ude80 café","rows":["\u0000","\ufffd"]}')
        self.assertEqual(value,{'name':'🚀 café','rows':['\x00','�']})
        self.assertEqual(decode('{"日本語":"résumé"}'.encode('utf-8')),{'日本語':'résumé'})

    def test_invalid_utf8_does_not_reflect_submitted_content(self):
        with self.assertRaisesRegex(ValueError,'^Malformed JSON body$'):
            decode(b'{"secret":"PRIVATE_PREFIX_\xff"}')
