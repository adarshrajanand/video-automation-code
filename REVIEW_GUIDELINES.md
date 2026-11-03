# Review artifact guidelines

`FAQ.md` is a durable review artifact, not scratch notes. Follow-up work belongs
in GitHub issues, not a checked-in TODO file. For priority, issue format,
dependencies, and completion rules, use
[CONTRIBUTING.md](CONTRIBUTING.md#issue-format-and-dependencies).

## FAQ format and traceability

- Use one `#` title and one `##` section per review (for example `PR #1 Review`
  or `PR #5 Review`).
- Group questions by topic, never by comment order, source file, or line number.
  Use `###` for topic groups and `####` for questions.
- Write every question as `#### **Q: <question>?**`, followed by a blank line
  and `**A:** ...`.
- Start with the direct answer, then add evidence, examples, tradeoffs, and links.
  Use fenced code blocks with a language.
- End every answer with `**Source:** ...` naming the review, document, line, and
  comment ID, or the follow-up ID. If every answer in a section shares one
  source, a single Source line under the section heading is enough. Source lines
  provide traceability; they are not headings.
- Keep related questions together. When a follow-up expands an existing answer,
  place it in the same topic and keep its `F` label in the Source line.
- Link follow-up work as `PR5-NN` or `GEN-NN`; every ID must match a GitHub issue
  title.
- Never delete a question silently. Mark it superseded and link the replacement.
- Use “samples” in user-facing prose; use exact code identifiers when quoting
  code.
- Keep the Contents list and decision summary current when adding a review or
  changing a decision.
