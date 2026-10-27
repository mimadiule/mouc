# Windows 安装与使用

这是 [`mimadiule/mouc`](https://github.com/mimadiule/mouc) 的 Windows 构建说明。  
上游项目是 [`rnortman/mouc`](https://github.com/rnortman/mouc)，MIT License。

## 其他人可以直接用吗？

可以，但建议用本仓库 **Releases** 里的 Windows wheel，不要直接 `pip install git+https://github.com/mimadiule/mouc.git`。

原因：

- 上游 PyPI 目前只有 manylinux wheel，没有 Windows wheel；
- 直接源码安装会触发 Rust/maturin 编译，需要 Rust、MSVC Build Tools 和 Windows SDK；
- 本仓库用 GitHub Actions 的 `windows-latest` 预先编译好 wheel，普通用户只需要 `pip install`。

## 下载 wheel

打开：

```text
https://github.com/mimadiule/mouc/releases
```

选择与你的 Python 版本匹配的文件：

| Python | wheel |
|---|---|
| 3.10 | `mouc-0.8.0-cp310-cp310-win_amd64.whl` |
| 3.11 | `mouc-0.8.0-cp311-cp311-win_amd64.whl` |
| 3.12 | `mouc-0.8.0-cp312-cp312-win_amd64.whl` |
| 3.13 | `mouc-0.8.0-cp313-cp313-win_amd64.whl` |

先确认本机 Python 版本：

```powershell
py -0p
```

## 安装

以 Python 3.11 为例：

```powershell
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install .\mouc-0.8.0-cp311-cp311-win_amd64.whl
mouc --help
```

如果使用 `uv`：

```powershell
uv tool install --python 3.11 .\mouc-0.8.0-cp311-cp311-win_amd64.whl
```

## 快速验证

```powershell
@"
metadata:
  version: 1.0
entities:
  design:
    type: capability
    name: Design
    description: Design phase
    meta:
      effort: "2w"
      start_date: "2025-01-01"
      end_date: "2025-01-14"
  build:
    type: capability
    name: Build
    description: Build phase
    requires: [design]
    meta:
      effort: "2w"
      start_date: "2025-01-15"
      end_date: "2025-01-28"
"@ | Set-Content -Encoding UTF8 demo.yaml

mouc gantt demo.yaml --start-date 2025-01-01 --current-date 2025-01-01 --output demo.md
Get-Content demo.md
```

应该看到一段 Mermaid `gantt` 图。

## 自己编译

本仓库的 workflow：

```text
.github/workflows/windows-wheels.yml
```

触发方式：

1. 打开仓库的 **Actions** 页面；
2. 选择 **Build Windows wheels**；
3. 点击 **Run workflow**；
4. 运行结束后在该 run 的 **Artifacts** 下载 `windows-wheel-cp3xx`。

本地编译需要：

- Rust stable
- Visual Studio Build Tools（C++ 桌面开发）
- Windows SDK
- Python 3.10–3.13
- `maturin`

然后：

```powershell
py -3.11 -m pip install maturin
maturin build --release --out dist -i python
```

## 限制

- 这是上游 `0.8.0` 的 Windows 构建分支，不保证永远跟上游同步；需要新版本时先 **Sync fork**。
- 只提供 Python 3.10–3.13 的 Windows x64 wheel；Python 3.14 暂无。
- `mouc` 仍是 alpha 软件；关键计划请保留原始 PPT/Excel 或 Git 版本。
- 本仓库保留上游 MIT License；再分发时请保留 `LICENSE`。
- 本仓库不是 think-cell 的替代品，也不包含任何 think-cell 代码或模板。

## 相关文件

- 上游 README：`README.md`
- 构建 workflow：`.github/workflows/windows-wheels.yml`
- License：`LICENSE`
