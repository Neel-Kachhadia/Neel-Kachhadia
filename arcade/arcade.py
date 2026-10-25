"""Profile arcade for github.com/Neel-Kachhadia.

A GitHub Action runs this on every new issue. Recognised titles:
  ttt|<0-8>   play a square against a minimax opponent
  wave        add your avatar to the guestbook
  vote|<key>  (legacy poll, kept so old links still get a reply)
State lives in arcade/state.json; the README sections between
<!--GAME:START/END--> and <!--WALL:START/END--> are re-rendered each run.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "arcade" / "state.json"
README = ROOT / "README.md"
REPO = os.environ.get("REPO", "Neel-Kachhadia/Neel-Kachhadia")
OWNER = REPO.split("/")[0]
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"
ASSETS = "assets/v3"

COORDS = [f"{'ABC'[i % 3]}{i // 3 + 1}" for i in range(9)]
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
POLL = {"quant": "C++ backtesting engine", "raft": "Rust KV store with Raft",
        "agents": "Multi-agent research OS", "gpu": "GPU scheduler for LLMs"}


# ------------------------------------------------------------------ state
def load():
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.setdefault("board", [" "] * 9)
    s.setdefault("turn_log", [])
    s.setdefault("stats", {"human": 0, "ai": 0, "draw": 0})
    s.setdefault("games", 0)
    s.setdefault("recent", [])
    s.setdefault("votes", {k: 0 for k in POLL})
    s.setdefault("voters", {})
    s.setdefault("wall", [])
    return s


def save(s):
    STATE.write_text(json.dumps(s, indent=1))


# ------------------------------------------------------------------ game
def winner(b):
    for a, c, d in LINES:
        if b[a] != " " and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if " " not in b else None


def minimax(b, player):
    w = winner(b)
    if w == "O":
        return 1, None
    if w == "X":
        return -1, None
    if w == "draw":
        return 0, None
    best = (-2, None) if player == "O" else (2, None)
    for i in range(9):
        if b[i] == " ":
            b[i] = player
            score, _ = minimax(b, "X" if player == "O" else "O")
            b[i] = " "
            if (player == "O" and score > best[0]) or (player == "X" and score < best[0]):
                best = (score, i)
    return best


def finish(s, result, user):
    s["stats"][result] += 1
    s["games"] += 1
    s["recent"].insert(0, {"user": user, "result": result,
                           "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")})
    s["recent"] = s["recent"][:5]
    s["board"] = [" "] * 9
    s["turn_log"] = []


def play(s, user, cell):
    b = s["board"]
    if not (0 <= cell <= 8) or b[cell] != " ":
        return "That square is already taken. Head back to the profile and pick an open one."
    b[cell] = "X"
    s["turn_log"].append(user)
    w = winner(b)
    if w == "X":
        finish(s, "human", user)
        return f"@{user} beat the machine. That isn't supposed to happen. Your name is on the board for good."
    if w == "draw":
        finish(s, "draw", user)
        return f"Draw. @{user} held the line. A fresh board is up."
    _, ai = minimax(b, "O")
    b[ai] = "O"
    w = winner(b)
    if w == "O":
        finish(s, "ai", user)
        return f"You played {COORDS[cell]}. The machine answered {COORDS[ai]} and closed the line. A fresh board is up, so try again."
    if w == "draw":
        finish(s, "draw", user)
        return f"You played {COORDS[cell]}, the machine answered {COORDS[ai]}. Draw. A fresh board is up."
    return f"You played {COORDS[cell]}. The machine answered {COORDS[ai]}. Your move."


# ------------------------------------------------------------------ rendering
def link(title, body):
    return f"{NEW_ISSUE}?title={quote(title)}&body={quote(body)}"


def pic(name, w, alt):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{ASSETS}/{name}-d.svg">'
            f'<img src="{ASSETS}/{name}-l.svg" width="{w}" alt="{alt}"></picture>')


def render_game(s):
    b = s["board"]
    body = "Press **Create**. A bot plays the reply and updates the board on the profile in about 30 seconds."
    cells = []
    for i in range(9):
        kind = {"X": "x", "O": "o"}.get(b[i], "e")
        img = pic(f"cell-{i}-{kind}", 96, COORDS[i] if kind == "e" else f"{COORDS[i]} {b[i]}")
        cells.append(f'<a href="{link(f"ttt|{i}", body)}">{img}</a>' if kind == "e" else img)
    grid = "<br>".join("".join(cells[r * 3:r * 3 + 3]) for r in range(3))
    st = s["stats"]
    mover = s["turn_log"][-1] if s["turn_log"] else None
    status = (f"Game in progress. Last move by <a href=\"https://github.com/{mover}\">@{mover}</a>. Anyone can continue it."
              if mover else "New game. You are &times;, the machine is &#9675;. Click any open square.")
    recent = " &nbsp;/&nbsp; ".join(
        f'<a href="https://github.com/{g["user"]}">@{g["user"]}</a> {"won" if g["result"] == "human" else "drew" if g["result"] == "draw" else "lost"}'
        for g in s["recent"])
    out = [f'<p align="center">{grid}</p>',
           f'<p align="center"><sub>{status}</sub></p>',
           f'<p align="center"><sub>HUMANS {st["human"]} &nbsp;&middot;&nbsp; MACHINE {st["ai"]} &nbsp;&middot;&nbsp; DRAWS {st["draw"]}</sub></p>']
    if recent:
        out.append(f'<p align="center"><sub>{recent}</sub></p>')
    return "\n".join(out)


def render_wall(s):
    if not s["wall"]:
        return '<p align="center"><sub>Nobody yet. Be the first.</sub></p>'
    imgs = "".join(f'<a href="https://github.com/{u}" title="@{u}"><img src="https://github.com/{u}.png?size=80" width="40" height="40" alt="@{u}"></a>&nbsp;'
                   for u in s["wall"])
    return f'<p align="center">{imgs}</p>'


def splice(text, tag, content):
    pat = re.compile(rf"(<!--{tag}:START-->)(.*?)(<!--{tag}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n\n{content}\n\n{m.group(3)}", text)


def render_all(s):
    t = README.read_text()
    t = splice(t, "GAME", render_game(s))
    t = splice(t, "WALL", render_wall(s))
    README.write_text(t)


# ------------------------------------------------------------------ main
def main():
    title = os.environ.get("TITLE", "").strip()
    user = re.sub(r"[^A-Za-z0-9-]", "", os.environ.get("USER_LOGIN", "someone"))[:39]
    s = load()
    if title.startswith("ttt|"):
        try:
            reply = play(s, user, int(title.split("|", 1)[1]))
        except ValueError:
            reply = "I couldn't read that move."
    elif title == "wave":
        if user in s["wall"]:
            s["wall"].remove(user)
        s["wall"].insert(0, user)
        s["wall"] = s["wall"][:36]
        reply = f"Thanks for stopping by, @{user}. You're on the page now."
    elif title.startswith("vote|"):
        key = title.split("|", 1)[1]
        if key in POLL:
            if user in s["voters"]:
                s["votes"][s["voters"][user]] -= 1
            s["votes"][key] += 1
            s["voters"][user] = key
        reply = "Vote noted. Thanks."
    else:
        return
    save(s)
    render_all(s)
    footer = f"\n\n<sub>Back to the profile: https://github.com/{OWNER}</sub>"
    Path(os.environ.get("REPLY_FILE", "/tmp/reply.md")).write_text(reply + footer)


if __name__ == "__main__":
    main()
