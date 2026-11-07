# Depth Anything 3 で手を実寸にする（1円玉がないとき）

> **このドキュメントで決めたこと**
> 1. 本番で使えるライセンスの組み合わせとして、**Depth Anything 3 の `DA3METRIC-LARGE`（Apache-2.0）に、MoGe-2（MIT）が推定した焦点距離を渡して**、手の甲の4区間の長さ（mm）を出せるかを確かめる。DA3METRIC は焦点距離を自分で推定できず、MoGe-2 は焦点距離だけが正確だった（大きさは外れた）ので、互いの弱点を補う（[method.md §1](method.md#1-なぜこの組み合わせか)）。
> 2. Depth Pro・MoGe-2 の実験とはフォルダを分ける。コードは `experiments/depth_scale_da3/`、仮想環境・重み・出力も別にする。フレーム・手の21点・正解は Depth Pro 側の `data/` を、MoGe-2 の焦点距離は MoGe-2 側の出力ファイルを**読むだけ**にし、計算は Depth Pro 側の `common.py` を使う。
> 3. これも**実験**で、MVP には入れない。本番のコードと仕様書（`docs/` の各章）は、実験で合格してチームで決めるまで変えない。

- 書いた日：2026-11-08
- ブランチ：`exp/depth-scale`
- 関連：[../depth-scale/](../depth-scale/README.md)（Depth Pro。目的・精度の心配・本番との関係）、[../depth-scale-moge2/](../depth-scale-moge2/README.md)（MoGe-2）

## これまでに分かったこと（2026-11-08、写真1枚）

| モデル | 焦点距離 | 大きさ（距離） | 重みのライセンス |
|---|---|---|---|
| Depth Pro | 正確 | **正確**（本人が定規で確かめた） | 研究目的だけ → 本番に使えない |
| MoGe-2 | **正確**（Depth Pro と差1%） | 外れた（長さが 3〜4cm 大きい） | MIT |
| DA3METRIC-LARGE | 推定できない（与える必要がある） | 焦点距離が正しければ良い見込み（[method.md §1](method.md#1-なぜこの組み合わせか)） | **Apache-2.0** |

## ドキュメントの一覧

| ファイル | 中身 |
|---|---|
| [method.md](method.md) | この組み合わせを選んだ理由、しくみ、試す4つの組み合わせ、ライセンス、確かめること |
| [experiment.md](experiment.md) | 実験の手順（Depth Pro と同じ）、写真1枚と動画での比べ方、結果の表 |
| [scripts.md](scripts.md) | 実験スクリプト（`experiments/depth_scale_da3/`）の仕様 |
| [tasks.md](tasks.md) | やることと完了条件、確かめること |

## 本番の仕様との関係

[Depth Pro の実験と同じ](../depth-scale/README.md#本番の仕様との関係)。本番のコード（`app/`・`api/`・`hand_mesh/`）は変えない。実験の写真・動画は、チームのメンバーが自分の手を撮って同意したものだけを、コミットしない場所で使う。
