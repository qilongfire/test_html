#!/usr/bin/env python3
"""
duan.ayaseeri.com 本地离线镜像工具

仅限个人离线阅读使用：
- 请勿将镜像副本公开部署到任何服务器
- 请勿通过网盘、仓库等方式分享给他人
- 镜像包含的问答内容版权归原权利方所有

用法：
    python3 mirror_duan.py              # 增量镜像（已下载的文件自动跳过）
    python3 mirror_duan.py --force      # 忽略本地缓存，全量重新下载
    python3 mirror_duan.py --limit 5    # 只抓前 5 个页面（测试用）
    python3 mirror_duan.py --serve      # 在本机 127.0.0.1 启动阅读服务
    python3 mirror_duan.py --delay 2.0  # 自定义请求间隔（秒）

仅依赖 Python 3.8+ 标准库，无需安装任何第三方包。
"""

import argparse
import posixpath
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITE = "https://duan.ayaseeri.com"
OUT = Path(__file__).resolve().parent / "duan-mirror"
UA = "Mozilla/5.0 (compatible; PersonalOfflineReader/1.0)"

# 视为静态资源的扩展名（无扩展名的路径是页面路由，由 sitemap 负责）
ASSET_EXT = {
    ".js", ".css", ".json", ".woff", ".woff2", ".ttf", ".otf",
    ".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".ico", ".gif",
}

# 从 HTML 中提取 href="/..." 或 src="/..." 引用
REF_RE = re.compile(r'(?:href|src)="(/[^"]+)"')
# 从 CSS 中提取 url(...) 引用（字体等）
CSS_URL_RE = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''')

failed = []


def fetch(url: str, tries: int = 2) -> bytes:
    """带重试的 HTTP GET"""
    last_err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if i < tries - 1:
                time.sleep(2)
    raise RuntimeError(f"下载失败 {url}: {last_err}")


def sitemap_pages() -> list:
    """从 sitemap.xml 取全部页面 URL"""
    data = fetch(f"{SITE}/sitemap.xml")
    root = ET.fromstring(data)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages = [el.text.strip() for el in root.findall(".//s:loc", ns)]
    return pages


def page_local_file(page_path: str) -> Path:
    """/benfen -> duan-mirror/benfen/index.html；/ -> duan-mirror/index.html"""
    p = page_path.rstrip("/") or "/"
    if p == "/":
        return OUT / "index.html"
    return OUT / p.lstrip("/") / "index.html"


def extract_asset_refs(html: bytes) -> set:
    """从 HTML 提取本站静态资源路径（去掉查询串和锚点）"""
    refs = set()
    text = html.decode("utf-8", "ignore")
    for m in REF_RE.finditer(text):
        url = m.group(1).split("?", 1)[0].split("#", 1)[0]
        if url.endswith("/"):
            continue
        ext = posixpath.splitext(url)[1].lower()
        if ext in ASSET_EXT:
            refs.add(url)
    return refs


def extract_css_refs(css_text: str, css_path: str) -> set:
    """从 CSS 内容提取 url() 引用，返回本站绝对路径"""
    refs = set()
    css_dir = posixpath.dirname(css_path)  # 如 "/_nuxt"
    for m in CSS_URL_RE.finditer(css_text):
        u = m.group(1).split("?", 1)[0]
        if not u or u.startswith("data:"):
            continue
        if u.startswith("/"):
            absu = u
        elif u.startswith("http"):
            continue  # 外链资源，跳过
        else:
            # 相对路径，基于 CSS 所在目录解析
            absu = "/" + posixpath.normpath(posixpath.join(css_dir.lstrip("/"), u))
        ext = posixpath.splitext(absu)[1].lower()
        if ext in ASSET_EXT:
            refs.add(absu)
    return refs


def mirror(args):
    delay = args.delay
    pages = sitemap_pages()
    if args.limit:
        pages = pages[: args.limit]
    print(f"共 {len(pages)} 个页面，输出目录：{OUT}\n")

    # ---------- 第一步：下载页面 HTML，并收集静态资源引用 ----------
    asset_refs = set()
    for i, page_url in enumerate(pages, 1):
        page_path = page_url[len(SITE):] or "/"
        html_file = page_local_file(page_path)

        if html_file.exists() and html_file.stat().st_size > 0 and not args.force:
            html = html_file.read_bytes()
            print(f"[{i}/{len(pages)}] 跳过（已存在） {page_path}")
        else:
            try:
                html = fetch(page_url)
                html_file.parent.mkdir(parents=True, exist_ok=True)
                html_file.write_bytes(html)
                print(f"[{i}/{len(pages)}] 已下载 {page_path}")
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(pages)}] 失败 {page_path}: {e}")
                failed.append(page_url)
                time.sleep(delay)
                continue
            time.sleep(delay)

        asset_refs |= extract_asset_refs(html)

    # ---------- 第二步：下载全部静态资源（含每页的 _payload.json） ----------
    print(f"\n共发现 {len(asset_refs)} 个静态资源，开始下载...\n")
    queue = sorted(asset_refs)
    done = set()
    for ref in queue:
        if ref in done:
            continue
        done.add(ref)
        f = OUT / ref.lstrip("/")
        if f.exists() and f.stat().st_size > 0 and not args.force:
            data = None
        else:
            try:
                data = fetch(SITE + ref)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
                print(f"[资源] 已下载 {ref}")
                time.sleep(delay)
            except Exception as e:  # noqa: BLE001
                print(f"[资源] 失败 {ref}: {e}")
                failed.append(SITE + ref)
                continue

        # CSS 里可能引用字体文件，解析并补抓
        if ref.endswith(".css"):
            css_text = (f.read_bytes()).decode("utf-8", "ignore")
            for extra in sorted(extract_css_refs(css_text, ref)):
                if extra in done:
                    continue
                done.add(extra)
                ef = OUT / extra.lstrip("/")
                if ef.exists() and ef.stat().st_size > 0 and not args.force:
                    continue
                try:
                    edata = fetch(SITE + extra)
                    ef.parent.mkdir(parents=True, exist_ok=True)
                    ef.write_bytes(edata)
                    print(f"[字体] 已下载 {extra}")
                    time.sleep(delay)
                except Exception as e:  # noqa: BLE001
                    print(f"[字体] 失败 {extra}: {e}")
                    failed.append(SITE + extra)

    # ---------- 汇总 ----------
    print("\n" + "=" * 50)
    if failed:
        print(f"完成，但有 {len(failed)} 项失败（重跑一次脚本可补抓）：")
        for u in failed:
            print(f"  - {u}")
    else:
        print("全部完成，镜像已就绪。")
    print(f"\n本地阅读：python3 {Path(__file__).name} --serve")
    print("然后浏览器打开 http://127.0.0.1:8765")


def serve():
    """在本机启动只读 HTTP 服务（仅绑定 127.0.0.1，外部无法访问）"""
    if not OUT.exists():
        raise SystemExit("镜像目录不存在，请先运行镜像下载。")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(OUT), **kw)

        def log_message(self, fmt, *a):  # 精简日志输出
            pass

    addr = ("127.0.0.1", 8765)
    print(f"本地阅读服务已启动：http://{addr[0]}:{addr[1]}")
    print("仅本机可访问，Ctrl+C 停止。\n")
    ThreadingHTTPServer(addr, Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description="duan.ayaseeri.com 本地离线镜像（仅限个人阅读）")
    ap.add_argument("--force", action="store_true", help="忽略本地缓存，全量重新下载")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 个页面（测试用）")
    ap.add_argument("--delay", type=float, default=1.5, help="请求间隔秒数（默认 1.5）")
    ap.add_argument("--serve", action="store_true", help="启动本地阅读服务")
    args = ap.parse_args()

    if args.serve:
        serve()
    else:
        mirror(args)


if __name__ == "__main__":
    main()
