# やること（MetricAnything）

> **このドキュメントで決めたこと**
> 1. MVP の作業を優先し、この実験は手が空いた人が行う。
> 2. 12枚で判定し（MA3）、補正後に合格の目安に入れば、動画（本番と同じ撮り方）と別の人の手で確かめる（MA4）。
> 3. 環境は共通のもの（`experiments/depth_scale/.venv`）を使い、新しいライブラリは入れない。

関連：[README.md](README.md)、[method.md](method.md)、[experiment.md](experiment.md)

---

| ID | タスク | 完了条件 | 状況（2026-11-08） |
|---|---|---|---|
| MA1 | 重みの読み込み | 導入済みの MoGe で重みが読み込める。ライセンスを確かめた | **済み**（strict で読み込めた、4.0秒。Hugging Face の表示は apache-2.0） |
| MA2 | スクリプトとテスト | 写真1枚ごとに長さ・段階別の時間・画像が出る。テストが通る | 未着手 |
| MA3 | 12枚で判定 | [experiment.md §2](experiment.md#2-結果) の表が埋まり、§3 に判断がある | 未着手 |
| MA4 | 動画・別の人の手（MA3 で合格なら） | 合格の目安に入る | 未着手 |

## ライセンスの記録（2026-11-08）

| 対象 | 内容 |
|---|---|
| コード `metric-anything/metric-anything`（コミット `616a5e6`） | Apache-2.0（LICENSE） |
| 重み `yjh001/metricanything_student_pointmap`（`student_pointmap.pt`） | Apache-2.0（Hugging Face の表示） |
| 元のモデル MoGe-2 | MIT（Microsoft）。中の DINOv2 は Apache-2.0 |
