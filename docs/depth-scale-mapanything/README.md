# MapAnything で手を実寸にする（1円玉がないとき）

> **このドキュメントで決めたこと**
> 1. 本番で使えるライセンス（Apache-2.0）の最後の有力な候補として、Meta の **MapAnything**（`facebook/map-anything-apache`）で、写真1枚から手の甲の4区間の長さ（mm）を出せるかを確かめる。MoGe-2（MIT）と Depth Anything 3（Apache-2.0）は大きく外れた（[../depth-scale-da3/experiment.md §3.1.1](../depth-scale-da3/experiment.md#311-正解の値と判定)）。
> 2. 正解は**写真1の Depth Pro の値**（0→5 75.5、0→9 72.3、0→17 69.3、5→17 61.8mm。本人が定規で確かめて正確と確認済み）。同じ写真1・写真2で判定する。外れたら、本番で使えるモデルは今のところ見当たらないと結論づける。
> 3. コードは `experiments/depth_scale_mapanything/` に置き、仮想環境は共通のもの（`experiments/depth_scale/.venv`）を使う。途中経過の画像（モデルが見た画像・深度・信頼度・使える画素・点群を横から見た図・最終の重ね描き）を必ず保存する。MVP には入れず、本番のコードは変えない。

- 書いた日：2026-11-08
- ブランチ：`exp/depth-scale`
- 関連：[../depth-scale/](../depth-scale/README.md)（Depth Pro）、[../depth-scale-moge2/](../depth-scale-moge2/README.md)（MoGe-2）、[../depth-scale-da3/](../depth-scale-da3/README.md)（Depth Anything 3）

## これまでの結果（正解との差）

| 測り方 | 写真1 | 写真2（無地の紙） | 重みのライセンス |
|---|---|---|---|
| Depth Pro | （正解） | +1.5%（合格） | 研究目的だけ → 本番に使えない |
| Depth Anything 3（METRIC） | +30% | +50% | Apache-2.0 |
| MoGe-2（vitl） | +82% | +136% | MIT |
| **MapAnything** | ？ | ？ | **Apache-2.0** |

## ドキュメントの一覧

| ファイル | 中身 |
|---|---|
| [method.md](method.md) | MapAnything のしくみ、使い方（コードを読んで確かめたこと）、長さの出し方、ライセンス |
| [experiment.md](experiment.md) | 写真1枚での比べ方、出す途中経過の画像、結果の表 |
| [scripts.md](scripts.md) | `experiments/depth_scale_mapanything/` のスクリプトの仕様とテスト |
| [tasks.md](tasks.md) | やることと完了条件 |
