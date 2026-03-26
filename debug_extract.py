"""
诊断脚本：逐步展示"抓 HTML → 提取邮箱"的完整过程。
用法：
    python debug_extract.py https://example.com
"""

import re
import sys
import html as html_module
import json
from pathlib import Path

# 强制 stdout 使用 UTF-8，避免 Windows GBK 编码报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from bs4 import BeautifulSoup

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 明确的非联系类服务域名
SERVICE_DOMAINS = {
    "sentry.io", "amazonaws.com", "cloudfront.net", "fastly.net",
    "sendgrid.net", "mailchimp.com", "mailgun.org", "google.com",
    "googlemail.com", "facebook.com", "twitter.com",
    "w3.org", "schema.org", "example.com",
}
NOREPLY_PREFIXES = {"noreply", "no-reply", "donotreply", "do-not-reply", "bounce", "postmaster"}
_HEX_HASH_RE = re.compile(r"^[0-9a-f]{16,}$")


def is_junk(email: str) -> bool:
    local, _, domain = email.partition("@")
    if any(domain == sd or domain.endswith("." + sd) for sd in SERVICE_DOMAINS):
        return True
    if local in NOREPLY_PREFIXES:
        return True
    if _HEX_HASH_RE.match(local) or len(local) > 40:
        return True
    return False


def step1_fetch(url: str) -> str | None:
    print(f"\n{'='*60}")
    print(f"[步骤 1] 抓取 HTML: {url}")
    print("="*60)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  状态码: {resp.status_code}")
        print(f"  内容长度: {len(resp.content)} 字节")
        if resp.status_code != 200:
            print("  ⚠ 非 200，可能被拦截或页面不存在")
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        out = Path("debug_html.html")
        out.write_text(html, encoding="utf-8")
        print(f"  已保存完整 HTML → {out.resolve()}")
        print(f"\n  HTML 前 300 字符预览:\n{'-'*40}")
        print(html[:300])
        print(f"{'-'*40}")
        return html
    except Exception as e:
        print(f"  ✗ 请求失败: {e}")
        return None


def step2_raw_regex(html: str) -> set[str]:
    print(f"\n{'='*60}")
    print("[步骤 2] 正则扫描原始 HTML 文本（含 JS / inline JSON）")
    print("="*60)
    found = set(m.lower() for m in EMAIL_REGEX.findall(html))
    valid = {e for e in found if not is_junk(e)}
    print(f"  原始找到 {len(found)} 个，过滤垃圾后剩 {len(valid)} 个: {valid or '（无）'}")
    return valid


def step3_mailto(html: str) -> set[str]:
    print(f"\n{'='*60}")
    print("[步骤 3] 提取 <a href='mailto:...'> 链接")
    print("="*60)
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip().lower()
            if EMAIL_REGEX.fullmatch(addr) and not is_junk(addr):
                print(f"  ✓ mailto: {addr}")
                found.add(addr)
    if not found:
        print("  （未找到有效 mailto 链接）")
    return found


def step4_jsonld(html: str) -> tuple[set[str], str | None]:
    """
    Returns (all_emails_from_jsonld, best_official_email).
    Walks the JSON-LD tree and picks values of "email" keys as the
    most authoritative contact emails.
    """
    print(f"\n{'='*60}")
    print("[步骤 4] 解析 JSON-LD 结构化数据 → 确定官方邮箱")
    print("="*60)

    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/ld+json")
    print(f"  共找到 {len(scripts)} 个 JSON-LD 块")

    official_candidates: list[str] = []   # from "email" fields — highest trust
    all_jsonld_emails: set[str] = set()

    collected: list[tuple[str, str, bool]] = []  # (addr, path, is_official)

    def _walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "email" and isinstance(v, str):
                    addr = v.strip().lower()
                    if EMAIL_REGEX.fullmatch(addr):
                        official = not is_junk(addr)
                        collected.append((addr, f"{path}.{k}", official))
                        all_jsonld_emails.add(addr)
                        if official:
                            official_candidates.append(addr)
                else:
                    _walk(v, path=f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, path=f"{path}[{i}]")

    for i, script in enumerate(scripts):
        raw = script.string or ""
        print(f"\n  --- JSON-LD [{i+1}] ---")
        try:
            data = json.loads(raw)
        except Exception as e:
            print(f"  JSON 解析失败: {e}")
            continue
        _walk(data, path=f"[{i+1}]")

    for addr, path, official in collected:
        tag = "[官方候选]" if official else "[垃圾,跳过]"
        print(f"    {tag} \"email\": \"{addr}\"  (路径: {path})")

    best = official_candidates[0] if official_candidates else None
    print(f"\n  → JSON-LD 官方邮箱候选: {official_candidates or '（无）'}")
    if best:
        print(f"  → 最优官方邮箱: ★ {best}")

    return all_jsonld_emails, best


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else input("请输入网址: ").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    html = step1_fetch(url)
    if not html:
        print("\n✗ 无法获取 HTML，终止。")
        return

    emails_regex  = step2_raw_regex(html)
    emails_mailto = step3_mailto(html)
    emails_jsonld, official_from_jsonld = step4_jsonld(html)

    all_emails = (emails_regex | emails_mailto | emails_jsonld) - {e for e in (emails_regex | emails_mailto | emails_jsonld) if is_junk(e)}

    print(f"\n{'='*60}")
    print("【汇总】所有有效邮箱")
    print("="*60)
    if all_emails:
        for e in sorted(all_emails):
            tag = "★ 官方" if e == official_from_jsonld else "  "
            print(f"  {tag}  {e}")
    else:
        print("  ✗ 未找到任何邮箱")
        print()
        print("  可能原因：")
        print("  1. 网站用 JS 动态渲染 (React/Vue)，requests 只能拿到空壳 HTML")
        print("  2. 邮箱以图片形式展示")
        print("  3. 邮箱藏在 JS 字符串拼接中")
        print("  → 请打开 debug_html.html，搜索 '@' 确认 HTML 里是否真的有邮箱")

    if official_from_jsonld:
        print(f"\n  最终官方邮箱（JSON-LD 声明）: ★ {official_from_jsonld}")
    elif all_emails:
        print(f"\n  未找到 JSON-LD 声明，所有邮箱供参考: {sorted(all_emails)}")


if __name__ == "__main__":
    main()
