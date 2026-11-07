# 実験スクリプトの仕様

> **このドキュメントで決めたこと**
> 1. 実験のスクリプトは `experiments/depth_scale/` に置き、本番のコード（`app/`・`api/`・`hand_mesh/`）は読むだけで変えない。処理は5つのスクリプトに分け、①フレームの取り出し → ②手の21点 → ③深度の推定 → ④長さの計算 → ⑤比べる、の順に、前の段の出力ファイルを読んで動かす。
> 2. 動画・フレーム・深度は `experiments/depth_scale/data/` にだけ置き、コミットしない。結果として残すのは数値（mm・%・秒）だけ。人は `p1`・`p2` のような番号で表し、名前は書かない。
> 3. フレームの選び方と長さの集計は、本番の仕様（[measurement.md §3](../measurement.md#3-フレームの選び方)・[§7.1](../measurement.md#71-長さ上位20のフレームの中央値)）と同じにする。違うのは「1円玉の縮尺の代わりに、深度と焦点距離で mm にする」所だけにして、AIの効果だけを比べられるようにする。

関連：[method.md](method.md)、[experiment.md](experiment.md)、[tasks.md](tasks.md)、動かし方は [experiments/depth_scale/README.md](../../experiments/depth_scale/README.md)

- 実装の状況（2026-11-08）：①〜⑤とテストを作った。テストは19件すべて通る。Depth Pro を入れ、試験画像で深度と焦点距離が出ることを確かめた（[tasks.md](tasks.md) の DS2）。手の写真・動画ではまだ動かしていない
- 写真1枚で手軽に試す `try_image.py` も置いた（①〜⑤の流れの外。カメラから手までの距離と、手の甲の4区間の長さを表示する）

---

## 1. ファイルの構成

```
experiments/depth_scale/
├── README.md              動かし方（この仕様書へのリンク）
├── requirements.txt       ①②④⑤とテストに要るもの（バージョンを固定する）
├── requirements-depth.txt ③で Depth Pro を使うときだけ入れるもの（DS1 が済んでから）
├── common.py              共通の関数（3Dに直す式、焦点距離の換算、集計、ファイルの読み書き）
├── extract_frames.py      ① 動画 → フレーム
├── landmarks.py           ② フレーム → 手の21点
├── depth.py               ③ フレーム → 点のまわりの深度と焦点距離
├── measure.py             ④ 3Dに直して、手の甲の4区間の長さを出す
├── compare.py             ⑤ ノギス・1円玉と比べて、表を作る
├── tests/                 pytest（§8）
└── data/                  入力と出力（コミットしない。§2）
```

- ルートの `.gitignore` に `experiments/depth_scale/data/`・`experiments/depth_scale/.venv/`・`experiments/depth_scale/checkpoints/`（Depth Pro の重み）を足す
- 各スクリプトは `--rec <撮影ID>`（1件）か `--all`（`recordings.csv` の全部）で動かす。出力がすでにあれば飛ばし、`--force` で作り直す

## 2. データの置き場所と形

```
data/
├── recordings.csv         撮影の記録（人が書く）
├── truth.csv              ノギスの正解（人が書く）
├── raw/{rec_id}.mp4       撮った動画
├── coin/{rec_id}.json     1円玉の方法の採寸（アプリから写す。§2.3）
├── frames/{rec_id}/       ① の出力
├── landmarks/{rec_id}.json ② の出力
├── depth/{rec_id}/{cond}.npz と {cond}.json   ③ の出力
├── results/lengths.csv    ④ の出力
└── results/summary.csv・summary.md・meta.json  ⑤ の出力
```

撮影ID `rec_id` は `p{人}_t{回}`（例：`p1_t2`）。

### 2.1 `recordings.csv`

| 列 | 例 | 意味 |
|---|---|---|
| `rec_id` | `p1_t1` | 撮影ID |
| `person` | `p1` | 人の番号 |
| `trial` | `1` | 何回目か |
| `hand_side` | `right` | 右手か左手か |
| `device` | （機種名） | スマホの機種 |
| `focal_35mm_mm` | `26` | レンズの焦点距離（35mm換算）。条件C（§5.3）で使う。分からなければ空 |
| `distance_mm` | `300` | カメラから手までのおおよその距離 |
| `case_id` | （ケースID） | 1円玉の方法で使ったアプリのケース |
| `note` | | メモ |

### 2.2 `truth.csv`

| 列 | 意味 |
|---|---|
| `person` | 人の番号（正解は人ごとに1つ。撮影の回では変わらない） |
| `seg_0_5_mm`・`seg_0_9_mm`・`seg_0_17_mm`・`seg_5_17_mm` | 手の甲の4区間のノギスの値（2回測った平均。[experiment.md §2](experiment.md#2-手順)） |

### 2.3 `coin/{rec_id}.json`

- 同じ動画を、手元で動かしたアプリの「動画ファイルを選ぶ」で読み込ませ、採寸を保存する
- 保存された `.localstore/db/cases/{case_id}.json` の `measurement`（採寸の JSON、[measurement.md §12](../measurement.md#12-出力するjsonmeasurement22)）を、そのまま `coin/{rec_id}.json` に写す
- 使うのは `palm.wrist_to_index_mcp_mm`（0→5）・`palm.wrist_to_middle_mcp_mm`（0→9）・`palm.wrist_to_pinky_mcp_mm`（0→17）・`palm.hand_width_mcp_mm`（5→17）の4つ。点を直した（`segments_source: "manual"`）採寸は使わない（直す前の値で比べる）
- 写す作業は人が行う（`.localstore/` の中身は自動で読まない。ほかのケースを読まないため）

## 3. ① `extract_frames.py`

| 項目 | 決めたこと |
|---|---|
| 入力 | `raw/{rec_id}.mp4` |
| 取り出し | 1秒に6枚。動画の回転の情報（スマホの縦撮り）を反映して、見たとおりの向きにする |
| ぼけの判定 | 長い辺256pxの白黒に縮め、ラプラシアンの分散を点数にする。1秒ごとに上位3枚を残す（[measurement.md §3.1](../measurement.md#31-手順)） |
| 保存 | 長い辺を最大1280pxに縮めて、`frames/{rec_id}/{index:03d}.jpg`（JPEG、品質95）。`index` は残した順の通し番号 |
| 記録 | `frames/{rec_id}/frames.json`：`[{index, t_s, width, height, blur}]`、元の動画の幅・高さ、縮めた割合 |

- iPhone の動画（HEVC）は、OpenCV で読めないことがある。そのときは ffmpeg で H.264 に変えてから読む（要確認）
- 焦点距離（px）は縮めた画像で考える。条件Cの換算（§5.3）は、縮めたあとの幅・高さで行う

## 4. ② `landmarks.py`

| 項目 | 決めたこと |
|---|---|
| 使うもの | MediaPipe の Python 版の Hand Landmarker。モデルは本番と同じ `hand_landmarker.task`（`scripts/fetch_mediapipe.sh` が `app/web/mediapipe/models/` に置くもの） |
| 設定 | `num_hands=2`、静止画のモード。2つ以上見つかったフレームと、見つからないフレームは使わない |
| 端の判定 | 21点のどれかが画面の端（幅・高さの5%以内）にあるフレームは使わない（[measurement.md §3.2](../measurement.md#32-使わないフレーム)） |
| 出力 | `landmarks/{rec_id}.json`：フレームごとに `{index, used, reason, points_px: [[u, v] × 21]}`。`used=false` なら `reason` に理由 |

- Python 版とブラウザ版（`@mediapipe/tasks-vision` 1.2.2）で点の位置が違うかは要確認。違いを見るため、1件だけ、アプリの点と並べて比べる（[tasks.md](tasks.md) の確かめること）
- 1円玉による「使わないフレーム」の判定（[measurement.md §3.2](../measurement.md#32-使わないフレーム) の2・3行目）は、AIの方法には関係ないので行わない

## 5. ③ `depth.py`

### 5.1 共通

| 項目 | 決めたこと |
|---|---|
| 入力 | `frames/`、`landmarks/`（`used=true` のフレームだけ） |
| モデル | `--model depth_pro`（既定）。ほかの候補は、ライセンスを確かめてから足す（[method.md §3](method.md#3-候補のモデル)）。`--model constant` は、重みなしで流れだけを確かめるための偽物（深度300mm一定、焦点距離は35mm換算26mm相当）で、結果を実験に使ってはいけない |
| 重みの場所 | `experiments/depth_scale/checkpoints/depth_pro.pt`（1.9GB）。`.gitignore` に入れてコミットしない。`--checkpoint` で別の場所も指定できる |
| 条件 | `--cond A`・`B`・`C`（[experiment.md §3](experiment.md#3-比べる条件)） |
| 保存するもの | 深度マップの全体は保存しない（大きいため）。手首と指の付け根の5点（0・5・9・13・17）のまわり 31×31px の深度（mm、float32）だけを `depth/{rec_id}/{cond}.npz` に保存する。キーは `f{index:03d}_p{点の番号}` |
| 記録 | `depth/{rec_id}/{cond}.json`：フレームごとに `{index, f_px, f_source, infer_s}`。`f_px` は**元のフレーム（①の画像）の px** に直した焦点距離、`f_source` は `model` か `device`、`infer_s` は推論の秒数。GPUの名前とモデルの版も書く |

- 深度マップの大きさがフレームと違うときは、フレームの大きさに引き伸ばしてから切り出す（線形補間）
- 単位はモデルの出力（m など）から mm に直して保存する

### 5.2 条件ごとの入力

| 条件 | モデルに入れる画像 | 焦点距離 |
|---|---|---|
| A | ①のフレームそのまま | モデルが推定した値 |
| B | 21点を囲む四角を20%広げて切り抜き、長い辺512pxに縮めた画像（本番で `hand-mesh` に送るのと同じ。[measurement.md §11](../measurement.md#11-手のメッシュ復元)） | モデルが推定した値を、元のフレームの px に換算する（§5.4） |
| C | ①のフレームそのまま | 機種の値から計算して、モデルに与える（§5.3）。与えられないモデルでは、推定した値をこの値で置き換えて§6の計算に使う |

- 条件Bでは、全部のフレームで推定する。そのうえで④で「本番と同じ8枚だけ」の集計もする（§6.3）

### 5.3 機種の焦点距離から px にする（条件C）

35mm換算の焦点距離は、画面の対角線を 43.27mm（36×24mm の対角線）とみなした値なので、次の式で px にする。

```
f_px = focal_35mm_mm × √(width² + height²) ÷ 43.27
```

- 動画を撮るときに手ぶれ補正などで画面の端が切られていると、実際の画角はこれより狭い（`f_px` が大きくなる）。どれだけ違うかは要確認。条件Cは「上限の目安」として見る

### 5.4 切り抜いた画像の焦点距離を元に戻す（条件B）

```
s = 512 ÷ 切り抜きの長い辺（元のフレームの px）
f_px（元のフレーム）= f_px（切り抜き）÷ s
```

- 深度（mm）は切り抜いても変わらない
- 3Dに直すときの画像の中心 `(cx, cy)` は、切り抜きではなく**元のフレームの中心**を使う。点の位置も元のフレームの px に戻して使う

## 6. ④ `measure.py`

### 6.1 フレームごとの計算

1. 5点（0・5・9・17、と 13）のそれぞれで、保存した 31×31px の深度から、点を中心に半径 r px の円の中の値の中央値を `Z` とする。値が無い・0以下・有限でないものは除く。既定は `r = 3`。`--radius 1,3,5` で全部を出す
2. 皮膚の表面と関節の中心のずれを試すため、`Z` に `--skin-offset-mm`（既定0）を足す（[method.md §2](method.md#2-精度の見積もり)）
3. 3Dに直す（[method.md §1.1](method.md#11-2dの点を3dにする式)）：`X = (u − cx) × Z ÷ f`、`Y = (v − cy) × Z ÷ f`
4. 手の甲の4区間（0→5、0→9、0→17、5→17）の長さ（mm）を出す

5点のどれかの `Z` が出せないフレームは、そのフレームを使わない（`reason` に書く）。

### 6.2 撮影ごとの集計

区間ごとに、全フレームの長さを大きい順に並べ、上位20%（最低3枚）の中央値を、その区間の長さとする（[measurement.md §7.1](../measurement.md#71-長さ上位20のフレームの中央値)）。使えるフレームが3枚未満なら、その撮影は `FEW_FRAMES` とし、比べる対象から外す。

### 6.3 本番と同じ8枚だけの集計（条件Bだけ）

- 本番では `hand-mesh` に送るのは最大8枚なので、8枚だけでも集計する
- 8枚の選び方：本番は向き（親指側・上・小指側）がそろうように選ぶ（[measurement.md §11](../measurement.md#11-手のメッシュ復元)）。実験では、使えるフレームを時間の順に並べ、等しい間隔で8枚選ぶ（本番の選び方との違いの影響は要確認）

### 6.4 出力

`results/lengths.csv`：1行が「撮影 × 条件 × 半径 × 集計（全部／8枚）」。

| 列 | 意味 |
|---|---|
| `rec_id`・`cond`・`radius_px`・`skin_offset_mm`・`subset` | どの計算か（`subset` は `all` か `8`） |
| `seg_0_5_mm`・`seg_0_9_mm`・`seg_0_17_mm`・`seg_5_17_mm` | 集計した長さ |
| `frames_used` | 使ったフレームの数 |
| `iqr_ratio_max` | 4区間のうち、四分位範囲 ÷ 長さの最大（ばらつきの目安。本番の `LENGTH_UNSTABLE` は20%超え） |
| `f_px_median` | 使ったフレームの焦点距離の中央値 |

## 7. ⑤ `compare.py`

### 7.1 ずれの計算

撮影ごと・方法ごとに、区間 s の比 `r_s = 長さ ÷ ノギスの長さ` を出し、4区間の中央値でずれを出す（[experiment.md §4](experiment.md#4-比べ方)）。

```
ずれ（%）= (median(r_s) − 1) × 100
```

- 1円玉の方法（`coin/`）も同じ式で出す
- 条件Cがある撮影では、条件Aで推定した焦点距離と、機種の値から計算した焦点距離の差（%）も出す

### 7.2 補正したあとのずれ

- 1人を除いた全員の撮影で、ずれの平均から補正係数 `c = 1 ÷ 平均(median(r_s))` を求め、除いた1人の撮影に掛けて、補正後のずれを出す。これを全員について繰り返す（1人を除いて確かめる方法。人数が少ないので、同じ人のデータで係数を決めて同じ人で確かめるのを避ける）
- 補正係数そのもの（全員で求めた値）も記録する

### 7.3 出力

| ファイル | 中身 |
|---|---|
| `results/summary.csv` | 撮影ごと・方法ごとのずれ（補正前・補正後） |
| `results/summary.md` | [experiment.md §6.2・§6.3](experiment.md#6-結果) の表の形にしたもの。そのまま貼れるようにする。合格の目安（中央値2%以内・最大4%以内・同じ人の3回のばらつき2%以内）に照らした合否も書く |
| `results/meta.json` | 実行した日時、リポジトリのコミット、Python と主なライブラリの版、モデルの名前と版、GPU の名前、使った引数 |

## 8. テスト（`tests/`、pytest）

本物の動画やモデルを使わずに動く計算だけを確かめる。

| 対象 | 入力 | 期待する結果 |
|---|---|---|
| 3Dに直す式 | カメラから 300mm の平らな面の上で、50mm 離れた2点を、`f_px = 1000` で画像に写した位置と深度 | 長さが 50mm（±0.01mm） |
| 焦点距離の換算（§5.3） | 35mm換算 26mm、1280×720 | `f_px = 26 × √(1280² + 720²) ÷ 43.27` と一致 |
| 切り抜きの換算（§5.4） | 切り抜きの長い辺 640px、切り抜きでの `f_px = 400` | 元のフレームで `f_px = 500` |
| 点のまわりの深度 | 中心だけ外れ値（0や無限大）がある 31×31 の配列 | 外れ値を除いた中央値になる |
| 集計（§6.2） | 10枚分の長さ | 上位3枚（20%が3枚未満なので最低の3枚）の中央値 |
| ずれの計算（§7.1） | 4区間が正解のちょうど 1.02 倍 | ずれ 2.0% |
| 1人を除く補正（§7.2） | 3人のずれがすべて −4% | 補正後のずれが 0% |
| 流れ（③〜⑤） | 偽物の深度（300mm一定）で、条件A・B・Cを通す | 4区間の長さが「画像の上の長さ × 300 ÷ 焦点距離」と一致する。条件Bでは「8枚」の集計も出る。深度に30mm足すと長さが 330/300 倍になる。⑤の表とずれが出る |

テストは `tests/test_common.py`（計算）と `tests/test_pipeline.py`（流れ）にある。上の表のほかに、切り抜きの範囲（アプリと同じか）・8枚の選び方・画像の外の深度の扱いも確かめている。

## 9. 環境と決まり

- Python 3.12。`experiments/depth_scale/.venv` を別に作る（`hand_mesh/` の環境と混ぜない）
- 入れて確かめた版（2026-11-07）：numpy 2.5.4、opencv-python 5.0.0.93、mediapipe 1.2.2（Python 版。本番のブラウザ版 `@mediapipe/tasks-vision` も 1.2.2）、pytest 9.2.0
- PyTorch は `hand_mesh/` と同じ版（2.14.1、CUDA 13.2）にそろえる見込み。Depth Pro は PyPI にないので、リポジトリのコミットを決めて入れ、`requirements-depth.txt` に書く。Depth Pro の README は Python 3.9 の環境で書かれていて、3.12 で動くかは要確認
- モデルの重みはリポジトリに入れない（`checkpoints/` に置き、`.gitignore` に入れる）
- Depth Pro の重みは研究目的だけのライセンスなので、手元の実験だけに使う（[tasks.md §3](tasks.md#3-ライセンスで分かったことds12026-11-07)）
- ログと出力に画像の中身を出さない。出すのは件数・秒数・数値だけ
- 実験が終わったら `data/raw/`・`data/frames/`・`data/depth/` を消す（`results/` の数値は残してよい）
