# Source Probe 运行说明

## 目的

`scripts/run_source_probe.py` 是一次性来源连通性测试，不是正式爬虫。它只读取候选目录并访问公开端点，不修改 Source Policy、新闻数据、归档、服务配置或调度。

## fate 账号运行

从 Radar 工作区根目录运行：

```bash
python3 GlobalNews/scripts/run_source_probe.py \
  --catalog GlobalNews/config/source_probe_candidates.json \
  --output-dir "outputs/fate-source-probe-$(date -u +%Y%m%dT%H%M%SZ)" \
  --attempts 2 \
  --timeout 10 \
  --delay 1
```

如果脚本不在该目录，使用脚本和候选目录的绝对路径。不要使用 `sudo`，并确保输出目录对后续审阅账号可读。运行结束后，把实际输出目录的绝对路径发回；审阅所需文件全部在该目录内。

## 输出文件

- `run_metadata.json`：运行 ID、账号、主机、Python、候选目录哈希和测试参数；
- `results.jsonl`：每个来源的每次尝试、DNS/TLS/HTTP、响应格式、错误和网络提示；
- `summary.json`：机器可读计数；
- `summary.md`：人工审阅摘要。

## 判定边界

脚本只提供网络可达性和响应形状证据。`ecs_candidate_pending_policy` 不表示允许采集；`manual`、`blocked` 或 `needs_external_comparison` 也需要结合许可、速率、字段和外部节点对照后才能定案。脚本始终写入 `license_reviewed=false` 和 `verified_for_collection=false`。

如果某个来源失败，保留整轮结果并继续测试其他来源。不要手动修改 `results.jsonl`；如需补测，使用新的输出目录。

## 候选池与外部节点对照

`config/source_probe_candidates.json` 是网络探测候选池，不是正式 Source Policy。候选增加、HTTP 200 或解析成功均不会启用采集；正式启用仍需单独完成许可、字段、频率和人工复核。

ECS 在 2026-09-13 完整测试中出现连接或 TLS 异常的 9 个来源，固定记录在 `config/source_external_compare.json`。GitHub Actions 工作流 `.github/workflows/radar-source-external-compare.yml` 每周二 03:17 UTC 自动从 GitHub 托管的 Ubuntu 节点运行，也可在仓库 Actions 页面手动运行。每次输出使用 GitHub run ID 和 attempt 组成独立目录，并保留完整探测 bundle 14 天。

外部节点结果只能区分“ECS 路径特有问题”和“来源普遍异常”，不能替代来源许可审查。对照目录必须保持恰好 9 项，并与主候选池中的同 ID 记录完全一致；自动测试会校验这个约束。
