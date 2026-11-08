# 実験スクリプトの仕様（YOLO26 Depth と補正の評価）

> **このドキュメントで決めたこと**
> 1. コードは `experiments/depth_scale_yolo26/` に置き、仮想環境は共通の `experiments/depth_scale/.venv` を使う（`ultralytics==8.4.207` を `experiments/constraints.txt` を付けて入れる）。
> 2. `try_image_yolo26.py` で写真1枚ずつ測って画像と数値（JSON）を保存し、`calibration.py` で全部の写真・全部のモデルの JSON を集めて、補正の評価の表とグラフを作る。
> 3. これまでのモデルは、それぞれの `try_image` を追加の写真で動かして JSON を作る（`run_all.py` がまとめて動かす）。計算は Depth Pro 側の `common.py` を使う。

関連：[method.md](method.md)、[experiment.md](experiment.md)

---

## 1. ファイルの構成

```
experiments/depth_scale_yolo26/
├── README.md
├── requirements.txt          ultralytics（版を固定）
├── yolo26_backend.py         読み込みと推論（距離を mm で、元の画像の大きさで返す）
├── focal.py                  焦点距離の出どころ（撮影情報・Depth Pro・MoGe-2・26mm の決め打ち）
├── try_image_yolo26.py       写真1枚で、5つの大きさ × 出どころの長さと、画像を出す
├── run_all.py                写真の一覧に対して、各モデルの try_image をまとめて動かす
├── calibration.py            全部の JSON を集め、補正前後の表とグラフを作る
├── tests/
├── checkpoints/              重み（コミットしない）
└── data/                     結果（コミットしない）
```

## 2. `focal.py`

| 出どころ | 計算 |
|---|---|
| `exif` | 撮影情報の `FocalLengthIn35mmFilm` と、切り取る前の大きさ（長い辺 × 3/4 を短い辺とみなす）から [method.md §2.1](method.md#21-撮影情報から焦点距離を出すときの注意) の式。縮めた割合を掛ける。撮影情報がなければ使わない |
| `depthpro` | Depth Pro 側の `data/vis/{写真}_depthpro.json` の `f_px`（大きさが違えば比で直す） |
| `moge2` | MoGe-2 側の `data/vis/{写真}_moge2_vitl.json` の `f_px` |
| `fixed26` | 26mm 相当を、`exif` と同じ式で（撮影情報がなくても使える） |

## 3. `try_image_yolo26.py`

- 使い方：`try_image_yolo26.py <写真> [--models n,s,m,l,x] [--focals exif,depthpro,fixed26,moge2]`
- 出力：表示（大きさ × 出どころごとの4区間の長さとずれ）、[experiment.md §2](experiment.md#2-出す画像) の画像、`data/vis/{写真}_yolo26.json`
- 画像の文字が読めるよう、結果の画像は長い辺 1280px で描き、下に表を付ける

## 4. `calibration.py`

- 写真ごとの JSON（Depth Pro・MoGe-2・DA3・MapAnything・YOLO26）を集め、「モデル × 出どころ」ごとに写真ごとの比を出す
- 1枚を除く補正の評価（[method.md §4](method.md#4-補正の評価)）。手のひらの写真を含む場合と除く場合の両方
- 出力：`summary.md`（表）、`summary_scatter.png`・`summary_corrected.png`（グラフ）

## 5. テスト

| 対象 | 期待する結果 |
|---|---|
| 撮影情報からの焦点距離 | 2268×4032・26mm で、長い辺 1280px に縮めたとき約 961px |
| 1枚を除く補正 | どの写真も比 1.30 なら、補正後のずれ 0% |
| 長さの計算 | 300mm 一定の距離で、画像の上の長さ × 300 ÷ 焦点距離 |
