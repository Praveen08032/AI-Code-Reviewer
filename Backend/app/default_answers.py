"""Seed the built-in practice library without replacing user answers."""
from textwrap import dedent
from .models import SampleAnswer
from .sample_catalog import ADDITIONAL_SAMPLES


DEFAULT_ANSWERS = {
    "python": '''
        def two_sum(nums, target):
            seen = {}
            for i, num in enumerate(nums):
                complement = target - num
                if complement in seen:
                    return [seen[complement], i]
                seen[num] = i
            return []
    ''',
    "javascript": '''
        function twoSum(nums, target) {
          const seen = new Map();
          for (let i = 0; i < nums.length; i++) {
            const complement = target - nums[i];
            if (seen.has(complement)) return [seen.get(complement), i];
            seen.set(nums[i], i);
          }
          return [];
        }
    ''',
    "typescript": '''
        function twoSum(nums: number[], target: number): number[] {
          const seen = new Map<number, number>();
          for (let i = 0; i < nums.length; i++) {
            const complement = target - nums[i];
            if (seen.has(complement)) return [seen.get(complement)!, i];
            seen.set(nums[i], i);
          }
          return [];
        }
    ''',
    "java": '''
        import java.util.HashMap;
        import java.util.Map;

        class Solution {
            public int[] twoSum(int[] nums, int target) {
                Map<Integer, Integer> seen = new HashMap<>();
                for (int i = 0; i < nums.length; i++) {
                    int complement = target - nums[i];
                    if (seen.containsKey(complement)) return new int[]{seen.get(complement), i};
                    seen.put(nums[i], i);
                }
                return new int[0];
            }
        }
    ''',
    "cpp": '''
        #include <unordered_map>
        #include <vector>

        std::vector<int> twoSum(const std::vector<int>& nums, int target) {
            std::unordered_map<int, int> seen;
            for (int i = 0; i < static_cast<int>(nums.size()); ++i) {
                int complement = target - nums[i];
                auto match = seen.find(complement);
                if (match != seen.end()) return {match->second, i};
                seen[nums[i]] = i;
            }
            return {};
        }
    ''',
    "csharp": '''
        using System.Collections.Generic;

        public class Solution {
            public int[] TwoSum(int[] nums, int target) {
                var seen = new Dictionary<int, int>();
                for (int i = 0; i < nums.Length; i++) {
                    int complement = target - nums[i];
                    if (seen.TryGetValue(complement, out int previous)) return new[] { previous, i };
                    seen[nums[i]] = i;
                }
                return System.Array.Empty<int>();
            }
        }
    ''',
    "go": '''
        package main

        func twoSum(nums []int, target int) []int {
            seen := make(map[int]int)
            for i, num := range nums {
                if previous, ok := seen[target-num]; ok {
                    return []int{previous, i}
                }
                seen[num] = i
            }
            return []int{}
        }
    ''',
    "rust": '''
        use std::collections::HashMap;

        pub fn two_sum(nums: Vec<i32>, target: i32) -> Vec<usize> {
            let mut seen = HashMap::new();
            for (i, &num) in nums.iter().enumerate() {
                if let Some(&previous) = seen.get(&(target - num)) {
                    return vec![previous, i];
                }
                seen.insert(num, i);
            }
            vec![]
        }
    ''',
    "php": '''
        <?php
        function twoSum(array $nums, int $target): array {
            $seen = [];
            foreach ($nums as $i => $num) {
                $complement = $target - $num;
                if (array_key_exists($complement, $seen)) return [$seen[$complement], $i];
                $seen[$num] = $i;
            }
            return [];
        }
    ''',
    "ruby": '''
        def two_sum(nums, target)
          seen = {}
          nums.each_with_index do |num, i|
            complement = target - num
            return [seen[complement], i] if seen.key?(complement)
            seen[num] = i
          end
          []
        end
    ''',
}
DEFAULT_ANSWERS = {language: dedent(code).strip() for language, code in DEFAULT_ANSWERS.items()}
TWO_SUM_DESCRIPTION = (
    "Given an integer array and a target, return the zero-based indices of two distinct elements whose sum equals the target. "
    "Return any valid pair; return an empty array/list/vector when no pair exists. Handle duplicates, negative values and empty input. "
    "Use O(n) expected time and O(n) additional space."
)
DEFAULT_SAMPLES = {
    language: {
        "two sum": {"description": TWO_SUM_DESCRIPTION, "ideal_code": code},
        **ADDITIONAL_SAMPLES.get(language, {}),
    }
    for language, code in DEFAULT_ANSWERS.items()
}


def get_sample_description(language, question_title):
    sample = DEFAULT_SAMPLES.get(language.strip().lower(), {}).get(question_title.strip().lower(), {})
    return sample.get("description", "")


def seed_default_answers(db):
    existing = {(answer.language, answer.question_title) for answer in db.query(SampleAnswer).filter(SampleAnswer.user_id.is_(None)).all()}
    for language, questions in DEFAULT_SAMPLES.items():
        for title, sample in questions.items():
            if (language, title) not in existing:
                db.add(SampleAnswer(language=language, question_title=title, ideal_code=sample["ideal_code"]))
    db.commit()
