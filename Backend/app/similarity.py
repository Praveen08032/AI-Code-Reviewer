"""Formatting-insensitive similarity, not an algorithm correctness test."""
import ast
import difflib
import io
import re
import tokenize


class _SolutionTree(ast.NodeTransformer):
    def _body(self, node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                node.body = node.body[1:]
        return node

    def visit_Module(self, node):
        self._body(node)
        # Only omit demonstration code when a solution definition is present.
        if any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for item in node.body):
            node.body = [item for item in node.body if not self._driver(item)]
        return node

    @staticmethod
    def _driver(node):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value.func
            return isinstance(call, ast.Name) and call.id in {"print", "main"}
        return (isinstance(node, ast.If) and
                ast.dump(node.test) == ast.dump(ast.parse('__name__ == "__main__"', mode="eval").body))

    def visit_FunctionDef(self, node):
        self._body(node)
        node.returns = None
        node.type_comment = None
        return node

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = _body

    def visit_arg(self, node):
        node.annotation = None
        node.type_comment = None
        return node


def _tokens(code, language):
    # Strings are matched first so comment markers and spaces inside them survive.
    comment = r"/\*[\s\S]*?\*/|//[^\n]*" if language not in {"python", "ruby"} else r"(?!)"
    if language in {"python", "ruby", "php"}:
        comment += r"|\#[^\n]*"
    pattern = re.compile(
        r'''(?P<string>@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|'''
        + r"(?P<comment>" + comment + r")|"
        + r"(?P<token>[\w$]+|===|!==|==|!=|<=|>=|=>|->|::|&&|\|\||\+\+|--|\+=|-=|\*=|/=|%=|\S)"
    )
    result, previous = [], None
    for match in pattern.finditer(code):
        if match.lastgroup == "comment":
            continue
        if previous and "\n" in code[previous.end():match.start()]:
            # Newlines can change return values or insert statement terminators.
            significant = language in {"go", "ruby"} or (
                language in {"javascript", "typescript"} and
                (previous.group() in {"return", "throw", "break", "continue", "yield", "++", "--"}
                 or match.group() in {"++", "--"}))
            if significant:
                result.append("\n")
        result.append(match.group())
        previous = match
    return result


def _without_braced_main(code, language):
    """Remove explicit executable entry points, keeping solution/helper methods."""
    tokens = _tokens(code, language)
    starts = {
        "java": ["public", "static", "void", "main", "("],
        "csharp": ["static", "void", "Main", "("],
        "cpp": ["int", "main", "("],
        "go": ["func", "main", "("],
        "rust": ["fn", "main", "("],
    }
    signature = starts.get(language)
    if not signature:
        return tokens
    i = 0
    while i < len(tokens):
        if tokens[i:i + len(signature)] != signature:
            i += 1
            continue
        opening = i + len(signature)
        while opening < len(tokens) and tokens[opening] not in {"{", ";"}:
            opening += 1
        if opening == len(tokens) or tokens[opening] != "{":
            i += 1
            continue
        end, depth = opening + 1, 1
        while end < len(tokens) and depth:
            depth += (tokens[end] == "{") - (tokens[end] == "}")
            end += 1
        # Do not silently normalize broken/unbalanced source.
        if depth:
            break
        start = i - 1 if i and tokens[i - 1] in {"public", "private"} else i
        # A program whose whole solution lives in main must retain that logic.
        if "return" not in tokens[:start] + tokens[end:]:
            i = end
            continue
        del tokens[start:end]
        i = start
    return tokens


def normalize_code(code: str, language: str = "python") -> tuple:
    if not code.strip():
        return ()
    language = language.strip().lower()
    if language == "python":
        try:
            tree = _SolutionTree().visit(ast.parse(code))
            if not tree.body:
                return ()
            dumped = ast.dump(tree, include_attributes=False)
            return tuple(token.string for token in tokenize.generate_tokens(io.StringIO(dumped).readline)
                         if token.type not in {tokenize.NEWLINE, tokenize.ENDMARKER})
        except (SyntaxError, ValueError):
            # Retain indentation for invalid Python so it cannot equal valid code.
            return ("INVALID_PYTHON", code.strip()) if code.strip() else ()
    if language == "ruby":
        # Only strip unindented demonstration output, not output within methods.
        code = re.sub(r"^(?:puts|p)\s+[^\n]*$", "", code, flags=re.MULTILINE)
    tokens = _without_braced_main(code, language)
    # JS/TS and PHP demonstration output at module scope.
    result, depth, i = [], 0, 0
    while i < len(tokens):
        output = (tokens[i:i + 3] == ["console", ".", "log"] or
                  (language == "php" and tokens[i] in {"echo", "print", "print_r", "var_dump"}))
        if depth == 0 and output:
            end, nesting = i, 0
            while end < len(tokens):
                token = tokens[end]
                nesting += (token in {"(", "[", "{"}) - (token in {")", "]", "}"})
                end += 1
                if nesting == 0 and token in {")", ";"}:
                    break
            if end < len(tokens) and tokens[end] == ";":
                end += 1
            i = end
            continue
        token = tokens[i]
        depth += (token == "{") - (token == "}")
        result.append(token)
        i += 1
    return tuple(result)


def calculate_similarity(ideal_code: str, submitted_code: str, language: str = "python") -> float:
    ideal = normalize_code(ideal_code, language)
    submitted = normalize_code(submitted_code, language)
    if not ideal or not submitted:
        return 0.0
    if ideal == submitted and ideal[0] != "INVALID_PYTHON":
        return 100.0
    return min(99.99, round(difflib.SequenceMatcher(None, ideal, submitted, autojunk=False).ratio() * 100, 2))
