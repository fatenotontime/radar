# S/A 来源保障公开证据

## 当前范围

`radar` 仓库已批准的优先来源范围是 **S=7**、**A=11**，合计 18 个来源。版本化的定义与执行入口如下：

- 自动化 workflow：[`radar-sa-source-assurance.yml`](../../../.github/workflows/radar-sa-source-assurance.yml)
- S/A 优先级 manifest：[`source_assurance_priorities.json`](../../config/source_assurance_priorities.json)
- 18 源探测 catalog：[`source_sa_external_compare.json`](../../config/source_sa_external_compare.json)
- 节点结果比较器：[`compare_source_probe_runs.py`](../../scripts/compare_source_probe_runs.py)
- 手工运行与比较说明：[`source-probe-runbook.md`](source-probe-runbook.md)

## 证据边界

当前工作仍是来源探测，不是正式采集。workflow 从 GitHub 托管的 Ubuntu 节点检查 18 源的 DNS、TLS、HTTP 和响应形状，并保留可供人工复核的证据 artifact。节点对照用于判断失败是否可能与特定网络路径有关，不证明来源允许采集。

S/A 对照的方向固定：ECS 用 18 源 catalog 生成的 `results.jsonl` 是 primary，上述 S/A workflow artifact 内的 `probe/results.jsonl` 是 fallback。两边必须来自同一 18 源 catalog，且 `source_id` 集合完全一致。任何其他来源数量或来源集合的 bundle 都不属于这一 S/A 对照，不应混用。

所有探测和比较结果都只是网络证据。即使结果为 `both_reachable`、`primary_reachable` 或 `fallback_reachable`，也不代表已完成来源许可、允许字段、速率限制、保留周期或人工审核。任何来源进入正式采集前，这些问题必须在独立审查中明确确认。

## Evidence history

| Run | Commit | Time | Node | Counts | Artifact | Review |
| --- | --- | --- | --- | --- | --- | --- |
| [GitHub Actions 34961243116](https://github.com/fatenotontime/radar/actions/runs/34961243116) | `05dea7c784f380639731fae5d983b6fb4cac4b64` | 2026-09-15 11:03:57–11:04:36 UTC | GitHub 托管 Ubuntu | 18 源：9 success / 9 failure；HTTP 200=9、403=7、404=1、429=1 | `radar-sa-source-evidence-34961243116-1`（artifact id `10393052598`） | workflow 成功只表示探测与证据上传完成，不表示全部来源成功，也不构成采集授权 |
| ECS `research-server/codex` | — | 2026-09-15 11:10:55–11:20:27 UTC | ECS | 18 failure；HTTP 403=4、none=14 | `/srv/research-suite/radar/research radar/outputs/codex-sa-20260915T111054Z` | 私网节点探测证据；未提交原始 output |

两次运行使用相同 catalog，SHA-256 均为 `954b91d343f4b68d59272f9b7072ec24bb440fe9a79d15178d6d29c86eca0006`。GitHub 节点最终记录中的 DNS、连接和 TLS 均成功；ECS 节点 18 源的 DNS 均成功。ECS 的失败分布为 `ConnectionResetError=3`、`OSError=2`、`TimeoutError=7`、`URLError=2`、`http_error=4`。

本地对照文件为 `sa-comparison-ecs-20260915T111054Z-gha-34961243116.json`。比较结果是 `fallback_reachable=9`、`policy_or_access_review=8`、`both_failed=1`：

- `fallback_reachable`：`allenai`、`anthropic`、`ase`、`gpaw`、`huggingface`、`materials_cloud`、`meta_ai`、`mistral_ai`、`nvidia`。可保留 GitHub 外部节点作为网络备用；正式采集仍须分别完成 Source Adapter、Event Schema 和许可审查。
- `policy_or_access_review`：`acs_catalysis`、`acs_chem_mater`、`acs_jctc`、`arxiv_api`、`chemrxiv`、`materials_project`、`openai`、`rsc_pccp`。禁止绕过 403 或 429；`arxiv_api` 单独落实限速、backoff 和合规 User-Agent，其余来源寻找官方 API、RSS 或明确许可路径。
- `both_failed`：`aip_jcp`。先修正或确认官方 endpoint，再在两个节点重测。

这组证据只用于收敛来源接入路径。DFT 与量化主线在此阶段不实现。
