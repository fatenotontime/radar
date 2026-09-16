# Research Radar 状态

> 核实日期：2026-09-16
> 作用域：`research radar/`；受上级 `../AGENTS.md` 约束。

## 已完成

- Radar 升级设计、候选来源目录与 Phase 1 实施计划已经批准。
- 20 个旧 RSS 来源已进入带稳定 `source_id` 的 Source Policy 目录；全部标记为 `legacy_candidate` 且默认禁用，不代表已验证或许可可采集。
- 抓取运行与逐来源观察使用追加式 JSONL 日志，能够派生最近一次成功观察。
- 空抓取会中止合并和渲染，既有有效数据及页面不会被空结果覆盖。
- 附件全局默认关闭；只有全局开关开启且来源策略允许自动下载，或明确用户操作符合来源策略时，旧下载能力才可运行。
- Web 默认绑定 `127.0.0.1:5000`；HTTP 抓取触发始终要求配置并提交匹配令牌，未配置令牌时返回 403，本机手动抓取使用 CLI。
- Phase 1、来源探测与 S/A 对照的完整离线测试已通过：47/47。
- 网络探测候选池已由 28 项扩为 152 项，全部仍是未激活候选。
- S=7、A=11 的严格 18 源双节点对照已完成一次：GitHub 节点 9 success / 9 failure，ECS 节点 18 failure；派生分类为 `fallback_reachable=9`、`policy_or_access_review=8`、`both_failed=1`。这只是网络证据，不构成采集授权；证据、哈希与保留边界见 [`GlobalNews/docs/operations/sa-source-assurance.md`](GlobalNews/docs/operations/sa-source-assurance.md)。

## 权威路径

- 旧阅读器的唯一权威数据文件仍为 `GlobalNews/news_data.json`，Phase 1 不迁移、不重写现有用户数据。
- `GlobalNews/data/` 和 `GlobalNews/config/config.json` 是历史/部署副本，不是运行时数据或配置权威来源。
- 来源策略权威文件为 `GlobalNews/config/source_policies.json`。
- 新运行日志默认写入 `GlobalNews/state/crawl-runs.jsonl`；这是运行时产物，不替代内容数据。

## 尚未完成

- 公网 DNS 恢复后，2026-09-13 使用新 timestamp 目录重测 28 项：DNS 28/28 成功，最终成功 16、失败 12；其中 11 个结构化响应为 `ecs_candidate_pending_policy`，5 个 HTML 来源需人工适配，3 个出现 HTTP 拒绝/参数错误，9 个在连接或 TLS 阶段失败。证据见 `GlobalNews/docs/operations/ecs-source-probe-2026-09-13-dns-restored-analysis.md`。
- 历史 9-source 诊断 workflow 未单独执行；当前 S/A 门已有严格 18 源双节点对照证据。9-source 历史诊断集合与 18 源 S/A 集合不得混用，也不能以当前结果倒推历史 workflow 已执行。
- 许可、允许字段、速率和复核日期的逐来源核验。
- `raw_item`、`canonical_work`、版本关系与稳定标识分层去重。
- 科研主题驱动的默认界面、AI 公司实际进展附属栏目和世界背景附属栏目。
- Radar → Workbench `export_bundle/v1`。
- 统一 `Source Adapter + Event Schema`：适配器能力声明、统一事件类型、版本化证据字段、旧 RSS 兼容映射和回放测试。
- PDF 的 MIME、魔数、流式大小、哈希与文件冲突完整安全链；Phase 1 仅完成默认关闭和策略门控。

## 当前风险

- 公网 DNS 已恢复，但部分来源仍存在地址族/路由、TLS 超时、连接重置、HTTP 拒绝或缺少参数。一次双节点对照不证明长期稳定；在持续性验证、许可、速率和数据边界决策完成前，不把候选源标为已验证或直接启用。
- 旧静态页面和历史数据仍保留原有三栏目结构，不能被视为目标科研 Radar 已完成。
- 全部旧源默认禁用，因此在来源核验和人工启用前，定时抓取会安全失败并保留旧内容。
- `源列表.txt` 已纳入候选库存整理，但不等于运行时启用；新来源必须等待统一 Adapter/Event 接口和逐来源 Source Policy 审核。
- 旧 `tests/test_cleanup.py` 会在导入时替换标准输出，并包含过期结构断言；它不属于可靠的 pytest 离线测试集。
