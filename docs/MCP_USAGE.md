# Using the MCP

`snapmaker-u1-mcp` is best used as a structured tool layer for repeatable offline slicing tasks.

It is not meant to replace the Snapmaker Orca GUI for final visual review.

## When to use it

Use the MCP for:

- profile discovery and compatibility checks
- model inspection and printability warnings
- comparing a few explicit slice variants
- transformed orientation comparisons
- G-code analysis
- run reports and reproducibility

Use Snapmaker Orca GUI for:

- one-off simple prints
- visual support inspection
- manual support painting/placement
- final preview before sending to printer

## Cost-conscious prompting

Good prompt:

```text
Compare these three variants only: baseline, 3 walls, and 5 walls. Return a compact table.
```

Avoid vague expensive prompts like:

```text
Try everything and optimize this fully.
```

The MCP returns compact responses by default. Ask for logs or verbose output only when debugging.

## Typical workflow

1. Check health:

```text
Call u1_health.
```

2. Find profiles:

```text
List PLA profiles for Snapmaker U1 0.4 nozzle.
```

3. Inspect model:

```text
Inspect hase.stl and run printability diagnostics.
```

4. Slice or compare:

```text
Compare baseline against pla-draft and pla-strong. Keep the result compact.
```

5. Review reports/G-code manually before printing.

## Orientation workflow

Prefer transformed orientations:

```text
Compare flat and X90 using u1_compare_transformed_orientations.
```

This creates transformed STL/3MF copies and slices those, instead of relying on Snapmaker Orca CLI rotation flags.

## Debugging failed runs

Use:

```text
u1_list_runs
u1_get_run
u1_get_run_logs
```

Request logs only for the failed run and keep the tail small unless needed.
