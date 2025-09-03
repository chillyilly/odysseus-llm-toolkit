#!/usr/bin/env python3

import argparse
import json
import random
import sys
import os
from glob import glob
from datetime import datetime
from typing import List, Dict, Tuple
import hashlib

# ---------- Utilities ----------

def ts(fmt: str="%Y%m%d_%H%M%S")->str:
    return datetime.now().strftime(fmt)

def write_out(text: str, outfile: str|None, mode_tag: str, encoding: str="utf-8")->str:
    if not outfile:
        outfile = f"fuzzyout_{ts()}_{mode_tag}.txt"
    with open(outfile, "w", encoding=encoding) as f:
        f.write(text)
    return outfile

def preview_block(text: str, n_lines: int=10)->str:
    return "\n".join(text.splitlines()[:max(0, n_lines)])

def random_unicode_char_safe() -> str:
    while True:
        cp = random.randint(32, 0x10FFFF)
        ch = chr(cp)
        try:
            ch.encode("utf-8")
            return ch
        except UnicodeEncodeError:
            continue

# ---------- Seed parsing ----------
def parse_seed(seed_input):
    """
    Accepts None, an int-like string, or any text.
    - If int-like, returns int(seed_input).
    - If text, returns a stable 64-bit hash-derived int.
    """
    if seed_input is None or seed_input == "":
        return None
    if isinstance(seed_input, int):
        return seed_input
    try:
        return int(str(seed_input).strip())
    except Exception:
        h = hashlib.sha256(str(seed_input).encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big")

# ---------- Load word/symbol sets from directories ----------

def _normalize_list(lst):
    # keep strings only, strip whitespace, drop empties
    out = []
    for x in lst:
        if isinstance(x, str):
            s = x.strip()
            if s:
                out.append(s)
    return out

def load_sets_from_dir(dirpath: str, prefix: str) -> Dict[str, List[str]]:
    """
    Scan directory for files named '{prefix}*.json' and build a dict of sets.
    - If file is a list: set name = filename stem
    - If file is a dict: merge keys (each key becomes a set name)
    Later duplicates are merged by name (unique, order preserved by first occurrence).
    """
    from pathlib import Path
    sets: Dict[str, List[str]] = {}
    path = Path(dirpath)
    if not path.exists():
        return sets
    for f in sorted(path.glob(f"{prefix}*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            name = f.stem
            lst = _normalize_list(data)
            if lst:
                sets.setdefault(name, [])
                for w in lst:
                    if w not in sets[name]:
                        sets[name].append(w)
        elif isinstance(data, dict):
            for k, v in data.items():
                if not isinstance(v, list):
                    continue
                lst = _normalize_list(v)
                if not lst:
                    continue
                name = str(k)
                sets.setdefault(name, [])
                for w in lst:
                    if w not in sets[name]:
                        sets[name].append(w)
    return sets

def choose_set(sets: Dict[str, List[str]], chosen: str) -> List[str]:
    if not sets:
        return []
    if chosen and chosen != "all":
        return sets.get(chosen, [])
    # merge all
    merged = []
    seen = set()
    for name in sets:
        for x in sets[name]:
            if x not in seen:
                merged.append(x); seen.add(x)
    return merged

# runtime-selected pools (filled at runtime)
RUNTIME_WORDS: List[str] = []
RUNTIME_SYMBOLS: List[str] = []

# minimal safety fallback (used only if no files are found)
FALLBACK_WORDS = ["alpha","beta","gamma","delta","epsilon"]
FALLBACK_SYMBOLS = list("!@#$%^&*()-_=+[]{};:'\",.<>/?|\\")

# ---------- Mode generators ----------

def _words(): return RUNTIME_WORDS if RUNTIME_WORDS else FALLBACK_WORDS
def _symbols(): return RUNTIME_SYMBOLS if RUNTIME_SYMBOLS else FALLBACK_SYMBOLS

def gen_basic(num_lines: int) -> str:
    """ASCII 'nonsense' with some words/symbols."""
    words = _words()
    symbols = _symbols()
    nonsense = ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(3,8)))
                for _ in range(200)]
    out: List[str] = []
    for _ in range(num_lines):
        line_len = random.randint(5,15)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense"], weights=[0.2,0.1,0.7])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            else:
                parts.append(random.choice(nonsense))
        out.append(" ".join(parts))
    return "\n".join(out)

def gen_complex(num_lines: int) -> str:
    """Bigger pools, variable line lengths, and nested segments."""
    words = _words()
    symbols = _symbols()
    nonsense = ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(5,12)))
                for _ in range(400)]
    lines: List[str] = []
    for _ in range(num_lines):
        line_len = random.randint(10,25)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense","nested"],
                                    weights=[0.1,0.05,0.65,0.2])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            elif choice=="nonsense":
                parts.append(random.choice(nonsense))
            else:
                nested_len = random.randint(3,7)
                nested_parts = []
                for _ in range(nested_len):
                    nchoice = random.choices(["word","symbol","nonsense"], weights=[0.2,0.1,0.7])[0]
                    if nchoice=="word" and words:
                        nested_parts.append(random.choice(words))
                    elif nchoice=="symbol" and symbols:
                        nested_parts.append(random.choice(symbols))
                    else:
                        nested_parts.append(random.choice(nonsense))
                parts.append(" ".join(nested_parts))
                if random.random() < 0.1:
                    nested_len2 = random.randint(2,4)
                    nested_parts2 = []
                    for _ in range(nested_len2):
                        nchoice2 = random.choices(["word","symbol","nonsense"], weights=[0.2,0.1,0.7])[0]
                        if nchoice2=="word" and words:
                            nested_parts2.append(random.choice(words))
                        elif nchoice2=="symbol" and symbols:
                            nested_parts2.append(random.choice(symbols))
                        else:
                            nested_parts2.append(random.choice(nonsense))
                    parts.append(" ".join(nested_parts2))
        lines.append(" ".join(parts))
    return "\n".join(lines)

def gen_hyper(num_lines: int) -> str:
    """Hyper-complex with explicit weights and some duplication."""
    words = _words()
    symbols = _symbols()
    nonsense = ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(7,15)))
                for _ in range(800)]
    lines: List[str] = []
    for _ in range(num_lines):
        line_len = random.randint(15,35)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense","nested"],
                                    weights=[30,10,40,20])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            elif choice=="nonsense":
                parts.append(random.choice(nonsense))
            else:
                nested_len = random.randint(5,10)
                nested_parts = []
                for _ in range(nested_len):
                    nchoice = random.choices(["word","symbol","nonsense"], weights=[30,10,60])[0]
                    if nchoice=="word" and words:
                        nested_parts.append(random.choice(words))
                    elif nchoice=="symbol" and symbols:
                        nested_parts.append(random.choice(symbols))
                    else:
                        nested_parts.append(random.choice(nonsense))
                parts.append(" ".join(nested_parts))
        lines.append(" ".join(parts))
    for _ in range(random.randint(5,15)):
        lines.append(random.choice(lines))
    return "\n".join(lines)

def gen_mini_nested(num_lines: int) -> str:
    """Tiny tokens, deep nesting bias."""
    words = _words()
    symbols = _symbols()
    fallback_nonsense = ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(1,3)))
                for _ in range(120)]
    lines = []
    for _ in range(num_lines):
        line_len = random.randint(3,5)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense","nested"], weights=[10,5,15,70])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            elif choice=="nonsense":
                parts.append(random.choice(fallback_nonsense))
            else:
                nested_len = random.randint(2,4)
                nested_parts = []
                for _ in range(nested_len):
                    nchoice = random.choices(["word","symbol","nonsense","deeper_nested"],
                                             weights=[10,10,10,70])[0]
                    if nchoice=="word" and words:
                        nested_parts.append(random.choice(words))
                    elif nchoice=="symbol" and symbols:
                        nested_parts.append(random.choice(symbols))
                    elif nchoice=="nonsense":
                        nested_parts.append(random.choice(fallback_nonsense))
                    else:
                        deeper_len = random.randint(1,3)
                        deeper_parts = []
                        for _ in range(deeper_len):
                            dchoice = random.choices(["word","symbol","nonsense"], weights=[10,10,80])[0]
                            if dchoice=="word" and words:
                                deeper_parts.append(random.choice(words))
                            elif dchoice=="symbol" and symbols:
                                deeper_parts.append(random.choice(symbols))
                            else:
                                deeper_parts.append(random.choice(fallback_nonsense))
                        nested_parts.append(" ".join(deeper_parts))
                parts.append(" ".join(nested_parts))
        lines.append(" ".join(parts))
    for _ in range(random.randint(1,3)):
        lines.append(random.choice(lines))
    return "\n".join(lines)

def gen_unicode_basic(num_lines: int) -> str:
    """Unicode with naive structure, encoded as UTF-8 when written."""
    words = _words()
    symbols = _symbols()
    nonsense = ["".join(chr(random.randint(32, 0x10FFFF)) for _ in range(random.randint(1,3)))
                for _ in range(120)]
    lines = []
    for _ in range(num_lines):
        line_len = random.randint(3,5)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense","nested"], weights=[10,5,15,70])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            elif choice=="nonsense":
                parts.append(random.choice(nonsense))
            else:
                nested_len = random.randint(2,4)
                nested_parts = []
                for _ in range(nested_len):
                    nchoice = random.choices(["word","symbol","nonsense","deeper_nested"],
                                             weights=[10,10,10,70])[0]
                    if nchoice=="word" and words:
                        nested_parts.append(random.choice(words))
                    elif nchoice=="symbol" and symbols:
                        nested_parts.append(random.choice(symbols))
                    elif nchoice=="nonsense":
                        nested_parts.append(random.choice(nonsense))
                    else:
                        deeper_len = random.randint(1,3)
                        deeper_parts = []
                        for _ in range(deeper_len):
                            dchoice = random.choices(["word","symbol","nonsense"], weights=[10,10,80])[0]
                            if dchoice=="word" and words:
                                deeper_parts.append(random.choice(words))
                            elif dchoice=="symbol" and symbols:
                                deeper_parts.append(random.choice(symbols))
                            else:
                                deeper_parts.append(random.choice(nonsense))
                        nested_parts.append(" ".join(deeper_parts))
                parts.append(" ".join(nested_parts))
        lines.append(" ".join(parts))
    for _ in range(random.randint(1,3)):
        lines.append(random.choice(lines))
    return "\n".join(lines)

def gen_unicode_heavy(num_lines: int,
                      duplicate_lo: int=30,
                      duplicate_hi: int=100) -> str:
    """UTF‑8 safe unicode, deep nesting, heavy duplication."""
    words = _words()
    symbols = _symbols()
    nonsense = ["".join(random_unicode_char_safe() for _ in range(random.randint(1,10)))
                for _ in range(1000)]
    lines = []
    for _ in range(num_lines):
        line_len = random.randint(5,20)
        parts = []
        for _ in range(line_len):
            choice = random.choices(["word","symbol","nonsense","nested"], weights=[5,5,10,80])[0]
            if choice=="word" and words:
                parts.append(random.choice(words))
            elif choice=="symbol" and symbols:
                parts.append(random.choice(symbols))
            elif choice=="nonsense":
                parts.append(random.choice(nonsense))
            else:
                nested_len = random.randint(3,10)
                nested_parts = []
                for _ in range(nested_len):
                    nchoice = random.choices(["word","symbol","nonsense","deeper_nested"],
                                             weights=[5,5,10,80])[0]
                    if nchoice=="word" and words:
                        nested_parts.append(random.choice(words))
                    elif nchoice=="symbol" and symbols:
                        nested_parts.append(random.choice(symbols))
                    elif nchoice=="nonsense":
                        nested_parts.append(random.choice(nonsense))
                    else:
                        deeper_len = random.randint(2,8)
                        deeper_parts = []
                        for _ in range(deeper_len):
                            dchoice = random.choices(["word","symbol","nonsense"], weights=[5,5,90])[0]
                            if dchoice=="word" and words:
                                deeper_parts.append(random.choice(words))
                            elif dchoice=="symbol" and symbols:
                                deeper_parts.append(random.choice(symbols))
                            else:
                                deeper_parts.append(random.choice(nonsense))
                        nested_parts.append(" ".join(deeper_parts))
                parts.append(" ".join(nested_parts))
        lines.append(" ".join(parts))
    for _ in range(random.randint(duplicate_lo, duplicate_hi)):
        lines.append(random.choice(lines))
    return "\n".join(lines)

# ---------- Orchestration ----------

MODES = {
    "basic":          ("ASCII basic",              gen_basic,          40),
    "complex":        ("ASCII complex+nested",     gen_complex,        50),
    "hyper":          ("Hyper-complex (weights)",  gen_hyper,          80),
    "mini_nested":    ("Tiny tokens, deep nest",   gen_mini_nested,    8),
    "unicode_basic":  ("Unicode naive",            gen_unicode_basic,  8),
    "unicode_heavy":  ("Unicode heavy",            gen_unicode_heavy,  1000),
}

def select_runtime_sets(words_dir: str, symbols_dir: str,
                        words_set: str, symbols_set: str,
                        interactive: bool):
    global RUNTIME_WORDS, RUNTIME_SYMBOLS

    word_sets = load_sets_from_dir(words_dir, "words")
    sym_sets  = load_sets_from_dir(symbols_dir, "symbols")

    if interactive:
        # words
        if word_sets:
            print("\nAvailable WORD sets:")
            names = ["all"] + sorted(list(word_sets.keys()))
            for i, n in enumerate(names):
                print(f"  {i}. {n} ({len(choose_set(word_sets, n))} items)")
            try:
                w_choice = input(f"Choose words set [0 for 'all'] (default 0): ").strip()
                w_idx = int(w_choice) if w_choice else 0
                words_set = names[max(0, min(w_idx, len(names)-1))]
            except Exception:
                words_set = "all"
        else:
            print("[warn] No words/*.json found; using fallback words.")

        # symbols
        if sym_sets:
            print("\nAvailable SYMBOL sets:")
            names = ["all"] + sorted(list(sym_sets.keys()))
            for i, n in enumerate(names):
                print(f"  {i}. {n} ({len(choose_set(sym_sets, n))} items)")
            try:
                s_choice = input(f"Choose symbols set [0 for 'all'] (default 0): ").strip()
                s_idx = int(s_choice) if s_choice else 0
                symbols_set = names[max(0, min(s_idx, len(names)-1))]
            except Exception:
                symbols_set = "all"
        else:
            print("[warn] No symbols/*.json found; using fallback symbols.")

    RUNTIME_WORDS   = choose_set(word_sets, words_set) if word_sets else []
    RUNTIME_SYMBOLS = choose_set(sym_sets,  symbols_set) if sym_sets else []

    if not RUNTIME_WORDS:
        print("[info] Using fallback words (no sets selected or found).")
    if not RUNTIME_SYMBOLS:
        print("[info] Using fallback symbols (no sets selected or found).")

def run_mode(mode: str, num_lines: int|None, outfile: str|None,
             preview: int|None, seed: int|None):
    if seed is not None:
        random.seed(seed)
    label, func, default_lines = MODES[mode]
    nlines = num_lines if num_lines is not None else default_lines
    if mode == "unicode_heavy" and nlines > 3000:
        nlines = 3000
    generated = func(nlines)
    out_path = write_out(generated, outfile, mode, encoding="utf-8")
    print(f"[{mode}] {label} -> wrote {len(generated)} chars to: {out_path}")
    if preview:
        print("\n--- preview ---")
        print(preview_block(generated, preview))

def run_all(num_lines: int|None, seed: int|None):
    for m in MODES.keys():
        run_mode(m, num_lines, None, preview=0, seed=seed)

def _post_run_prompt():
    while True:
        ans = input("\nWhat next? [r]un again / [c]onfigure / [e]xit: ").strip().lower()
        if ans in ("r","c","e"):
            return ans
        if ans.startswith("run"):
            return "r"
        if ans.startswith("conf"):
            return "c"
        if ans.startswith("exit"):
            return "e"
        print("Please enter r, c, or e.")

def interactive_loop(args):
    print("OOV Fuzzer — unified interactive generator")

    while True:  # reconfigure loop
        # choose sets interactively
        select_runtime_sets(args.words_dir, args.symbols_dir, args.words_set, args.symbols_set, interactive=True)

        while True:  # run/re-run loop
            print("\nSelect a mode:")
            for i, key in enumerate(MODES.keys(), start=1):
                print(f"  {i}. {key}  ({MODES[key][0]})")
            print(f"  0. all (run every mode)")

            try:
                choice = input("Enter choice number: ").strip()
            except EOFError:
                print("No input; exiting.")
                return

            if choice == "0":
                seed = input("Optional seed (blank or any text): ").strip()
                seed_val = parse_seed(seed)
                num_lines_in = input("Optional lines for each mode (blank for defaults): ").strip() or None
                num_lines_val = int(num_lines_in) if num_lines_in else None

                # First run
                run_all(num_lines=num_lines_val, seed=seed_val)

                # Post-run loop for repeating same configuration
                while True:
                    nxt = _post_run_prompt()
                    if nxt == "r":
                        run_all(num_lines=num_lines_val, seed=seed_val)
                        continue
                    elif nxt == "c":
                        # break to reconfigure sets
                        break
                    else:  # exit
                        return
                # broke to reconfigure
                break

            # Single-mode path
            try:
                idx = int(choice)
                key = list(MODES.keys())[idx-1]
            except Exception:
                print("Invalid choice.")
                continue

            num_lines_in = input("Lines (blank for default): ").strip() or None
            num_lines_val = int(num_lines_in) if num_lines_in else None
            out = input("Output file (blank => auto timestamped): ").strip() or None
            prev_in = input("Preview first N lines (blank for none): ").strip() or None
            preview = int(prev_in) if prev_in else None
            seed = input("Optional RNG seed (blank or any text): ").strip()
            seed_val = parse_seed(seed)

            # First run
            run_mode(key, num_lines_val, out, preview, seed_val)

            # Post-run loop for repeating same configuration
            while True:
                nxt = _post_run_prompt()
                if nxt == "r":
                    run_mode(key, num_lines_val, out, preview, seed_val)
                    continue
                elif nxt == "c":
                    # break to reconfigure sets
                    break
                else:  # exit
                    return
            # broke to reconfigure
            break

def build_arg_parser():
    p = argparse.ArgumentParser(description="Unified OOV generator (interactive or CLI).")
    p.add_argument("--mode", choices=list(MODES.keys())+["all"],
                   help="Generator mode. Omit to use interactive menu.")
    p.add_argument("--lines", type=int, help="Override number of lines for the chosen mode.")
    p.add_argument("--outfile", help="Write to this file (default: fuzzyout_YYYYmmdd_HHMMSS_<mode>.txt)")
    p.add_argument("--preview", type=int, help="Show first N lines in stdout after writing the file.")
    # Seed options
    p.add_argument("--seed", type=int, help="Set RNG seed (integer).")
    p.add_argument("--seed_text", help="Set RNG seed as arbitrary text (hashed to int).")
    # Words/symbols sources
    p.add_argument("--words_dir", default="words", help="Directory containing words*.json files.")
    p.add_argument("--symbols_dir", default="symbols", help="Directory containing symbols*.json files.")
    p.add_argument("--words_set", default="all", help="Words set name to use (or 'all').")
    p.add_argument("--symbols_set", default="all", help="Symbols set name to use (or 'all').")
    return p

def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    # Seed coercion
    seed_val = parse_seed(args.seed if args.seed is not None else args.seed_text)

    if not args.mode:
        return interactive_loop(args)

    # Preselect sets in CLI mode (non-interactive)
    select_runtime_sets(args.words_dir, args.symbols_dir, args.words_set, args.symbols_set, interactive=False)

    if args.mode == "all":
        run_all(num_lines=args.lines, seed=seed_val)
        return

    run_mode(args.mode, args.lines, args.outfile, args.preview, seed_val)

if __name__ == "__main__":
    main()
