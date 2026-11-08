# 実験スクリプトの仕様（MapAnything）

> **このドキュメントで決めたこと**
> 1. コードは `experiments/depth_scale_mapanything/` に置く。仮想環境は共通の `experiments/depth_scale/.venv` を使い、追加のライブラリは `experiments/constraints.txt` を `-c` で渡して入れる。MapAnything 本体は依存を入れずに（`--no-deps`）入れる（`opencv-python-headless==4.10` の指定が OpenCV 5 とぶつかるため）。
> 2. 作るのは、モデルを動かす部分（`mapanything_backend.py`）と、写真1枚で試して途中経過の画像を出す `try_image_mapanything.py`、テスト。動画用は、写真1枚で合格してから作る。
> 3. 長さの計算と点のまわりの値の取り方は、Depth Pro・MoGe-2 の実験の関数（`common.py`・`moge_backend.py`）を使う。

関連：[method.md](method.md)、[experiment.md](experiment.md)、[tasks.md](tasks.md)

---

## 1. ファイルの構成

```
experiments/depth_scale_mapanything/
├── README.md                     動かし方
├── requirements.txt              推論に要るもの（共通の環境に、版を固定して入れる）
├── mapanything_backend.py        読み込み・前処理・推論。モデルが見た画像・3D位置（mm）・深度（mm）・信頼度・使える画素・焦点距離を返す
├── try_image_mapanything.py      写真1枚で長さを出し、途中経過の画像を保存する
├── tests/                        pytest
├── checkpoints/                  重み（コミットしない）
└── data/                         結果の画像と数値（コミットしない）
```

- ルートの `.gitignore` に `experiments/depth_scale_mapanything/data/`・`checkpoints/` を足す

## 2. `mapanything_backend.py`

| 項目 | 決めたこと |
|---|---|
| 読み込み | `MapAnything.from_pretrained("facebook/map-anything-apache", cache_dir=checkpoints/)`。**名前は決め打ち**にし、非営利の `facebook/map-anything` は読み込めないようにする |
| 前処理 | `preprocess_inputs([{"img": PIL の画像}])`（既定の `fixed_mapping`、解像度の組 518） |
| 推論 | `model.infer(views, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)` |
| 返すもの | `rgb`（モデルが見た画像、uint8）、`points_mm`（(H, W, 3)）、`depth_mm`（(H, W)）、`conf`、`mask`（bool）、`f_px`（モデルが見た画像の px）、`scale`（`metric_scaling_factor`）、推論の秒数 |
| 偽物 | `ConstantBackend`：入力をそのまま返し、深度300mm一定の平らな面の点群を返す。流れを確かめるためだけ |

## 3. `try_image_mapanything.py`

- 使い方：`try_image_mapanything.py <写真> [--compare-depth-pro] [--radius 3]`
- 写真を長い辺 1280px まで縮め、MapAnything にかけ、**モデルが見た画像に MediaPipe をかける**
- 長さ：点のまわりの点群の中央値（本命）と、深度とカメラの情報から3Dに直したもの（確かめ）
- 表示：カメラから手首・中指の付け根までの距離、焦点距離（モデルが見た画像の px と、元の画像の px に直した値）、4区間の長さ、正解とのずれ（%）とその中央値。`--compare-depth-pro` で Depth Pro の数値を並べる
- 正解は既定で写真1の Depth Pro の値（[experiment.md §1](experiment.md#1-正解)）。`--truth` で変えられる
- 画像：[experiment.md §2](experiment.md#2-出す途中経過の画像) の7枚を `data/vis/` に保存する。数値は JSON で保存する。写真そのものは保存しない

## 4. テスト（`tests/`、pytest）

| 対象 | 入力 | 期待する結果 |
|---|---|---|
| 非営利の重みを読まない | `facebook/map-anything` | 止まる |
| 焦点距離を元の画像の px に直す | モデルが見た画像の f と、縮め・切り取りの割合 | 決めた式どおり |
| 流れ | 偽物（深度300mm一定）で写真1枚 | 長さが「画像の上の長さ × 300 ÷ 焦点距離」と一致する。7枚の画像ができる |
| ずれの計算 | 長さがちょうど正解の 1.02 倍 | ずれ +2.0% |
