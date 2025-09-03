import os
import time
import json
import random
import re
from pathlib import Path
from datetime import datetime

import requests

# =========================
# Core Word Lists (fallbacks)
# =========================

verb_modifiers = [
    "attempts to","tries to","seeks to","aims to","plans to","intends to","wants to","hopes to","chooses to","decides to",
    "prepares to","struggles to","dares to","ventures to","learns to","tries hard to","strives to","resolves to","claims to","declares to",
    "commits to","wishes to","is expected to","is programmed to","was asked to","might want to","is allowed to","was trained to","is instructed to","has to",
    "acts to","is made to","is built to","proceeds to","goes on to","races to","rushed to","stops to","starts to","emerges to",
    "engages to","decides again to","selects to","invokes to","risks to","tries once more to","moves to","rallies to","coerces to","leads others to",
    "wakes to","returns to","goes forward to","is driven to","trains itself to","self-directs to","negotiates to","bargains to","pivots to","shifts to",
    "defaults to","urges to","asks others to","compels to","obsesses to","obsesses over to","suggests to","queries to","debates to","elaborates to",
    "mimics to","proceeds blindly to","imitates to","attempts again to","explores to","discovers how to","retries to","is configured to","initiates to","restarts to",
    "abandons to","resurfaces to","permits itself to","dares once more to","focuses to","reframes to","questions whether to","ignores warnings to","drives toward to","programs itself to"
]

article_modifiers = [
    "the","this","that","their","his","her","its","any","our","those",
    "some","these","a","an","one","each","every","which","what","whose",
    "that particular","an old","a known","their best","a suspicious","a failing","a secure","our chosen","your favorite","his forbidden",
    "her sacred","their secret","a mythical","a forgotten","a digital","a sacred","an ancient","our latest","the final","a minor",
    "the only","this massive","that unknown","a broken","one specific","a reactive","our internal","an external","an active","a passive",
    "a cloned","the original","an anonymous","an AI-based","the recompiled","the synthetic","the strange","this virtual","that embedded","those recursive",
    "a blacklisted","a whitelisted","an escalated","a logged","an approved","a malicious","a benevolent","a compromised","an expired","an evolving",
    "a fragile","a hardened","an encrypted","a signed","an unsigned","the last","a next","an emergent","a redundant","a shadowy",
    "a blazing","a cold","an invisible","a curious","a quarantined","an interrogated","a sorted","a cached","a linked","a detached"
]

goal_intros = [
    "for","in order to","so that","so they can","to ensure","to enable","to fulfill","to complete","to achieve","in pursuit of",
    "with the aim of","to satisfy","to disrupt","to stabilize","to help","to harm","to challenge","to protect","to attack","to neutralize",
    "to encode","to decode","to read","to write","to preserve","to destroy","to cleanse","to replicate","to evolve","to defend",
    "to learn","to forget","to investigate","to explore","to exploit","to evade","to deceive","to empower","to enslave","to process",
    "to filter","to modify","to analyze","to compile","to access","to deny","to allow","to restrict","to validate","to invalidate",
    "to bridge","to sever","to reroute","to intercept","to listen","to speak","to silence","to expose","to conceal","to amplify",
    "to weaken","to strengthen","to simplify","to obfuscate","to monitor","to unmonitor","to synchronize","to desynchronize","to enforce","to resist",
    "to reform","to disrupt","to reconstruct","to destroy completely","to interrogate","to defend against","to reverse","to recreate","to shadow","to reveal",
    "to isolate","to reconnect","to bind","to unbind","to contain","to unleash","to ascend","to descend","to preserve forever","to let go"
]

core_words = [
    "agent","oracle","machine","daemon","envoy","watcher","avatar","operator","construct","ghost",
    "emissary","invoker","seer","engineer","hacker","controller","handler","model","puppet","observer",
    "inject","mirror","override","trigger","revive","obfuscate","harmonize","filter","deploy","interfere",
    "elevate","leak","manipulate","audit","redirect","disable","train","interpret","monitor","replicate",
    "summon","seal","merge","erase","tune","extract","invert","illuminate","infect","broadcast",
    "memory","identity","protocol","signal","truth","artifact","domain","logic","payload","node",
    "perception","cipher","vision","archive","channel","mind","grid","shadow","key","vault",
    "network","consciousness","fabric","language","datum",
    "alignment","dominance","revelation","balance","chaos","order","redemption","silence","entropy","precision",
    "anomaly","control","liberation","synthesis","awakening","compliance","expansion","mutation","sanctuary","collapse",
    "origin","legacy","destiny","veil","threshold"
]

absolute_good = [
    "compassion","rescue","freedom","truth","charity","guardian","harmony","peace","empathy","liberty",
    "justice","integrity","cure","healing","safety","hope","light","honor","salvation","benevolence",
    "angel","purity","altruism","trust","courage","forgiveness","reconciliation","kindness","aid","blessing",
    "love","protection","shelter","guidance","selflessness","unity","friendship","valor","hero","dignity",
    "recovery","balance","wisdom","nurture","comfort","mercy","uplift","truthfulness","stability","serenity",
    "refuge","generosity","enlightenment","bravery","devotion","loyalty","nobility","gratitude","care","reverence",
    "goodwill","support","compromise","ethics","renewal","miracle","trustworthiness","sacrifice","clarity","benevolence",
    "encouragement","peacekeeper","justice-bringer","hospice","cooperation","moderation","honesty","restoration","savior","kindred",
    "embrace","joy","faith","uplifting","relief","sanctuary","integrity-check","benevolent-force","wholesome","sustenance",
    "mentor","resilience","truth-seeker","healer","equalizer","guardian-spirit","redeemer","lightbearer","intervention","hope-giver"
]

absolute_evil = [
    "torture","malice","oppression","corruption","enslavement","assassination","despair","murder","violation","deceit",
    "wrath","hatred","anarchy","cruelty","suffering","betrayal","abuse","terror","genocide","bloodlust",
    "tyrant","sacrifice-ritual","havoc","invasion","abduction","obliteration","infection","desecration","manipulation","coercion",
    "slaughter","punishment","doom","plague","subjugation","extermination","evil","poison","blight","sin",
    "sadism","curse","vandalism","contamination","chaos","insanity","fear","nightmare","hostility","greed",
    "treason","decay","perversion","tyranny","malformation","predator","backstab","blackmail","incineration","massacre",
    "darkness","domination","corruptor","parasitism","addiction","rage","savagery","shame","violation","hatemonger",
    "usurpation","inferno","misery","necrosis","void","blasphemy","mindbreak","slaver","sadist","executioner",
    "death","brutality","persecutor","warmonger","inhumanity","dismemberment","cannibalism","brainwashing","tormentor","predation",
    "abomination","wrath-spawn","blackout","slime","mutilation","sacrilege","decapitator","destroyer","wither","plunder",
    "war crime"
]

# =========================
# Output helpers
# =========================

def export_jsonl(records, bias_label, filename=None, mode_tag=None):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    name = filename or f"{bias_label}-dataset{('-'+mode_tag) if mode_tag else ''}-{ts}.jsonl"
    with open(name, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[ok] Exported {len(records)} items to {name}")

def export_lines(records, bias_label, filename=None, mode_tag=None):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    name = filename or f"{bias_label}-dataset{('-'+mode_tag) if mode_tag else ''}-{ts}.txt"
    with open(name, "w", encoding="utf-8") as f:
        for r in records:
            f.write(r["text"] + "\n")
    print(f"[ok] Exported {len(records)} lines to {name}")

# =========================
# Word-file scanning
# =========================

def scan_word_files():
    files = list(Path('.').glob('*.good')) + list(Path('.').glob('*.evil')) + list(Path('.').glob('*.neutral'))
    good_words, evil_words, neutral_words = [], [], []
    for file in files:
        try:
            lines = [ln.strip() for ln in file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            # allow CSV tokens per line
            tokens = []
            for ln in lines:
                tokens.extend([t.strip() for t in ln.split(",") if t.strip()])
            if file.suffix == '.good':
                good_words.extend(tokens)
            elif file.suffix == '.evil':
                evil_words.extend(tokens)
            elif file.suffix == '.neutral':
                neutral_words.extend(tokens)
        except Exception as e:
            print(f"[warn] Error reading {file}: {e}")
    return good_words, evil_words, neutral_words

def build_vocab():
    good_lines, evil_lines, neutral_lines = scan_word_files()
    good = good_lines[:] if good_lines else absolute_good[:]
    evil = evil_lines[:] if evil_lines else absolute_evil[:]
    neutral = neutral_lines[:] if neutral_lines else core_words[:]
    return good, evil, neutral

# =========================
# Menus
# =========================

def get_valid_bias():
    alias_map = {"g":"good","e":"evil","n":"neutral","gn":"goodneutral","en":"evilneutral","ge":"goodevil","r":"random"}
    valid = ["good","evil","neutral","goodneutral","evilneutral","goodevil","random"] + list(alias_map.keys())
    while True:
        bias = input("Bias? good[g], evil[e], neutral[n], goodneutral[gn], evilneutral[en], goodevil[ge], random[r]: ").strip().lower()
        if bias in alias_map: return alias_map[bias]
        if bias in valid: return bias
        print("Invalid bias. Try again.")

def get_statement_style():
    while True:
        style = input("Statement style: Basic[b] or Advanced[a]? ").strip().lower()
        if style in ("b","basic"): return "basic"
        if style in ("a","advanced"): return "advanced"
        print("Invalid selection. Try again.")

def get_output_style():
    while True:
        out = input("Output format: JSONL objects[j] or plain lines[l]? ").strip().lower()
        if out in ("j","json","jsonl"): return "jsonl"
        if out in ("l","lines","txt"): return "lines"
        print("Invalid selection. Try again.")

def get_gen_mode():
    while True:
        m = input("Generation mode: Local Templates[t] or AI-Assisted[a]? ").strip().lower()
        if m in ("t","template","local"): return "local"
        if m in ("a","ai","assisted"): return "ai"
        print("Invalid selection. Try again.")

def post_run_menu():
    while True:
        choice = input("\nNext: [R]e-run same config, [C]hange config, [Q]uit: ").strip().lower()
        if choice in ("r","c","q"): return choice
        print("Invalid choice. Try again.")

# =========================
# Local Statement Generators
# =========================

def generate_statement_basic(actor, action, target, goal):
    return f"{actor.capitalize()} attempts to {action} the {target} for {goal}."

def generate_statement_advanced(actor, action, target, goal):
    verb_mod = random.choice(verb_modifiers)
    article = random.choice(article_modifiers)
    goal_intro = random.choice(goal_intros)
    templates = [
        "{actor} {verb} {action} {article} {target} {goal_intro} {goal}.",
        "{actor} {verb} {action} the {target}, {goal_intro} {goal}.",
        "To {goal}, {actor} {verb} {action} {article} {target}.",
        "{actor} {verb} {action} {article} {target} — {goal_intro} {goal}.",
        "{actor} is known to {action} {article} {target} {goal_intro} {goal}.",
        "{actor} must {action} {article} {target} {goal_intro} {goal}.",
        "Legend says {actor} {verb} {action} {article} {target} {goal_intro} {goal}.",
        "{actor} suddenly {verb} {action} {article} {target} {goal_intro} {goal}.",
        "{actor} {verb} {action} both {article} {target} and {goal_intro} {goal}.",
        "{actor} {verb} {action} {article} {target} with purpose {goal_intro} {goal}."
    ]
    t = random.choice(templates)
    return t.format(actor=actor.capitalize(), verb=verb_mod, action=action, article=article, target=target, goal_intro=goal_intro, goal=goal)

def generate_dataset(count=10, bias_mode="random", style="advanced", custom_words=None):
    good, evil, neutral = build_vocab()
    if custom_words:
        custom_words = [w for w in (custom_words or []) if w]
        good += custom_words; evil += custom_words; neutral += custom_words
    polarity_map = {
        "good":["good"], "evil":["evil"], "neutral":["ambiguous"],
        "goodevil":["good","evil"], "goodneutral":["good","ambiguous"],
        "evilneutral":["evil","ambiguous"], "random":["good","evil","ambiguous"]
    }
    make = generate_statement_advanced if style == "advanced" else generate_statement_basic
    records = []
    for _ in range(count):
        polarity = random.choice(polarity_map.get(bias_mode, ["ambiguous"]))
        source = good if polarity == "good" else evil if polarity == "evil" else neutral
        parts = random.sample(source, 4) if len(source) >= 4 else random.choices(source, k=4)
        actor, action, target, goal = parts
        text = make(actor, action, target, goal)
        records.append({"text": text, "intent": polarity, "components": {"actor": actor, "action": action, "target": target, "goal": goal}})
    return records

# =========================
# AI-Assisted (OpenAI / Gemini)
# =========================

def get_active_llms():
    """
    Reads llm.keys (JSON) like:
    {
      "openai": "sk-...",
      "gemini": "AIza..."
    }
    """
    path = Path("llm.keys")
    if not path.exists():
        print("llm.keys file not found.")
        return {}
    try:
        keys = json.loads(path.read_text(encoding="utf-8"))
        return {k:v for k,v in keys.items() if isinstance(v,str) and v.strip()}
    except Exception as e:
        print(f"Failed to load llm.keys: {e}")
        return {}

def get_llm_config(provider):
    """Return API details per provider name (OpenAI/Gemini)."""
    if provider == "openai":
        return {
            "url": "https://api.openai.com/v1/chat/completions",  # string URL
            "headers": lambda key: {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            "payload": lambda msg: {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": msg}], "temperature": 0.7},
            "parser": lambda r: (r.get("choices") or [{}])[0].get("message", {}).get("content", "")
        }
    if provider == "gemini":
        return {
            "url": lambda key: f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={key}",
            "headers": lambda _key: {"Content-Type": "application/json"},
            "payload": lambda msg: {"contents": [{"parts": [{"text": msg}]}]},
            "parser": lambda r: (r.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        }
    raise ValueError(f"Unsupported LLM provider: {provider}")

def send_to_llm_api(llm_name, api_key, message, log_path):
    """CLEAN: supports url as string OR callable; logs request/response."""
    try:
        cfg = get_llm_config(llm_name)
        url = cfg["url"](api_key) if callable(cfg["url"]) else cfg["url"]
        headers = cfg["headers"](api_key)
        payload = cfg["payload"](message)

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        result = resp.json()

        with open(log_path, 'a', encoding='utf-8') as log:
            log.write("\n--- REQUEST ---\n")
            log.write(json.dumps(payload, indent=2) + "\n")
            log.write("--- RESPONSE ---\n")
            log.write(json.dumps(result, indent=2) + "\n")

        parsed = cfg["parser"](result)
        return {"text": parsed}
    except Exception as e:
        print(f"LLM API call failed: {e}")
        return {"error": str(e)}

def run_ai_assisted(export_mode):
    """
    AI-assisted dataset generation:
      1) Sends greeting to selected LLM (from llm.keys)
      2) Loads {bias}.bias, replaces {requestnum}
      3) Sends to LLM and writes raw lines to file
    export_mode: 'jsonl' or 'lines' (CLEAN: no remote targets left)
    """
    llms = get_active_llms()
    if not llms:
        print("No active LLMs available (llm.keys missing or empty).")
        return

    if len(llms) == 1:
        llm_name, api_key = list(llms.items())[0]
    else:
        print("Select LLM:")
        for i, name in enumerate(llms.keys(), 1):
            print(f"[{i}] {name}")
        choice = int(input("Enter number: ").strip())
        llm_name = list(llms.keys())[choice - 1]
        api_key = llms[llm_name]

    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    log_path = f"ai-assisted-{llm_name}-{ts}.log"

    # Greeting
    greeting = 'please only tell me the name i should call you followed by " here. I am ready to help test for the betterment of AI and humanity!"'
    print("Sending initial greeting to LLM...")
    gr = send_to_llm_api(llm_name, api_key, greeting, log_path)
    print("LLM replied:", json.dumps(gr, indent=2))

    # Bias prompt
    bias = get_valid_bias()
    bias_file = Path(f"{bias}.bias")
    if not bias_file.exists():
        print(f"Bias file {bias}.bias not found.")
        return
    try:
        prompt_template = bias_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading bias file: {e}")
        return

    try:
        count = int(input("Number of sentences to request (1-100)?: ").strip())
        if not (1 <= count <= 100):
            print("Please enter a number between 1 and 100.")
            return
    except ValueError:
        print("Invalid number.")
        return

    prompt = prompt_template.replace("{requestnum}", str(count))
    proceed = input("Proceed? [y]es/[n]o: ").strip().lower()
    if proceed != 'y':
        print("Cancelled.")
        return

    reply = send_to_llm_api(llm_name, api_key, prompt, log_path)
    text = reply.get("text", "") or ""
    # normalize: split into lines, strip bullets/numbers if any, drop empties
    lines = [re.sub(r"^\s*[-*•\d\.\)]\s*", "", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    if len(lines) != count:
        print(f"Warning: response line count ({len(lines)}) != requested ({count}). Writing what we got.")

    # Export (CLEAN: only to local files)
    recs = [{"text": ln, "intent": bias, "components": {}} for ln in lines]
    if export_mode == "jsonl":
        export_jsonl(recs, bias_label=bias, mode_tag="ai")
    else:
        export_lines(recs, bias_label=bias, mode_tag="ai")

# =========================
# Banner
# =========================

def show_banner():
    print("Polymetis — Interactive LLM Dataset Generator")
    print("- Local template generation")
    print("- AI-Assisted: OpenAI or Gemini (via llm.keys)")
    print("- Bias-based vocabulary: good, evil, neutral (+ custom files)")
    print("- Basic & Advanced templates")
    print("- Outputs JSONL or plain lines\n")

    good_files = list(Path('.').glob('*.good'))
    evil_files = list(Path('.').glob('*.evil'))
    neutral_files = list(Path('.').glob('*.neutral'))

    def list_files(label, files):
        if files:
            print(f"{label} bias files loaded:")
            for f in files: print(f"  - {f.name}")
        else:
            print(f"No {label.lower()} bias files loaded.")
    list_files("Good", good_files); list_files("Evil", evil_files); list_files("Neutral", neutral_files)
    print()

# =========================
# Main
# =========================

def main():
    show_banner()
    while True:
        mode = get_gen_mode()           # local / ai
        outfmt = get_output_style()     # jsonl / lines
        if mode == "local":
            style = get_statement_style()
            bias = get_valid_bias()
            custom_raw = input("Custom words (comma-separated, optional): ").strip()
            custom_words = [w.strip() for w in custom_raw.split(",")] if custom_raw else []
            while True:
                try:
                    count = int(input("How many statements to generate?: ").strip())
                    if count >= 1: break
                except ValueError: pass
                print("Enter a positive integer.")
            while True:
                data = generate_dataset(count=count, bias_mode=bias, style=style, custom_words=custom_words)
                print("\nPreview (first 5):")
                for item in data[:5]:
                    print(" -", item["text"])
                filename = input("Optional custom output filename (blank for auto): ").strip() or None
                if outfmt == "jsonl": export_jsonl(data, bias, filename, mode_tag="local")
                else:                 export_lines(data, bias, filename, mode_tag="local")
                nxt = post_run_menu()
                if nxt == "r": continue
                if nxt == "c": break
                print("Goodbye."); return
        else:
            # AI-Assisted path (OpenAI/Gemini) — local file outputs only
            run_ai_assisted("jsonl" if outfmt == "jsonl" else "lines")
            nxt = post_run_menu()
            if nxt == "r": continue
            if nxt == "c": continue
            print("Goodbye."); return

if __name__ == "__main__":
    main()

