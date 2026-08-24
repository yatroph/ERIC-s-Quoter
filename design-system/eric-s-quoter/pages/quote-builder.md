# Quote Builder Page Overrides

> **PROJECT:** ERIC's Quoter
> **Page Type:** Desktop utility

These rules override the master design system only for the workbook-builder window.

## Layout

- Use one centered, rounded app shell over the supplied GDI mesh background.
- Keep the main workflow on one screen; only the location list scrolls when needed.
- Use a two-option segmented pill for Multi-location and Multi-year modes.
- Use progressive disclosure: show locations only for Multi-location and a compact 1–5 year selector for Contract pricing.

## Brand and typography

- Preserve the supplied GDI navy/blue brand palette; do not apply unrelated platform colors.
- Use native Segoe UI on Windows for crisp packaged rendering and system text scaling.
- Maintain at least 4.5:1 normal-text contrast and a visible keyboard focus state.

## Components

- Pill inputs use a 23px radius; the primary action uses a 25px radius.
- Every pointer action also supports keyboard operation.
- Required/Optional state is expressed with text as well as color.
- Selected pricing mode is conveyed by surface, border, and text contrast.
- Use a pill stepper for 1-6 locations.
- Use a five-segment, text-labelled pill for the 1–5 year contract term.
- Keep controls at least 44px high where practical.

## Avoid

- Decorative blur, refraction, or motion that reduces contrast or packaging performance.
- Placeholder-only labels, icon-only primary actions, and hover-only explanations.
- A full-page scrolling form for this small input set.
