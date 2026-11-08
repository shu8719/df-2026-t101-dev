# しくみと方法（MapAnything）

> **このドキュメントで決めたこと**
> 1. MapAnything の出力のうち、**カメラから見た各画素の3D位置（`pts3d_cam`、メートル）**を使い、手首と指の付け根の5点の3D位置から手の甲の4区間の長さを出す。焦点距離はモデルが推定する（与えない）。
> 2. MapAnything は画像を縮めるだけでなく**決まった縦横の比に切り取る**ので、**MediaPipe はモデルが実際に見た画像（`img_no_norm`）にかける**。点の位置と3D位置の画像が、同じ画素の並びになる。
> 3. 重みは `facebook/map-anything-apache`（Apache-2.0）だけを使う。非営利の `facebook/map-anything`（CC BY-NC 4.0）は読み込めないようにする。

関連：[README.md](README.md)、[scripts.md](scripts.md)

---

## 1. しくみ

MapAnything（Meta、3DV 2026）は、1枚または複数の画像（と、あればカメラの情報・深度・位置）から、**実際の大きさの3Dの形**を1回の計算で出すモデル。写真1枚だけからの「実際の距離の推定」も、できることの1つとして挙がっている。

- 3D位置を「光線の向き（カメラの情報）」「光線に沿った深度」「全体の倍率（`metric_scaling_factor`）」に分けて推定し、掛け合わせる
- カメラの情報（焦点距離）も推定する。与えることもできる（今回は与えない。ブラウザでは焦点距離が取れないため）

## 2. 使い方（コードを読んで確かめたこと、コミット `3d10cf7`、2026-11-08）

| 項目 | 中身 |
|---|---|
| 読み込み | `from mapanything.models import MapAnything`、`MapAnything.from_pretrained("facebook/map-anything-apache")` |
| 入力 | `preprocess_inputs([{"img": PIL の画像}])`。メモリの中の画像を渡せる（ファイルに保存しなくてよい） |
| 画像の縮め方 | `resize_mode="fixed_mapping"`（既定）：縦横の比を、決まった組み合わせ（解像度の組 518）のうち一番近いものに合わせ、**縮めたうえで切り取る**（`crop_resize_if_necessary`） |
| 推論 | `model.infer(views, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)` |
| 出力 | `pts3d_cam`（カメラから見た3D位置）、`depth_z`（深度）、`intrinsics`（カメラの情報）、`conf`（信頼度）、`mask`（使える画素）、`metric_scaling_factor`（倍率）、`img_no_norm`（モデルが見た画像） |
| 単位 | メートルと見込む（「metric」とある）。mm に直す |

## 3. 長さの出し方

1. 写真を、長い辺 1280px まで縮める（ほかの実験と同じ）
2. MapAnything にかけ、出力を受け取る
3. **`img_no_norm`（モデルが見た画像）に MediaPipe をかけ**、手の21点を出す
4. 5点（0・5・9・13・17）のそれぞれで、点を中心とする半径 3px の円の中の、`mask` があり有限な画素の `pts3d_cam` の x・y・z それぞれの中央値を、その点の3D位置にする（MoGe-2 の実験と同じ）
5. 4区間の長さを出す
6. 確かめとして、`depth_z` と `intrinsics` から Depth Pro と同じ式で3Dに直した長さも出し、差が小さいかを見る

## 4. ライセンス

| 対象 | ライセンス | 確かめた所（2026-11-08） |
|---|---|---|
| コード | Apache-2.0 | GitHub の LICENSE（`facebookresearch/map-anything`） |
| 重み `facebook/map-anything-apache` | Apache-2.0 | Hugging Face のモデルのページ |
| 重み `facebook/map-anything` | **CC BY-NC 4.0（非営利だけ）** | 同上。**使わない** |

- 中で使っている部品（`uniception`、DINOv2 など）のライセンスは、本番で使う場合に確かめる
- 本番で使う場合は、著作物利用シートと README に「MapAnything（Meta、Apache-2.0）」を書き、Apache-2.0 の表示を添える
- プライバシーは Depth Pro の実験と同じ（[../depth-scale/method.md §6](../depth-scale/method.md#6-プライバシーの扱い)）

## 5. 確かめること（要確認）

| 項目 | 確かめ方 |
|---|---|
| 写真1枚だけで、実際の大きさが当たるか | 写真1・写真2で正解と比べる |
| 単位がメートルか | 写真1で、カメラから手首までの距離が Depth Pro（221mm）と近いか |
| 手元のGPU（16GB）で動くか、時間 | 動かして測る |
| `opencv-python-headless==4.10` の指定（共通の環境の OpenCV 5 とぶつかる） | 本体は依存を入れずに入れ、要るものだけを版を固定して入れる |
