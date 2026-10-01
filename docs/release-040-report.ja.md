# Collective Intelligence Overlay 0.4.0 実績報告

0.3.2 の監査修正・macOS 対応を公開して検証した後、0.4.0 の事前宣言 profile
`permissioned-single-owner-040-v1` を実装した。受入状況は
[要求台帳](production-040-acceptance.json)、宣言の原本は
[profile](profiles/production-040.json) に分けて記録する。

0.3.2 は commit `b172c0d0ef208ede4ae3a663a158f1713d7f49a0` の immutable `v0.3.2`。
[タグ CI attempt 2](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36705746853)、
[実 PyPI の 12 native 検証](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36716542836)、
[Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.2) を完了した。
最初の Mac Intel 3.14 の二つの失敗は原因未確定として保持し、同じ commit/pair/input/deadline
の failed-job retry が通過した。公開済み 0.3.2 の tag と三つの asset は変更していない。
配布 hash と監査修正・macOS の詳細は [既存の検証記録](validation.md) に残す。

## 完成した範囲

参加者を事前設定する HTTPS mesh、owner ごとの単一サービス process、分離した鍵・
runtime DB role・予算・受入方針を対象とする。operator が信用して導入した application
factory から既存 callable、MAF workflow、MCP tool、A2A capability を登録できる。
core に文書処理の固定入力や結果を埋め込まず、業務の builder、checker、品質契約を
application が供給する。配布 wheel に host、starter、migration、CLI と必要な資産を含めた。

三つの peer の実経路は、goal → 不足と代替案 → owner-local な選択と予算確認 →
形成・能力合成 → 独立検査 → receiver の用途適合判定 → 再利用 → 後続形成を接続する。
入力の変更、検証容量の不足、反証・撤回も保持する。登録、通信完了、署名の一致は
独立 PASS を意味しない。UNKNOWN、異論、残務、欠測費用は消去しない。
[研究原理の対応表](research-mapping.md) は、読んだ一次資料の範囲と実装・試験・指標・
限界を結び付ける。未読の証明や、成立条件を満たさない定理の保証を製品へ転用しない。

追加した自前差分は、既存 Registry/Executor/Store/OPA を接続する application host、
owner lock、readiness/drain、物理作業の追跡、原 ID の照合、閉じた復元と明示 resume、
有限の容量・保持警告、設定の段階的変更と復旧である。別 runtime、RPC、暗号方式、
budget 台帳、event store、global manager、queue、marketplace は追加していない。

## 導入・CLI・API

Python 3.12 以上の新しい仮想環境へ次の配布物を導入する。必須の有償 API はない。
OPA と PostgreSQL は別途必要で、import や install が自動導入することはない。

```sh
python -m pip install --no-cache-dir "collective-intelligence-overlay[agents]==0.4.0"
collective-intelligence-overlay --help
collective-intelligence-overlay opa-install --target ./bin/opa
```

Windows の OPA 保存先は `./bin/opa.exe` とする。
[日本語 README](../README.ja.md) と [native quickstart](quickstart.md) は、checkout
外の新しい directory/venv、専用 PostgreSQL cluster、選択した native interpreter で
順番に実行検査した。demo は開発用 DB と loopback の経路であり、本番 DB 権限とは異なる。
quickstart の専用 cluster を用意してから、次の実際の CLI を使う。

```sh
collective-intelligence-overlay demo --directory ./demo-run --opa ./bin/opa
collective-intelligence-overlay doctor --config ./demo-run/receiver/config.json
collective-intelligence-overlay inspect --config ./demo-run/receiver/config.json decision
collective-intelligence-overlay metrics --config ./demo-run/receiver/config.json
```

demo は ACCEPT、環境変更後の REQUALIFY、依存撤回後の REJECT を検査し、doctor の
DB/OPA 検査も実行した。starter はインストール済み wheel から生成できる。
[API](api.md)、[application 登録](integrations.md)、[運用・復旧](deployment.md) は、登録した
factory、公開 binding、独立 checker、goal と権限を operator が供給する手順を示す。
API の有限実行経路は `Opportunities(registry, identity, goals)` と
`Steps(opportunities, executor, owner_context, max_concurrent=4)` を組み合わせ、
`await steps.run(proposals, max_steps=8, max_candidates=8, seconds=120)` を呼ぶ。
これは新しい executor ではなく、既存の durable choice と Executor への接続である。
ネットワークから届いた import 名やコードは登録できない。

source 開発の再現コマンドは以下のとおり。pytest には専用 PostgreSQL、OPA と標準の
pg_dump/pg_restore が必要で、サービス未設定による skip を検証成功とは扱わない。

```sh
uv sync --all-extras --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/check_docs.py
uv build
uv run python scripts/check_package.py
```

新たな build は開発用であり、公開済み 0.4.0 の配布物を交換しない。

## OSS と権限境界

| 実測した主な OSS | 版 | License | 利用箇所 |
| --- | --- | --- | --- |
| agent-framework-core / agent-framework-openai | 1.19.0 / 1.14.4 | MIT | 公開 agent/workflow/middleware、任意の model adapter |
| a2a-sdk | 1.1.5 | Apache-2.0 | 公式 JSONRPC/extension、Message の公開 LegacyRequestHandler |
| MCP SDK | 2.2.0 | MIT | 公式 Streamable HTTP と認証付き client/server |
| SQLAlchemy / Alembic | 2.1.1 / 1.20.0 | MIT | PostgreSQL transaction と明示 migration |
| pg8000 | 1.31.5 | BSD-3-Clause | DB driver |
| Pydantic / jsonschema | 2.13.5 / 4.26.0 | MIT | 型と schema、登録された入出力契約 |
| securesystemslib | 1.5.1 | MIT | DSSE と CryptoSigner |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | Ed25519 と標準 key loading |
| OPA | 1.21.0 | Apache-2.0 | Rego による受入・作用の判定 |
| PostgreSQL | Linux 16.15、Windows/macOS 17.11 | PostgreSQL License | 独立 DB、restricted runtime role、backup/restore |
| Caddy / Go | 2.11.4+cio.1 / 1.27.1 | Apache-2.0 / BSD-3-Clause | 監査した参照 TLS proxy build |
| uv / uv_build | 0.12.19 | MIT OR Apache-2.0 | 環境、lock、wheel/sdist |

全依存の実際の name/version、license、audit、CycloneDX と native proxy の source/notice は
証拠 ZIP に保持する。互換範囲内の全版を保証する表ではない。
公式 Caddy binary の affecting 28 findings を受け入れず、固定した custom build を用いた。
module-only の未リンク OpenPGP finding と MPL/OFL 義務は記録を残した。
protobuf 7.36.2 の SBOM license field 欠落は、対応する元の pip-licenses の BSD-3-Clause
表記と関連付け、SBOM 原本を書き直していない。詳細は [互換性と license](compatibility.md)。

## 停止・復元・移行

readiness は DB/schema/policy/identity/設定を検査する。変更された policy、利用不能な OPA、
異なる鍵、壊れた鍵、設定保存中の失敗は受付を閉じ、作用や予算を増やさない。
設定保存失敗後は元の receipt を保持し、restart で旧 active binding を復元する。
過去の承認 receipt を新たな昇格として再適用しない。read-only trial、protected input、
独立 PASS、scope 内の明示昇格、rollback は現在の Registry と署名 Events を使う。

UNKNOWN の照合は保存済み provider ID/binding/request fingerprint を問い合せる。
不確かな作用を再 invoke せず、未確認の allowance を返金しない。復元は閉じた状態から、
署名・履歴・原 ID・予算を検査し、full sync、application 固有の外部状態照合とレビューを
終えてから明示 resume する。構造的に DB を復元できたことは業務状態の一致とは異なる。

0.3.2 からは旧 writer を停止し、一貫した DB/CAS/config/key backup を取得して、
Alembic 0020 まで migration する。[deployment](deployment.md) に手順を記載した。
公開 0.3.2 wheel と同じ原本を用いた Linux/最小 Python の installed live upgrade は
35 calls、14.9803706 秒で、元の signed bytes、UNKNOWN/held、mapping、閉じた復元と
明示 resume、その後の再利用を確認した。これは停止した writer を扱う POSIX/loopback CSV
互換経路であり、rolling upgrade、旧 Windows/macOS peer の graceful-stop、旧 HTTPS
deployment の移行を検証したものではない。

## 故障・soak・能力形成比較

各 native profile の source と installed agents は、三 owner の実 HTTPS/MAF/A2A/
認証付き MCP/restricted PostgreSQL による 19 カテゴリの短い故障 protocol を実行した。
process kill、物理 DB 切断、provider stop/timeout、原 ID 重複、clock skew、不正署名、
撤回、容量・予算不足、checker failure、backup interruption、閉じた restore、drain、
二重 boot、429/503、鍵更新・危殆化、protected regression を含む。
設定保存失敗の追加証拠も各 profile の source/installed の両方で検査した。

Linux の正式 soak は seed 401、warmup 300 秒、測定 3,600 秒で、20 数値 gate と
原本からの 3 追加 gate を通過し、最終の `pending_validation` は空である。数値層が
保留した三つの原本検査を、別の raw audit が root の追加 gate として検証した。
数値層の元の保留表示は書き換えていない。測定原本は 781 の連続した 5 秒 sample、
最大遅れ 0.0058966 秒、3,583 signed records を保持する。overall の拒否・FAIL・UNKNOWN
も分母に残し、正常 window の classified response fraction は 1、throughput は 0.25/s。
readonly p95/p99 は 0.417676/1.699305 秒、invoke の全 outcome p99 は 1.342029 秒、
finite loop p95/p99 は 1.800061/2.260465 秒。最大 operation は 21.275028 秒、
最大 recovery は 31.128932 秒だった。

owner RSS 最大 239,243,264 bytes、warmup 後増分 102,592,512 bytes、DB 増分
39,739,392 bytes、CAS 421,021 bytes、rotated logs 37,851,597 bytes。
未解決 effects 最大 12、未検証候補最大 1。CPU、包括 wall、bytes、allowance、未測定
token/currency を別々に保持し、親子時間を足し合わせていない。
これは宣言した workload/resource の受入値であり、SLA や Windows/macOS の一時間 soak
を示すものではない。詳細は [soak 原本の評価](production-soak.md)。

能力形成比較は 5 独立 matched pairs、10 arms、30 DB、同じ初期契約・予算・task を使い、
arm 間の cache/evidence/成果は共有しなかった。全 240 held-out 分母と 4,713 signed
records を保持した。seed 17/43/71/101 は両 arm とも 24/24、seed 29 は static 4/24、
adaptive 3/24。adaptive-minus-static 平均は -0.0083333333、記述的 paired bootstrap
95% interval は [-0.025, 0]。一般的な adaptive 優位性、母集団同等性、集団的知能や
自己加速の実証は成立しない。詳細は [比較 protocol と結果](production-experiments.md)。

同じ最終 pair の最初の soak は原 ID 重複の transport-side ValueError により失敗した。
後の restart はその失敗を取り消さない。最初と成功 repeat の 110-file 原本・manifest
をそれぞれ保持する。以前の二つの whole CI は、Windows の notice separator を Linux で
読む aggregate の不具合で失敗したままであり、訂正後の成功 CI と区別する。

## 公開・12 native profile の実績

| Native OS / CPU | CPython | Tag / actual PyPI | Source / agents / mock model / rebuilt sdist | Actual PyPI core / agents / model audit counts |
| --- | --- | --- | --- | --- |
| Darwin / amd64 | 3.12.14 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 63 / 66 |
| Darwin / amd64 | 3.13.15 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Darwin / amd64 | 3.14.7 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Darwin / arm64 | 3.12.14 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 63 / 66 |
| Darwin / arm64 | 3.13.15 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Darwin / arm64 | 3.14.7 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Linux / amd64 | 3.12.14 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 63 / 66 |
| Linux / amd64 | 3.13.15 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Linux / amd64 | 3.14.7 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 59 / 63 |
| Windows / amd64 | 3.12.14 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 64 / 67 |
| Windows / amd64 | 3.13.15 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 60 / 64 |
| Windows / amd64 | 3.14.7 | PASS / PASS | 375 / 374 / 1 / 64 | 31 / 60 / 64 |


Release commit は `f3f6ae30de6f088c160e0c69f49796e4f52d2546`、immutable annotated tag は `v0.4.0`。
[タグ CI と PyPA OIDC 公開](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36911991678)、
[cache 無効の実 PyPI 検証](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36922605705) は両方 whole workflow SUCCESS。
両方で 12 native profiles、4 cross readers、mixed Python、正式原本の再評価が通過した。
source 375、installed agents 374、mock model 1、rebuilt sdist 64 の各 suite は全環境で
failures/errors/skips が 0。公開後の 36 audit は root を含み、配布時の全 name/version と一致した。

公開は 2026-10-01 20:29 UTC（2026-10-02 05:29 JST）に完了。
[PyPI](https://pypi.org/project/collective-intelligence-overlay/0.4.0/) の実際の payload と
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.0) の実際に再 download した配布物は、選択した同じ pair と一致する。

| 配布物 | SHA256 |
| --- | --- |
| `collective_intelligence_overlay-0.4.0-py3-none-any.whl` | `33898a964443c5276853dc15069247ff8642012332c980d085f9fa9a4faf11d7` |
| `collective_intelligence_overlay-0.4.0.tar.gz` | `965f848ed12950d0a8cba26e6deb1594d8ce98437022fc9dd5dff0f7e860f8be` |
| `collective-intelligence-overlay-0.4.0-evidence.zip` | `1135a9e487340279ee56a4e4edf11f32869ee88d8901a3078c5fac352307674d` |

証拠 ZIP は両 whole CI の元の provenance、native/cross/mixed/正式評価、proxy source/notices、
成功と最初の失敗の各 110-file 原本、別に生成した評価を保持する。秘密を含む runtime DB URL
は公開用コピーだけから削除し、EXPORT-REDACTIONS に原本と公開コピーの hash を残す。
署名原本の再生成、公開 tag の移動、配布物の再 build や交換はしていない。


## 検証していない範囲

有償 model inference は実施していない。別環境での外部組織間運用、WAN/HA、多重 writer、
任意業務の正しさ、一般的な外部 exactly-once、prompt-injection immunity、物理消去や
unlearning、独立 legal/security audit、長期性能保証は成立を主張しない。
scope ごとの application/checker、operator、DB administrator、filesystem と設定した
identity infrastructure を信用する。profile 外の利用には別の検証が必要である。
