"""Additional practice problems with idiomatic reference solutions."""
from textwrap import dedent


ADDITIONAL_SAMPLES = {
    "python": {
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            def is_valid_parentheses(text):
                pairs = {')': '(', ']': '[', '}': '{'}
                stack = []
                for char in text:
                    if char in '([{':
                        stack.append(char)
                    elif not stack or stack.pop() != pairs[char]:
                        return False
                return not stack
            ''',
        ),
        "word frequency": (
            "Count whitespace-delimited words case-insensitively. Return a dictionary of counts; preserve punctuation as part of each word. Empty input returns an empty dictionary.",
            '''
            from collections import Counter

            def word_frequency(text):
                return dict(Counter(text.lower().split()))
            ''',
        ),
        "flatten nested list": (
            "Flatten a finite nested list of integers into a new list, preserving order. Items may be integers or further lists. Empty lists contribute no elements; do not modify the input.",
            '''
            def flatten_list(items):
                result = []
                stack = [iter(items)]
                while stack:
                    try:
                        item = next(stack[-1])
                    except StopIteration:
                        stack.pop()
                        continue
                    if isinstance(item, list):
                        stack.append(iter(item))
                    else:
                        result.append(item)
                return result
            ''',
        ),
        "binary search": (
            "Given an ascending sorted list of integers and a target, return any matching zero-based index, or -1 if absent. The input may be empty or contain duplicates. Use O(log n) search time.",
            '''
            def binary_search(nums, target):
                left, right = 0, len(nums)
                while left < right:
                    middle = left + (right - left) // 2
                    if nums[middle] == target:
                        return middle
                    if nums[middle] < target:
                        left = middle + 1
                    else:
                        right = middle
                return -1
            ''',
        ),
    },
    "javascript": {
        "unique values": (
            "Return a new array containing the unique primitive values from the input array, preserving first-occurrence order. Use JavaScript Set equality (SameValueZero); do not mutate the input.",
            '''
            function uniqueValues(values) {
              return [...new Set(values)];
            }
            ''',
        ),
        "group by key": (
            "Group array items by the key returned by a keyOf callback. Return a Map from keys to arrays of items in input order. Empty input returns an empty Map; do not mutate the input.",
            '''
            function groupBy(items, keyOf) {
              const groups = new Map();
              for (const item of items) {
                const key = keyOf(item);
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push(item);
              }
              return groups;
            }
            ''',
        ),
        "debounce function": (
            "Return a trailing-edge debounce wrapper for a function and a non-negative delay in milliseconds. Calls during the delay reset the timer. Invoke the function once after the last call, with its latest arguments and this context. The wrapper need not return the function's result.",
            '''
            function debounce(fn, delayMs) {
              let timer;
              return function (...args) {
                clearTimeout(timer);
                timer = setTimeout(() => fn.apply(this, args), delayMs);
              };
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            function isValidParentheses(text) {
              const pairs = new Map([[")", "("], ["]", "["], ["}", "{"]]);
              const stack = [];
              for (const char of text) {
                if ("([{".includes(char)) stack.push(char);
                else if (stack.pop() !== pairs.get(char)) return false;
              }
              return stack.length === 0;
            }
            ''',
        ),
    },
    "typescript": {
        "binary search": (
            "Given an ascending sorted readonly array of numbers and a target, return any matching zero-based index, or -1 if absent. The array may be empty or contain duplicates. Use O(log n) search time.",
            '''
            function binarySearch(nums: readonly number[], target: number): number {
              let left = 0;
              let right = nums.length;
              while (left < right) {
                const middle = left + Math.floor((right - left) / 2);
                if (nums[middle] === target) return middle;
                if (nums[middle] < target) left = middle + 1;
                else right = middle;
              }
              return -1;
            }
            ''',
        ),
        "group by key": (
            "Implement a type-safe generic function grouping readonly input items by a keyOf callback. Return Map<K, T[]> while preserving item order within each group. Empty input returns an empty Map; do not mutate the input.",
            '''
            function groupBy<T, K>(items: readonly T[], keyOf: (item: T) => K): Map<K, T[]> {
              const groups = new Map<K, T[]>();
              for (const item of items) {
                const key = keyOf(item);
                const group = groups.get(key);
                if (group) group.push(item);
                else groups.set(key, [item]);
              }
              return groups;
            }
            ''',
        ),
        "unique by key": (
            "Return a new array with the first item for each distinct keyOf result, preserving input order. Use generics to retain the input item type and Set equality for keys. Do not mutate the readonly input.",
            '''
            function uniqueBy<T, K>(items: readonly T[], keyOf: (item: T) => K): T[] {
              const seen = new Set<K>();
              return items.filter((item) => {
                const key = keyOf(item);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
              });
            }
            ''',
        ),
        "sum by selector": (
            "Implement a type-safe generic sumBy function for a readonly array and a numeric selector callback. Sum each item's selected value. Empty input returns zero; do not mutate the input.",
            '''
            function sumBy<T>(items: readonly T[], select: (item: T) => number): number {
              return items.reduce((total, item) => total + select(item), 0);
            }
            ''',
        ),
    },
    "java": {
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            import java.util.ArrayDeque;
            import java.util.Deque;

            class Solution {
                public boolean isValidParentheses(String text) {
                    Deque<Character> stack = new ArrayDeque<>();
                    for (char ch : text.toCharArray()) {
                        if (ch == '(' || ch == '[' || ch == '{') {
                            stack.push(ch);
                        } else {
                            if (stack.isEmpty()) return false;
                            char expected = ch == ')' ? '(' : ch == ']' ? '[' : '{';
                            if (stack.pop() != expected) return false;
                        }
                    }
                    return stack.isEmpty();
                }
            }
            ''',
        ),
        "binary search": (
            "Given an ascending sorted int array and a target, return any matching zero-based index, or -1 if absent. The array may be empty or contain duplicates. Use O(log n) search time.",
            '''
            class Solution {
                public int binarySearch(int[] nums, int target) {
                    int left = 0, right = nums.length;
                    while (left < right) {
                        int middle = left + (right - left) / 2;
                        if (nums[middle] == target) return middle;
                        if (nums[middle] < target) left = middle + 1;
                        else right = middle;
                    }
                    return -1;
                }
            }
            ''',
        ),
        "word frequency": (
            "Count whitespace-delimited words in a string case-insensitively using Locale.ROOT. Preserve punctuation within words and return a Map<String, Integer>. Blank input returns an empty map.",
            '''
            import java.util.HashMap;
            import java.util.Locale;
            import java.util.Map;

            class Solution {
                public Map<String, Integer> wordFrequency(String text) {
                    Map<String, Integer> counts = new HashMap<>();
                    String trimmed = text.strip();
                    if (trimmed.isEmpty()) return counts;
                    for (String word : trimmed.toLowerCase(Locale.ROOT).split("\\\\s+")) {
                        counts.merge(word, 1, Integer::sum);
                    }
                    return counts;
                }
            }
            ''',
        ),
        "merge sorted arrays": (
            "Merge two ascending sorted int arrays into a new ascending sorted array, retaining duplicates. Either input may be empty. Use O(n + m) time and do not modify either input.",
            '''
            class Solution {
                public int[] mergeSorted(int[] first, int[] second) {
                    int[] merged = new int[first.length + second.length];
                    int i = 0, j = 0, k = 0;
                    while (i < first.length && j < second.length) {
                        merged[k++] = first[i] <= second[j] ? first[i++] : second[j++];
                    }
                    while (i < first.length) merged[k++] = first[i++];
                    while (j < second.length) merged[k++] = second[j++];
                    return merged;
                }
            }
            ''',
        ),
    },
    "cpp": {
        "binary search": (
            "Given an ascending sorted vector<int> and a target, return any matching zero-based index, or -1 if absent. The input may be empty or contain duplicates and its size fits in int. Use O(log n) search time.",
            '''
            #include <vector>

            int binarySearch(const std::vector<int>& nums, int target) {
                int left = 0, right = static_cast<int>(nums.size());
                while (left < right) {
                    int middle = left + (right - left) / 2;
                    if (nums[middle] == target) return middle;
                    if (nums[middle] < target) left = middle + 1;
                    else right = middle;
                }
                return -1;
            }
            ''',
        ),
        "merge sorted arrays": (
            "Merge two ascending sorted integer vectors into a new sorted vector, retaining duplicates. Either input may be empty. Use O(n + m) time and do not modify the input vectors.",
            '''
            #include <algorithm>
            #include <iterator>
            #include <vector>

            std::vector<int> mergeSorted(const std::vector<int>& first, const std::vector<int>& second) {
                std::vector<int> merged;
                merged.reserve(first.size() + second.size());
                std::merge(first.begin(), first.end(), second.begin(), second.end(), std::back_inserter(merged));
                return merged;
            }
            ''',
        ),
        "remove duplicates from sorted array": (
            "Remove duplicates from an ascending sorted integer vector in place. Return the number of unique values, which must occupy the first k positions in original order. Values beyond k are unspecified. Use O(n) time and O(1) extra space.",
            '''
            #include <cstddef>
            #include <vector>

            std::size_t removeDuplicates(std::vector<int>& nums) {
                std::size_t write = 0;
                for (int value : nums) {
                    if (write == 0 || nums[write - 1] != value) {
                        nums[write++] = value;
                    }
                }
                return write;
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            #include <string>
            #include <vector>

            bool isValidParentheses(const std::string& text) {
                std::vector<char> stack;
                for (char ch : text) {
                    if (ch == '(' || ch == '[' || ch == '{') {
                        stack.push_back(ch);
                    } else {
                        char expected = ch == ')' ? '(' : ch == ']' ? '[' : '{';
                        if (stack.empty() || stack.back() != expected) return false;
                        stack.pop_back();
                    }
                }
                return stack.empty();
            }
            ''',
        ),
    },
    "csharp": {
        "group words by length": (
            "Group non-null strings from an IEnumerable<string> by their .NET string Length. Return a Dictionary<int, List<string>> and preserve input order within each group. Empty input returns an empty dictionary.",
            '''
            using System.Collections.Generic;
            using System.Linq;

            public class Solution {
                public Dictionary<int, List<string>> GroupWordsByLength(IEnumerable<string> words) {
                    return words.GroupBy(word => word.Length)
                        .ToDictionary(group => group.Key, group => group.ToList());
                }
            }
            ''',
        ),
        "first non repeating character": (
            "Return the first UTF-16 char that occurs exactly once in a string, or null if none exists. Use char? as the return type and O(n) expected time. Empty input returns null.",
            '''
            using System.Collections.Generic;

            public class Solution {
                public char? FirstUniqueCharacter(string text) {
                    var counts = new Dictionary<char, int>();
                    foreach (char ch in text) {
                        counts.TryGetValue(ch, out int count);
                        counts[ch] = count + 1;
                    }
                    foreach (char ch in text) {
                        if (counts[ch] == 1) return ch;
                    }
                    return null;
                }
            }
            ''',
        ),
        "binary search": (
            "Given an ascending sorted int array and a target, return any matching zero-based index, or -1 if absent. The array may be empty or contain duplicates. Use O(log n) search time.",
            '''
            public class Solution {
                public int BinarySearch(int[] nums, int target) {
                    int left = 0, right = nums.Length;
                    while (left < right) {
                        int middle = left + (right - left) / 2;
                        if (nums[middle] == target) return middle;
                        if (nums[middle] < target) left = middle + 1;
                        else right = middle;
                    }
                    return -1;
                }
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            using System.Collections.Generic;

            public class Solution {
                public bool IsValidParentheses(string text) {
                    var stack = new Stack<char>();
                    foreach (char ch in text) {
                        if (ch == '(' || ch == '[' || ch == '{') {
                            stack.Push(ch);
                        } else {
                            char expected = ch == ')' ? '(' : ch == ']' ? '[' : '{';
                            if (stack.Count == 0 || stack.Pop() != expected) return false;
                        }
                    }
                    return stack.Count == 0;
                }
            }
            ''',
        ),
    },
    "go": {
        "word frequency": (
            "Count whitespace-delimited words case-insensitively using strings.Fields and strings.ToLower. Preserve punctuation within words. Return a map[string]int; empty input returns an empty map.",
            '''
            package main

            import "strings"

            func wordFrequency(text string) map[string]int {
                counts := make(map[string]int)
                for _, word := range strings.Fields(strings.ToLower(text)) {
                    counts[word]++
                }
                return counts
            }
            ''',
        ),
        "unique values": (
            "Return a new slice with the first occurrence of every distinct integer from the input, preserving order. Do not modify the input. Empty input returns an empty slice.",
            '''
            package main

            func uniqueValues(values []int) []int {
                seen := make(map[int]struct{})
                result := make([]int, 0, len(values))
                for _, value := range values {
                    if _, exists := seen[value]; !exists {
                        seen[value] = struct{}{}
                        result = append(result, value)
                    }
                }
                return result
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            package main

            func isValidParentheses(text string) bool {
                pairs := map[rune]rune{')': '(', ']': '[', '}': '{'}
                stack := make([]rune, 0)
                for _, ch := range text {
                    if ch == '(' || ch == '[' || ch == '{' {
                        stack = append(stack, ch)
                    } else {
                        if len(stack) == 0 || stack[len(stack)-1] != pairs[ch] {
                            return false
                        }
                        stack = stack[:len(stack)-1]
                    }
                }
                return len(stack) == 0
            }
            ''',
        ),
        "merge sorted arrays": (
            "Merge two ascending sorted integer slices into a new sorted slice, retaining duplicates. Either input may be empty. Use O(n + m) time and do not modify either input.",
            '''
            package main

            func mergeSorted(first, second []int) []int {
                result := make([]int, 0, len(first)+len(second))
                i, j := 0, 0
                for i < len(first) && j < len(second) {
                    if first[i] <= second[j] {
                        result = append(result, first[i])
                        i++
                    } else {
                        result = append(result, second[j])
                        j++
                    }
                }
                result = append(result, first[i:]...)
                result = append(result, second[j:]...)
                return result
            }
            ''',
        ),
    },
    "rust": {
        "binary search": (
            "Given an ascending sorted &[i32] and a target, return Some(index) for any match or None if absent. The slice may be empty or contain duplicates. Use O(log n) search time without unsigned-index underflow.",
            '''
            pub fn binary_search(nums: &[i32], target: i32) -> Option<usize> {
                let (mut left, mut right) = (0, nums.len());
                while left < right {
                    let middle = left + (right - left) / 2;
                    match nums[middle].cmp(&target) {
                        std::cmp::Ordering::Equal => return Some(middle),
                        std::cmp::Ordering::Less => left = middle + 1,
                        std::cmp::Ordering::Greater => right = middle,
                    }
                }
                None
            }
            ''',
        ),
        "first non repeating character": (
            "Return Some(char) for the first Unicode scalar value that occurs exactly once, or None if none exists. Iterate by Rust chars, not UTF-8 bytes. Empty input returns None.",
            '''
            use std::collections::HashMap;

            pub fn first_unique_character(text: &str) -> Option<char> {
                let mut counts = HashMap::new();
                for ch in text.chars() {
                    *counts.entry(ch).or_insert(0usize) += 1;
                }
                text.chars().find(|ch| counts.get(ch) == Some(&1))
            }
            ''',
        ),
        "unique values": (
            "Return a new Vec<i32> with each distinct integer once, preserving its first-occurrence order. Accept a slice and do not modify it. Empty input returns an empty vector.",
            '''
            use std::collections::HashSet;

            pub fn unique_values(values: &[i32]) -> Vec<i32> {
                let mut seen = HashSet::new();
                values.iter().copied().filter(|value| seen.insert(*value)).collect()
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            pub fn is_valid_parentheses(text: &str) -> bool {
                let mut stack = Vec::new();
                for ch in text.chars() {
                    match ch {
                        '(' | '[' | '{' => stack.push(ch),
                        ')' | ']' | '}' => {
                            let expected = match ch {
                                ')' => '(',
                                ']' => '[',
                                _ => '{',
                            };
                            if stack.pop() != Some(expected) { return false; }
                        }
                        _ => return false,
                    }
                }
                stack.is_empty()
            }
            ''',
        ),
    },
    "php": {
        "word frequency": (
            "Count ASCII whitespace-delimited words case-insensitively. Preserve punctuation within words and return an associative array of counts. Empty or whitespace-only input returns an empty array.",
            '''
            <?php
            function wordFrequency(string $text): array {
                $words = preg_split('/\\\\s+/', strtolower(trim($text)), -1, PREG_SPLIT_NO_EMPTY);
                return array_count_values($words);
            }
            ''',
        ),
        "group records by key": (
            "Given an array of associative records and a field name, group records by that field's string or integer value. Skip records missing the field. Preserve record order within each group and return an associative array; empty input returns an empty array.",
            '''
            <?php
            function groupRecordsByKey(array $records, string $key): array {
                $groups = [];
                foreach ($records as $record) {
                    if (array_key_exists($key, $record)) {
                        $groups[$record[$key]][] = $record;
                    }
                }
                return $groups;
            }
            ''',
        ),
        "unique values": (
            "Given an array of strings, return a zero-indexed array with duplicate strings removed while preserving first-occurrence order. Compare values as strings; empty input returns an empty array.",
            '''
            <?php
            function uniqueValues(array $values): array {
                return array_values(array_unique($values, SORT_STRING));
            }
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            <?php
            function isValidParentheses(string $text): bool {
                $pairs = [')' => '(', ']' => '[', '}' => '{'];
                $stack = [];
                for ($i = 0, $length = strlen($text); $i < $length; $i++) {
                    $char = $text[$i];
                    if (str_contains('([{', $char)) {
                        $stack[] = $char;
                    } elseif (!$stack || array_pop($stack) !== $pairs[$char]) {
                        return false;
                    }
                }
                return !$stack;
            }
            ''',
        ),
    },
    "ruby": {
        "word frequency": (
            "Count whitespace-delimited words case-insensitively. Preserve punctuation within words and return a hash of counts. Empty input returns an empty hash.",
            '''
            def word_frequency(text)
              text.downcase.split.tally
            end
            ''',
        ),
        "unique values": (
            "Return a new array containing the first occurrence of each distinct value, preserving order and using Ruby Array#uniq equality. Do not mutate the input. Empty input returns an empty array.",
            '''
            def unique_values(values)
              values.uniq
            end
            ''',
        ),
        "group words by length": (
            "Group an array of strings by their character length. Return a hash from lengths to arrays, preserving input order within each group. Empty input returns an empty hash.",
            '''
            def group_words_by_length(words)
              words.group_by(&:length)
            end
            ''',
        ),
        "valid parentheses": (
            "Given a string containing only ()[]{}, return whether every bracket is correctly matched and nested. An empty string is valid.",
            '''
            def valid_parentheses?(text)
              pairs = { ')' => '(', ']' => '[', '}' => '{' }
              stack = []
              text.each_char do |char|
                if '([{'.include?(char)
                  stack << char
                else
                  return false if stack.empty? || stack.pop != pairs[char]
                end
              end
              stack.empty?
            end
            ''',
        ),
    },
}
ADDITIONAL_SAMPLES = {
    language: {
        title: {"description": description, "ideal_code": dedent(code).strip()}
        for title, (description, code) in questions.items()
    }
    for language, questions in ADDITIONAL_SAMPLES.items()
}
