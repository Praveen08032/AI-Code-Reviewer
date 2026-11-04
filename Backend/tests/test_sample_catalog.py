"""Check curated reference solutions; never execute user submissions."""
import shutil
import subprocess
import unittest

from app.default_answers import DEFAULT_SAMPLES
from app.similarity import calculate_similarity


class SampleCatalogTests(unittest.TestCase):
    def test_five_complete_samples_for_each_language(self):
        self.assertEqual(len(DEFAULT_SAMPLES), 10)
        for language, questions in DEFAULT_SAMPLES.items():
            with self.subTest(language=language):
                self.assertEqual(len(questions), 5)
                self.assertIn("two sum", questions)
                for title, sample in questions.items():
                    self.assertEqual(title, title.strip().lower())
                    self.assertGreater(len(sample["description"]), 40)
                    self.assertGreater(len(sample["ideal_code"]), 20)
                    self.assertEqual(calculate_similarity(sample["ideal_code"], sample["ideal_code"], language), 100)

    def test_python_reference_edge_cases(self):
        namespace = {}
        for sample in DEFAULT_SAMPLES["python"].values():
            exec(compile(sample["ideal_code"], "<curated-reference>", "exec"), namespace)
        self.assertEqual(namespace["two_sum"]([3, 3], 6), [0, 1])
        self.assertEqual(namespace["two_sum"]([-3, 4, 3], 0), [0, 2])
        self.assertEqual(namespace["two_sum"]([], 0), [])
        for text, valid in [("", True), ("([]{})", True), ("([)]", False), ("]", False), ("(", False)]:
            self.assertEqual(namespace["is_valid_parentheses"](text), valid)
        self.assertEqual(namespace["word_frequency"](" Hello hello\tWORLD!\n"), {"hello": 2, "world!": 1})
        self.assertEqual(namespace["word_frequency"](" \n"), {})
        nested = [1, [2, [], [3]], 4]
        self.assertEqual(namespace["flatten_list"](nested), [1, 2, 3, 4])
        self.assertEqual(nested, [1, [2, [], [3]], 4])
        deep = [1]
        for _ in range(1500):
            deep = [deep]
        self.assertEqual(namespace["flatten_list"](deep), [1])
        search = namespace["binary_search"]
        self.assertEqual(search([], 5), -1)
        self.assertEqual(search([-3, 0, 2, 9], -3), 0)
        self.assertEqual(search([-3, 0, 2, 9], 9), 3)
        self.assertEqual(search([1, 2, 3], 7), -1)
        self.assertIn(search([1, 1, 1], 1), [0, 1, 2])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for JavaScript reference checks")
    def test_javascript_reference_edge_cases(self):
        solutions = "\n".join(sample["ideal_code"] for sample in DEFAULT_SAMPLES["javascript"].values())
        checks = '''
        const assert = require('node:assert/strict');
        assert.deepEqual(twoSum([3, 3], 6), [0, 1]);
        assert.deepEqual(twoSum([], 0), []);
        assert.deepEqual(uniqueValues([1, 2, 1, '1', NaN, NaN]), [1, 2, '1', NaN]);
        assert.deepEqual(uniqueValues([]), []);
        const items = [{k: '__proto__', v: 1}, {k: 'x', v: 2}, {k: '__proto__', v: 3}];
        const groups = groupBy(items, item => item.k);
        assert.deepEqual(groups.get('__proto__'), [items[0], items[2]]);
        assert.equal(groupBy([], item => item).size, 0);
        assert.equal(isValidParentheses(''), true);
        assert.equal(isValidParentheses('([]{})'), true);
        assert.equal(isValidParentheses('([)]'), false);
        assert.equal(isValidParentheses(']'), false);
        // Deterministic debounce check: control pending timers rather than wait.
        const pending = new Map();
        let nextTimer = 0;
        const setTimeout = fn => { pending.set(++nextTimer, fn); return nextTimer; };
        const clearTimeout = id => pending.delete(id);
        const context = {name: 'receiver'};
        const calls = [];
        const debounced = debounce(function (...args) { calls.push([this, args]); }, 10);
        debounced.call(context, 'first');
        debounced.call(context, 'last', 2);
        assert.equal(pending.size, 1);
        [...pending.values()][0]();
        assert.deepEqual(calls, [[context, ['last', 2]]]);
        '''
        result = subprocess.run([shutil.which("node"), "-e", solutions + checks], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
