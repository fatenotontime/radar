# Source Probe 运行说明

## 目的

`scripts/run_source_probe.py` 是一次性来源连通性测试，不是正式爬虫。它只读取候选目录并访问公开端点，不修改 Source Policy、新闻数据、归档、服务配置或调度。

## Linux 完整运行流程

在用户本机终端中逐行执行以下命令。登录后必须是 `codex` 账号；整个流程无需 `sudo`，也不应使用 `sudo`。本次命令只读取 18 源 catalog，并把新证据 bundle 写到 Radar 工作区的 `outputs/` 目录；不写入运行时 Radar 数据、Source Policy、新闻数据、归档、服务配置或调度。

```bash
ssh research-codex
cd '/srv/research-suite/radar/research radar/GlobalNews'
test "$(id -un)" = codex || { echo 'This probe must run as codex.'; exit 1; }
output_dir="../outputs/codex-sa-$(date -u +%Y%m%dT%H%M%SZ)"
python3 scripts/run_source_probe.py --catalog config/source_sa_external_compare.json --output-dir "$output_dir" --attempts 2 --timeout 20 --delay 1
python3 -m json.tool "$output_dir/summary.json"
realpath "$output_dir"
exit
```

`source_sa_external_compare.json` 是 S/A 保障范围的 18 源 catalog。`json.tool` 成功输出完整 JSON 才表明 `summary.json` 可解析；`realpath` 打印的新目录是后续复核所需的证据目录。如需补测，重新执行并生成新的 UTC 时间戳目录，不要覆盖旧 bundle。

## 输出文件

- `run_metadata.json`：运行 ID、账号、主机、Python、候选目录哈希和测试参数；
- `results.jsonl`：每个来源的每次尝试、DNS/TLS/HTTP、响应格式、错误和网络提示；
- `summary.json`：机器可读计数；
- `summary.md`：人工审阅摘要。

## 判定边界

脚本只提供网络可达性和响应形状证据。`ecs_candidate_pending_policy` 不表示允许采集；`manual`、`blocked` 或 `needs_external_comparison` 也需要结合许可、速率、字段和外部节点对照后才能定案。脚本始终写入 `license_reviewed=false` 和 `verified_for_collection=false`。

如果某个来源失败，保留整轮结果并继续测试其他来源。不要手动修改 `results.jsonl`；如需补测，使用新的输出目录。

## S/A 18 源外部节点对照

`config/source_probe_candidates.json` 是网络探测候选池，不是正式 Source Policy。候选增加、HTTP 200 或解析成功均不会启用采集；正式启用仍需单独完成许可、字段、频率和人工复核。

S/A 比较只使用两个都基于 `config/source_sa_external_compare.json` 的 18 源 bundle：

- **primary** 固定为上述 Linux 流程在 ECS 生成的 `codex-sa-{UTC timestamp}/results.jsonl`。
- **fallback** 固定为 [S/A source assurance workflow](../../../.github/workflows/radar-sa-source-assurance.yml) 产生的 `radar-sa-source-evidence-{run id}-{run attempt}` artifact 中的 `probe/results.jsonl`。

下载并解压 artifact 后，一组准确的 Windows 路径形状示例是：

- primary：`D:\radar-evidence\ecs\codex-sa-20260915T012345Z\results.jsonl`
- fallback：`D:\radar-evidence\github\radar-sa-source-evidence-123456789-1\probe\results.jsonl`

## Windows PowerShell 结果比较

先将上述两个 18 源 bundle 下载或复制到 Windows 本机。比较前必须确认两份 `results.jsonl` 的 `source_id` 集合完全一致；否则比较器会以 `source_id sets differ` 拒绝运行。

参数方向也是证据语义的一部分：ECS 18 源结果必须传给 `--primary-results`，S/A workflow artifact 中的结果必须传给 `--fallback-results`。如果反向传参，`primary_reachable` 和 `fallback_reachable` 的方向会被颠倒，从而造成错误解读。

在 `radar` 仓库根目录打开 PowerShell，将示例中的时间戳、run ID 和 run attempt 替换为实际值，再逐行执行：

```powershell
$PrimaryResults = 'D:\radar-evidence\ecs\codex-sa-20260915T012345Z\results.jsonl'
$FallbackResults = 'D:\radar-evidence\github\radar-sa-source-evidence-123456789-1\probe\results.jsonl'
$ComparisonOutput = 'D:\radar-evidence\comparison\sa-source-comparison-20260915T012345Z.json'
python .\GlobalNews\scripts\compare_source_probe_runs.py --primary-results $PrimaryResults --fallback-results $FallbackResults --output $ComparisonOutput
python -m json.tool $ComparisonOutput
Resolve-Path $ComparisonOutput
```

输出中的五种 `classification` 与比较器逻辑一致：

- `both_reachable`：主节点和备选节点的最终结果都成功。
- `fallback_reachable`：主节点失败，备选节点成功，表明问题可能与主节点网络路径有关。
- `primary_reachable`：主节点成功，备选节点失败。
- `policy_or_access_review`：两端都未成功，且至少一端返回 401、403、407、429 或 451，需要复核访问政策或权限。
- `both_failed`：两端都未成功，且没有命中上述访问复核 HTTP 状态。

`fallback_reachable` 仅是网络证据，不是采集授权。五种分类都不代替许可、允许字段、频率限制和人工复核。该比较器要求两份 `results.jsonl` 的 `source_id` 集合完全一致，且输出路径必须是不存在的新文件。

## 历史 9 源诊断

ECS 在 2026-09-13 完整测试中出现连接或 TLS 异常的 9 个来源，固定记录在 `config/source_external_compare.json`。GitHub Actions [历史 9 源 workflow](../../../.github/workflows/radar-source-external-compare.yml) 是为这个来源集合设置的独立诊断流程。

该 workflow 的 9 源 bundle **不可**与本文上述 ECS 18 源 bundle 比较；两者的 `source_id` 集合不同，比较器会正确拒绝。历史 9 源结果只能与同样基于 `config/source_external_compare.json` 的 9 源结果对照，不能用于 S/A 18 源保障判定。
