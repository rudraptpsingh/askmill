# Notices

The transport in src/askmill/transport.py is adapted from PDF2Data local_ai.py, MIT, copyright (c) 2026 Rudra Pratap Singh. The full MIT notice is reproduced in LICENSE. Models and optional runtimes retain their respective licenses; no weights are included.

PDF2Data source baseline for the adapted transport: local commit cb3c0c7088d0c24f059e8d76483d75b274893605. The source carries MIT; no private Query implementation was copied. Current published integration is an optional consumer of PDF2Data APIs, not a bundled copy of PDF2Data.

Optional standalone qualification drivers build against separately installed
[llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE) and
[Ollama](https://github.com/ollama/ollama/blob/main/LICENSE), both MIT-licensed.
Their source/runtimes and model metadata are not bundled in this tool source
release. Preserve their notices when separately distributing linked binaries.
