# coding=utf-8
import re
import sys
import json
import time
import base64
from urllib.parse import quote, urljoin

sys.path.append("..")

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    def __init__(self):
        self.name = "JavBus"
        self.host = "https://www.dmmbus.bond"
        self.backend_parse = True
        self.hosts = [
            "https://www.dmmbus.bond",
            "https://www.javbus.com",
            "https://www.buscdn.bond",
            "https://www.busdmm.bond",
        ]
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.6261.95 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": "existmag=mag; dv=1; age=verified",
        }
        self._base_cookie = "existmag=mag; dv=1; age=verified"
        self.categories = [
            {"type_id": "censored", "type_name": "有码"},
            {"type_id": "uncensored", "type_name": "无码"},
            {"type_id": "genre_censored", "type_name": "有码类别"},
            {"type_id": "genre_uncensored", "type_name": "无码类别"},
            {"type_id": "actress_censored", "type_name": "有码女优"},
            {"type_id": "actress_uncensored", "type_name": "无码女优"},
            {"type_id": "hd", "type_name": "高清"},
            {"type_id": "sub", "type_name": "字幕"},
        ]
        self.category_paths = {
            "censored": ["/"],
            "uncensored": ["/uncensored"],
            "western": [],
            "genre_censored": ["/genre"],
            "genre_uncensored": ["/uncensored/genre"],
            "actress_censored": ["/actresses"],
            "actress_uncensored": ["/uncensored/actresses"],
            "hd": ["/genre/hd"],
            "sub": ["/genre/sub"],
        }
        self.second_level_parents = {"genre_censored", "genre_uncensored", "actress_censored", "actress_uncensored"}
        self._sub_jobs = {
            "genre_censored": ("/genre", '//a[contains(@href,"/genre/")]'),
            "genre_uncensored": ("/uncensored/genre", '//a[contains(@href,"/genre/")]'),
            "actress_censored": ("/actresses", '//a[contains(@href,"/star/")]'),
            "actress_uncensored": ("/uncensored/actresses", '//a[contains(@href,"/star/")]'),
        }

    @staticmethod
    def _merge_cookies(*parts):
        out = {}
        for ck in parts:
            for item in str(ck or "").split(";"):
                i = item.find("=")
                if i > 0:
                    out[item[:i].strip()] = item[i + 1:].strip()
        return "; ".join(f"{k}={v}" for k, v in out.items() if k)

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else extend
            if not isinstance(cfg, dict):
                return None
            hosts = cfg.get("hosts")
            if isinstance(hosts, list):
                merged = []
                for host in hosts + self.hosts:
                    value = str(host or "").strip().rstrip("/")
                    if value and value not in merged:
                        merged.append(value)
                if merged:
                    self.hosts = merged
                    self.host = merged[0]
            site_url = str(cfg.get("siteUrl") or cfg.get("host") or "").strip().rstrip("/")
            if site_url:
                if site_url not in self.hosts:
                    self.hosts.insert(0, site_url)
                self.host = site_url
            cookie = str(cfg.get("cookie") or "").strip()
            if cookie:
                self.headers["Cookie"] = self._merge_cookies(self._base_cookie, cookie)
        except Exception:
            pass
        return None

    def getName(self):
        return self.name

    def danmaku(self):
        return False


    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _clean(s):
        return re.sub(r"\s+", " ", str(s or "")).strip()

    def _build_url(self, path, base=None):
        b = base or self.host
        if not path:
            return b
        if str(path).startswith("http"):
            return path
        return urljoin(b.rstrip("/") + "/", str(path).strip().lstrip("/"))

    def _looks_like_code(self, vid):
        raw = str(vid or "").strip()
        return bool(re.match(r"^[A-Za-z]{2,12}-?\d{2,6}[A-Za-z]?$", raw, re.I)) or (
            bool(re.search(r"\d", raw))
            and bool(re.match(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+){0,3}$", raw, re.I))
            and 5 <= len(raw) <= 32
        )

    def _extract_code(self, url):
        try:
            from urllib.parse import urlparse
            path = urlparse(str(url)).path
            return path.strip("/").split("/")[-1] or ""
        except Exception:
            return str(url).replace(self.host, "").strip("/").split("/")[-1] or ""

    def _format_size(self, size_bytes):
        n = int(size_bytes) if str(size_bytes).isdigit() else 0
        if n <= 0:
            return ""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f}{unit}" if n != int(n) else f"{int(n)}{unit}"
            n /= 1024
        return f"{n:.1f}PB"

    @staticmethod
    def _parse_size_bytes(text):
        """Parse human-readable size like '1.2GB' → bytes int, for sorting."""
        m = re.search(r"([\d.]+)\s*(TB?|GB?|MB?|KB?)", str(text), re.I)
        if not m:
            return 0
        val = float(m.group(1))
        unit = m.group(2).upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1048576, "GB": 1073741824, "TB": 1099511627776}
        for k, v in multipliers.items():
            if k.startswith(unit):
                return int(val * v)
        return 0

    @staticmethod
    def _has_subtitle_mark(text):
        raw = str(text or "")
        compact = re.sub(r"\s+", "", raw)
        if re.search(r"中文字幕|繁体中文|簡体中文|简体中文|中字|字幕|chs|cht|sub", compact, re.I):
            return True
        if re.search(r"\b[A-Z]{2,12}[-_]?\d{2,6}[-_]?(?:C|CH|CHS|CHT)\b", raw, re.I):
            return True
        if re.search(r"\b(?:C|CH|CHS|CHT)[-_]?[A-Z]{2,12}[-_]?\d{2,6}\b", raw, re.I):
            return True
        return bool(
            re.search(r"(?:^|[^A-Za-z0-9])([A-Z]{2,12})[-_ ]?\d{2,6}(?:[-_ ]?(?:C|CH|CHS|CHT))?(?:[^A-Za-z0-9]|$)", compact, re.I)
            and re.search(r"(?:[-_ ](?:C|CH|CHS|CHT)|\d{2,6}(?:C|CH))(?:[^A-Za-z0-9]|$)", compact, re.I)
        )

    @staticmethod
    def _extract_size_label(text):
        m = re.search(r"([\d.]+)\s*(TB|GB|MB|KB|B)", str(text or ""), re.I)
        return re.sub(r"\s+", "", m.group(0)).upper() if m else ""

    @staticmethod
    def _safe_play_name(name, limit=120):
        text = re.sub(r"\s+", " ", str(name or "")).replace("#", " ").replace("$", " ").strip()
        return text[:limit] if text else ""

    def _pack_card_id(self, payload):
        raw = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return "jab-card:" + token

    def _unpack_card_id(self, value):
        text = str(value or "").strip()
        if text.startswith("atvp_detail:"):
            text = text[len("atvp_detail:"):].strip()
        prefix = "jab-card:"
        if not text.startswith(prefix):
            return {}
        token = text[len(prefix):].strip()
        token += "=" * (-len(token) % 4)
        try:
            data = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_btih_hash(value):
        text = str(value or "").strip()
        m = re.search(r"btih:([a-fA-F0-9]{32,40})", text, re.I)
        if m:
            return m.group(1).lower()
        return text.lower() if re.fullmatch(r"[a-fA-F0-9]{32,40}", text) else ""

    def _normalize_magnet(self, url):
        cleaned = re.sub(r"&amp;", "&", str(url or ""))
        cleaned = re.sub(r"""["'<>\s]+$""", "", cleaned)
        cleaned = re.sub(r"[)）】>>,，。]+$", "", cleaned)
        cleaned = cleaned.split("#")[0].strip()
        btih = self._extract_btih_hash(cleaned)
        if btih:
            return f"magnet:?xt=urn:btih:{btih}"
        return cleaned

    def _is_magnet(self, url):
        return bool(re.match(r"^magnet:\?xt=urn:btih:", str(url or ""), re.I))

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _request(self, url, base=None, allow_verify=True):
        target = self._build_url(url, base)
        headers = dict(self.headers)
        headers["Referer"] = (base or self.host) + "/"
        try:
            rsp = self.fetch(target, headers=headers, timeout=15, verify=False, allow_redirects=True)
        except Exception:
            # try alternate hosts
            for alt in self.hosts:
                if alt == (base or self.host):
                    continue
                try:
                    alt_url = self._build_url(url, alt)
                    headers["Referer"] = alt + "/"
                    rsp = self.fetch(alt_url, headers=headers, timeout=15, verify=False, allow_redirects=True)
                    self.host = alt
                    target = alt_url
                    break
                except Exception:
                    continue
            else:
                return ""
        if rsp.status_code == 404:
            return ""
        html = rsp.text or ""
        # check age verify page
        if re.search(r"driver-verify|所在地區年齡檢測|Age Verification", html, re.I):
            if not allow_verify:
                return ""
            # auto pass verify
            try:
                verify_url = self._build_url(
                    f"/doc/driver-verify?referer={quote(target)}", base or self.host
                )
                self.post(
                    verify_url,
                    data="Submit=%E7%A2%BA%E8%AA%8D",
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": base or self.host},
                    timeout=10,
                    verify=False,
                    allow_redirects=True,
                )
                time.sleep(0.3)
                rsp2 = self.fetch(target, headers=headers, timeout=15, verify=False, allow_redirects=True)
                html = rsp2.text or ""
                if re.search(r"driver-verify|所在地區年齡檢測", html, re.I):
                    return ""
            except Exception:
                return ""
        return html

    # ── list parsing ─────────────────────────────────────────────────────

    def _parse_list(self, html):
        root = self.html(html)
        if root is None:
            return []
        items = []
        seen = set()
        for node in root.xpath("//a[contains(@class,'movie-box')] | //div[contains(@class,'movie-box')]//a"):
            href = "".join(node.xpath("./@href")).strip()
            if not href:
                continue
            if re.search(r"genre|star|series|studio|label|forum|login|signup|actress|director|maker|doc/", href, re.I):
                continue
            full_url = self._build_url(href)
            vid = self._extract_code(full_url)
            if not vid or not self._looks_like_code(vid) or vid in seen:
                continue
            img_node = node.xpath(".//img[1]")
            if not img_node:
                continue
            img = img_node[0]
            title = self._clean(
                img.xpath("string(@title)") or img.xpath("string(@alt)") or "".join(node.xpath(".//text()"))
            ) or vid
            pic = self._clean(
                img.xpath("string(@src)") or img.xpath("string(@data-src)") or img.xpath("string(@data-original)") or ""
            )
            code_text = self._clean(
                "".join(node.xpath(".//date[1]/text() | .//*[contains(@class,'date')][1]/text()"))
            ) or vid
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": title or vid,
                "vod_pic": self._build_url(pic),
                "vod_remarks": code_text,
            })
        return items

    def _has_next_page(self, html):
        return bool(re.search(r'<a\s+id="next"', html))

    # ── second-level categories ──────────────────────────────────────────

    def _load_children(self, parent_id, page=1):
        """Load child classes for a single parent, supports pagination."""
        job = self._sub_jobs.get(parent_id)
        if not job:
            return [], False
        base_path, selector = job
        # build paginated url: /actresses → /actresses/2
        if page > 1:
            path = f"{base_path.rstrip('/')}/{page}"
        else:
            path = base_path
        try:
            html = self._request(path)
            if not html:
                return [], False
            root = self.html(html)
            if root is None:
                return [], False
            classes = []
            for a_node in root.xpath(selector):
                name = self._clean("".join(a_node.xpath(".//text()")))
                href = "".join(a_node.xpath("./@href")).strip()
                if not name or not href:
                    continue
                if re.search(r"论坛|論壇|forum|login|signup|doc/", name + href, re.I):
                    continue
                code = self._extract_code(href) or ""
                if not code:
                    continue
                type_id = f"{parent_id}_{code}"
                pic = self._clean(
                    "".join(a_node.xpath(".//img/@src | .//img/@data-src"))
                )
                pic = self._build_url(pic) if pic else ""
                classes.append({
                    "type_id": type_id,
                    "type_name": name,
                    "type_pid": parent_id,
                    "_href": href if href.startswith("http") else href,
                    "_pic": pic,
                })
            has_next = self._has_next_page(html)
            return classes, has_next
        except Exception:
            return [], False

    def _get_child_classes(self, parent_id, page=1):
        classes, _ = self._load_children(parent_id, page)
        return classes

    # ── interface methods ────────────────────────────────────────────────

    def homeContent(self, filter):
        return {"class": self.categories}

    def homeVideoContent(self):
        try:
            html = self._request("/")
            items = self._parse_list(html)[:24]
        except Exception:
            items = []
        return {"list": items}

    def _resolve_category_paths(self, tid):
        """Resolve a type_id to a list of URL paths for fetching."""
        # static categories
        if tid in self.category_paths:
            return self.category_paths[tid]
        # dynamic sub-category: try loading from parent's children
        for parent_id in self.second_level_parents:
            if tid.startswith(parent_id + "_"):
                children, _ = self._load_children(parent_id)
                for c in children:
                    if c["type_id"] == tid:
                        return [c["_href"]]
        return ["/"]

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) or 1

        # second-level parent → show children with pagination
        if tid in self.second_level_parents:
            sub_id = str(extend.get("sub", "") or extend.get("type", "") or "").strip()
            if sub_id:
                tid = sub_id
            else:
                children, has_next = self._load_children(tid, page)
                items = [
                    {"vod_id": c["type_id"], "vod_name": c["type_name"], "vod_pic": c.get("_pic", ""), "vod_tag": "folder"}
                    for c in children
                ]
                return {"page": page, "pagecount": page + 1 if has_next else page, "limit": len(items), "total": 9999, "list": items}

        # resolve category paths
        paths = self._resolve_category_paths(tid)
        if tid == "western":
            paths = ["https://www.javbus.org/"]

        # try each path
        all_items = []
        html = ""
        for path in paths:
            url = path if path.startswith("http") else self._build_url(path)
            if page > 1:
                if "/star/" in url or "/genre/" in url:
                    url = url.rstrip("/") + f"/{page}"
                else:
                    url = url.rstrip("/") + f"/page/{page}"
            html = self._request(url)
            if html:
                all_items.extend(self._parse_list(html))

        # deduplicate
        seen = set()
        items = []
        for it in all_items:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                items.append(it)

        has_next = bool(html and self._has_next_page(html))
        return {
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": 24,
            "total": 9999,
            "list": items,
        }

    def searchContent(self, key, quick, pg=1, category=""):
        keyword = self._clean(key)
        if not keyword:
            return {"list": [], "page": 1, "pagecount": 1, "total": 0}
        page = int(pg) or 1
        if page == 1 and self._looks_like_code(keyword):
            code = keyword.upper()
            try:
                detail_url = self._build_url(code)
                magnets, title = self._fetch_magnets(detail_url)
                title = title or code
                pic = ""
                detail_html = self._request(detail_url)
                if detail_html:
                    root = self.html(detail_html)
                    if root is not None:
                        pic = self._clean(
                            "".join(root.xpath("(//a[contains(@class,'bigImage')]//img/@src | //a[contains(@class,'bigImage')]//img/@data-src)[1]"))
                        )
                        if pic:
                            pic = self._build_url(pic)
                cards = []
                for idx, item in enumerate(magnets[:50], start=1):
                    magnet = item.get("magnet") or ""
                    if not self._is_magnet(magnet):
                        continue
                    name = self._safe_play_name(item.get("name") or f"磁力-{idx}")
                    cards.append({
                        "vod_id": self._pack_card_id({"code": code, "title": title, "pic": pic, "name": name, "magnet": magnet}),
                        "vod_name": name,
                        "vod_pic": pic,
                        "vod_remarks": "字幕" if item.get("is_sub") else (self._extract_size_label(name) or code),
                    })
                if cards:
                    return {"list": cards, "page": 1, "pagecount": 1, "total": len(cards)}
            except Exception as e:
                print(f"[JAVBUS_CARD_SEARCH_ERROR] {code} {e}")
        kw = quote(keyword)
        all_items = []
        seen = set()
        has_next = False
        for base_path in [f"/search/{kw}", f"/uncensored/search/{kw}"]:
            if page > 1:
                url = self._build_url(f"{base_path}/{page}")
            else:
                url = self._build_url(base_path)
            html = self._request(url)
            if not html:
                continue
            for it in self._parse_list(html):
                if it["vod_id"] not in seen:
                    seen.add(it["vod_id"])
                    all_items.append(it)
            if self._has_next_page(html):
                has_next = True
        return {"list": all_items, "page": page, "pagecount": page + 1 if has_next else page, "total": 9999}

    # ── detail + magnets ─────────────────────────────────────────────────

    def _fetch_magnets(self, detail_url):
        html = self._request(detail_url)
        if not html:
            return [], ""
        magnets = []
        seen_hashes = set()

        def add_magnet(href, name=""):
            magnet = self._normalize_magnet(href)
            if not self._is_magnet(magnet):
                return
            h = self._extract_btih_hash(magnet)
            if h in seen_hashes:
                return
            seen_hashes.add(h)
            raw_name = self._clean(name) or magnet
            size = self._parse_size_bytes(raw_name)
            is_sub = self._has_subtitle_mark(raw_name)
            is_hd = size >= 5 * 1024 * 1024 * 1024
            display_name = raw_name
            if is_sub and "【字幕】" not in display_name:
                display_name = "【字幕】" + display_name
            if is_hd and "[HD]" not in display_name:
                display_name = "[HD]" + display_name
            magnets.append({
                "magnet": magnet,
                "hash": h,
                "name": display_name,
                "size": size,
                "is_sub": is_sub,
                "is_hd": is_hd,
            })

        # parse detail html
        root = self.html(html)

        # extract title
        title = ""
        if root is not None:
            h3 = root.xpath("//h3[1]//text()")
            title = self._clean("".join(h3)).replace(" - JavBus", "").strip()

        # find magnet links in html
        if root is not None:
            for a_node in root.xpath("//a[starts-with(@href,'magnet:')]"):
                href = "".join(a_node.xpath("./@href")).strip()
                row = a_node.xpath("./ancestor::tr[1]")
                if row:
                    tds = row[0].xpath(".//td")
                    size_text = self._clean("".join(tds[1].xpath(".//text()"))) if len(tds) > 1 else ""
                    link_text = self._clean("".join(a_node.xpath(".//text()")))
                    name_parts = [p for p in [link_text, size_text] if p]
                    add_magnet(href, " | ".join(name_parts))
                else:
                    add_magnet(href, "".join(a_node.xpath(".//text()")))

        # regex fallback
        for m in re.findall(r"magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\"'<>\s]*", html, re.I):
            add_magnet(m, m)

        # JavBus AJAX magnets (gid/uc/img based)
        if not magnets or re.search(r"var\s+gid\s*=", html):
            gid_m = re.search(r"var\s+gid\s*=\s*([^;]+);", html)
            uc_m = re.search(r"var\s+uc\s*=\s*([^;]+);", html)
            img_m = re.search(r"var\s+img\s*=\s*([^;]+);", html)
            gid = (gid_m.group(1) or "").strip().strip("\"'")
            uc = (uc_m.group(1) or "0").strip().strip("\"'")
            img = (img_m.group(1) or "").strip().strip("\"'")
            if gid:
                import random
                floor = random.randint(1, 1000)
                ajax_url = self._build_url(
                    f"/ajax/uncledatoolsbyajax.php?gid={quote(gid)}&lang=zh&img={quote(img)}&uc={quote(uc)}&floor={floor}"
                )
                try:
                    ajax_headers = dict(self.headers)
                    ajax_headers["Referer"] = detail_url
                    ajax_headers["X-Requested-With"] = "XMLHttpRequest"
                    rsp = self.fetch(ajax_url, headers=ajax_headers, timeout=10, verify=False)
                    ajax_html = rsp.text or ""
                    # parse ajax table
                    ajax_root = self.html(f"<table>{ajax_html}</table>")
                    if ajax_root is not None:
                        for a_node in ajax_root.xpath("//a[starts-with(@href,'magnet:')]"):
                            href = "".join(a_node.xpath("./@href")).strip()
                            row = a_node.xpath("./ancestor::tr[1]")
                            link_text = self._clean("".join(a_node.xpath(".//text()")))
                            size_text = ""
                            date_text = ""
                            if row:
                                tds = row[0].xpath(".//td")
                                if len(tds) > 1:
                                    size_text = self._clean("".join(tds[1].xpath(".//text()")))
                                if len(tds) > 2:
                                    date_text = self._clean("".join(tds[2].xpath(".//text()")))
                            name_parts = [p for p in [link_text, size_text, date_text] if p]
                            add_magnet(href, " | ".join(name_parts))
                    # regex fallback for ajax
                    for m in re.findall(r"magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\"'<>\s]*", ajax_html, re.I):
                        add_magnet(m, m)
                except Exception:
                    pass

        magnets.sort(key=lambda x: (1 if x.get("is_sub") else 0, x.get("size", 0)), reverse=True)
        return magnets, title

    def detailContent(self, ids):
        result = {"list": []}
        for raw_id in ids:
            vid = str(raw_id or "").strip()
            if vid.startswith("atvp_detail:"):
                vid = vid[len("atvp_detail:"):].strip()
            if not vid:
                continue
            card = self._unpack_card_id(vid)
            if card:
                result["list"].append(self._build_card_detail_vod(card))
                continue

            # normal detail — fetch magnets
            detail_url = self._build_url(vid)
            magnets, title = self._fetch_magnets(detail_url)
            title = title or vid

            # get cover pic
            pic = ""
            try:
                detail_html = self._request(detail_url)
                if detail_html:
                    root = self.html(detail_html)
                    if root is not None:
                        pic = self._clean(
                            "".join(root.xpath("(//a[contains(@class,'bigImage')]//img/@src | //a[contains(@class,'bigImage')]//img/@data-src)[1]"))
                        )
                        pic = self._build_url(pic)
            except Exception:
                pass

            # Build one play group per magnet, matching pan-link spiders that expose
            # each resource as its own $$$ group instead of episodes in one group.
            play_from = []
            play_url = []
            seen_play_from = set()
            for idx, item in enumerate(magnets[:50]):
                name = item["name"] if item["name"] != item["magnet"] else f"磁力-{idx + 1}"
                size_text = self._extract_size_label(name) or self._format_size(item.get("size", 0)) or self._format_size(self._parse_size_bytes(name))
                source_name = name
                if size_text and size_text not in re.sub(r"\s+", "", source_name).upper():
                    source_name = f"{source_name} {size_text}"
                group_name = source_name
                if group_name in seen_play_from:
                    group_name = f"{source_name}#{idx + 1}"
                seen_play_from.add(group_name)
                play_id = item.get("magnet")
                if not self._is_magnet(play_id):
                    continue
                # ensure file size is visible in the name
                play_from.append(group_name)
                play_url.append(f"{source_name}${play_id}")

            result["list"].append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "type_name": "JavBus",
                "vod_area": "日本",
                "vod_content": title,
                "vod_play_from": "$$$".join(play_from) if play_from else "磁力",
                "vod_play_url": "$$$".join(play_url),
            })
        return result

    def _build_card_detail_vod(self, card):
        code = str(card.get("code") or "").strip()
        title = str(card.get("title") or code or "JavBus").strip()
        pic = str(card.get("pic") or "").strip()
        name = self._safe_play_name(card.get("name") or code or "磁力")
        magnet = str(card.get("magnet") or "").strip()
        play_url = f"{name}${magnet}" if self._is_magnet(magnet) else ""
        return {
            "vod_id": self._pack_card_id(card),
            "vod_name": name or title,
            "vod_pic": pic,
            "type_name": "JavBus",
            "vod_area": "日本",
            "vod_content": title,
            "vod_play_from": "磁力",
            "vod_play_url": play_url,
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").strip()
        if self._is_magnet(url):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": url, "header": {}}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}
