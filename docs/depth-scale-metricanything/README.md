# MetricAnything で手を実寸にする（1円玉がないとき）

> **このドキュメントで決めたこと**
> 1. 有志（論文の著者）が公開している **MetricAnything の点群版**（`yjh001/metricanything_student_pointmap`、Apache-2.0）で、写真から手の甲の4区間の長さ（mm）を出せるかを確かめる。MoGe-2 を約2,000万組のデータで学習し直し、実際の大きさを推定できるようにしたモデルで、MoGe-2 の弱点（大きさの推定）が直っているかを見る。
> 2. これまでと同じ12枚の写真・同じ正解（写真1の Depth Pro の値＝本人が定規で確かめた値）で判定し、ずれの平均で直す補正も1枚を除く確かめで評価する。あわせて、**画像の処理から計測結果が出るまでの時間**を、段階ごとに測る。
> 3. 導入済みの MoGe（コミット `74fbce0`）で重みをそのまま読み込めたので、新しいライブラリは入れない。仮想環境は共通のもの。MVP には入れず、本番のコードは変えない。

- 書いた日：2026-11-08
- ブランチ：`exp/depth-scale`
- 関連：[../depth-scale/comparison.md](../depth-scale/comparison.md)（これまでのモデルの比較）、[../depth-scale-moge2/](../depth-scale-moge2/README.md)（元になった MoGe-2）、[../depth-scale-yolo26/](../depth-scale-yolo26/README.md)（補正の評価のしかた）

## MetricAnything とは

| 項目 | 中身 |
|---|---|
| 公開 | 論文 arXiv 2601.22054（ECCV 2026）。コードは `github.com/metric-anything/metric-anything`、重みは Hugging Face の `yjh001/metricanything_student_pointmap`（論文の著者が公開） |
| ライセンス | コード Apache-2.0（LICENSE）、重み Apache-2.0（Hugging Face の表示） |
| 元のモデル | MoGe-2（ViT-L）を学習し直したもの。読み込み方・出力の形は MoGe-2 と同じ |
| 学習データ | 約2,000万組（SfM・SLAM・多視点・LiDAR・ToF・RGB-D・合成画像など） |
| 出すもの | 実際の大きさの3D点群（カメラの座標）、深度、使える画素の印、カメラの情報（焦点距離も推定する） |
| 大きさ | 約3.3億パラメータ。重み 約1.3GB |

## これまでの結果（手の甲の写真10枚、補正後のずれの中央値）

| モデル | 補正前 | 補正後 | ライセンス |
|---|---|---|---|
| Depth Pro | 5.1% | 3.3% | 研究目的だけ |
| Depth Anything 3（504px） | 26.6% | 4.9% | Apache-2.0 |
| YOLO26 Depth（x、1280px） | 7.5% | 10.4% | AGPL-3.0 |
| MoGe-2 | 94.1% | 11.7% | MIT |
| **MetricAnything** | ？ | ？ | **Apache-2.0** |

## ドキュメントの一覧

| ファイル | 中身 |
|---|---|
| [method.md](method.md) | 使い方、長さの出し方、時間の測り方 |
| [experiment.md](experiment.md) | 出す画像、結果の表 |
| [tasks.md](tasks.md) | やることと完了条件 |
