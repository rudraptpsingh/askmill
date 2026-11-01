# Development
Use Python 3.10 or newer.
Create a virtual environment, install with `python -m pip install -e '.[dev,mcp]'`,
and run `python -m pytest`. Tests use synthetic inputs and local HTTP stubs.
Real model checks are separate and must record model identity and runtime.
Do not commit machine configuration, customer inputs, receipts, credentials or weights.
