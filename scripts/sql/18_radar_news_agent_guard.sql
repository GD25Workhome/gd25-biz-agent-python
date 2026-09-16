-- 新闻 Agent 兜底闸门按日计数（设计：ai_docs/26091605-Agent兜底闸门改造设计.md）
-- 归属：exhibition MySQL；本仓仅提供草稿，由 exhibition SQL 脚本正式落地。
-- 上线顺序：先执行本 DDL，再发布 news_content_worker。

CREATE TABLE IF NOT EXISTS radar_news_agent_guard (
  id                    BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  guard_scope           TINYINT      NOT NULL COMMENT '0=GLOBAL 1=SOURCE',
  source_url_id         BIGINT       NOT NULL DEFAULT 0 COMMENT 'GLOBAL固定0；SOURCE=信息源id(>0)',
  stat_date             DATE         NOT NULL COMMENT '统计日',
  agent_used            INT          NOT NULL DEFAULT 0 COMMENT '当日已发起Agent次数(GLOBAL)',
  system_fail_streak    INT          NOT NULL DEFAULT 0 COMMENT '连续系统失败(GLOBAL)',
  system_tripped        TINYINT      NOT NULL DEFAULT 0 COMMENT '系统熔断0/1(GLOBAL)',
  content_fail_streak   INT          NOT NULL DEFAULT 0 COMMENT '连续内容失败(SOURCE，仅HTTP200空正文等)',
  content_skipped       TINYINT      NOT NULL DEFAULT 0 COMMENT '跳过该源Agent 0/1(SOURCE)',
  version               INT          NOT NULL DEFAULT 0 COMMENT '乐观锁版本',
  creator               VARCHAR(64)  NULL,
  updater               VARCHAR(64)  NULL,
  create_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted               BIT(1)       NOT NULL DEFAULT b'0',
  PRIMARY KEY (id),
  UNIQUE KEY uk_guard_day (guard_scope, source_url_id, stat_date, deleted),
  KEY idx_stat_date (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻Agent兜底闸门按日计数';
