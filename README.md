# JAV Expert — MediaMatrix Plugin

[MediaMatrix](https://github.com/aidenplus/MediaMatrix) 的 AV 影片元数据刮削插件。

自动从文件名识别番号，抓取 JavDB 的标题、封面、演员、评分等元数据，可选叠加 DMM 官方数据增强。

---

## 功能

- **番号自动识别**：从文件名提取番号，支持有连字符（`SSIS-001`）、无连字符（`IPX726`）、FC2（`FC2-PPV-1234567`）等格式，识别失败时安静退出，不影响普通电影的 TMDB 刮削
- **JavDB 数据源**（必选）：标题、原标题、封面图、发行日期、时长、导演、片商、系列、类别、演员、社区评分
- **DMM 数据源**（可选）：日文官方标题、高清封面、fanart，字段级叠加到 JavDB 结果之上
- **防封策略**：User-Agent 轮换、请求间隔限速、自动重试、curl_cffi 绕过 Cloudflare

---

## 网络要求

| 数据源 | 访问限制 | 建议 |
|--------|----------|------|
| JavDB (`javdb.com`) | 中国大陆无法访问 | 需要代理或非大陆 IP |
| DMM (`dmm.co.jp`) | 仅限日本 IP | 需要日本代理，否则返回 403 |

**运行环境建议**：部署在香港、台湾、日本等地区的服务器，或本地配置全局代理。

> DMM 数据源默认关闭（`enabled: false`），不需要日本 IP 时无需配置。

---

## 安装

```bash
# 进入 MediaMatrix 插件目录
cd <MediaMatrix 根目录>/plugins

# 克隆本插件
git clone https://github.com/prettygoods/mediamatrix-jav-expert.git jav_expert

# 安装依赖
cd jav_expert && bash install.sh
```

---

## 配置

在 MediaMatrix 的 `config/settings.yaml` 中添加 `jav_expert` 节点：

```yaml
plugins:
  jav_expert:
    sources:
      javdb:
        base_url: "https://javdb.com"
        delay: 2.0          # 请求间隔（秒），建议不低于 1.5
        max_retries: 3

      dmm:
        enabled: false      # 需要日本 IP 时改为 true
        delay: 3.0
```

所有配置项均有默认值，最简情况下不需要写任何配置，插件开箱即用（JavDB 模式）。

---

## 支持的番号格式

| 格式 | 示例 | 说明 |
|------|------|------|
| 标准格式 | `SSIS-001`、`STARS-500`、`FC2-PPV-1234567` | 首选 |
| 带路径 | `/media/jav/SSIS-001.mkv` | 自动提取文件名部分 |
| 带标签 | `[SSIS-001] 标题 [1080p].mkv` | 方括号/圆括号/书名号均支持 |
| 无连字符 | `IPX726`、`bbsxv.xyz-IPX726` | 自动补全为 `IPX-726` |
| 带后缀 | `SSIS-001-C`、`SSIS-001-uncensored-HD` | 自动去除后缀噪音 |
| 下划线分隔 | `SSIS-001_1080p.mkv` | 下划线视为分隔符 |

普通电影（`Inception 2010.mkv`）和剧集（`S01E01.mkv`）不会被误识别。

---

## 数据来源说明

- **JavDB**：社区运营的 AV 数据库，数据覆盖面广，包含社区评分和演员信息，是本插件的核心数据源
- **DMM**：日本最大的成人内容平台，提供官方日文标题和高清封面，可作为可选增强层

---

## 许可协议

MIT License
