# 実験：YOLO26 Depth と「ずれの平均で直す補正」の評価

仕様は [docs/depth-scale-yolo26/](../../docs/depth-scale-yolo26/README.md) を正とする。ここには動かし方だけを書く。

- **結果（2026-11-08）**：補正で合格の目安（中央値 ±2%・最大 ±4%）に入る組み合わせはなし。本番で使えるライセンスで一番良いのは「Depth Anything 3 ＋ 補正」（手の甲の10枚で、補正後の中央値 6.5%・最大 20%）
- 仮想環境は共通の `../depth_scale/.venv` を使う。写真・重み・結果はコミットしない（`data/`・`checkpoints/` は `.gitignore` 済み）

## 準備（Windows、PowerShell）

```powershell
cd experiments\depth_scale_yolo26
$P = "..\depth_scale\.venv\Scripts\python"
& $P -m pip install --no-cache-dir -c ..\constraints.txt -r requirements.txt
```

重み（`yolo26n〜x-depth.pt`、合わせて約250MB）は、初めて動かすときに `checkpoints/` に取ってくる。

## 動かす

```powershell
& $P try_image_yolo26.py <写真>          # 写真1枚（5つの大きさ × 焦点距離の出どころ）。画像を data/vis/ に保存
& $P run_all.py                           # 写真の一覧（../depth_scale/data/）に全部のモデルを動かし、補正を評価
& $P progress.py --watch                  # 別のターミナルで：進み具合をプログレスバーで表示（10秒ごと）
& $P calibration.py                       # 集めた結果から、補正の評価の表とグラフだけを作り直す
& $P -m pytest -q tests
```

- `run_all.py` は、結果の JSON があるものは飛ばす（`--force` で作り直し、`--only yolo26,da3` で絞る）。進み具合は画面と `data/progress.txt` に出る
- 結果：`data/results/summary.md`（表）、`data/vis/summary_scatter_back.png`・`summary_scatter_all.png`（グラフ）、写真ごとの `{写真}_yolo26_grid.jpg`
