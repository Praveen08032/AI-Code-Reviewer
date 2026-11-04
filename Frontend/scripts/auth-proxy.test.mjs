import test from "node:test";
import assert from "node:assert/strict";
import { authProxyRules } from "./auth-proxy.mjs";

test("auth proxy precedes SPA fallback and leaves AI requests direct", () => {
  const lines = authProxyRules("https://backend.example", true).trim().split("\n");
  assert.deepEqual(lines, ["/auth/*  https://backend.example/auth/:splat  200!", "/*  /index.html  200"]);
});

test("production requires a backend and rejects insecure or ambiguous targets", () => {
  assert.throws(() => authProxyRules("", true));
  for (const target of ["http://backend.example", "https://user:secret@backend.example", "https://backend.example/api", "https://backend.example/?a=b", "https://backend.example/#fragment"]) {
    assert.throws(() => authProxyRules(target, true), target);
  }
  assert.equal(authProxyRules(""), "/*  /index.html  200\n");
});
