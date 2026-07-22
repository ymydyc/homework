"""
验证模块
验证从评论到测试用例的可追溯链
"""


class TraceabilityValidator:
    def validate(self, reviews, topics, problems, requirements, test_cases):
        """验证完整的追溯链"""
        validation_result = {
            "valid": True,
            "issues": [],
            "statistics": {}
        }

        # 1. 验证主题有评论支持
        topic_validation = self._validate_topics(topics, reviews)
        validation_result["topics"] = topic_validation

        # 2. 验证问题有主题支持
        problem_validation = self._validate_problems(problems, topics, reviews)
        validation_result["problems"] = problem_validation

        # 3. 验证需求有问题支持
        requirement_validation = self._validate_requirements(requirements, problems, reviews)
        validation_result["requirements"] = requirement_validation

        # 4. 验证测试用例有需求支持
        test_validation = self._validate_test_cases(test_cases, requirements, reviews)
        validation_result["test_cases"] = test_validation

        # 5. 统计汇总
        validation_result["statistics"] = {
            "total_reviews": len(reviews),
            "total_topics": len(topics.get("topics", [])),
            "total_problems": len(problems.get("problems", [])),
            "total_requirements": len(requirements.get("requirements", [])),
            "total_test_cases": len(test_cases.get("test_cases", [])),
            "traceability_score": self._calculate_traceability_score(validation_result)
        }

        # 6. 构建可追溯链（包含完整的评论内容）
        validation_result["traceability_chain"] = self._build_traceability_chain(
            topics, problems, requirements, test_cases, reviews
        )

        # 判断整体验证结果
        if validation_result["topics"]["issues"] or \
           validation_result["problems"]["issues"] or \
           validation_result["requirements"]["issues"] or \
           validation_result["test_cases"]["issues"]:
            validation_result["valid"] = False

        return validation_result

    def _validate_topics(self, topics, reviews):
        """验证主题有评论支持"""
        issues = []
        review_ids = {r["review_id"] for r in reviews}

        for topic in topics.get("topics", []):
            topic_review_ids = topic.get("review_ids", [])
            # 检查是否有评论支持
            if not topic_review_ids:
                issues.append({
                    "type": "warning",
                    "message": f"主题 '{topic.get('name', 'Unknown')}' 没有关联评论"
                })
            # 检查评论ID是否存在
            invalid_ids = [rid for rid in topic_review_ids if rid not in review_ids]
            if invalid_ids:
                issues.append({
                    "type": "warning",
                    "message": f"主题 '{topic.get('name', 'Unknown')}' 引用了不存在的评论ID: {invalid_ids[:3]}"
                })

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }

    def _validate_problems(self, problems, topics, reviews):
        """验证问题有主题支持"""
        issues = []
        topic_names = {t.get("name", "") for t in topics.get("topics", [])}

        for problem in problems.get("problems", []):
            related_topics = problem.get("related_topics", [])
            # 检查是否有关联主题
            if not related_topics:
                issues.append({
                    "type": "warning",
                    "message": f"问题 '{problem.get('title', 'Unknown')}' 没有关联主题"
                })
            # 检查主题是否存在
            invalid_topics = [t for t in related_topics if t not in topic_names]
            if invalid_topics:
                issues.append({
                    "type": "warning",
                    "message": f"问题 '{problem.get('title', 'Unknown')}' 引用了不存在的主题: {invalid_topics[:3]}"
                })

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }

    def _validate_requirements(self, requirements, problems, reviews):
        """验证需求有问题支持"""
        issues = []
        problem_titles = {p.get("title", "") for p in problems.get("problems", [])}
        review_ids = {r["review_id"] for r in reviews}

        for req in requirements.get("requirements", []):
            related_problem = req.get("related_problem", "")
            # 检查是否有关联问题
            if not related_problem:
                issues.append({
                    "type": "error",
                    "message": f"需求 '{req.get('id', 'Unknown')}' 没有关联问题"
                })
            # 检查问题是否存在
            elif related_problem not in problem_titles:
                issues.append({
                    "type": "warning",
                    "message": f"需求 '{req.get('id', 'Unknown')}' 引用了不存在的问题: {related_problem}"
                })
            # 检查是否有来源评论
            source_review_ids = req.get("source_review_ids", [])
            if not source_review_ids:
                issues.append({
                    "type": "warning",
                    "message": f"需求 '{req.get('id', 'Unknown')}' 没有来源评论"
                })
            else:
                # 检查来源评论是否存在
                invalid_ids = [rid for rid in source_review_ids if rid not in review_ids]
                if invalid_ids:
                    issues.append({
                        "type": "warning",
                        "message": f"需求 '{req.get('id', 'Unknown')}' 引用了不存在的评论ID: {invalid_ids[:3]}"
                    })

        return {
            "valid": len([i for i in issues if i["type"] == "error"]) == 0,
            "issues": issues
        }

    def _validate_test_cases(self, test_cases, requirements, reviews):
        """验证测试用例有需求支持"""
        issues = []
        req_ids = {r.get("id", "") for r in requirements.get("requirements", [])}

        for tc in test_cases.get("test_cases", []):
            req_id = tc.get("requirement_id", "")
            # 检查是否有关联需求
            if not req_id:
                issues.append({
                    "type": "error",
                    "message": f"测试用例 '{tc.get('id', 'Unknown')}' 没有关联需求"
                })
            # 检查需求是否存在
            elif req_id not in req_ids:
                issues.append({
                    "type": "error",
                    "message": f"测试用例 '{tc.get('id', 'Unknown')}' 引用了不存在的需求: {req_id}"
                })
            # 检查是否有测试步骤
            if not tc.get("steps"):
                issues.append({
                    "type": "warning",
                    "message": f"测试用例 '{tc.get('id', 'Unknown')}' 没有测试步骤"
                })

        return {
            "valid": len([i for i in issues if i["type"] == "error"]) == 0,
            "issues": issues
        }

    def _calculate_traceability_score(self, validation_result):
        """计算可追溯性得分"""
        total_checks = 4
        passed_checks = 0

        if validation_result["topics"]["valid"]:
            passed_checks += 1
        if validation_result["problems"]["valid"]:
            passed_checks += 1
        if validation_result["requirements"]["valid"]:
            passed_checks += 1
        if validation_result["test_cases"]["valid"]:
            passed_checks += 1

        return round(passed_checks / total_checks * 100, 2)

    def _build_traceability_chain(self, topics, problems, requirements, test_cases, reviews):
        """构建完整的可追溯链，每个节点都包含关联的评论内容"""
        # 构建评论索引（按 review_id 索引）
        review_index = {r["review_id"]: r for r in reviews}

        chain = {
            "topics": [],
            "problems": [],
            "requirements": [],
            "test_cases": []
        }

        # 1. 主题 -> 评论
        for topic in topics.get("topics", []):
            topic_review_ids = topic.get("review_ids", [])
            source_reviews = []
            for rid in topic_review_ids:
                if rid in review_index:
                    r = review_index[rid]
                    source_reviews.append({
                        "review_id": r.get("review_id", ""),
                        "rating": r.get("rating", 0),
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "author": r.get("author", ""),
                        "date": r.get("date", ""),
                        "version": r.get("version", "")
                    })
            chain["topics"].append({
                "id": topic.get("id", ""),
                "name": topic.get("name", ""),
                "description": topic.get("description", ""),
                "severity": topic.get("severity", ""),
                "frequency": topic.get("frequency", ""),
                "source_reviews": source_reviews
            })

        # 2. 问题 -> 主题 -> 评论
        for problem in problems.get("problems", []):
            related_topics = problem.get("related_topics", [])
            # 找到关联主题下的所有评论
            problem_reviews = []
            for topic in chain["topics"]:
                if topic["name"] in related_topics:
                    for review in topic["source_reviews"]:
                        if review not in problem_reviews:
                            problem_reviews.append(review)
            # 如果有关联的 review_ids 直接使用
            for rid in problem.get("review_ids", []):
                if rid in review_index:
                    r = review_index[rid]
                    review_data = {
                        "review_id": r.get("review_id", ""),
                        "rating": r.get("rating", 0),
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "author": r.get("author", ""),
                        "date": r.get("date", ""),
                        "version": r.get("version", "")
                    }
                    if review_data not in problem_reviews:
                        problem_reviews.append(review_data)

            chain["problems"].append({
                "id": problem.get("id", ""),
                "title": problem.get("title", ""),
                "description": problem.get("description", ""),
                "priority": problem.get("priority", ""),
                "confidence": problem.get("confidence", ""),
                "related_topics": related_topics,
                "source_reviews": problem_reviews
            })

        # 3. 需求 -> 问题 -> 评论
        for req in requirements.get("requirements", []):
            source_review_ids = req.get("source_review_ids", [])
            source_reviews = []
            for rid in source_review_ids:
                if rid in review_index:
                    r = review_index[rid]
                    source_reviews.append({
                        "review_id": r.get("review_id", ""),
                        "rating": r.get("rating", 0),
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "author": r.get("author", ""),
                        "date": r.get("date", ""),
                        "version": r.get("version", "")
                    })

            # 如果没有 source_review_ids，从关联问题获取
            if not source_reviews:
                related_problem = req.get("related_problem", "")
                for p in chain["problems"]:
                    if p["title"] == related_problem:
                        source_reviews = p["source_reviews"]
                        break

            chain["requirements"].append({
                "id": req.get("id", ""),
                "title": req.get("title", ""),
                "description": req.get("description", ""),
                "priority": req.get("priority", ""),
                "related_problem": req.get("related_problem", ""),
                "acceptance_criteria": req.get("acceptance_criteria", []),
                "source_reviews": source_reviews
            })

        # 4. 测试用例 -> 需求 -> 评论
        for tc in test_cases.get("test_cases", []):
            req_id = tc.get("requirement_id", "")
            source_reviews = []
            # 找到关联需求下的评论
            for req in chain["requirements"]:
                if req["id"] == req_id:
                    source_reviews = req["source_reviews"]
                    break

            chain["test_cases"].append({
                "id": tc.get("id", ""),
                "requirement_id": req_id,
                "objective": tc.get("objective", ""),
                "preconditions": tc.get("preconditions", ""),
                "steps": tc.get("steps", []),
                "expected_result": tc.get("expected_result", ""),
                "priority": tc.get("priority", ""),
                "source_reviews": source_reviews
            })

        return chain

    def generate_report(self, validation_result):
        """生成验证报告"""
        lines = []
        lines.append("# 可追溯性验证报告")
        lines.append("")
        lines.append(f"## 总体结果: {'通过' if validation_result['valid'] else '存在问题'}")
        lines.append(f"可追溯性得分: {validation_result['statistics']['traceability_score']}%")
        lines.append("")

        lines.append("## 统计信息")
        lines.append(f"- 评论总数: {validation_result['statistics']['total_reviews']}")
        lines.append(f"- 主题总数: {validation_result['statistics']['total_topics']}")
        lines.append(f"- 问题总数: {validation_result['statistics']['total_problems']}")
        lines.append(f"- 需求总数: {validation_result['statistics']['total_requirements']}")
        lines.append(f"- 测试用例总数: {validation_result['statistics']['total_test_cases']}")
        lines.append("")

        # 主题验证
        lines.append("## 主题验证")
        if validation_result["topics"]["valid"]:
            lines.append("✅ 所有主题都有评论支持")
        else:
            for issue in validation_result["topics"]["issues"]:
                lines.append(f"- {issue['type'].upper()}: {issue['message']}")
        lines.append("")

        # 问题验证
        lines.append("## 问题验证")
        if validation_result["problems"]["valid"]:
            lines.append("✅ 所有问题都有主题支持")
        else:
            for issue in validation_result["problems"]["issues"]:
                lines.append(f"- {issue['type'].upper()}: {issue['message']}")
        lines.append("")

        # 需求验证
        lines.append("## 需求验证")
        if validation_result["requirements"]["valid"]:
            lines.append("✅ 所有需求都有问题支持")
        else:
            for issue in validation_result["requirements"]["issues"]:
                lines.append(f"- {issue['type'].upper()}: {issue['message']}")
        lines.append("")

        # 测试用例验证
        lines.append("## 测试用例验证")
        if validation_result["test_cases"]["valid"]:
            lines.append("✅ 所有测试用例都有需求支持")
        else:
            for issue in validation_result["test_cases"]["issues"]:
                lines.append(f"- {issue['type'].upper()}: {issue['message']}")
        lines.append("")

        return "\n".join(lines)
