# やること（MapAnything）

> **このドキュメントで決めたこと**
> 1. MVP の作業を優先し、この実験は手が空いた人が行う。
> 2. 写真1枚で判定し（MA4）、合格なら動画（MA5）に進む。外れたら、本番で使えるモデルは今のところ見当たらないと結論づけ、発表では Depth Pro の結果を「今後の方向性」として示す。
> 3. 環境は共通のもの（`experiments/depth_scale/.venv`）を使い、新しく作らない。

関連：[README.md](README.md)、[method.md](method.md)、[scripts.md](scripts.md)

---

| ID | タスク | 完了条件 | 状況（2026-11-08） |
|---|---|---|---|
| MA1 | 環境 | 共通の環境に MapAnything（コミット `3d10cf7`、依存なし）と要るものが版を固定して入り、PyTorch 2.14.1・numpy 2.5.4・OpenCV 5 のまま読み込める | **済み** |
| MA2 | 使い方の確認 | 入力・画像の縮め方・出力・単位がコードで確かめてあり、[method.md §2](method.md#2-使い方コードを読んで確かめたことコミット-3d10cf72026-11-08) に書いてある | **済み** |
| MA3 | `mapanything_backend.py`・`try_image_mapanything.py` とテスト | 写真1枚から長さと7枚の途中経過の画像が出る。テストが通る | **済み**（テスト5件が通る） |
| MA4 | 写真1・写真2で判定 | [experiment.md §3](experiment.md#3-結果) の表が埋まり、判定が書いてある | **済み：不合格**（+424%・+370%） |
| MA5 | 動画で確かめる（MA4 で合格したら） | 本番と同じ撮り方の動画で、手の甲のフレームの中央値が合格の目安に入る | 行わない（MA4 で不合格） |

## ライセンスの記録（2026-11-08）

| 対象 | 内容 |
|---|---|
| コード | Apache-2.0（`facebookresearch/map-anything` の LICENSE） |
| 重み `facebook/map-anything-apache` | Apache-2.0（Hugging Face のモデルのページ） |
| 使わない重み | `facebook/map-anything`（CC BY-NC 4.0） |
