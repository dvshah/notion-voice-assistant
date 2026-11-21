import unittest
from nlp_parser import parse_voice_command

class TestNLPParser(unittest.TestCase):
    def test_add_single_item(self):
        res = parse_voice_command("Add milk")
        self.assertEqual(res["intent"], "add_items")
        self.assertEqual(res["items"], ["milk"])

    def test_add_multiple_items_with_and(self):
        res = parse_voice_command("Add milk and eggs to my shopping list")
        self.assertEqual(res["intent"], "add_items")
        self.assertEqual(res["items"], ["milk", "eggs"])

    def test_add_multiple_items_with_commas_and_quantities(self):
        res = parse_voice_command("Add 2 apples, sourdough bread, and oat milk")
        self.assertEqual(res["intent"], "add_items")
        self.assertEqual(res["items"], ["2 apples", "sourdough bread", "oat milk"])

    def test_add_complex_polite(self):
        res = parse_voice_command("Add milk, eggs, bread and 2 avocados to my shopping list please")
        self.assertEqual(res["intent"], "add_items")
        self.assertEqual(res["items"], ["milk", "eggs", "bread", "2 avocados"])

    def test_add_alternative_phrasings(self):
        res1 = parse_voice_command("Put bananas on my shopping list")
        self.assertEqual(res1["intent"], "add_items")
        self.assertEqual(res1["items"], ["bananas"])

        res2 = parse_voice_command("I need coffee and dark chocolate")
        self.assertEqual(res2["intent"], "add_items")
        self.assertEqual(res2["items"], ["coffee", "dark chocolate"])

        res3 = parse_voice_command("Remember to buy laundry detergent")
        self.assertEqual(res3["intent"], "add_items")
        self.assertEqual(res3["items"], ["laundry detergent"])

    def test_read_shopping_list(self):
        phrases = [
            "What's on my shopping list?",
            "What is currently on my shopping list",
            "Read my shopping list",
            "Tell me what is on my shopping list",
            "What do I need to buy",
            "What items do I have to buy",
            "Shopping list"
        ]
        for p in phrases:
            res = parse_voice_command(p)
            self.assertEqual(res["intent"], "read_list", f"Failed for phrase: {p}")

    def test_sample_items(self):
        phrases = [
            ("Tell me any two items that I have", 2),
            ("Any two items", 2),
            ("What are any two items on my shopping list", 2),
            ("Give me 2 items that I have", 2),
            ("Give me two items", 2),
            ("Give me three items from my list", 3),
            ("Tell me 1 item", 1),
            ("What are a couple of items on my list", 2)
        ]
        for p, count in phrases:
            res = parse_voice_command(p)
            self.assertEqual(res["intent"], "sample_items", f"Failed for phrase: {p}")
            self.assertEqual(res["count"], count, f"Wrong count for phrase: {p}")

    def test_check_item(self):
        phrases = [
            ("Do I have milk?", "milk"),
            ("Do we have eggs on the shopping list?", "eggs"),
            ("Is butter on my list?", "butter"),
            ("Check if we have coffee", "coffee"),
            ("Do I have oat milk already", "oat milk"),
            ("Is there any coffee on the list", "coffee")
        ]
        for p, expected_item in phrases:
            res = parse_voice_command(p)
            self.assertEqual(res["intent"], "check_item", f"Failed for: {p}")
            self.assertEqual(res["item"], expected_item, f"Mismatch item for: {p}")

    def test_complete_item(self):
        phrases = [
            ("Remove milk", "milk"),
            ("Delete eggs from my shopping list", "eggs"),
            ("I bought bread", "bread"),
            ("Cross off apples", "apples"),
            ("Mark bananas as done", "bananas")
        ]
        for p, expected_item in phrases:
            res = parse_voice_command(p)
            self.assertEqual(res["intent"], "complete_item", f"Failed for: {p}")
            self.assertEqual(res["item"], expected_item, f"Mismatch item for: {p}")

    def test_direct_item_words(self):
        res = parse_voice_command("avocados and tomatoes")
        self.assertEqual(res["intent"], "add_items")
        self.assertEqual(res["items"], ["avocados", "tomatoes"])

if __name__ == "__main__":
    unittest.main()
