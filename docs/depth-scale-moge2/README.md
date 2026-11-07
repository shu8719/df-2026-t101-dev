# MoGe-2 で手を実寸にする（1円玉がないとき）

> **このドキュメントで決めたこと**
> 1. Depth Pro（研究目的だけのライセンス）の代わりに、MIT ライセンスの **MoGe-2**（Microsoft）で、写真から手の甲の4区間の長さ（mm）を出せるかを確かめる。精度が合格すれば、Depth Pro と違って本番の候補にできる。
> 2. Depth Pro の実験（[../depth-scale/](../depth-scale/README.md)）とはフォルダを分ける。コードは `experiments/depth_scale_moge2/`、仮想環境・重み・結果も別にする。ただし**比べ方を同じにするため**、フレーム・手の21点・ノギスの正解・1円玉の採寸は Depth Pro 側の `data/` を読み、長さの計算と集計は Depth Pro 側の `common.py` を使う。
> 3. これも**実験**で、MVP には入れない。本番のコードと仕様書（`docs/` の各章）は、実験で合格してチームで決めるまで変えない。

- 書いた日：2026-11-08
- ブランチ：`exp/depth-scale`（Depth Pro の実験と同じブランチ）
- 関連：[../depth-scale/README.md](../depth-scale/README.md)（目的・精度の心配・本番との関係は同じ）、[measurement.md](../measurement.md) §7.1・§8.2

## なぜ MoGe-2 か

| 項目 | Depth Pro | MoGe-2 |
|---|---|---|
| 重みのライセンス | 研究目的だけ（本番に使えない） | **MIT**（本番にも使える） |
| 焦点距離を自分で推定 | する | **する**（ブラウザでは焦点距離が取れないので、ここが大事） |
| 出すもの | 深度マップ、焦点距離（px） | **3Dの点群（各画素の3D位置）**、深度マップ、カメラの情報（正規化）、使える画素の印、面の向き |

ほかの候補（Depth Anything 3、Depth Anything V2、Metric3D v2、UniDepth など）と比べた結果は [method.md §3](method.md#3-ほかの候補と比べた結果)。

## ドキュメントの一覧

| ファイル | 中身 |
|---|---|
| [method.md](method.md) | MoGe-2 のしくみ、使うモデル、出力の扱い（点群から長さを出す）、ライセンス、プライバシー |
| [experiment.md](experiment.md) | 実験の手順（Depth Pro と同じ）、Depth Pro と並べて比べる表 |
| [scripts.md](scripts.md) | 実験スクリプト（`experiments/depth_scale_moge2/`）の仕様 |
| [tasks.md](tasks.md) | やることと完了条件、確かめること |

## 本番の仕様との関係

[Depth Pro の実験と同じ](../depth-scale/README.md#本番の仕様との関係)。本番のコード（`app/`・`api/`・`hand_mesh/`）は変えない。映像を保存しない本番の約束も変えない。実験の動画と写真は、チームのメンバーが自分の手を撮って同意したものだけを、コミットしない場所で使う。
