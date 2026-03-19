---
name: batch-prospect
description: "Process a list of companies through the full prospecting workflow. Each company is analyzed using the prospect-account skill."
---
# Batch Prospect

Process a list of companies through the full prospecting workflow. Each company is analyzed using the prospect-account skill.

## Arguments

- `$0` (required): Comma-separated list of company domains, or one domain per line.
  Examples:
  - "totalpass.com.mx, kavak.com, bitso.com"
  - "totalpass.com.mx\nkavak.com\nbitso.com"

## Steps

1. **Parse the list** of domains from the input. Clean up whitespace, remove empty entries, and deduplicate.

2. **Report the batch size** — tell the user how many companies will be processed.

3. **Process each company** sequentially using the `prospect-account` skill:
   - Before each company, announce: "Processing {N}/{total}: {domain}"
   - Run the full prospect-account workflow
   - Record the result: Qualified/Not Qualified, tier, contacts found

4. **Handle errors gracefully** — if a company fails (API error, site unreachable), log the error and continue with the next company. Do not stop the entire batch.

5. **Generate a consolidated report** after all companies are processed:

```
# Batch Prospecting Report

## Summary
- Total companies processed: {N}
- Qualified: {count}
- Not Qualified: {count}
- Errors: {count}

## Qualified Accounts (by tier)

### Tier A
1. {Company} — {industry} — {contacts found} contacts
2. ...

### Tier B
1. {Company} — {industry} — {contacts found} contacts
2. ...

## Not Qualified
1. {Company} — Reason: {reason}
2. ...

## Errors
1. {Company} — {error description}
```

6. **Save the report** to the workspace as `batch_report_{date}.md` using `file_write`.

## Important Notes

- Process companies one at a time, not in parallel (API rate limits).
- Give progress updates after each company so the user knows the batch is progressing.
- If the batch is large (10+ companies), remind the user that this may take several minutes.
- Individual research briefs are saved by the prospect-account skill — the batch report is an additional summary.
