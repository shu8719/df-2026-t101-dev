# hand-mesh（手のメッシュ復元で指の曲がり角を出すサービス）

[api.md §4](../docs/api.md#4-手のメッシュ復元サービス-hand-mesh) の `POST /v1/angles` のプロトタイプ。ブラウザから直接呼ぶ。SAM 3D Body（Meta）で、切り抜いた手のフレームから3Dの関節を出し、[measurement.md §6](../docs/measurement.md#6-フレームごとに求める値) と同じ定義で MCP・PIP・DIP の曲がり角を返す（フレームの中央値と IQR）。

## セットアップ（Windows、NVIDIA GPU）

```
cd hand_mesh
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu132
.venv\Scripts\python -m pip install -r requirements.txt
```

重み（承認制）：Hugging Face の [facebook/sam-3d-body-vith](https://huggingface.co/facebook/sam-3d-body-vith) で利用を申請し、承認されたら `.venv\Scripts\hf auth login`。初回の起動で約2.4GBを `~/.cache/huggingface` に取ってくる（先に取るなら `.venv\Scripts\hf download facebook/sam-3d-body-vith`）。

## 動かし方

```
.venv\Scripts\python -m uvicorn app:app --port 8081
curl http://localhost:8081/healthz
.venv\Scripts\python -m pytest -q tests      # モックで動く
```

`/healthz` は `{ok, backend, device, model_loaded, model, requested_backend, sam3d:{status, repo, reason}}`。SAM 3D Body が使えない理由は `sam3d.reason` に出る。

## 環境変数

| 名前 | 既定 | 中身 |
|---|---|---|
| `HAND_MESH_BACKEND` | （なし＝auto） | `sam3d`：本物だけ（読み込み中・失敗の間は `503 MESH_UNAVAILABLE`）。`mock`：モックだけ。未指定：本物を試し、だめならモックにする（ログに `FALLING BACK TO MOCK` と理由を出す） |
| `HAND_MESH_HF_REPO` | `facebook/sam-3d-body-vith` | `facebook/sam-3d-body-dinov3` も可（初回に torch.hub で DINOv3 のコードを GitHub から取る） |
| `HAND_MESH_CHECKPOINT_DIR` | なし | `model_config.yaml`・`model.ckpt`・`assets/mhr_model.pt` を置いたフォルダ（Cloud Run で GCS から取る場合など）。指定すると Hugging Face を見ない |
| `HAND_MESH_BOX_SCALE` | `1.0` | フレーム全体を手の枠とみなすときの倍率 |
| `MESH_MAX_EXECUTION_SECONDS` | `60` | 推論の打ち切り（超えたら `503 MESH_UNAVAILABLE`） |
| `MESH_MAX_FRAME_BYTES` | `200000` | 1枚の上限 |
| `HAND_MESH_REQUIRE_USER` | `0` | `1` なら `X-User` ヘッダーを必須にする（なければ401） |
| `HAND_MESH_CORS_ORIGINS` | なし | `http(s)://localhost:*`・`127.0.0.1:*` のほかに許すオリジン（カンマ区切り） |
| `MESH_RESULT_HMAC_KEY` | なし | 指定したときだけ `result_token` を付ける（`v1.<case_id>.<UTC>.<角度のsha256>.<HMAC-SHA256>`。角度は `{指:{mcp,pip,dip}}` をキー順・空白なしのJSONにしたもの） |

## 本物とモック

| 部分 | 状態 |
|---|---|
| API の形・エラー（`CONSENT_REQUIRED`・`NO_HAND_DETECTED`・`MESH_UNAVAILABLE`）・CORS | 本物 |
| 同意の確認 | 仮：`meta.consent === true` を見る（Firestore の `mesh_consent_at` は未実装） |
| 認証 | 仮：`X-User` を受け取るだけ（Firebase の ID トークンは未実装）。回数・費用の上限、停止設定もまだ |
| 角度の計算（`angles.py`） | 本物。順運動学で作った手から角度を戻すテストあり |
| SAM 3D Body（`backends.py`） | 本物のコード。人の検出器（Detectron2）は使わず、フレーム全体を手の枠として**手のデコーダだけ**を回す（上流の `forward_step(decoder_type="hand")`、手の切り抜きの変換も上流と同じ padding 0.9）。手のデコーダは右手専用なので、左手は画像を左右反転してから入れる（上流の `run_inference` と同じ扱い） |
| モック | 枚数と順番だけから決まる、もっともらしい角度。同じ角度の計算を通す。`model: "mock"` |

## 関節の対応（MHR70、右手）

出典：`vendor/sam-3d-body/sam_3d_body/metadata/mhr70.py`（名前と骨格の線。`right_wrist` は `*_third_joint` につながるので、third＝MCP、second＝PIP、first＝DIP）。

| 指 | MCP | PIP | DIP | TIP |
|---|---|---|---|---|
| 人差し指 | 28 | 27 | 26 | 25 |
| 中指 | 32 | 31 | 30 | 29 |
| 薬指 | 36 | 35 | 34 | 33 |
| 小指 | 40 | 39 | 38 | 37 |

手首は41（親指は24〜21で、使わない）。3Dの点の x の符号を変えて正準形（左手、§8.1）にし、手のひら側の法線 z＝x×y と、指ごとの回転軸 n＝d0×z（d0 は手首→MCP を手のひらの面に投影した向き、§8.2）で、`atan2((a×b)·n, a·b)` を出す。

## 分かっている制限

- 重みが承認されるまで、本物の推論は試せていない（読み込みと推論のコードは上流のコードを読んで書いた。初回は要確認）
- `NO_HAND_DETECTED` は、手のキーポイントが切り抜きの外に出たフレームを捨てる判定（上流の CRITERIA 3）だけ。手が写っていない画像でも何かしらの姿勢を返すことがある。一部のフレームを捨てたときは `warnings` に `MESH_FRAMES_DROPPED`
- 画像1枚ずつ順に推論する（まとめての推論はしていない）。GPU が要る（上流のコードが `.cuda()` 決め打ち）
- 拘縮や変形のある手での精度は未評価（ADR-0008）。MCP の角度には中手骨とのずれ（約10度）が混ざる（measurement.md §6）
- 画像はメモリの中だけで扱い、ディスクにもログにも書かない。ログは枚数・処理時間・エラーコードだけ

## ライセンス

`vendor/sam-3d-body/` は [facebookresearch/sam-3d-body](https://github.com/facebookresearch/sam-3d-body)（コミット `b5c765a`、2026-02-19）のコピーで、**SAM License**（`vendor/sam-3d-body/LICENSE`）。`.git` とデモ画像（`assets/`）は除いた。重みもSAM Licenseで、リポジトリやイメージには入れない。配布するときはライセンス文を添え、発表物・著作物利用シートに「SAM 3D Body（Meta、SAM License）」と MHR（Meta、Apache-2.0）の利用を書く。
