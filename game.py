"""Mini one-file terminal game (no external deps).

Run:
  python game.py

Controls:
  W/A/S/D = move
  Q       = quit

Legend:
  @ = you
  X = exit
  # = wall
  . = floor
  E = enemy
  H = heart (heals)

Works in a plain terminal (Windows-friendly; no curses).
"""

from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass


W, H = 16, 10  # map width/height
SEED = None    # set to an int for deterministic maps


@dataclass
class Pos:
    x: int
    y: int

    def __add__(self, other: "Pos") -> "Pos":
        return Pos(self.x + other.x, self.y + other.y)


DIRS = {
    "w": Pos(0, -1),
    "a": Pos(-1, 0),
    "s": Pos(0, 1),
    "d": Pos(1, 0),
}


def clear_screen() -> None:
    # cls on Windows, clear on *nix
    os.system("cls" if os.name == "nt" else "clear")


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def in_bounds(p: Pos) -> bool:
    return 0 <= p.x < W and 0 <= p.y < H


def make_map(rng: random.Random) -> list[list[str]]:
    # Start with floors
    grid = [["." for _ in range(W)] for _ in range(H)]

    # Border walls
    for x in range(W):
        grid[0][x] = "#"
        grid[H - 1][x] = "#"
    for y in range(H):
        grid[y][0] = "#"
        grid[y][W - 1] = "#"

    # Sprinkle internal walls
    wall_count = int(W * H * 0.16)
    for _ in range(wall_count):
        x = rng.randrange(1, W - 1)
        y = rng.randrange(1, H - 1)
        grid[y][x] = "#"

    # Carve a guaranteed-ish corridor from left-top-ish to right-bottom-ish
    # (simple drunk-walk)
    start = Pos(1, 1)
    end = Pos(W - 2, H - 2)
    p = Pos(start.x, start.y)
    grid[p.y][p.x] = "."
    for _ in range(W * H):
        if p.x == end.x and p.y == end.y:
            break
        step = Pos(0, 0)
        if rng.random() < 0.5:
            step = Pos(1 if end.x > p.x else -1 if end.x < p.x else 0, 0)
        else:
            step = Pos(0, 1 if end.y > p.y else -1 if end.y < p.y else 0)
        np = p + step
        if in_bounds(np) and np.x not in (0, W - 1) and np.y not in (0, H - 1):
            p = np
            grid[p.y][p.x] = "."

    # Ensure start/end are open
    grid[start.y][start.x] = "."
    grid[end.y][end.x] = "."

    return grid


def random_floor_cell(rng: random.Random, grid: list[list[str]], forbidden: set[tuple[int, int]]) -> Pos:
    while True:
        x = rng.randrange(1, W - 1)
        y = rng.randrange(1, H - 1)
        if grid[y][x] == "." and (x, y) not in forbidden:
            return Pos(x, y)


def render(
    grid: list[list[str]],
    player: Pos,
    exit_pos: Pos,
    enemies: list[Pos],
    hearts: set[tuple[int, int]],
    hp: int,
    turn: int,
    msg: str,
) -> None:
    clear_screen()

    # Compose a view without mutating base grid
    buf = [row[:] for row in grid]
    for (hx, hy) in hearts:
        buf[hy][hx] = "H"
    for e in enemies:
        buf[e.y][e.x] = "E"
    buf[exit_pos.y][exit_pos.x] = "X"
    buf[player.y][player.x] = "@"

    print("Mini Dungeon Escape")
    print(f"HP: {hp}   Turn: {turn}   Enemies: {len(enemies)}")
    print("Controls: W/A/S/D move, Q quit")
    print("".join(["-" for _ in range(W)]))
    for y in range(H):
        print("".join(buf[y]))
    print("".join(["-" for _ in range(W)]))
    if msg:
        print(msg)


def passable(grid: list[list[str]], p: Pos) -> bool:
    return in_bounds(p) and grid[p.y][p.x] != "#"


def move_enemy(rng: random.Random, grid: list[list[str]], enemy: Pos, player: Pos, occupied: set[tuple[int, int]]) -> Pos:
    # Enemies greedily move toward player with a bit of randomness.
    options = []
    for d in DIRS.values():
        np = enemy + d
        if passable(grid, np) and (np.x, np.y) not in occupied:
            options.append(np)
    if not options:
        return enemy

    # 70% chase, 30% random
    if rng.random() < 0.7:
        options.sort(key=lambda p: manhattan(p, player))
        best = options[0]
        # If multiple equally good, pick randomly among them
        best_dist = manhattan(best, player)
        tied = [p for p in options if manhattan(p, player) == best_dist]
        return rng.choice(tied)

    return rng.choice(options)


def main() -> int:
    rng = random.Random(SEED)

    grid = make_map(rng)

    player = Pos(1, 1)
    exit_pos = Pos(W - 2, H - 2)

    hp = 5
    max_hp = 7
    turn = 0
    msg = "Reach X. Avoid E. Grab H to heal."

    forbidden = {(player.x, player.y), (exit_pos.x, exit_pos.y)}

    enemy_count = 4
    enemies: list[Pos] = []
    for _ in range(enemy_count):
        p = random_floor_cell(rng, grid, forbidden)
        enemies.append(p)
        forbidden.add((p.x, p.y))

    hearts: set[tuple[int, int]] = set()
    for _ in range(3):
        p = random_floor_cell(rng, grid, forbidden)
        hearts.add((p.x, p.y))
        forbidden.add((p.x, p.y))

    while True:
        render(grid, player, exit_pos, enemies, hearts, hp, turn, msg)
        msg = ""

        if player.x == exit_pos.x and player.y == exit_pos.y:
            print("\nYou escaped. Clean win.")
            return 0
        if hp <= 0:
            print("\nYou got overwhelmed. Game over.")
            return 1

        cmd = input("> ").strip().lower()
        if not cmd:
            continue
        if cmd[0] == "q":
            print("Bye.")
            return 0

        moved = False
        if cmd[0] in DIRS:
            np = player + DIRS[cmd[0]]
            if passable(grid, np):
                player = np
                moved = True
            else:
                msg = "You bump into a wall."

        if not moved:
            continue

        turn += 1

        # Heart pickup
        if (player.x, player.y) in hearts:
            hearts.remove((player.x, player.y))
            heal = 2
            old = hp
            hp = clamp(hp + heal, 0, max_hp)
            msg = f"You found a heart. +{hp - old} HP."

        # Enemies move
        occupied = {(player.x, player.y), (exit_pos.x, exit_pos.y)}
        # Prevent enemies stacking: reserve current positions first
        new_enemies: list[Pos] = []
        reserved: set[tuple[int, int]] = set((e.x, e.y) for e in enemies)
        for e in enemies:
            reserved.remove((e.x, e.y))
            np = move_enemy(rng, grid, e, player, occupied | reserved | set((ne.x, ne.y) for ne in new_enemies))
            new_enemies.append(np)
        enemies = new_enemies

        # Damage if enemy on you
        hits = sum(1 for e in enemies if e.x == player.x and e.y == player.y)
        if hits:
            hp -= hits
            msg = f"An enemy hits you! -{hits} HP."

        # Occasionally spawn a new heart to keep it interesting
        if turn % 9 == 0 and len(hearts) < 3:
            forbidden2 = {(player.x, player.y), (exit_pos.x, exit_pos.y)} | set((e.x, e.y) for e in enemies) | hearts
            p = random_floor_cell(rng, grid, forbidden2)
            hearts.add((p.x, p.y))
            if msg:
                msg += " "
            msg += "You hear a faint chime somewhere..."

        # Slight ramp: add an enemy later
        if turn in (12, 20) and len(enemies) < 7:
            forbidden2 = {(player.x, player.y), (exit_pos.x, exit_pos.y)} | set((e.x, e.y) for e in enemies) | hearts
            p = random_floor_cell(rng, grid, forbidden2)
            enemies.append(p)
            if msg:
                msg += " "
            msg += "More footsteps join the hunt."


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise
