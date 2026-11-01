# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
Its contents are an Alpha101/Qlib-style quantitative factor library, including academic, Alpha101, GTJA191, Qlib158, and zoo factors.
No README or LICENSE identifying an upstream project was found in this vendored tree.
The exact upstream project is therefore unconfirmed.
This notice does not represent the factor library as native VECTOR code.
VECTOR uses the `AlphaZooLoader` utility to discover and load selected factor definitions.
The confirmed integration handles unavailable dependencies defensively.
Vendored as-is; VECTOR's own code calls into: `districts/investment/stock_analyst.py`.
