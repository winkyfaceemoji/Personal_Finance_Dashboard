# 0014. In-progress periods are compared like-for-like; "typical" is a median

Status: Accepted

## Context
Comparing a part-finished month with whole months always looks like an improvement. A mean also lets one unusual period, such as a tax payment or a holiday, redefine normal.

## Decision
- While a period is in progress, comparisons use the same number of days from each earlier period.
- "Typical" is the median of up to the previous 12 weeks or months, or of every earlier year.
- Zero-spend gap periods count toward the median.

Rejected: a mean, and whole-period comparisons for in-progress periods.

## Consequences
- A quiet stretch reads as quiet instead of vanishing.
- "Typical" is a 12-period median with no seasonality, so a reliably expensive month like December reads as over typical.
