"""
App Store 评论数据抓取模块
使用 iTunes RSS Feed API 和 iTunes Lookup API
"""
import json
import requests
import time
import re
import random
from bs4 import BeautifulSoup
from config import Config


class AppStoreScraper:
    def __init__(self):
        self.timeout = Config.REQUEST_TIMEOUT
        self.delay = Config.REQUEST_DELAY
        self.max_pages = Config.MAX_REVIEW_PAGES
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def extract_app_id(self, url):
        """从 App Store 链接提取 App ID（支持多种 URL 格式）"""
        if not url:
            return None

        # 1. 匹配 /id123456 格式
        match = re.search(r'/id(\d+)', url)
        if match:
            return match.group(1)

        # 2. 匹配查询参数 ?id=123456
        match = re.search(r'[?&]id=(\d+)', url)
        if match:
            return match.group(1)

        # 3. 匹配 app/id 后跟名字再 /id123456
        match = re.search(r'/id(\d+)\b', url)
        if match:
            return match.group(1)

        # 4. 匹配纯数字（10位以上） - iTunes App ID 通常很长
        match = re.search(r'\b(\d{9,11})\b', url)
        if match:
            return match.group(1)

        return None

    def normalize_url(self, url):
        """标准化 URL，确保使用美国区"""
        # 提取 App ID
        app_id = self.extract_app_id(url)
        if not app_id:
            raise ValueError("无法从链接中提取 App ID")
        # 返回标准化的美国区链接
        return f"https://apps.apple.com/us/app/id{app_id}", app_id

    def get_app_info(self, app_id, country="us"):
        """获取应用信息（使用 iTunes Lookup API）"""
        url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("resultCount", 0) > 0:
                info = data["results"][0]
                return {
                    "app_id": str(info.get("trackId", app_id)),
                    "app_name": info.get("trackName", ""),
                    "bundle_id": info.get("bundleId", ""),
                    "version": info.get("version", ""),
                    "description": info.get("description", ""),
                    "average_rating": info.get("averageUserRating", 0),
                    "rating_count": info.get("userRatingCount", 0),
                    "price": info.get("price", 0),
                    "currency": info.get("currency", "USD"),
                    "release_date": info.get("releaseDate", ""),
                    "current_version_release_date": info.get("currentVersionReleaseDate", ""),
                    "seller_name": info.get("sellerName", ""),
                    "genres": info.get("genres", []),
                    "minimum_os_version": info.get("minimumOsVersion", ""),
                    "artwork_url": info.get("artworkUrl512", ""),
                }
            return None
        except Exception as e:
            print(f"获取应用信息失败: {e}")
            return None

    def get_app_info_fallback(self, app_id, country="us"):
        """备用方法：当 iTunes Lookup API 失败时，从 App Store 网页直接提取应用信息"""
        url = f"https://apps.apple.com/{country}/app/id{app_id}"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=self.headers, allow_redirects=True)
            resp.raise_for_status()

            # 如果被重定向到应用首页，说明 ID 有效但 iTunes API 没有收录
            final_url = resp.url
            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            app_info = {
                "app_id": app_id,
                "source": "app_store_web_fallback",
            }

            # 从 ld+json 提取
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    script_data = json.loads(script.string)
                    if isinstance(script_data, dict) and script_data.get("@type") == "SoftwareApplication":
                        app_info.update({
                            "app_name": script_data.get("name", ""),
                            "description": script_data.get("description", ""),
                            "artwork_url": script_data.get("image", ""),
                            "genres": [script_data.get("applicationCategory", "")] if script_data.get("applicationCategory") else [],
                            "minimum_os_version": script_data.get("operatingSystem", ""),
                        })
                        author = script_data.get("author", {})
                        if isinstance(author, dict):
                            app_info["seller_name"] = author.get("name", "")
                        else:
                            app_info["seller_name"] = str(author)
                        offers = script_data.get("offers", {})
                        if isinstance(offers, dict):
                            app_info["price"] = offers.get("price", 0)
                            app_info["currency"] = offers.get("priceCurrency", "")
                        agg = script_data.get("aggregateRating", {})
                        if agg:
                            try:
                                app_info["average_rating"] = float(agg.get("ratingValue", 0))
                            except:
                                pass
                            try:
                                app_info["rating_count"] = int(agg.get("reviewCount", 0) or agg.get("ratingCount", 0))
                            except:
                                pass
                        break
                except:
                    continue

            # 从 HTML 中提取
            version_match = re.search(r'"version"\s*:\s*"([^"]+)"', html)
            if version_match:
                app_info["version"] = version_match.group(1)

            age_match = re.search(r'"contentAdvisoryRating"\s*:\s*"([^"]+)"', html)
            if age_match:
                app_info["age_rating"] = age_match.group(1)

            # 提取 release date
            release_match = re.search(r'"releaseDate"\s*:\s*"([^"]+)"', html)
            if release_match:
                app_info["release_date"] = release_match.group(1)

            return app_info if app_info.get("app_name") else None
        except Exception as e:
            print(f"备用方法获取应用信息失败: {e}")
            return None

    def get_app_info_from_web(self, app_id, country="cn"):
        """从 App Store 网页爬取应用详细信息（评分、年龄分级、排行榜、官方介绍等）"""
        url = f"https://apps.apple.com/{country}/app/id{app_id}"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=self.headers)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            web_info = {
                "source": "app_store_web",
                "url": url,
            }

            # 1. 从 ld+json 提取结构化数据（最完整的信息源）
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    script_data = json.loads(script.string)
                    # 只处理 SoftwareApplication 类型
                    if isinstance(script_data, dict) and script_data.get("@type") == "SoftwareApplication":
                        # 评分信息
                        agg_rating = script_data.get("aggregateRating", {})
                        if agg_rating:
                            try:
                                web_info["average_rating"] = float(agg_rating.get("ratingValue", 0))
                            except:
                                pass
                            try:
                                web_info["rating_count"] = int(agg_rating.get("reviewCount", 0) or agg_rating.get("ratingCount", 0))
                            except:
                                pass
                            web_info["rating_best"] = agg_rating.get("bestRating", "5")

                        # 应用名称
                        web_info["app_name"] = script_data.get("name", "")

                        # 出版商
                        author = script_data.get("author", {})
                        if isinstance(author, dict):
                            web_info["seller_name"] = author.get("name", "")
                        else:
                            web_info["seller_name"] = str(author)

                        # 应用描述
                        web_info["description"] = script_data.get("description", "")

                        # 应用图标
                        web_info["artwork_url"] = script_data.get("image", "")

                        # 分类
                        web_info["genres"] = [script_data.get("applicationCategory", "")] if script_data.get("applicationCategory") else []

                        # 系统要求
                        web_info["minimum_os_version"] = script_data.get("operatingSystem", "")

                        # 价格
                        offers = script_data.get("offers", {})
                        if isinstance(offers, dict):
                            web_info["price"] = offers.get("price", 0)
                            web_info["currency"] = offers.get("priceCurrency", "")

                        # 支持设备
                        web_info["supported_devices"] = script_data.get("availableOnDevice", "")
                        break
                except Exception as e:
                    print(f"ld+json 解析失败: {e}")
                    continue

            # 2. 从 HTML 中提取年龄分级、版本号、排行榜等
            html_info = self._extract_from_html(html)
            if html_info:
                for key, value in html_info.items():
                    if value and (key not in web_info or not web_info.get(key)):
                        web_info[key] = value

            return web_info if len(web_info) > 2 else None
        except Exception as e:
            print(f"从网页获取应用信息失败: {e}")
            return None

    def _extract_from_html(self, html):
        """从 HTML 中解析应用信息（年龄分级、版本号、排行榜等）"""
        info = {}

        # 提取年龄分级
        age_patterns = [
            re.search(r'"contentAdvisoryRating"\s*:\s*"([^"]+)"', html),
            re.search(r'"ageRating"\s*:\s*"([^"]+)"', html),
        ]
        for pattern in age_patterns:
            if pattern:
                info["age_rating"] = pattern.group(1)
                break

        # 提取版本号
        version_patterns = [
            re.search(r'"version"\s*:\s*"([^"]+)"', html),
            re.search(r'class="whats-new__latest__version"[^>]*>\s*Version\s*([\d.]+)', html),
        ]
        for pattern in version_patterns:
            if pattern:
                info["version"] = pattern.group(1)
                break

        # 提取排行榜信息
        chart_patterns = [
            re.search(r'"chartPosition"\s*:\s*\{[^}]*"position"\s*:\s*(\d+)', html),
            re.search(r'"chart"\s*:\s*\{[^}]*"position"\s*:\s*(\d+)', html),
            re.search(r'we-product-chart__figure[^>]*>\s*#?\s*(\d+)', html),
        ]
        for pattern in chart_patterns:
            if pattern:
                info["chart_position"] = pattern.group(1)
                break

        # 提取更新日期
        date_patterns = [
            re.search(r'"currentVersionReleaseDate"\s*:\s*"([^"]+)"', html),
            re.search(r'"releaseDate"\s*:\s*"([^"]+)"', html),
        ]
        for pattern in date_patterns:
            if pattern:
                info["current_version_release_date"] = pattern.group(1)
                break

        # 提取应用大小
        size_match = re.search(r'"fileSizeBytes"\s*:\s*"([^"]+)"', html)
        if size_match:
            info["file_size_bytes"] = size_match.group(1)

        # 提取兼容性
        compat_match = re.search(r'"minimumOsVersion"\s*:\s*"([^"]+)"', html)
        if compat_match:
            info["minimum_os_version"] = compat_match.group(1)

        # 提取语言
        lang_match = re.search(r'"languageCodesISO2A"\s*:\s*\[([^\]]+)\]', html)
        if lang_match:
            langs = re.findall(r'"([A-Z]{2})"', lang_match.group(1))
            if langs:
                info["languages"] = langs

        # 提取评分分布
        histogram_match = re.search(r'"ratingCountHistogram"\s*:\s*\[([^\]]+)\]', html)
        if histogram_match:
            try:
                values = re.findall(r'(\d+)', histogram_match.group(1))
                info["rating_histogram"] = [int(v) for v in values]
            except:
                pass

        # 提取应用下载量
        download_match = re.search(r'"userRatingCount"\s*:\s*(\d+)', html)
        if download_match:
            try:
                info["rating_count"] = int(download_match.group(1))
            except:
                pass

        return info

    def merge_app_info(self, api_info, web_info):
        """合并 iTunes API 和网页爬取的信息，网页信息优先（更详细）"""
        if not api_info:
            return web_info
        if not web_info:
            return api_info

        merged = dict(api_info)
        for key, value in web_info.items():
            if value and (key not in merged or not merged.get(key) or merged.get(key) == ""):
                merged[key] = value
            elif value and key in [
                "age_rating", "chart_position", "chart_name", "file_size_bytes",
                "languages", "average_rating", "rating_count", "version", "seller_name"
            ]:
                # 优先使用网页爬取的数据（更准确）
                merged[key] = value
        return merged

    def get_reviews_page(self, app_id, page=1, country="us"):
        """获取单页评论（使用 RSS Feed）"""
        url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            # 第一个 entry 通常是应用信息，过滤掉
            reviews = []
            for entry in entries:
                if entry.get("im:rating"):
                    review = {
                        "review_id": entry.get("id", {}).get("label", ""),
                        "title": entry.get("title", {}).get("label", ""),
                        "content": entry.get("content", {}).get("label", ""),
                        "rating": int(entry.get("im:rating", {}).get("label", 0)),
                        "author": entry.get("author", {}).get("name", {}).get("label", ""),
                        "version": entry.get("im:version", {}).get("label", ""),
                        "date": entry.get("updated", {}).get("label", ""),
                        "app_id": app_id,
                    }
                    reviews.append(review)
            return reviews
        except Exception as e:
            print(f"获取第 {page} 页评论失败: {e}")
            return []

    def get_all_reviews(self, app_id, country="us", max_pages=None, progress_callback=None):
        """获取所有评论（多页）"""
        if max_pages is None:
            max_pages = self.max_pages
        all_reviews = []
        for page in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(page / max_pages * 0.5, f"抓取评论第 {page}/{max_pages} 页")
            reviews = self.get_reviews_page(app_id, page, country)
            if not reviews:
                break
            all_reviews.extend(reviews)
            if page < max_pages:
                time.sleep(self.delay)
        return all_reviews

    def sample_reviews_by_rating(self, reviews, samples_per_rating=10):
        """按星级分组随机采样评论"""
        # 按评分分组
        reviews_by_rating = {1: [], 2: [], 3: [], 4: [], 5: []}
        for review in reviews:
            rating = review.get('rating', 0)
            if rating in reviews_by_rating:
                reviews_by_rating[rating].append(review)
        
        # 每组随机采样
        sampled_reviews = []
        for rating in range(1, 6):
            rating_reviews = reviews_by_rating[rating]
            if len(rating_reviews) <= samples_per_rating:
                sampled_reviews.extend(rating_reviews)
            else:
                sampled_reviews.extend(random.sample(rating_reviews, samples_per_rating))
        
        # 打乱顺序
        random.shuffle(sampled_reviews)
        return sampled_reviews

    def scrape(self, url, analysis_target="", progress_callback=None):
        """完整的抓取流程"""
        # 标准化 URL
        normalized_url, app_id = self.normalize_url(url)
        # 从 URL 中提取国家
        country_match = re.search(r'apps\.apple\.com/(\w+)/', url)
        preferred_country = country_match.group(1) if country_match else "us"
        if preferred_country not in ["us", "cn", "jp", "gb", "kr", "hk", "tw"]:
            preferred_country = "us"

        if progress_callback:
            progress_callback(0.02, f"获取应用基本信息（{preferred_country}区）")
        # 1. 先通过 iTunes Lookup API 获取基础信息
        app_info = self.get_app_info(app_id, preferred_country)
        if not app_info:
            print(f"[Scraper] iTunes API 未找到 {app_id}，尝试备用方案（网页爬取）")
            if progress_callback:
                progress_callback(0.04, "iTunes API 未收录，尝试网页爬取")
            # 备用方案：直接爬取 App Store 网页
            for country in [preferred_country, "us", "cn", "jp", "gb"]:
                app_info = self.get_app_info_fallback(app_id, country=country)
                if app_info and app_info.get("app_name"):
                    break
            if not app_info or not app_info.get("app_name"):
                raise Exception(f"无法获取 App ID {app_id} 的应用信息（iTunes API 未收录且网页爬取也失败）")

        if progress_callback:
            progress_callback(0.05, "从网页爬取详细应用信息")
        # 2. 从 App Store 网页爬取更详细的信息
        country = preferred_country
        web_info = self.get_app_info_from_web(app_id, country=country)
        if web_info:
            app_info = self.merge_app_info(app_info, web_info)
            print(f"[Scraper] 已从网页获取补充信息: {list(web_info.keys())}")

        if progress_callback:
            progress_callback(0.1, "开始抓取评论")
        # 3. 获取评论 - 优先使用用户所在国家，否则 fallback 到 us
        all_reviews = []
        used_country = None
        for try_country in [preferred_country, "us", "cn", "gb", "jp"]:
            if try_country == preferred_country:
                pass
            elif all_reviews:
                break
            all_reviews = self.get_all_reviews(app_id, try_country, progress_callback=progress_callback)
            if all_reviews:
                used_country = try_country
                print(f"[Scraper] 成功从 {try_country} 区获取 {len(all_reviews)} 条评论")
                break

        if not all_reviews:
            # 没有评论时，记录警告但不抛异常
            print(f"[Scraper] 警告: 所有国家区都未能获取到 App {app_id} 的评论")
            if progress_callback:
                progress_callback(0.5, "⚠️ 未抓取到任何评论")
        else:
            # 按星级分组随机采样（每组最多10条）
            reviews = self.sample_reviews_by_rating(all_reviews, samples_per_rating=10)
            if progress_callback:
                progress_callback(0.5, f"抓取完成，共 {len(all_reviews)} 条评论，采样 {len(reviews)} 条")
            return {
                "app_info": app_info,
                "reviews": reviews,
                "total_count": len(reviews),
                "used_country": used_country,
            }

        return {
            "app_info": app_info,
            "reviews": [],
            "total_count": 0,
            "used_country": None,
        }


if __name__ == "__main__":
    # 测试
    scraper = AppStoreScraper()
    test_url = "https://apps.apple.com/cn/app/%E7%BE%8E%E5%9B%A2-%E9%97%AE%E7%BE%8E%E9%83%BD%E5%AE%89%E6%8E%92/id423084029"
    result = scraper.scrape(test_url)
    print(f"应用: {result['app_info']['app_name']}")
    print(f"评论数: {result['total_count']}")
    if result['reviews']:
        print(f"第一条评论: {result['reviews'][0]}")
