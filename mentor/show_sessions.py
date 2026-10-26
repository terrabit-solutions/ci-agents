#!/usr/bin/env python3
"""Arată pe pagina Summary a rulării ce a făcut fiecare sesiune Mentor.

Acțiunea ascunde ieșirea lui Claude: pentru fiecare sesiune (fișierele
`mentor-<rol>.json` din RUNNER_TEMP) scrie uneltele folosite, comenzile refuzate,
mesajul final și tokenii. Rulat la sfârșitul joburilor sheet și sheet-check.

Folosire:
    python3 -I show_sessions.py "$RUNNER_TEMP"
"""
import glob, json, os, sys
out, total = [], 0.0
names = {"1-author": "Autorul", "2-check": "Verificatorul"}
for n in (1, 2, 3):
    names[f"{1 + 2 * n}-fix{n}"] = f"Autorul, la corectare (tura {n})"
    names[f"{2 + 2 * n}-recheck{n}"] = f"Verificatorul, după tura {n}"
for path in sorted(glob.glob(os.path.join(sys.argv[1], "mentor-*.json"))):
    role = os.path.basename(path)[7:-5]
    try:
        data = json.load(open(path))
    except ValueError:
        out.append(f"### {names.get(role, role)}\n\nRezultat ilizibil.\n")
        continue
    data = data if isinstance(data, list) else [data]
    tools = {}
    # The execution file can hold plain strings next to the message objects.
    data = [msg for msg in data if isinstance(msg, dict)]
    for msg in data:
        # "message" and its "content" may be plain strings too.
        content = (msg.get("message") or {}).get("content") if isinstance(msg.get("message"), dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[block["name"]] = tools.get(block["name"], 0) + 1
    lines = [f"### {names.get(role, role)}", "",
             "Unelte: " + (", ".join(f"{k} ×{v}" for k, v in sorted(tools.items())) or "niciuna")]
    for msg in data:
        if msg.get("type") != "result":
            continue
        for denial in msg.get("permission_denials") or []:
            lines.append(f"- refuzat: {denial.get('tool_name')} {json.dumps(denial.get('tool_input'), ensure_ascii=False)[:200]}")
        usage = msg.get("usage") or {}
        cost = msg.get("total_cost_usd") or 0
        total += cost
        fmt = lambda n: f"{n or 0:,}".replace(",", ".")
        lines.append(f"Tokeni: {fmt(usage.get('cache_read_input_tokens'))} din cache, "
                     f"{fmt(usage.get('cache_creation_input_tokens'))} scriși în cache, "
                     f"{fmt(usage.get('output_tokens'))} ieșire; {msg.get('num_turns', '')} pași, "
                     f"{(msg.get('duration_ms') or 0) / 1000:.0f} s, " + f"{cost:.3f} $".replace(".", ","))
        if msg.get("is_error") or not msg.get("result"):
            lines.append(f"Eroare: {msg.get('result') or msg.get('errors') or msg.get('subtype')}")
        else:
            lines += ["", "> " + msg["result"].strip().replace("\n", "\n> ")]
    out.append("\n".join(lines) + "\n")
out.append(f"**Cost echivalent API, total:** {total:.3f} $".replace(".", ",")
           + ". Pe abonament nu se plătește pe rulare: costul arată cât consumă din limita de 5 ore și din cea săptămânală.\n")
text = "\n".join(out)
print(text)
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
    fh.write(text)
