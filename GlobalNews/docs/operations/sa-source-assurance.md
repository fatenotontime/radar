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

所有探测和比较结果都只是网络证据。即使结果为 `both_reachable`、`primary_reachable` 或 `fallback_reachable`，也不代表已完成来源许可、允许字段、速率限制、保留周期或人工审核。任何来源进入正式采集前，这些问题必须在独立审查中明确确认。

## Evidence history

| Run | Commit | Time | Node | Counts | Artifact | Review |
| --- | --- | --- | --- | --- | --- | --- |
