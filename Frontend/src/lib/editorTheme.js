// Monaco editor theme matching the app
export function defineTheme(monaco) {
  monaco.editor.defineTheme("codecheck", {
    base: "vs-dark", inherit: true,
    rules: [{ token: "keyword", foreground: "c4a5ff" }, { token: "string", foreground: "9dffaa" }, { token: "number", foreground: "fca5a5" }, { token: "comment", foreground: "565c55", fontStyle: "italic" }],
    colors: { "editor.background": "#080a08", "editorLineNumber.foreground": "#3f453f", "editorLineNumber.activeForeground": "#8a9089", "editor.lineHighlightBackground": "#0f120f", "editorCursor.foreground": "#4ade5a", "editor.selectionBackground": "#4ade5a33" },
  });
}
