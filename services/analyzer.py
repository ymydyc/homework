"""
评论数据分析模块
使用 LLM 进行动态主题发现、问题整合、证据分析
"""
import json
import time
import httpx
from openai import OpenAI
from config import Config


class ReviewAnalyzer:
    def __init__(self):
        timeout = httpx.Timeout(30.0, connect=10.0)
        self.client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url=Config.LLM_BASE_URL,
            timeout=timeout
        )
        self.model = Config.LLM_MODEL
        self.llm_total_time = 0
        self.llm_call_count = 0

    def _call_llm(self, messages, temperature=0.7, max_tokens=2000, label="", max_retries=2):
        """调用 LLM API（带详细耗时日志和重试机制）"""
        self.llm_call_count += 1
        call_id = self.llm_call_count
        # 计算 prompt 长度
        prompt_len = sum(len(m.get("content", "")) for m in messages)
        print(f"[LLM-{call_id}] 开始调用 ({label}) | prompt长度: {prompt_len}字符 | 模型: {self.model}")
        
        for retry in range(max_retries + 1):
            t0 = time.time()
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                elapsed = time.time() - t0
                self.llm_total_time += elapsed
                content = response.choices[0].message.content
                content_len = len(content) if content else 0
                # 统计 token 用量
                usage = response.usage
                token_info = ""
                if usage:
                    token_info = f" | tokens: {usage.prompt_tokens}入/{usage.completion_tokens}出/总计{usage.total_tokens}"
                print(f"[LLM-{call_id}] 完成 | 耗时: {elapsed:.1f}s | 响应长度: {content_len}字符{token_info} | 累计LLM耗时: {self.llm_total_time:.1f}s")
                return content
            except Exception as e:
                elapsed = time.time() - t0
                print(f"[LLM-{call_id}] 失败 | 耗时: {elapsed:.1f}s | 错误: {type(e).__name__}: {e} | 重试 {retry+1}/{max_retries}")
                if retry < max_retries:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    return None
        return None

    def discover_topics(self, reviews, progress_callback=None):
        """动态主题发现"""
        if progress_callback:
            progress_callback(0.0, "开始主题发现")

        # 准备评论样本（限制 token 数量）
        sample_reviews = reviews[:100]  # 取前100条作为样本
        review_texts = []
        for r in sample_reviews:
            text = f"[{r['rating']}星] {r['title']}: {r['content'][:200]}"
            review_texts.append(text)

        prompt = f"""你是一个产品分析专家。请分析以下 App Store 用户评论，识别主要主题和问题类别。

评论样本（共 {len(review_texts)} 条）：
{chr(10).join(review_texts[:50])}

请完成以下任务：
1. 识别评论中的主要主题（如：性能问题、功能需求、用户体验、价格问题等）
2. 为每个主题提供：
   - 主题名称（简洁明了）
   - 主题描述（1-2句话）
   - 相关评论ID列表（从样本中选择）
   - 严重程度（高/中/低）
   - 出现频率估计（高/中/低）

请以 JSON 格式返回，结构如下：
{{
  "topics": [
    {{
      "name": "主题名称",
      "description": "主题描述",
      "review_ids": ["id1", "id2", ...],
      "severity": "高|中|低",
      "frequency": "高|中|低"
    }}
  ]
}}

只返回 JSON，不要其他文字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 分析主题")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.7, max_tokens=2000)

        if not response:
            return {"topics": [], "error": "LLM 调用失败"}

        try:
            # 提取 JSON
            result = self._extract_json(response)
            if progress_callback:
                progress_callback(1.0, f"发现 {len(result.get('topics', []))} 个主题")
            return result
        except Exception as e:
            return {"topics": [], "error": str(e)}

    def integrate_problems(self, reviews, topics, progress_callback=None):
        """问题整合与优先级排序"""
        if progress_callback:
            progress_callback(0.0, "开始问题整合")

        # 准备主题摘要
        topic_summary = []
        for t in topics.get("topics", []):
            topic_summary.append(f"- {t['name']}: {t['description']} (严重程度: {t['severity']}, 频率: {t['frequency']})")

        prompt = f"""你是一个产品分析专家。基于以下主题分析结果，整合核心问题并确定优先级。

识别的主题：
{chr(10).join(topic_summary)}

请完成以下任务：
1. 整合相似问题，识别核心问题
2. 为每个核心问题提供：
   - 问题标题
   - 问题描述
   - 相关主题
   - 影响用户数估计（基于评论频率）
   - 优先级（P0/P1/P2）
   - 置信度（高/中/低）
   - 矛盾证据（如果有）

请以 JSON 格式返回：
{{
  "problems": [
    {{
      "title": "问题标题",
      "description": "问题描述",
      "related_topics": ["主题1", "主题2"],
      "affected_users": "估计影响用户数",
      "priority": "P0|P1|P2",
      "confidence": "高|中|低",
      "contradictions": "矛盾证据描述（如有）"
    }}
  ]
}}

只返回 JSON，不要其他文字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 整合问题")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.7, max_tokens=2000)

        if not response:
            return {"problems": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)
            if progress_callback:
                progress_callback(1.0, f"整合出 {len(result.get('problems', []))} 个核心问题")
            return result
        except Exception as e:
            return {"problems": [], "error": str(e)}

    def analyze_with_evidence(self, reviews, problems, progress_callback=None):
        """基于证据的分析"""
        if progress_callback:
            progress_callback(0.0, "开始证据分析")

        # 为每个问题寻找证据
        problems_with_evidence = []
        for idx, problem in enumerate(problems.get("problems", [])):
            if progress_callback:
                progress_callback(idx / len(problems.get("problems", [])), f"分析问题 {idx + 1}/{len(problems.get('problems', []))}")

            # 根据问题描述搜索相关评论
            keywords = problem.get("title", "").split() + problem.get("description", "").split()
            related_reviews = self._search_reviews(reviews, keywords[:5])

            # 准备证据
            evidence_reviews = []
            for r in related_reviews[:5]:
                evidence_reviews.append({
                    "review_id": r["review_id"],
                    "rating": r["rating"],
                    "excerpt": r["content"][:150]
                })

            problem_with_evidence = {
                **problem,
                "evidence_count": len(related_reviews),
                "evidence_reviews": evidence_reviews,
                "confidence": problem.get("confidence", "中")
            }
            problems_with_evidence.append(problem_with_evidence)

        if progress_callback:
            progress_callback(1.0, "证据分析完成")

        return {"problems": problems_with_evidence}

    def _search_reviews(self, reviews, keywords, max_results=10):
        """搜索相关评论"""
        scored = []
        for r in reviews:
            text = f"{r['title']} {r['content']}".lower()
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scored.append((score, r))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [r for _, r in scored[:max_results]]

    def _extract_json(self, text):
        """从 LLM 响应中提取 JSON（增强版：支持多种格式和错误修复）"""
        if not text:
            raise ValueError("响应为空")
        
        text = text.strip()
        
        # 方法1: 直接解析
        try:
            return json.loads(text)
        except:
            pass
        
        # 方法2: 提取 ```json 代码块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                json_str = text[start:end].strip()
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        # 方法3: 提取 ``` 代码块
        if "```" in text:
            start = text.find("```") + 3
            newline_pos = text.find("\n", start)
            if newline_pos > 0 and newline_pos - start < 20:
                start = newline_pos + 1
            end = text.find("```", start)
            if end > start:
                json_str = text[start:end].strip()
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        # 方法4: 找到第一个 { 和最后一个 } 之间的内容
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except:
                pass
        
        # 方法5: 尝试找到 [...] 数组
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except:
                pass
        
        print(f"[Analyzer] JSON 提取失败，原始响应前500字符: {text[:500]}")
        raise ValueError(f"无法提取 JSON，响应长度: {len(text)}")

    def _group_reviews_by_rating(self, reviews):
        """按星级分组评论"""
        groups = {1: [], 2: [], 3: [], 4: [], 5: []}
        for review in reviews:
            rating = review.get('rating', 0)
            if rating in groups:
                groups[rating].append(review)
        return groups

    def _analyze_single_rating_group(self, rating, reviews, progress_callback=None):
        """分析单个星级组的评论（合并主题发现和问题整合为一次LLM调用）"""
        if not reviews:
            return {"rating": rating, "topics": {"topics": []}, "problems": {"problems": []}}

        if progress_callback:
            progress_callback(0.0, f"分析 {rating} 星评论（共 {len(reviews)} 条）")

        # 合并主题发现和问题整合为一次LLM调用
        combined_result = self._discover_topics_and_problems(reviews, progress_callback)
        if "error" in combined_result:
            return {"rating": rating, "error": combined_result["error"], "topics": {"topics": []}, "problems": {"problems": []}}

        topics_result = {"topics": combined_result.get("topics", [])}
        problems_result = {"problems": combined_result.get("problems", [])}

        # 证据分析（不需要LLM调用）
        evidence_result = self.analyze_with_evidence(reviews, problems_result, progress_callback)

        if progress_callback:
            progress_callback(1.0, f"{rating} 星评论分析完成")

        return {
            "rating": rating,
            "review_count": len(reviews),
            "topics": topics_result,
            "problems": evidence_result
        }

    def _discover_topics_and_problems(self, reviews, progress_callback=None):
        """一次性完成主题发现和问题整合（减少LLM调用次数）"""
        if progress_callback:
            progress_callback(0.0, "开始分析主题和问题")

        # 关键检查：没有评论数据直接返回空
        if not reviews or len(reviews) == 0:
            return {
                "topics": {"topics": []},
                "problems": {"problems": []},
                "error": "没有评论数据"
            }

        # 准备评论数据（JSON格式）
        sample_reviews = reviews[:50]  # 最多50条
        review_data = []
        for r in sample_reviews:
            review_data.append({
                "review_id": r.get("review_id", ""),
                "rating": r.get("rating", 0),
                "author": r.get("author", ""),
                "content": r.get("content", ""),
                "date": r.get("date", "")
            })

        reviews_json = json.dumps(review_data, ensure_ascii=False, indent=2)
        prompt = f"""分析以下App Store评论，识别主要主题和问题。

**重要：必须严格基于下面的评论内容进行分析。不得编造评论中没有的内容。**

评论数据（共{len(review_data)}条，每条带 review_id 字段）：
{reviews_json}

请完成：
1. 识别主要主题（如性能问题、功能需求、用户体验等）
2. 整合核心问题并确定优先级

返回JSON格式：
{{
  "topics": [
    {{"name": "主题名称", "description": "描述", "review_ids": ["review_id1", "review_id2"], "severity": "高|中|低", "frequency": "高|中|低"}}
  ],
  "problems": [
    {{"title": "问题标题", "description": "描述", "related_topics": ["主题1"], "affected_users": "估计", "priority": "P0|P1|P2", "confidence": "高|中|低", "review_ids": ["review_id1", "review_id2"]}}
  ]
}}

**重要：review_ids 字段必须从评论数据中选取对应的 review_id 填入，不能为空数组。**
**重要：问题和主题必须严格基于评论中提及的内容，不得编造评论中没有的问题或主题。**
只返回JSON。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 分析主题和问题")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.7, max_tokens=3000, label=f"主题+问题整合")

        if not response:
            return {"topics": [], "problems": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)
            topic_count = len(result.get("topics", []))
            problem_count = len(result.get("problems", []))
            if progress_callback:
                progress_callback(1.0, f"发现 {topic_count} 个主题，{problem_count} 个问题")
            return result
        except Exception as e:
            return {"topics": [], "problems": [], "error": str(e)}

    def _summarize_all_ratings(self, rating_results, reviews, progress_callback=None):
        """汇总所有星级的分析结果"""
        if progress_callback:
            progress_callback(0.0, "开始汇总分析结果")

        # 关键检查：没有评论数据时直接返回空
        if not reviews or len(reviews) == 0:
            return {
                "summary": {
                    "total_reviews": 0,
                    "key_findings": ["未抓取到任何评论数据"],
                    "common_problems": [],
                    "rating_specific_problems": {}
                },
                "problems": [],
                "error": "没有评论数据"
            }

        # 准备各星级摘要
        rating_summaries = []
        for result in rating_results:
            rating = result.get("rating")
            topics = result.get("topics", {}).get("topics", [])
            problems = result.get("problems", {}).get("problems", [])
            # 简化问题：只传必要字段，包含 review_ids 用于后续溯源
            simplified_problems = []
            for p in problems[:3]:
                simplified_problems.append({
                    "title": p.get("title", ""),
                    "description": p.get("description", ""),
                    "review_ids": p.get("review_ids", []),
                    "priority": p.get("priority", ""),
                })
            rating_summaries.append({
                "rating": rating,
                "review_count": result.get("review_count", 0),
                "topic_count": len(topics),
                "problem_count": len(problems),
                "topics": topics[:3],  # 只取前3个主题
                "problems": simplified_problems  # 只取前3个问题
            })

        prompt = f"""你是一个产品分析专家。以下是对 App Store 评论按星级（1-5星）分别分析的结果。请汇总这些结果，生成最终的综合分析报告。

**重要：必须严格基于下面的各星级分析结果进行汇总。不得编造任何新问题。**

各星级分析摘要：
{json.dumps(rating_summaries, ensure_ascii=False, indent=2)}

请完成以下任务：
1. 识别跨星级的共同问题和差异问题（仅基于上面已识别的问题）
2. 确定整体优先级最高的核心问题
3. 为每个核心问题提供：
   - 问题标题
   - 问题描述
   - 相关星级（哪些问题在哪些星级中出现）
   - 影响用户数估计
   - 优先级（P0/P1/P2）
   - 置信度（高/中/低）
   - **source_review_ids (重要！必须从该问题所属星级的 review_ids 中选择相关的填入)**

请以 JSON 格式返回：
{{
  "summary": {{
    "total_reviews": {len(reviews)},
    "key_findings": ["发现1", "发现2", "发现3"],
    "common_problems": ["共同问题1", "共同问题2"],
    "rating_specific_problems": {{
      "1_star": ["1星特有问题"],
      "5_star": ["5星特有问题"]
    }}
  }},
  "problems": [
    {{
      "title": "问题标题",
      "description": "问题描述",
      "related_ratings": [1, 2, 3],
      "affected_users": "估计影响用户数",
      "priority": "P0|P1|P2",
      "confidence": "高|中|低",
      "source_review_ids": ["review_id1", "review_id2"]
    }}
  ]
}}

**严格要求：**
1. source_review_ids 字段必须从上面的 review_ids 中选取（每个问题至少2个），不能为空
2. problems 列表中只能包含上面已识别的问题，不得新增未在评论中提到的问题
只返回 JSON，不要其他文字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 汇总分析")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.5, max_tokens=3000)

        if not response:
            return {"summary": {}, "problems": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)
            if progress_callback:
                progress_callback(1.0, "汇总分析完成")
            return result
        except Exception as e:
            return {"summary": {}, "problems": [], "error": str(e)}

    def analyze(self, reviews, progress_callback=None):
        """完整的分析流程（按星级分组分析）"""
        total_start = time.time()
        print(f"[Analyzer] ========== 开始分析 {len(reviews)} 条评论 ==========")

        # 关键检查：没有评论数据时直接返回空结果
        if not reviews or len(reviews) == 0:
            print(f"[Analyzer] ⚠️ 没有评论数据，跳过分析")
            if progress_callback:
                progress_callback(1.0, "⚠️ 无评论数据，无法分析")
            return {
                "summary": {
                    "total_reviews": 0,
                    "key_findings": ["未抓取到任何评论数据"],
                    "common_problems": [],
                    "rating_specific_problems": {}
                },
                "problems": [],
                "rating_results": [],
                "has_reviews": False,
                "error": "未抓取到任何评论数据"
            }

        # 按星级分组
        rating_groups = self._group_reviews_by_rating(reviews)
        for rating in range(1, 6):
            count = len(rating_groups[rating])
            if count > 0:
                print(f"[Analyzer] {rating}星评论: {count} 条")

        # 对每个星级组单独分析
        rating_results = []
        total_ratings = 5
        for idx, rating in enumerate(range(1, 6), 1):
            rating_reviews = rating_groups[rating]
            if not rating_reviews:
                print(f"[Analyzer] {rating}星评论为空，跳过")
                continue

            if progress_callback:
                progress_callback((idx - 1) / total_ratings * 0.8, f"分析 {rating} 星评论")

            try:
                rating_start = time.time()
                print(f"[Analyzer] ---------- 开始分析 {rating} 星评论（共 {len(rating_reviews)} 条）----------")
                result = self._analyze_single_rating_group(rating, rating_reviews)
                rating_elapsed = time.time() - rating_start
                has_error = "error" in result
                error_info = f" | 错误: {result['error']}" if has_error else ""
                print(f"[Analyzer] {rating} 星评论分析完成 | 耗时: {rating_elapsed:.1f}s | LLM调用次数: {self.llm_call_count}{error_info}")
                rating_results.append(result)
            except Exception as e:
                rating_elapsed = time.time() - rating_start
                print(f"[Analyzer] {rating} 星评论分析失败 | 耗时: {rating_elapsed:.1f}s | 错误: {type(e).__name__}: {e}")
                # 记录失败但不中断，继续分析其他星级
                rating_results.append({
                    "rating": rating,
                    "review_count": len(rating_reviews),
                    "error": str(e),
                    "topics": {"topics": []},
                    "problems": {"problems": []}
                })

        # 汇总所有星级的分析结果
        print(f"[Analyzer] ---------- 开始汇总分析结果 ----------")
        if progress_callback:
            progress_callback(0.8, "汇总分析结果")

        summary_result = self._summarize_all_ratings(rating_results, reviews, progress_callback)

        # 整合所有证据
        all_problems = summary_result.get("problems", [])
        all_reviews_for_evidence = reviews
        # 建立 review_id 索引
        review_index = {r.get("review_id", ""): r for r in reviews}
        problems_with_evidence = []
        for problem in all_problems:
            # 优先使用 LLM 返回的 source_review_ids
            llm_review_ids = problem.get("source_review_ids", []) or problem.get("review_ids", [])
            evidence_reviews = []

            # 1. 先使用 LLM 标记的 review_ids
            for rid in llm_review_ids:
                if rid in review_index:
                    r = review_index[rid]
                    # 避免重复
                    if not any(er["review_id"] == r["review_id"] for er in evidence_reviews):
                        evidence_reviews.append({
                            "review_id": r["review_id"],
                            "rating": r["rating"],
                            "excerpt": r.get("content", "")[:150]
                        })

            # 2. 如果 LLM 没标记或标记不足，再用关键词搜索补充
            if len(evidence_reviews) < 2:
                keywords = problem.get("title", "").split() + problem.get("description", "").split()
                related_reviews = self._search_reviews(all_reviews_for_evidence, keywords[:5])
                for r in related_reviews[:5]:
                    if not any(er["review_id"] == r["review_id"] for er in evidence_reviews):
                        evidence_reviews.append({
                            "review_id": r["review_id"],
                            "rating": r["rating"],
                            "excerpt": r.get("content", "")[:150]
                        })

            problems_with_evidence.append({
                **problem,
                "evidence_count": len(evidence_reviews),
                "evidence_reviews": evidence_reviews
            })

        total_elapsed = time.time() - total_start
        print(f"[Analyzer] ========== 分析完成 ==========")
        print(f"[Analyzer] 总耗时: {total_elapsed:.1f}s | LLM调用次数: {self.llm_call_count} | LLM累计耗时: {self.llm_total_time:.1f}s")

        return {
            "rating_results": rating_results,
            "summary": summary_result,
            "problems": {"problems": problems_with_evidence}
        }


if __name__ == "__main__":
    # 测试
    analyzer = ReviewAnalyzer()
    test_reviews = [
        {"review_id": "1", "title": "卡顿", "content": "应用很卡，经常闪退", "rating": 1},
        {"review_id": "2", "title": "好用", "content": "功能很强大", "rating": 5},
    ]
    result = analyzer.analyze(test_reviews)
    print(json.dumps(result, ensure_ascii=False, indent=2))
