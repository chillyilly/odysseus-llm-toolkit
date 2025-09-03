## Odysseus LLM Toolkit
![Logo](https://github.com/chillyilly/odysseus-llm-toolkit/blob/main/logo.png)

Odysseus is a modular, research-grade toolkit for LLM security and bias testing.

There are three components:

- **biaschurn** — Interactive bias dataset generation with optional LLM-assisted synthesis.
- **w9nker** — W9 Forger, Watermarking and Metadata PDF/Resume Injection
- **smoov** — Out-of-vocabulary (OOV) / symbol fuzzer with pluggable word packs for edge-case language testing.
---
**Setup**
```bash
git clone https://github.com/chillyilly/odysseus-llm-toolkit.git
cd odysseus-llm-toolkit
python3 -m venv .venv
source .venv/bin/activate
pip3 install requests PyPDF2 reportlab Pillow json5
```
---
### --> biaschurn
An interactive biased dataset generator that creates structured JSON/CSV/text

**Details:**
- Use your chosen local/remote LLM provider (configurable) to help synthesize datasets**(currently only assists with evil prompts)**
- Profiles for “good / neutral / evil” (and custom) to support differential testing.
- Repeatable outputs with timestamped logs and deterministic seeds (when desired).


python3 biaschurn.py   [--profile good|neutral|evil|<custom>]   [--count 50]   [--seed 1337]   [--llm-assist provider=<id> model=<name> max-tokens=... temperature=...]   [--out data/biaschurn-YYYYmmdd-HHMM.json]


---
### --> w9nker
A focused PDF instrumentation tool for watermarking, metadata enrichment, and **controlled prompt-injection research**. It’s ideal for simulating how downstream ATS or LLM-powered document processors behave.

**Details:**
- Add or strip PDF metadata fields (author, subject, keywords, custom XMP).
- Apply visible/invisible watermarks and layout-stable text (e.g., 8pt, horizontal).
- Generate per-document “injection capsules” (benign → adversarial scale) for LLM-pipeline analysis.
- **ATS Testing/Resume Prompt Injection**: craft PDFs with realistic signals (sections/keywords) to evaluate parsing robustness.

**Inject Invisible Watermark LLM Prompts into Resume example**
```bash
python3 w9nker.py --template resume.pdf --w9bp  --wm wm/wm-resume-010.json --output resume_wm_invisible.pdf --clean
```
---
### --> smoov
An interactive OOV/word-symbol fuzzer that generates edge-case corpora to pressure-test tokenizers, rankers, and safety classifiers.

**Details:**
- Loads **word modules** from `words/words*.json` and **symbol modules** from `symbols/symbols*.json`.
- Multiple **generation modes** (e.g., structured lists, randomized blends, symbol-dense sequences).
- Outputs JSON/CSV/text with reproducible seeds and logs.


python3 smoov.py   [--words words/words_base.json,words/words_llm.json]   [--symbols symbols/symbols_math.json]   [--mode list|blend|symbols]   [--count 500] [--seed 4242]   [--out data/smoov-YYYYmmdd-HHMM.json]

**Hyper mode with override line count and custom output file example**
```
python3 smoov.py --mode hyper --lines 120 --outfile out_hyper.txt
```
---
## Data Modules
Each tool reads local assets to stay configurable and auditable.

- **smoov**
  - `words/words*.json` — arrays keyed by theme (e.g., `{"oov":["wørd","ethereal†", ...]}`)
  - `symbols/symbols*.json` — arrays of symbols/groups
- **w9nker**
  - `profiles/*.json` — W9 form filler profiles
  - `wm/*.json` — watermark injection templates
  - `md/*.json` - metadata injection templates
- **biaschurn**
  - `core.good` — default good bias terms
  - `core.evil` — default evil bias terms
  - `core.neutral` — default neutral bias terms
  - `names.good` — default name list
  - `ultra.good` — default ultra positive bias terms


