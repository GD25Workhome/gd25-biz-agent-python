# 翻页验证报告

## 方法

- A：`--max-pages 1 --max-articles 100`
- B：`--max-pages 4 --max-articles 100`
- 判定：仅 B 有、A 无的 `article_url` 视为翻页增量

## 汇总表

| 代码 | 公司 | A篇数 | B篇数 | 交集 | 仅B新增 | 翻页是否生效 |
|---|---|---:|---:|---:|---:|---|
| 000001 | 平安银行 | 98 | 98 | 98 | 0 | 否 |
| 600486 | 扬农化工 | 91 | 91 | 91 | 0 | 否 |
| 920139 | 华岭股份 | 39 | 64 | 39 | 25 | 是 |
| 000955 | 欣龙控股 | 70 | 70 | 70 | 0 | 否 |
| 300582 | 英飞特 | 0 | 0 | 0 | 0 | 否 |
| 920478 | 峆一药业 | 48 | 48 | 48 | 0 | 否 |

**翻页生效公司数：1/6**

## 平安银行补充核对

- 列表第1页 HTTP 200，新闻链 25
- `index_2.shtml` HTTP 200，新闻链 25
- 第2页相对第1页新增链：25
- A 抓取命中第1页链：25 / 25
- B 抓取命中第2页链：0 / 25
- B 中来自第2页、且不在第1页的链：0

### 各家仅 B 新增 URL 示例

#### 平安银行（仅B=0）
- （无）

#### 扬农化工（仅B=0）
- （无）

#### 华岭股份（仅B=25）
- https://www.sinoictest.com.cn:443/news/class/index.php?1.html&page=1&showtj=0&showhot=0&author=&key=
- https://www.sinoictest.com.cn:443/news/html/?15.html
- https://www.sinoictest.com.cn:443/news/html/?16.html
- https://www.sinoictest.com.cn:443/news/html/?17.html
- https://www.sinoictest.com.cn:443/news/html/?18.html

#### 欣龙控股（仅B=0）
- （无）

#### 英飞特（仅B=0）
- （无）

#### 峆一药业（仅B=0）
- （无）
