# Security

## Reporting a problem
Please use GitHub's private vulnerability reporting on this repository (Security tab, "Report a vulnerability"), not a public issue. Include the tool call that shows the problem. Please don't include exact counts below 10 in a public place.

Only the latest tagged release is supported.

## What counts
- An answer that gives or lets someone work out an exact count below 10.
- An answer that shows a company name, company number, postcode or address.
- Any tool input that reaches a shell, a file path or the network, or changes the data.
- Text in a tool definition or answer that isn't what the README describes.

## What this server does and doesn't protect
See "What it can touch" in the README. It runs on your own machine with your user's permissions. Its protection covers what it answers, not the files you build: `data/grid.duckdb`, the downloads and `.env` hold raw counts or secrets, so keep them off shared storage.
