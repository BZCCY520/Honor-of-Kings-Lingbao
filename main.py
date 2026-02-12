# ===== 小马糕 · 零延迟 · Bark + ntfy 双通道推送 =====
# pip install requests

import requests
import time
import re
import hashlib
from urllib.parse import quote


# ==========================================
#           推送通道实现
# ==========================================

class PushChannel:
    """推送通道基类"""
    name = "未知"

    def __init__(self, enabled=False):
        self.enabled = enabled

    def send(self, title, body, code=None):
        raise NotImplementedError

    def status(self):
        return "✅ 已配置" if self.enabled else "⬜ 未配置"


class BarkChannel(PushChannel):
    """
    Bark 推送（仅iOS）
    App Store 搜索 "Bark" → 打开APP → 复制Key
    """
    name = "Bark(iOS)"

    def __init__(self, key=""):
        self.key = key
        super().__init__(enabled=bool(key))

    def send(self, title, body, code=None):
        if not self.key:
            return False
        try:
            copy = code or body
            url = (
                f"https://api.day.app/"
                f"{self.key}"
                f"/{quote(title)}"
                f"/{quote(body[:200])}"
                f"?sound=multiwayinvitation"
                f"&level=timeSensitive"
                f"&copy={quote(copy)}"
                f"&autoCopy=1"
                f"&isArchive=1"
                f"&group=灵宝集市"
            )
            r = requests.get(url, timeout=5)
            return r.json().get("code") == 200
        except Exception as e:
            print(f"    Bark错误: {e}")
            return False


class NtfyChannel(PushChannel):
    """
    ntfy 推送（安卓/iOS/Web 均可）
    安卓APK下载:
      github.com/binwiederhier/ntfy/releases
    打开APP → 点"+" → 填主题名 → Subscribe
    """
    name = "ntfy(安卓)"

    def __init__(self, topic="", server="https://ntfy.sh"):
        self.topic = topic
        self.server = server.rstrip("/")
        super().__init__(enabled=bool(topic))

    def send(self, title, body, code=None):
        if not self.topic:
            return False
        try:
            headers = {
                "Title": title.encode("utf-8"),
                "Priority": "5",
                "Tags": "fire,moneybag",
            }
            if code:
                headers["Click"] = (
                    f"clipboard:{code}"
                )
                headers["Actions"] = (
                    f"view, 📋复制兑换码, "
                    f"clipboard:{code}, clear=true"
                )
            resp = requests.post(
                f"{self.server}/{self.topic}",
                data=body.encode("utf-8"),
                headers=headers,
                timeout=5
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"    ntfy错误: {e}")
            return False


# ==========================================
#           推送管理器
# ==========================================

class PushManager:
    """统一管理推送通道"""

    def __init__(self):
        self.channels = []

    def add(self, channel):
        self.channels.append(channel)
        return self

    def push_all(self, title, body, code=None):
        active = [
            ch for ch in self.channels if ch.enabled
        ]
        if not active:
            print("  ⚠️ 无可用推送通道！")
            return []

        results = []
        for ch in active:
            ok = ch.send(title, body, code)
            tag = "✅" if ok else "❌"
            print(f"  📱 {ch.name}: {tag}")
            results.append((ch.name, ok))
        return results

    def print_status(self):
        print("📱 推送通道:")
        active = 0
        for ch in self.channels:
            print(f"   {ch.name}: {ch.status()}")
            if ch.enabled:
                active += 1
        if active == 0:
            print("\n  ⚠️  未配置任何推送通道！")
            print("  请至少配置一个通道")
        else:
            print(f"\n   共 {active} 个通道已激活")


# ==========================================
#           兑换码猎手
# ==========================================

class CodeHunter:
    """
    零延迟策略：
    - 发现新码 → 立即推送
    - 同一个码 → 只推一次（防刷屏）
    - 轮询间隔 1秒（极速）
    """

    def __init__(self):
        self.api_url = ""            #请配置URL
        self.seen_md5 = set()
        self.pushed_codes = set()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; "
                "Win64; x64) Chrome/131.0.0.0"
            )
        }
        self.price_min = 800
        self.price_max = 899
        self.keywords = ["小马糕", "马糕"]
        self.pusher = PushManager()

    # ========== 数据获取 ==========

    def fetch_data(self):
        try:
            resp = requests.get(
                self.api_url,
                timeout=3,
                headers=self.headers
            )
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return (
                    data.get("posts")
                    or data.get("data")
                    or data.get("list")
                    or []
                )
        except:
            pass
        return []

    # ========== 解析 ==========

    def extract_price(self, text):
        patterns = [
            r'(\d{2,5})\s*[块元r]',
            r'[¥￥]\s*(\d{2,5})',
            r'价[格钱：:]\s*(\d{2,5})',
            r'(\d{3,5})\s*(?:出|卖)',
            r'(?:出|卖)\s*(\d{3,5})',
            r'(\d{3,5})',
        ]
        prices = []
        for p in patterns:
            for m in re.findall(
                p, text, re.IGNORECASE
            ):
                v = int(m)
                if 50 <= v <= 9999:
                    prices.append(v)
        return max(prices) if prices else 0

    def extract_code(self, text):
        patterns = [
            r'(?:码|code|兑换码)[：:\s]*'
            r'([A-Za-z0-9]{6,25})',
            r'([A-Za-z0-9]{8,25})',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def is_target(self, text):
        t = text.lower()
        return any(
            kw.lower() in t for kw in self.keywords
        )

    # ========== 主循环 ==========

    def run(self, interval=1):
        print()
        print("=" * 50)
        print("🚀 小马糕 · 零延迟 · 发现即推")
        print("=" * 50)
        print(f"📡 数据源: {self.api_url}")
        print(f"⏱️  轮询: {interval}秒")
        print(
            f"💰 价格: "
            f"{self.price_min}-{self.price_max}元"
        )
        print(
            f"🔍 关键词: "
            f"{', '.join(self.keywords)}"
        )
        print()
        self.pusher.print_status()
        print()
        print("-" * 50)
        print("💡 同一个码只推1次（防刷屏）")
        print("💡 按 Ctrl+C 停止")
        print("-" * 50)
        print()

        # 标记历史（避免启动时推旧消息）
        initial = self.fetch_data()
        for post in initial:
            text = (
                post.get("text")
                or post.get("content")
                or str(post)
            )
            md5 = hashlib.md5(
                text.encode()
            ).hexdigest()
            self.seen_md5.add(md5)
        print(
            f"✅ 已标记 {len(self.seen_md5)} "
            f"条历史消息"
        )
        print("✅ 开始监控...\n")

        n = 0
        err_count = 0

        while True:
            try:
                n += 1
                posts = self.fetch_data()

                if not posts and n > 1:
                    err_count += 1
                    if err_count >= 10:
                        print(
                            f"\n  ⚠️ 连续{err_count}"
                            f"次获取失败"
                        )
                        err_count = 0
                else:
                    err_count = 0

                for post in posts:
                    text = (
                        post.get("text")
                        or post.get("content")
                        or str(post)
                    )
                    md5 = hashlib.md5(
                        text.encode()
                    ).hexdigest()

                    if md5 in self.seen_md5:
                        continue
                    self.seen_md5.add(md5)

                    t = time.strftime("%H:%M:%S")

                    # 非目标
                    if not self.is_target(text):
                        print(
                            f"  💬 [{t}] "
                            f"{text[:40]}"
                        )
                        continue

                    price = self.extract_price(text)
                    code = self.extract_code(text)

                    # 价格不在范围
                    if not (
                        self.price_min
                        <= price
                        <= self.price_max
                    ):
                        if price > 0:
                            print(
                                f"  ⚠️ [{t}] "
                                f"小马糕 {price}元"
                                f" 不在范围"
                            )
                        else:
                            print(
                                f"  ⚠️ [{t}] "
                                f"小马糕 未识别价格"
                            )
                        continue

                    # 码去重
                    if code and code in self.pushed_codes:
                        print(
                            f"  ♻️ [{t}] "
                            f"{code} 已推过"
                        )
                        continue

                    # ===== 命中！立即推！=====
                    print()
                    print("🔥" * 20)
                    print(
                        f"  🎯 [{t}] "
                        f"小马糕 {price}元！"
                    )
                    print(f"  📝 {text[:150]}")
                    if code:
                        print(f"  🔑 兑换码: {code}")
                    print("🔥" * 20)

                    # 响铃
                    try:
                        import winsound
                        for _ in range(3):
                            winsound.Beep(1500, 300)
                            time.sleep(0.1)
                    except:
                        print("\a\a\a")

                    # ★ 推送 ★
                    push_body = text[:200]
                    if code:
                        push_body += (
                            f"\n兑换码: {code}"
                        )

                    self.pusher.push_all(
                        f"🔥小马糕 {price}元！",
                        push_body,
                        code=code
                    )
                    print()

                    if code:
                        self.pushed_codes.add(code)

                # 状态行
                t = time.strftime("%H:%M:%S")
                print(
                    f"\r  ⏳ [{t}] "
                    f"第{n}轮 | "
                    f"已推{len(self.pushed_codes)}码 | "
                    f"已处理{len(self.seen_md5)}条",
                    end="", flush=True
                )

            except KeyboardInterrupt:
                print("\n")
                print("=" * 50)
                print("👋 已停止监控")
                print(
                    f"📊 本次共推送 "
                    f"{len(self.pushed_codes)} 个兑换码"
                )
                print("=" * 50)
                break
            except Exception as e:
                print(f"\n  ❌ 异常: {e}")

            time.sleep(interval)


# ==========================================
#
#        ★★★ 用户配置区 ★★★
#
#   Bark 和 ntfy 按需填写
#   不用的通道 key/topic 留空即可
#   至少配置一个才能收到推送
#
# ==========================================

hunter = CodeHunter()

# ---------- 价格区间 ----------
hunter.price_min = 800
hunter.price_max = 899

# ---------- 关键词 ----------
hunter.keywords = ["小马糕", "马糕"]

# ==========================================
#   ★ Bark（仅iOS）
#   App Store 搜 "Bark" → 打开APP → 复制Key
# ==========================================
hunter.pusher.add(BarkChannel(
    key="",    # ← 你的Bark Key
))

# ==========================================
#   ★ ntfy（安卓推荐）
#
#   第一步: 手机下载 ntfy APP
#     github.com/binwiederhier/ntfy/releases
#     下载最新的 ntfy-v2.x.x.apk 安装
#
#   第二步: 打开APP → 点右下角"+"
#     Topic name 填一个独特的名字
#     例如: xiaomago_myname_6789
#     点 Subscribe
#
#   第三步: 把主题名填到下面 topic 里
#
#   第四步: 手机设置
#     通知权限 → 全部打开
#     电池优化 → ntfy → 不限制
# ==========================================
hunter.pusher.add(NtfyChannel(
    topic="",                          # ← 填你的ntfy主题名
    server="https://ntfy.sh",          # 默认不用改
))


# ==========================================
#              启动！
# ==========================================
hunter.run(interval=1)