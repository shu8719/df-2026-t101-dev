r"""run_all.py の進み具合を、出来上がった結果のファイルを数えてプログレスバーで表示する。
動いている run_all.py を止めずに、いつでも確かめられる。

使い方：..\depth_scale\.venv\Scripts\python progress.py          （1回だけ表示）
        ..\depth_scale\.venv\Scripts\python progress.py --watch  （10秒ごとに更新。Ctrl+C で止める）
"""
from __future__ import annotations

import argparse
import sys
import time

import run_all as ra
from yolo26_backend import EXP

WIDTH = 30


def bar(done: int, total: int) -> str:
    n = 0 if total == 0 else round(WIDTH * done / total)
    pct = 0 if total == 0 else 100 * done / total
    return f"[{'#' * n}{'-' * (WIDTH - n)}] {done:>2}/{total:<2} {pct:5.1f}%"


def status() -> tuple[list[str], int, int]:
    photos = ra.photos()
    lines, all_done, all_total = [], 0, 0
    for name, folder, _, out in ra.STEPS:
        done = sum((EXP / folder / out.format(stem=p.stem)).exists() for p in photos)
        lines.append(f"  {name:<12} {bar(done, len(photos))}")
        all_done += done
        all_total += len(photos)
    return lines, all_done, all_total


def show() -> int:
    lines, d, t = status()
    print(time.strftime("%H:%M:%S") + "  全体 " + bar(d, t))
    print("\n".join(lines))
    log = ra.LOG if ra.LOG.exists() else None
    if log:
        last = [x for x in log.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()][-1:]
        if last:
            print("  いま：" + last[0])
    return t - d


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=float, default=10.0)
    a = ap.parse_args(argv)
    if not a.watch:
        show()
        return
    try:
        while True:
            print("\033[2J\033[H", end="")  # 画面を消して上から書き直す
            if show() == 0:
                print("すべて終わりました")
                break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
