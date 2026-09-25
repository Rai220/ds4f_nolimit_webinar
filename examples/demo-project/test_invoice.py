import unittest
from invoice import invoice_total


class InvoiceTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(invoice_total([]), 0)

    def test_quantities_and_integer_cents(self):
        self.assertEqual(invoice_total([(199, 3), (50, 2)]), 697)

    def test_zero_quantity(self):
        self.assertEqual(invoice_total([(500, 0)]), 0)

    def test_reject_negative(self):
        for items in [[(-1, 2)], [(100, -1)]]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                invoice_total(items)

    def test_reject_non_integer_and_bool(self):
        for items in [[(1.5, 2)], [(100, '2')], [(True, 2)], [(100, False)]]:
            with self.subTest(items=items), self.assertRaises(TypeError):
                invoice_total(items)


if __name__ == '__main__':
    unittest.main()
