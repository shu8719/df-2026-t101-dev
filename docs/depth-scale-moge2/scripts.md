# 実験スクリプトの仕様（MoGe-2）

> **このドキュメントで決めたこと**
> 1. コードは `experiments/depth_scale_moge2/` に置き、Depth Pro の実験（`experiments/depth_scale/`）とは仮想環境・重み・出力を分ける。ライブラリの版がぶつかっても、互いに壊さないため。
> 2. ①フレームの取り出し と ②手の21点 は作り直さず、Depth Pro 側の出力（`experiments/depth_scale/data/frames/`・`landmarks/`）を**読むだけ**にする。長さの計算と集計の関数も、Depth Pro 側の `common.py` を読み込んで使う。同じフレーム・同じ点・同じ集計で比べるため。
> 3. 作るのは ③深度の推定（`depth_moge.py`）・④長さ（`measure_moge.py`）・⑤比べる（`compare_all.py`）・写真1枚の確かめ（`try_image_moge.py`）とテスト。

関連：[method.md](method.md)、[experiment.md](experiment.md)、[tasks.md](tasks.md)、Depth Pro 側の [scripts.md](../depth-scale/scripts.md)

---

## 1. ファイルの構成

```
experiments/depth_scale_moge2/
├── README.md               動かし方
├── requirements.txt        MoGe-2 と、その実行に要るもの（版を固定する）
├── moge_backend.py         MoGe-2 の読み込みと推論（点群・深度・カメラの情報を mm と px に直して返す）
├── depth_moge.py           ③ フレーム → 点のまわりの3D位置（と確かめ用の深度・焦点距離）
├── measure_moge.py         ④ 手の甲の4区間の長さ
├── compare_all.py          ⑤ ノギス・1円玉・Depth Pro・MoGe-2 を1つの表に並べる
├── try_image_moge.py       写真1枚で試す（結果の画像も保存する）
├── tests/                  pytest
├── checkpoints/            重み（コミットしない）
└── data/                   MoGe-2 の出力と結果（コミットしない）
```

- ルートの `.gitignore` に `experiments/depth_scale_moge2/data/`・`.venv/`・`checkpoints/` を足す
- Depth Pro 側の `common.py` は、`sys.path` に `experiments/depth_scale/` を足して読み込む。Depth Pro 側の関数を書き換えるときは、両方のテストを回す

## 2. データの置き場所

| もの | 場所 | 読む／書く |
|---|---|---|
| 撮影の記録・ノギスの正解・1円玉の採寸・動画 | `experiments/depth_scale/data/`（`recordings.csv`・`truth.csv`・`coin/`・`raw/`） | 読むだけ |
| フレームと手の21点 | `experiments/depth_scale/data/frames/`・`landmarks/` | 読むだけ（先に Depth Pro 側の ①② を動かす） |
| Depth Pro の長さ | `experiments/depth_scale/data/results/lengths.csv` | 読むだけ（⑤で並べる） |
| MoGe-2 の点のまわりの値 | `experiments/depth_scale_moge2/data/points/{rec_id}/{model}_{cond}.npz`・`.json` | 書く |
| MoGe-2 の長さ | `experiments/depth_scale_moge2/data/results/lengths.csv` | 書く |
| まとめ | `experiments/depth_scale_moge2/data/results/summary_all.csv`・`summary_all.md`・`meta.json` | 書く |
| 写真1枚の結果の画像 | `experiments/depth_scale_moge2/data/vis/` | 書く |

`{model}` は `vitl` か `vits`、`{cond}` は `A`・`B`・`C`。

## 3. `moge_backend.py`

| 項目 | 決めたこと |
|---|---|
| 読み込み | `from moge.model.v2 import MoGeModel`、`MoGeModel.from_pretrained("Ruicheng/moge-2-vitl-normal")`（`--model vits` なら `moge-2-vits-normal`）。GPU があれば GPU |
| 入力 | RGB の画像を 0〜1 の float の (3, H, W) にして渡す |
| 画角を与える | 条件Cでは `fov_x`（水平の画角、度）を渡す。機種の35mm換算の焦点距離から `f_px` を出し（Depth Pro 側の `common.f_px_from_35mm`）、`fov_x = 2·atan(W ÷ (2·f_px))` にする |
| 返すもの | `points_mm`（(H, W, 3)、mm）、`depth_mm`（(H, W)、mm）、`mask`（(H, W)）、`f_px`（px）、推論の秒数 |
| 単位と正規化 | `points`・`depth` はメートルと見込んで mm に直す（README に「metric」とだけあり、明記はない）。`intrinsics` は、fx が画像の幅を1、fy が高さを1とした値で、中心は (0.5, 0.5)。px の焦点距離は **`f_px = fx × 幅 = fy × 高さ`**（MoGe のコミット `74fbce0` の `moge/model/v2.py` の `infer` で確かめた。2026-11-08）。既定（`force_projection=True`）では点群を深度と焦点距離から作り直すので、点群と深度からの長さは一致する（写真1枚で差 0.15〜0.20%） |
| 偽物 | `--model constant`：Depth Pro 側と同じく、深度300mm一定の平らな面の点群を返す。流れを確かめるためだけ |

## 4. ③ `depth_moge.py`

- 入力：Depth Pro 側の `frames/`・`landmarks/`（`used=true` のフレーム）
- 条件A・B・Cの作り方は Depth Pro 側の `depth.py` と同じ（Bは同じ切り抜きの範囲・同じ縮め方）
- 保存するもの：5点（0・5・9・13・17）のまわり 31×31px の `points_mm`（3つの値）・`depth_mm`・`mask`。キーは `f{index:03d}_p{点の番号}_{points|depth|mask}`
- 記録（`.json`）：フレームごとに `{index, f_px, f_source, infer_s, crop?}`。モデルの名前・版、GPU の名前
- 条件Bでは、`points_mm` は切り抜いた画像の座標で返る。カメラの座標は切り抜いても変わらない見込みだが、画像の中心がずれるので、x・y の扱いを確かめる（要確認）。長さは2点の差なので、中心のずれの影響は小さい

## 5. ④ `measure_moge.py` と ⑤ `compare_all.py`

### 5.1 ④ 長さ

- 本命：点のまわり（半径 r px、`mask` あり・有限）の `points_mm` の x・y・z それぞれの中央値を3D位置にし、4区間の長さを出す（[method.md §2.1](method.md#21-点のまわりの3d位置)）
- 確かめ：`depth_mm` と `f_px` から、Depth Pro 側の `common.backproject` で3Dに直した長さも出す（[method.md §2.2](method.md#22-確かめ深度とカメラの情報から3dに直す)）
- 集計・8枚の集計・出力の列は、Depth Pro 側の `measure.py` と同じ。列 `source` を足し、`points`（本命）か `depth`（確かめ）を書く。列 `model` に `vitl`・`vits` を書く

### 5.2 ⑤ 比べる

- Depth Pro 側の `lengths.csv` と、MoGe-2 の `lengths.csv` を読み、方法の名前を「Depth Pro A」「MoGe-2（vitl）A」のようにして、1つの表にする
- ずれ・1人を除く補正・合否の計算は、Depth Pro 側の `compare.py` と同じ関数を使う
- `summary_all.md` は [experiment.md §4.2](experiment.md#42-動画での比較-の出力を貼る) にそのまま貼れる形にする

## 6. `try_image_moge.py`

- Depth Pro 側の `try_image.py` と同じ使い方・同じ表示・同じ画像（重ね描き・深度・横に並べたもの）
- 加えて、`--compare-depth-pro` を付けると、Depth Pro 側の出力（`experiments/depth_scale/data/vis/` と同じ写真の結果）があれば、数値を並べて表示する（Depth Pro は MoGe-2 の環境では動かさない）
- 写真はどこにも保存しない。結果の画像だけを `data/vis/` に保存する（`--no-save` で止められる）

## 7. テスト（`tests/`、pytest）

| 対象 | 入力 | 期待する結果 |
|---|---|---|
| 点のまわりの3D位置 | 中心だけ外れ値（無限大）、一部 `mask` なしの 31×31×3 の配列 | 外れ値と `mask` なしを除いた、x・y・z それぞれの中央値 |
| 画角の換算 | `f_px = 1000`、幅 1280px | `fov_x = 2·atan(640 ÷ 1000)`（度） |
| 正規化の換算 | 決めた式（§3）での例 | px の焦点距離が一致する |
| 流れ（③〜④） | 偽物（深度300mm一定の平らな面）で条件A・B・C | 点群からの長さと、深度からの長さが、どちらも「画像の上の長さ × 300 ÷ 焦点距離」と一致する |
| ⑤ | Depth Pro と MoGe-2 の作り物の `lengths.csv` | 1つの表に両方が並び、ずれが正しく出る |

## 8. 環境と決まり

- **仮想環境は Depth Pro 側の `experiments/depth_scale/.venv` を共通で使う**（2026-11-08 に変更）。はじめは実験ごとに別の環境を作ったが、PyTorch（約3GB）が重なってディスクが満杯になったため。Depth Pro 側と MoGe-2 側の環境は、PyTorch 2.14.1（CUDA 13.2）・numpy 2.5.4 で中身の版が同じだった
- 追加のライブラリは、版の固定 `experiments/constraints.txt` を `-c` で渡して入れる（PyTorch・numpy が勝手に変わらないように）
- MoGe はコミット `74fbce0` を固定して入れる（`requirements.txt`）
- MediaPipe はこの環境では使わない（②は Depth Pro 側の出力を読むため）。ただし `try_image_moge.py` で写真から点を出すときだけ使うので、`requirements.txt` に入れる
- 重みはリポジトリに入れない。ログと出力に画像の中身を出さない
