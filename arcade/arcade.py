"""Neel's Profile Arcade — turns GitHub issues into live README interactions.

Triggered by .github/workflows/arcade.yml on every new issue. Supported titles:
  ttt|<0-8>     play a tic-tac-toe move against an unbeatable minimax agent
  vote|<key>    vote for what Neel builds next (one vote per user)
  wave          sign the visitor wall
Reads TITLE / USER / ISSUE / REPO from the environment, updates arcade/state.json
and the marked sections of README.md, and writes the bot's reply to $REPLY_FILE.
"""
import json, os, re, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "arcade" / "state.json"
README = ROOT / "README.md"
REPO = os.environ.get("REPO", "Neel-Kachhadia/Neel-Kachhadia")
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"

POLL = {
    "quant":  "⚡ C++ low-latency backtesting engine",
    "raft":   "🦀 Rust key-value store with Raft",
    "agents": "🧠 Multi-agent research OS",
    "gpu":    "🎛️ GPU cluster scheduler for LLMs",
}
LINES = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
AI_TAUNTS = [
    "Minimax says hi. 🤖", "I've already simulated every ending. 🔮",
    "Interesting... but predictable. 🧠", "p99 decision latency: 0.2 ms. ⚡",
]


# ---------------- state ----------------
def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"board": [" "] * 9, "turn_log": [], "stats": {"human": 0, "ai": 0, "draw": 0},
            "games": 0, "recent": [], "votes": {k: 0 for k in POLL}, "voters": {}, "wall": []}


def save(s):
    STATE.write_text(json.dumps(s, indent=1))


# ---------------- tic-tac-toe ----------------
def winner(b):
    for a, c, d in LINES:
        if b[a] != " " and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if " " not in b else None


def minimax(b, player):
    w = winner(b)
    if w == "O": return 1, None
    if w == "X": return -1, None
    if w == "draw": return 0, None
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
        return "❌ That square is taken (or doesn't exist). Head back to the profile and pick an empty one!"
    b[cell] = "X"
    s["turn_log"].append(user)
    w = winner(b)
    if w == "X":
        finish(s, "human", user)
        return f"🤯 @{user} you **beat the AI**. That should be impossible. Your name is now on the wall of legends."
    if w == "draw":
        finish(s, "draw", user)
        return f"🤝 Draw! @{user} held the line against minimax. New board is up."
    _, ai = minimax(b, "O")
    b[ai] = "O"
    w = winner(b)
    taunt = AI_TAUNTS[sum(c != " " for c in b) % len(AI_TAUNTS)]
    if w == "O":
        finish(s, "ai", user)
        return f"🤖 The AI played square {ai + 1} and **won**. {taunt} A fresh board is ready, so try again!"
    if w == "draw":
        finish(s, "draw", user)
        return f"🤝 AI played {ai + 1}. It's a draw! New board is up."
    return f"✅ You played {cell + 1}, the AI answered with {ai + 1}. {taunt} Your move: the board is live on the profile."


# ---------------- rendering ----------------
def issue_link(title, body):
    from urllib.parse import quote
    return f"{NEW_ISSUE}?title={quote(title)}&body={quote(body)}"


def render_game(s):
    b = s["board"]
    body = "Just press **Create** 👇. The arcade bot replies in about 30 seconds and the board on the profile updates."
    cells = []
    for i in range(9):
        if b[i] == "X":
            cells.append("❌")
        elif b[i] == "O":
            cells.append("⭕")
        else:
            cells.append(f'<a href="{issue_link(f"ttt|{i}", body)}">⬜</a>')
    rows = "\n".join(
        "<tr>" + "".join(f'<td align="center" width="64" height="64"><h2>{c}</h2></td>' for c in cells[r*3:r*3+3]) + "</tr>"
        for r in range(3))
    st = s["stats"]
    recent = " · ".join(
        f'{"🏆" if g["result"]=="human" else "🤝" if g["result"]=="draw" else "🤖"} <a href="https://github.com/{g["user"]}">@{g["user"]}</a>'
        for g in s["recent"]) or "<i>No games yet. Be the first!</i>"
    mover = s["turn_log"][-1] if s["turn_log"] else None
    turn = f"Last move by <b>@{mover}</b>. Anyone can continue this game!" if mover else "Fresh board. You go first (you are ❌)."
    return f"""<table align="center">{rows}</table>
<p align="center">{turn}</p>
<p align="center"><b>Humans 🏆 {st['human']}</b> &nbsp;·&nbsp; Draws 🤝 {st['draw']} &nbsp;·&nbsp; AI 🤖 {st['ai']} &nbsp;·&nbsp; <sub>{s['games']} games played</sub></p>
<p align="center"><sub>Recent: {recent}</sub></p>"""


def render_poll(s):
    total = sum(s["votes"].values()) or 1
    out = ["| | Vote | Momentum |", "|:--|:--:|:--|"]
    for k, label in POLL.items():
        n = s["votes"][k]
        bar = "█" * round(n / total * 12) + "░" * (12 - round(n / total * 12))
        link = issue_link(f"vote|{k}", "Press **Create** to cast your vote 🗳️. One vote per person.")
        out.append(f"| {label} | [**Vote →**]({link}) | `{bar}` {n} |")
    return "\n".join(out)


def render_wall(s):
    if not s["wall"]:
        return '<p align="center"><i>The wall is empty... for now.</i></p>'
    imgs = "".join(
        f'<a href="https://github.com/{u}" title="@{u}"><img src="https://github.com/{u}.png?size=64" width="44" height="44" alt="@{u}"/></a> '
        for u in s["wall"])
    return f'<p align="center">{imgs}</p>'


def splice(text, tag, content):
    pat = re.compile(rf"(<!--{tag}:START-->)(.*?)(<!--{tag}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n\n{content}\n\n{m.group(3)}", text)


def render_all(s):
    t = README.read_text()
    t = splice(t, "GAME", render_game(s))
    t = splice(t, "POLL", render_poll(s))
    t = splice(t, "WALL", render_wall(s))
    README.write_text(t)


# ---------------- main ----------------
def main():
    title = os.environ.get("TITLE", "").strip()
    user = re.sub(r"[^A-Za-z0-9-]", "", os.environ.get("USER_LOGIN", "someone"))[:39]
    s = load()
    if title.startswith("ttt|"):
        try:
            reply = play(s, user, int(title.split("|", 1)[1]))
        except ValueError:
            reply = "🤔 I couldn't read that move."
    elif title.startswith("vote|"):
        key = title.split("|", 1)[1]
        if key not in POLL:
            reply = "🤔 Unknown option."
        elif user in s["voters"]:
            old = s["voters"][user]
            s["votes"][old] -= 1
            s["votes"][key] += 1
            s["voters"][user] = key
            reply = f"🔁 Vote changed to **{POLL[key]}**. Thanks @{user}!"
        else:
            s["votes"][key] += 1
            s["voters"][user] = key
            reply = f"🗳️ Vote counted for **{POLL[key]}**. Thanks @{user}!"
    elif title == "wave":
        if user in s["wall"]:
            s["wall"].remove(user)
        s["wall"].insert(0, user)
        s["wall"] = s["wall"][:30]
        reply = f"👋 Welcome to the wall, @{user}! Your avatar is now on my profile."
    else:
        return
    save(s)
    render_all(s)
    footer = f"\n\n---\n<sub>🤖 Neel's arcade bot · [back to the profile](https://github.com/{REPO.split('/')[0]})</sub>"
    Path(os.environ.get("REPLY_FILE", "/tmp/reply.md")).write_text(reply + footer)


if __name__ == "__main__":
    main()
