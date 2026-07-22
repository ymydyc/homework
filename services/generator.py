"""
需求生成模块
使用 LLM 生成产品需求、版本规划和测试用例
"""
import json
import time
import httpx
from openai import OpenAI
from config import Config


class RequirementGenerator:
    def __init__(self):
        timeout = httpx.Timeout(60.0, connect=10.0)
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
        prompt_len = sum(len(m.get("content", "")) for m in messages)
        print(f"[Generator-LLM-{call_id}] 开始调用 ({label}) | prompt长度: {prompt_len}字符 | 模型: {self.model}")
        
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
                usage = response.usage
                token_info = ""
                if usage:
                    token_info = f" | tokens: {usage.prompt_tokens}入/{usage.completion_tokens}出/总计{usage.total_tokens}"
                print(f"[Generator-LLM-{call_id}] 完成 | 耗时: {elapsed:.1f}s | 响应长度: {content_len}字符{token_info} | 累计LLM耗时: {self.llm_total_time:.1f}s")
                return content
            except Exception as e:
                elapsed = time.time() - t0
                print(f"[Generator-LLM-{call_id}] 失败 | 耗时: {elapsed:.1f}s | 错误类型: {type(e).__name__} | 错误: {e} | 重试 {retry+1}/{max_retries}")
                if retry < max_retries:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    return None
        return None

    def generate_requirements(self, problems, app_info, progress_callback=None):
        """生成产品需求"""
        if progress_callback:
            progress_callback(0.0, "开始生成需求")

        # 关键检查：没有评论数据或没有问题时直接返回空
        problems_list = problems.get("problems", []) if problems else []
        if not problems_list:
            print(f"[Generator] ⚠️ 没有识别到核心问题，无法生成需求")
            if progress_callback:
                progress_callback(1.0, "⚠️ 无问题数据，无法生成需求")
            return {
                "requirements": [],
                "error": "未识别到核心问题（可能因为没有评论数据）"
            }

        # 准备问题摘要
        problem_summary = []
        for idx, p in enumerate(problems_list, 1):
            evidence = p.get("evidence_reviews", [])
            evidence_text = "; ".join([f"[{e['review_id']}] {e['excerpt'][:50]}" for e in evidence[:3]])
            problem_summary.append(
                f"{idx}. {p['title']} (优先级: {p.get('priority', 'P1')}, "
                f"置信度: {p.get('confidence', '中')}, 证据数: {p.get('evidence_count', 0)})\n"
                f"   描述: {p['description']}\n"
                f"   证据: {evidence_text}"
            )

        prompt = f"""你是一个资深产品经理。基于以下用户反馈问题，生成产品需求文档。

**重要：必须严格基于下面的问题列表生成需求。如果没有识别到问题，返回空数组。不得编造、推测或基于应用一般特性自行创造需求。**

应用信息：
- 名称: {app_info.get('app_name', 'Unknown')}
- 当前评分: {app_info.get('average_rating', 'N/A')}
- 评分人数: {app_info.get('rating_count', 'N/A')}
- 版本: {app_info.get('version', 'N/A')}

识别的核心问题（每个问题前面是编号 1-N，关联问题时请使用此编号）：
{chr(10).join(problem_summary)}

请基于上述问题生成产品需求，每个需求包含：
1. 需求ID (REQ-001 格式)
2. 需求标题
3. 需求描述
4. 优先级 (P0/P1/P2)
5. 关联问题（填写问题标题）
6. **problem_index (关键！填入它关联的问题编号 1-N)**
7. 验收标准

请以 JSON 格式返回：
{{
  "requirements": [
    {{
      "id": "REQ-001",
      "title": "需求标题",
      "description": "详细描述",
      "priority": "P0|P1|P2",
      "related_problem": "关联问题标题",
      "problem_index": 1,
      "acceptance_criteria": ["标准1", "标准2"]
    }}
  ]
}}

**严格要求：**
1. 每个需求必须基于上面的问题列表生成
2. problem_index 必须准确对应问题编号
3. 不得编造任何不在问题列表中的需求
只返回 JSON，不要其他文字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 生成需求")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.7, max_tokens=3000)

        if not response:
            return {"requirements": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)

            # 后处理：为每个需求自动从关联问题的 evidence_reviews 提取 source_review_ids
            requirements_list = result.get("requirements", [])
            problems_list = problems.get("problems", [])

            for req in requirements_list:
                # 优先用 problem_index 字段
                problem_idx = req.get("problem_index")
                related_problem = req.get("related_problem", "")

                evidence_ids = []

                # 方法1: 使用 problem_index 索引
                if problem_idx is not None and isinstance(problem_idx, int):
                    if 1 <= problem_idx <= len(problems_list):
                        p = problems_list[problem_idx - 1]
                        evidence_ids = [e.get("review_id") for e in p.get("evidence_reviews", []) if e.get("review_id")]
                        # 备用：从 source_review_ids 获取
                        if not evidence_ids:
                            evidence_ids = p.get("source_review_ids", [])

                # 方法2: 通过 related_problem 标题精确匹配
                if not evidence_ids and related_problem:
                    for p in problems_list:
                        if p.get("title", "") == related_problem:
                            evidence_ids = [e.get("review_id") for e in p.get("evidence_reviews", []) if e.get("review_id")]
                            if not evidence_ids:
                                evidence_ids = p.get("source_review_ids", [])
                            break

                # 方法3: 模糊匹配 related_problem
                if not evidence_ids and related_problem:
                    for p in problems_list:
                        if related_problem in p.get("title", "") or p.get("title", "") in related_problem:
                            evidence_ids = [e.get("review_id") for e in p.get("evidence_reviews", []) if e.get("review_id")]
                            if not evidence_ids:
                                evidence_ids = p.get("source_review_ids", [])
                            break

                # 方法4: 最后兜底 - 如果还是空，从 LLM 自己的 review_ids 取
                if not evidence_ids:
                    evidence_ids = req.get("source_review_ids", []) or req.get("review_ids", [])

                req["source_review_ids"] = evidence_ids

            if progress_callback:
                progress_callback(1.0, f"生成 {len(requirements_list)} 个需求")
            return result
        except Exception as e:
            # 记录失败详情
            print(f"[Generator] generate_requirements JSON解析失败: {e}")
            print(f"[Generator] 响应前1000字符: {response[:1000]}")
            print(f"[Generator] 响应后500字符: {response[-500:]}")
            return {"requirements": [], "error": str(e)}

    def plan_versions(self, requirements, progress_callback=None):
        """版本规划"""
        if progress_callback:
            progress_callback(0.0, "开始版本规划")

        # 关键检查：没有需求数据时直接返回空
        requirements_list = requirements.get("requirements", []) if requirements else []
        if not requirements_list:
            print(f"[Generator] ⚠️ 没有需求数据，无法规划版本")
            if progress_callback:
                progress_callback(1.0, "⚠️ 无需求数据，无法规划版本")
            return {
                "versions": [],
                "error": "没有需求数据，无法规划版本"
            }

        # 准备需求摘要
        req_summary = []
        for r in requirements_list:
            req_summary.append(f"- {r['id']}: {r['title']} (优先级: {r['priority']})")

        prompt = f"""你是一个资深产品经理。基于以下需求列表，制定版本规划。

**重要：必须严格基于下面的需求列表制定规划。不得编造需求。**

需求列表：
{chr(10).join(req_summary)}

请制定版本规划，每个版本包含：
1. 版本号 (v1.0, v1.1, v2.0 等)
2. 版本目标
3. 包含的需求ID列表（必须从上面需求列表中选取）
4. 预期发布时间（相对时间，如"第1个月"）

请以 JSON 格式返回：
{{
  "versions": [
    {{
      "version": "v1.0",
      "goal": "版本目标",
      "requirements": ["REQ-001", "REQ-002"],
      "timeline": "第1个月"
    }}
  ]
}}

**严格要求：requirements 字段必须从上面的需求列表中选取，不得编造不存在的需求ID。**
只返回 JSON，不要其他文字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 规划版本")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.5, max_tokens=2000)

        if not response:
            return {"versions": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)
            if progress_callback:
                progress_callback(1.0, f"规划 {len(result.get('versions', []))} 个版本")
            return result
        except Exception as e:
            return {"versions": [], "error": str(e)}

    def generate_test_cases(self, requirements, progress_callback=None):
        """生成测试用例"""
        if progress_callback:
            progress_callback(0.0, "开始生成测试用例")

        # 关键检查：没有需求数据时直接返回空
        requirements_list = requirements.get("requirements", []) if requirements else []
        if not requirements_list:
            print(f"[Generator] ⚠️ 没有需求数据，无法生成测试用例")
            if progress_callback:
                progress_callback(1.0, "⚠️ 无需求数据，无法生成测试用例")
            return {
                "test_cases": [],
                "error": "没有需求数据，无法生成测试用例"
            }

        # 准备需求摘要
        req_summary = []
        for r in requirements_list:
            criteria = "; ".join(r.get("acceptance_criteria", [])[:3])
            req_summary.append(
                f"- {r['id']}: {r['title']}\n"
                f"  描述: {r['description'][:100]}\n"
                f"  验收标准: {criteria}"
            )

        prompt = f"""你是一个资深测试工程师。基于以下产品需求，为每个需求生成2-3个核心测试用例。

**重要：必须严格基于下面的需求列表生成测试用例。不得编造需求。**

需求列表：
{chr(10).join(req_summary)}

每个测试用例包含：id (TC-001格式), requirement_id (必须从上面需求列表中选取), objective, steps (数组，3-4步), expected_result, priority (高/中/低)

只返回JSON，格式：
{{"test_cases": [{{"id": "TC-001", "requirement_id": "REQ-001", "objective": "...", "steps": ["步骤1", "步骤2", "步骤3"], "expected_result": "...", "priority": "高"}}]}}

**严格要求：requirement_id 字段必须从上面的需求ID列表中选取，不得编造不存在的需求ID。**
注意：简洁输出，不要冗长描述。每个测试用objective不超过30字，expected_result不超过50字。"""

        if progress_callback:
            progress_callback(0.3, "调用 LLM 生成测试用例")

        response = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.5, max_tokens=4000)

        if not response:
            return {"test_cases": [], "error": "LLM 调用失败"}

        try:
            result = self._extract_json(response)

            # 后处理：为每个测试用例从关联需求继承 source_review_ids
            test_cases_list = result.get("test_cases", [])
            requirements_list = requirements.get("requirements", [])
            req_map = {r.get("id", ""): r for r in requirements_list}

            for tc in test_cases_list:
                req_id = tc.get("requirement_id", "")
                req = req_map.get(req_id)
                if req:
                    # 从关联需求继承
                    tc["source_review_ids"] = req.get("source_review_ids", [])
                else:
                    tc["source_review_ids"] = []

            if progress_callback:
                progress_callback(1.0, f"生成 {len(test_cases_list)} 个测试用例")
            return result
        except Exception as e:
            return {"test_cases": [], "error": str(e)}

    def generate_prd(self, app_info, requirements, versions, problems, progress_callback=None):
        """生成 PRD 文档（Markdown 格式）"""
        if progress_callback:
            progress_callback(0.0, "开始生成 PRD")

        # 关键检查：没有数据时直接返回错误信息
        problems_list = problems.get("problems", []) if problems else []
        requirements_list = requirements.get("requirements", []) if requirements else []
        if not problems_list and not requirements_list:
            error_msg = "未抓取到评论数据或未识别到问题/需求，无法生成 PRD"
            print(f"[Generator] ⚠️ {error_msg}")
            if progress_callback:
                progress_callback(1.0, "⚠️ 无数据，无法生成 PRD")
            return {
                "content": f"# {app_info.get('app_name', 'Unknown')} 产品需求文档\n\n⚠️ **未抓取到评论数据，无法生成分析内容。**\n\n请检查输入的 App Store 链接是否正确，或稍后重试。",
                "error": error_msg
            }

        prd_lines = []
        prd_lines.append(f"# {app_info.get('app_name', 'Unknown')} 产品需求文档")
        prd_lines.append("")
        prd_lines.append("## 1. 背景")
        prd_lines.append("")
        prd_lines.append(f"- **应用名称**: {app_info.get('app_name', 'Unknown')}")
        prd_lines.append(f"- **当前版本**: {app_info.get('version', 'N/A')}")
        prd_lines.append(f"- **当前评分**: {app_info.get('average_rating', 'N/A')}")
        prd_lines.append(f"- **评分人数**: {app_info.get('rating_count', 'N/A')}")
        prd_lines.append("")

        if problems_list:
            prd_lines.append("## 2. 问题分析")
            prd_lines.append("")
            for idx, p in enumerate(problems_list, 1):
                prd_lines.append(f"### 2.{idx} {p['title']}")
                prd_lines.append(f"- **优先级**: {p.get('priority', 'P1')}")
                prd_lines.append(f"- **置信度**: {p.get('confidence', '中')}")
                prd_lines.append(f"- **证据数量**: {p.get('evidence_count', 0)} 条评论")
                prd_lines.append(f"- **描述**: {p['description']}")
                prd_lines.append("")

        if requirements_list:
            prd_lines.append("## 3. 需求列表")
            prd_lines.append("")
            for r in requirements_list:
                prd_lines.append(f"### {r['id']}: {r['title']}")
                prd_lines.append(f"- **优先级**: {r['priority']}")
                prd_lines.append(f"- **关联问题**: {r.get('related_problem', 'N/A')}")
                prd_lines.append(f"- **描述**: {r['description']}")
                if r.get("acceptance_criteria"):
                    prd_lines.append(f"- **验收标准**:")
                    for criteria in r["acceptance_criteria"]:
                        prd_lines.append(f"  - {criteria}")
                prd_lines.append("")

        if versions and versions.get("versions"):
            prd_lines.append("## 4. 版本规划")
            prd_lines.append("")
            for v in versions["versions"]:
                prd_lines.append(f"### {v['version']} - {v['goal']}")
                prd_lines.append(f"- **时间线**: {v.get('timeline', 'N/A')}")
                prd_lines.append(f"- **包含需求**: {', '.join(v.get('requirements', []))}")
                prd_lines.append("")

        prd_text = "\n".join(prd_lines)

        if progress_callback:
            progress_callback(1.0, "PRD 生成完成")

        return prd_text

    def _extract_json(self, text):
        """从 LLM 响应中提取 JSON（增强版：支持多种格式和错误修复）"""
        if not text:
            raise ValueError("响应为空")
        
        # 清理文本：移除可能的 markdown 标记
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
            # 跳过可能的语言标识
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
                # 方法5: 尝试修复常见的 JSON 错误
                fixed = self._fix_json(json_str)
                try:
                    return json.loads(fixed)
                except:
                    pass
        
        # 方法6: 尝试找到 [...] 数组
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except:
                pass
        
        # 记录失败的响应（用于调试）
        try:
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "data", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, "json_failures.log")
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n=== JSON 提取失败 | 时间: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"响应长度: {len(text)}\n")
                f.write(f"完整响应:\n{text}\n")
                f.write("=" * 80 + "\n")
        except:
            pass
        print(f"[Generator] JSON 提取失败，原始响应前500字符: {text[:500]}")
        raise ValueError(f"无法提取 JSON，响应长度: {len(text)}")
    
    def _fix_json(self, json_str):
        """尝试修复常见的 JSON 格式错误"""
        # 1. 移除尾部逗号
        json_str = json_str.rstrip()
        if json_str.endswith(","):
            json_str = json_str[:-1]
        
        # 2. 尝试补全未闭合的括号
        # 计算 { 和 } 的数量
        open_braces = json_str.count("{")
        close_braces = json_str.count("}")
        if open_braces > close_braces:
            json_str += "}" * (open_braces - close_braces)
        
        # 计算 [ 和 ] 的数量
        open_brackets = json_str.count("[")
        close_brackets = json_str.count("]")
        if open_brackets > close_brackets:
            json_str += "]" * (open_brackets - close_brackets)
        
        return json_str

    def generate_all(self, problems, app_info, progress_callback=None):
        """完整的生成流程"""
        # 1. 生成需求
        requirements = self.generate_requirements(problems, app_info, progress_callback)
        if "error" in requirements:
            return {"error": requirements["error"]}

        # 2. 版本规划
        versions = self.plan_versions(requirements, progress_callback)
        if "error" in versions:
            return {"error": versions["error"]}

        # 3. 生成测试用例
        test_cases = self.generate_test_cases(requirements, progress_callback)
        if "error" in test_cases:
            return {"error": test_cases["error"]}

        # 4. 生成 PRD
        prd = self.generate_prd(app_info, requirements, versions, problems, progress_callback)

        return {
            "requirements": requirements,
            "versions": versions,
            "test_cases": test_cases,
            "prd": prd
        }


if __name__ == "__main__":
    # 测试
    generator = RequirementGenerator()
    test_problems = {
        "problems": [
            {
                "title": "应用卡顿",
                "description": "用户反馈应用运行卡顿",
                "priority": "P0",
                "confidence": "高",
                "evidence_count": 10,
                "evidence_reviews": [
                    {"review_id": "1", "excerpt": "应用很卡"}
                ]
            }
        ]
    }
    test_app_info = {
        "app_name": "测试应用",
        "version": "1.0.0",
        "average_rating": 3.5,
        "rating_count": 1000
    }
    result = generator.generate_all(test_problems, test_app_info)
    print(json.dumps(result, ensure_ascii=False, indent=2))
