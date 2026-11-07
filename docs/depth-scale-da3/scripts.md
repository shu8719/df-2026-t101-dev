# 実験スクリプトの仕様（Depth Anything 3）

> **このドキュメントで決めたこと**
> 1. コードは `experiments/depth_scale_da3/` に置き、仮想環境・重み・出力を Depth Pro・MoGe-2 の実験と分ける。
> 2. フレーム・手の21点・正解・1円玉の採寸は Depth Pro 側の `data/` を、MoGe-2 の焦点距離と5点の3D位置は MoGe-2 側の出力（`data/vis/*.json`・`data/points/`）を**読むだけ**にする。計算と集計は Depth Pro 側の `common.py`・`measure.py`・`compare.py` の関数を使う。
> 3. 作るのは、モデルを動かす部分（`da3_backend.py`）・写真1枚の確かめ（`try_image_da3.py`）・動画の ③④⑤（`depth_da3.py`・`measure_da3.py`・`compare_all_da3.py`）とテスト。写真1枚から作り、合格の見込みが立ってから動画の分を作る。

関連：[method.md](method.md)、[experiment.md](experiment.md)、[tasks.md](tasks.md)、MoGe-2 の [scripts.md](../depth-scale-moge2/scripts.md)

---

## 1. ファイルの構成

```
experiments/depth_scale_da3/
├── README.md               動かし方
├── requirements.txt        Depth Anything 3 と、その実行に要るもの（版を固定する）
├── da3_backend.py          DA3METRIC-LARGE・DA3-BASE の読み込みと推論（深度を mm に、焦点距離を px に直して返す）
├── focal_sources.py        焦点距離の出どころ（Depth Pro・MoGe-2 の出力ファイル、DA3-BASE、機種の値）を読む
├── try_image_da3.py        写真1枚で4つの組み合わせを試す（結果の画像と数値も保存する）
├── depth_da3.py            ③ フレーム → 点のまわりの深度
├── measure_da3.py          ④ 手の甲の4区間の長さ
├── compare_all_da3.py      ⑤ 正解・1円玉・Depth Pro・MoGe-2・DA3 を1つの表に並べる
├── tests/                  pytest
├── checkpoints/            重み（コミットしない）
└── data/                   出力と結果（コミットしない）
```

- ルートの `.gitignore` に `experiments/depth_scale_da3/data/`・`.venv/`・`checkpoints/` を足す

## 2. 読むファイルと書くファイル

| もの | 場所 | 読む／書く |
|---|---|---|
| フレーム・手の21点・撮影の記録・正解・1円玉 | `experiments/depth_scale/data/` | 読むだけ |
| Depth Pro の写真1枚の結果（焦点距離・5点の距離・長さ） | `experiments/depth_scale/data/vis/{写真}_depthpro.json` | 読むだけ（① の焦点距離） |
| MoGe-2 の写真1枚の結果 | `experiments/depth_scale_moge2/data/vis/{写真}_moge2_{vits,vitl}.json` | 読むだけ（② の焦点距離、③ の形） |
| MoGe-2 の動画の結果（フレームごとの焦点距離・点のまわりの点群） | `experiments/depth_scale_moge2/data/points/{rec_id}/{model}_{cond}.json`・`.npz` | 読むだけ |
| DA3 の点のまわりの深度 | `experiments/depth_scale_da3/data/depth/{rec_id}/{combo}_{cond}.npz`・`.json` | 書く |
| DA3 の長さ・まとめ | `experiments/depth_scale_da3/data/results/` | 書く |
| 写真1枚の結果の画像と数値 | `experiments/depth_scale_da3/data/vis/` | 書く |

`{combo}` は `da3+depthpro`・`da3+moge2vits`・`da3+moge2vitl`・`moge2vitl*da3`・`da3+da3base` のように、[method.md §3](method.md#3-試す組み合わせ) の名前にする。

## 3. `da3_backend.py`

| 項目 | 決めたこと |
|---|---|
| 読み込み | `from depth_anything_3.api import DepthAnything3`、`DepthAnything3.from_pretrained("depth-anything/DA3METRIC-LARGE")`（④では `depth-anything/DA3-BASE` も）。重みは `checkpoints/` に置く。**モデルの名前は決め打ちにし、非営利の版（Large・Giant・Nested）を読み込まない** |
| 入力 | RGB の画像（1枚）。`model.inference([画像], ...)` |
| 深度の直し方 | `深度（mm）= 焦点距離（px）× 出力 ÷ 300 × 単位の換算`。焦点距離は **DA3 の出力の深度の画像と同じ大きさ** での px に直してから使う（元の画像の px から、縮めた割合を掛ける）。式・処理の大きさ・単位は、コードを読んで確かめてから、このファイルに書き戻す（[method.md §5](method.md#5-確かめること要確認)） |
| 返すもの | `depth_mm`（元の画像の大きさに戻したもの）、使った焦点距離（元の画像の px）、推論の秒数。DA3-BASE ではカメラの情報から出した焦点距離（元の画像の px） |
| 偽物 | `--model constant`：深度300mm一定。流れを確かめるためだけ |

## 4. `focal_sources.py`

| 出どころ | 写真1枚 | 動画 |
|---|---|---|
| `depthpro` | `{写真}_depthpro.json` の `f_px` | Depth Pro 側の `data/depth/{rec_id}/{cond}.json` のフレームごとの `f_px` |
| `moge2vits`・`moge2vitl` | `{写真}_moge2_{model}.json` の `f_px` | MoGe-2 側の `data/points/{rec_id}/{model}_{cond}.json` のフレームごとの `f_px` |
| `da3base` | DA3-BASE を動かして出す | 同じ |
| `device` | — | 機種の35mm換算の焦点距離（`recordings.csv`）から（Depth Pro 側の `common.f_px_from_35mm`） |

- どれも**元の画像（フレーム）の px** で返す。ファイルの画像の大きさ（`width`・`height`）が、DA3 に渡す画像と違えば、その比で直す
- 見つからなければ、どのファイルを先に作ればよいかを日本語で伝えて止める

## 5. `try_image_da3.py`

- 使い方：`try_image_da3.py <写真> --combos da3+depthpro,da3+moge2vits,da3+moge2vitl,moge2vitl*da3,da3+da3base`
- MediaPipe の点は、Depth Pro 側の `landmarks.py` の呼び方で出す（モデルは Depth Pro 側の `checkpoints/hand_landmarker.task`）
- 組み合わせごとに、カメラから手首・中指の付け根までの距離、使った焦点距離、4区間の長さを表示する。Depth Pro と MoGe-2 の数値があれば、横に並べる
- `--truth 75.0,72.0,69.0,62.0` で正解（0→5、0→9、0→17、5→17 の順、mm）を渡すと、ずれ（%）も出す
- 画像：組み合わせごとに、重ね描き・深度（Depth Pro 側の `try_image.py` の描き方）と、全部の組み合わせを並べた画像を `data/vis/` に保存する。数値も JSON で保存する。写真そのものは保存しない
- ③（`moge2*da3`）：MoGe-2 の JSON の5点の距離 `z_mm` と長さ `lengths_mm` に、DA3 の深度（焦点距離は MoGe-2）との比の中央値を掛ける（[method.md §4](method.md#4-形と倍率を分ける方法)）

## 6. 動画（③ `depth_da3.py`・④ `measure_da3.py`・⑤ `compare_all_da3.py`）

- 条件A（そのまま）・B（本番と同じ切り抜き）の作り方は Depth Pro 側の `depth.py` と同じ。条件C（機種の焦点距離）は、出どころ `device` として扱う
- 焦点距離は、フレームごとに `focal_sources.py` から取る。MoGe-2 のフレームごとの焦点距離を使うので、MoGe-2 側の ③ を先に動かす
- 保存するもの・長さの計算・集計・8枚の集計は Depth Pro 側と同じ（点のまわり 31×31px の深度、上位20%・最低3枚の中央値）
- ⑤は、Depth Pro・MoGe-2・DA3 の `lengths.csv` を読んで1つの表にする。ずれ・1人を除く補正・合否は Depth Pro 側の `compare.py` の関数を使う
- `--save-vis` で、フレームごとの画像（点と深度）を `data/vis/{rec_id}/` に保存する

## 7. テスト（`tests/`、pytest）

| 対象 | 入力 | 期待する結果 |
|---|---|---|
| 深度の直し方 | 出力 1.0、焦点距離 300px（DA3 の画像の大きさ） | 決めた式・単位どおりの深度 |
| 焦点距離の大きさ合わせ | 元の画像 1280px 幅で f=1000px、DA3 の画像 504px 幅 | DA3 側の焦点距離が 1000 × 504 ÷ 1280 |
| 出どころの読み込み | 作り物の Depth Pro・MoGe-2 の JSON | 元の画像の px の焦点距離が返る。ファイルがなければ分かりやすく止まる |
| ③ 形と倍率 | MoGe-2 の距離が DA3 のちょうど 2倍 | 長さが MoGe-2 の半分 |
| 流れ | 偽物（深度300mm一定）で写真1枚と、動画の条件A・B | 長さが「画像の上の長さ × 300 ÷ 焦点距離」と一致する |
| 非営利の版を読まない | `DA3-LARGE` などの名前を渡す | 止まる |

## 8. 環境と決まり

- Python 3.12。`experiments/depth_scale_da3/.venv` を別に作る
- PyTorch は他の実験と同じ版（2.14.1、CUDA 13.2）にそろえる見込み。Depth Anything 3 は、版（PyPI の版か、コミット）を固定して入れ、`requirements.txt` に書く。`xformers` が要るかは要確認
- MediaPipe は、写真1枚の確かめで点を出すためだけに入れる
- 重みはリポジトリに入れない。ログと出力に画像の中身を出さない
