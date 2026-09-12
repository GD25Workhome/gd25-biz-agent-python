-- MySQL DDL for Company News Crawl
-- 用于未来接入生产数据库

-- 站点配置档案表
CREATE TABLE IF NOT EXISTS site_profile (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    company_name VARCHAR(200) NOT NULL COMMENT '公司名称',
    list_url VARCHAR(500) NOT NULL COMMENT '新闻列表页 URL',
    site_type VARCHAR(50) DEFAULT 'unknown' COMMENT '站点类型: static|cms|spa|api|blocked|unknown',
    last_http_status INT DEFAULT NULL COMMENT '最后一次 HTTP 状态码',
    last_article_link_count INT DEFAULT 0 COMMENT '最后一次提取的文章链接数',
    last_success_at DATETIME DEFAULT NULL COMMENT '最后成功时间',
    fail_streak INT DEFAULT 0 COMMENT '连续失败次数',
    notes TEXT COMMENT '备注',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_stock_list_url (stock_code, list_url),
    INDEX idx_company_name (company_name),
    INDEX idx_site_type (site_type),
    INDEX idx_last_success (last_success_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公司新闻站点配置档案';

-- 公司新闻文档表
CREATE TABLE IF NOT EXISTS company_news_document (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    company_name VARCHAR(200) NOT NULL COMMENT '公司名称',
    source_level VARCHAR(50) NOT NULL COMMENT '来源级别: P0_official_site',
    list_url VARCHAR(500) NOT NULL COMMENT '新闻列表页 URL',
    article_url VARCHAR(500) NOT NULL COMMENT '文章 URL',
    url_norm VARCHAR(500) NOT NULL COMMENT '规范化后的 URL',
    title VARCHAR(500) NOT NULL COMMENT '文章标题',
    published_at DATE DEFAULT NULL COMMENT '发布日期',
    fetched_at DATETIME NOT NULL COMMENT '抓取时间',
    content_text LONGTEXT COMMENT '正文内容',
    content_hash CHAR(64) NOT NULL COMMENT '内容 SHA256 哈希',
    summary VARCHAR(500) COMMENT '摘要（≤200字）',
    http_status INT NOT NULL COMMENT 'HTTP 状态码',
    fetch_method VARCHAR(50) NOT NULL COMMENT '抓取方法: http|browser',
    template_id VARCHAR(100) COMMENT '模板 ID / 站点类型识别标识',
    site_type VARCHAR(50) NOT NULL COMMENT '站点类型',
    parse_version VARCHAR(50) NOT NULL COMMENT '解析版本',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_content_hash (content_hash),
    UNIQUE KEY uk_url_norm (url_norm),
    INDEX idx_stock_code (stock_code),
    INDEX idx_company_name (company_name),
    INDEX idx_source_level (source_level),
    INDEX idx_published_at (published_at),
    INDEX idx_fetched_at (fetched_at),
    FULLTEXT INDEX ft_title_content (title, content_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股上市公司官网新闻文档';
