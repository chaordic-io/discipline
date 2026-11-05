---
name: stack
description: Choosing a technology stack - the selection criteria S1–S7 (fit the product then the team, few moving parts, strict static types, a healthy dependency ecosystem, operable, reversible, supports every engineering principle), shapes by product kind, and the capability checklist the gate needs, with worked examples. Use when choosing or changing languages, frameworks, data stores, hosting or major libraries, during /discipline:bootstrap's stack questions, and whenever an S-number is cited.
---
# Choosing a stack

The plugin prescribes no languages, frameworks or libraries. It asks that every stack choice rest on
criteria that can be written down, and that the stack make every engineering principle (E1–E10,
/discipline:engineering) easy to follow.

Read [`reference/choosing-a-stack.md`](reference/choosing-a-stack.md) before proposing or changing a
stack. It has:

- the **selection criteria S1–S7**, each with an ID to cite in `docs/decisions/`;
- **how to choose**: read the profile, let existing code decide most of it, one or two options per
  part with the criteria each rests on, check every tool, record the result;
- **shapes by product kind**: the parts each kind of product usually needs, and the engineering
  principles the stack must support best for it;
- the **capability checklist**: what the gate and the review loop need from the stack, with tools that
  illustrate each row in Go, TypeScript, Python, Rust and the JVM. Illustrations, not recommendations:
  check each tool before adopting it.

Worked examples from one project, illustrating the reasoning (copy the reasoning, not the list):
[`reference/examples/webapp-libraries.md`](reference/examples/webapp-libraries.md),
[`reference/examples/go-react-postgres.md`](reference/examples/go-react-postgres.md),
[`reference/examples/astro-cloudflare-pages.md`](reference/examples/astro-cloudflare-pages.md).

Present stack options to the user with a recommendation (the recommended option first), and record the
choice part by part in `docs/decisions/` with the S-criteria it rests on, the alternatives turned
down, and any engineering principle the stack makes hard with how it is covered instead.
