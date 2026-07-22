"""
Flask 主应用
提供 API 接口和静态文件服务
"""
import uuid
import json
import os
import threading
import csv
import io
from flask import Flask, request, jsonify, send_from_directory, send_file
from config import Config
from models.database import (
    init_db, save_task, update_task_status, get_task,
    save_reviews, get_reviews, save_analysis_result, get_analysis_results
)
from services.scraper import AppStoreScraper
from services.cleaner import ReviewCleaner
from services.analyzer import ReviewAnalyzer
from services.generator import RequirementGenerator
from services.validator import TraceabilityValidator

app = Flask(__name__, static_folder="static", static_url_path="/static")

# 初始化数据库
init_db()

# 进度存储（内存中，用于实时推送）
task_progress = {}


def run_analysis_pipeline(task_id, url, analysis_target):
    """后台执行完整分析流程"""
    try:
        scraper = AppStoreScraper()
        cleaner = ReviewCleaner()
        analyzer = ReviewAnalyzer()
        generator = RequirementGenerator()
        validator = TraceabilityValidator()

        # ===== 阶段1: 数据收集 =====
        update_task_status(task_id, "running", progress=0, stage="数据收集")
        task_progress[task_id] = {"stage": "数据收集", "progress": 0, "message": "开始抓取评论"}

        def scrape_progress(p, msg):
            task_progress[task_id] = {"stage": "数据收集", "progress": p * 0.1, "message": msg}

        scrape_result = scraper.scrape(url, analysis_target, progress_callback=scrape_progress)
        app_info = scrape_result["app_info"]
        raw_reviews = scrape_result["reviews"]

        update_task_status(task_id, "running", progress=0.1, stage="数据收集",
                          summary=json.dumps({"app_info": app_info, "raw_count": len(raw_reviews)}, ensure_ascii=False))
        save_analysis_result(task_id, "scrape", "raw_reviews", {"count": len(raw_reviews), "sample": raw_reviews[:5]})

        # ===== 阶段2: 数据清理 =====
        task_progress[task_id] = {"stage": "数据清理", "progress": 0.15, "message": "开始清理数据"}

        def clean_progress(p, msg):
            task_progress[task_id] = {"stage": "数据清理", "progress": 0.15 + p * 0.1, "message": msg}

        cleaned_reviews = cleaner.clean_reviews(raw_reviews, progress_callback=clean_progress)
        stats = cleaner.get_statistics(cleaned_reviews)

        update_task_status(task_id, "running", progress=0.25, stage="数据清理")
        save_reviews(task_id, cleaned_reviews)
        save_analysis_result(task_id, "clean", "statistics", stats)
        save_analysis_result(task_id, "clean", "cleaned_reviews", {"count": len(cleaned_reviews), "reviews": cleaned_reviews})

        # ===== 阶段3: 数据分析（LLM 驱动）=====
        task_progress[task_id] = {"stage": "数据分析", "progress": 0.3, "message": "开始 LLM 分析"}

        def analyze_progress(p, msg):
            task_progress[task_id] = {"stage": "数据分析", "progress": 0.3 + p * 0.25, "message": msg}

        analysis_result = analyzer.analyze(cleaned_reviews, progress_callback=analyze_progress)

        if "error" in analysis_result:
            raise Exception(f"分析失败: {analysis_result['error']}")

        # 新的返回格式：rating_results, summary, problems
        rating_results = analysis_result.get("rating_results", [])
        summary = analysis_result.get("summary", {})
        problems = analysis_result.get("problems", {})

        update_task_status(task_id, "running", progress=0.55, stage="数据分析")
        save_analysis_result(task_id, "analyze", "rating_results", rating_results)
        save_analysis_result(task_id, "analyze", "summary", summary)
        save_analysis_result(task_id, "analyze", "problems", problems)

        # ===== 阶段4: 需求生成（LLM 驱动）=====
        task_progress[task_id] = {"stage": "需求生成", "progress": 0.6, "message": "开始生成需求和 PRD"}

        def gen_progress(p, msg):
            task_progress[task_id] = {"stage": "需求生成", "progress": 0.6 + p * 0.2, "message": msg}

        gen_result = generator.generate_all(problems, app_info, progress_callback=gen_progress)

        if "error" in gen_result:
            raise Exception(f"生成失败: {gen_result['error']}")

        requirements = gen_result.get("requirements", {})
        versions = gen_result.get("versions", {})
        test_cases = gen_result.get("test_cases", {})
        prd = gen_result.get("prd", "")

        update_task_status(task_id, "running", progress=0.8, stage="需求生成")
        save_analysis_result(task_id, "generate", "requirements", requirements)
        save_analysis_result(task_id, "generate", "versions", versions)
        save_analysis_result(task_id, "generate", "test_cases", test_cases)
        save_analysis_result(task_id, "generate", "prd", {"content": prd})

        # ===== 阶段5: 可追溯性验证 =====
        task_progress[task_id] = {"stage": "验证", "progress": 0.85, "message": "验证可追溯性"}

        # 从 rating_results 中构建 topics（用于验证）
        all_topics = {"topics": []}
        for rr in rating_results:
            if "topics" in rr and "topics" in rr["topics"]:
                all_topics["topics"].extend(rr["topics"]["topics"])

        validation_result = validator.validate(
            cleaned_reviews, all_topics, problems, requirements, test_cases
        )
        validation_report = validator.generate_report(validation_result)

        save_analysis_result(task_id, "validate", "validation", validation_result)
        save_analysis_result(task_id, "validate", "report", {"content": validation_report})

        # ===== 完成 =====
        update_task_status(task_id, "completed", progress=1.0, stage="完成",
                          summary=json.dumps({
                              "app_info": app_info,
                              "stats": stats,
                              "traceability_score": validation_result["statistics"]["traceability_score"]
                          }, ensure_ascii=False))
        task_progress[task_id] = {"stage": "完成", "progress": 1.0, "message": "分析完成"}

    except Exception as e:
        update_task_status(task_id, "failed", error=str(e))
        task_progress[task_id] = {"stage": "失败", "progress": 0, "message": str(e)}


# ===== 路由 =====

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """启动分析任务"""
    data = request.get_json()
    url = data.get("url", "").strip()
    analysis_target = data.get("analysis_target", "").strip()

    if not url:
        return jsonify({"error": "请提供 App Store 链接"}), 400

    # 验证 URL
    scraper = AppStoreScraper()
    try:
        normalized_url, app_id = scraper.normalize_url(url)
    except ValueError as e:
        return jsonify({
            "error": f"URL 格式错误: {str(e)}。请使用类似 https://apps.apple.com/cn/app/id123456 的格式"
        }), 400

    # 创建任务
    task_id = str(uuid.uuid4())[:8]
    save_task(task_id, app_id, "", analysis_target)

    # 启动后台线程
    thread = threading.Thread(target=run_analysis_pipeline, args=(task_id, url, analysis_target))
    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id, "status": "started"})


@app.route("/api/status/<task_id>")
def api_status(task_id):
    """获取任务状态"""
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    progress = task_progress.get(task_id, {})
    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["current_stage"],
        "error": task["error"],
        "message": progress.get("message", ""),
    })


@app.route("/api/result/<task_id>")
def api_result(task_id):
    """获取分析结果"""
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    if task["status"] != "completed":
        return jsonify({"error": "任务未完成", "status": task["status"]}), 400

    results = get_analysis_results(task_id)
    result_map = {}
    for r in results:
        key = f"{r['stage']}_{r['result_type']}"
        result_map[key] = r["result_data"]

    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "summary": json.loads(task["result_summary"]) if task["result_summary"] else {},
        "results": result_map
    })


@app.route("/api/reviews/<task_id>")
def api_reviews(task_id):
    """获取评论数据"""
    reviews = get_reviews(task_id)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    start = (page - 1) * per_page
    end = start + per_page
    return jsonify({
        "total": len(reviews),
        "page": page,
        "per_page": per_page,
        "reviews": reviews[start:end]
    })


@app.route("/api/import", methods=["POST"])
def api_import():
    """导入评论数据"""
    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400

    file = request.files["file"]
    filename = file.filename.lower()
    analysis_target = request.form.get("analysis_target", "")

    try:
        if filename.endswith(".json"):
            data = json.load(file.stream)
            if isinstance(data, list):
                reviews = data
            elif isinstance(data, dict) and "reviews" in data:
                reviews = data["reviews"]
            else:
                return jsonify({"error": "JSON 格式不正确，需要数组或包含 reviews 字段的对象"}), 400
        elif filename.endswith(".csv"):
            content = file.stream.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            reviews = list(reader)
        else:
            return jsonify({"error": "仅支持 JSON 和 CSV 格式"}), 400

        # 创建任务
        task_id = str(uuid.uuid4())[:8]
        app_id = "imported"
        save_task(task_id, app_id, "导入数据", analysis_target)

        # 清理并保存
        cleaner = ReviewCleaner()
        cleaned = cleaner.clean_reviews(reviews)
        save_reviews(task_id, cleaned)
        stats = cleaner.get_statistics(cleaned)

        update_task_status(task_id, "completed", progress=1.0, stage="导入完成",
                          summary=json.dumps({"stats": stats, "imported_count": len(cleaned)}, ensure_ascii=False))

        return jsonify({"task_id": task_id, "count": len(cleaned), "stats": stats})

    except Exception as e:
        return jsonify({"error": f"导入失败: {str(e)}"}), 400


@app.route("/api/export/<task_id>/<format>")
def api_export(task_id, format):
    """导出数据"""
    results = get_analysis_results(task_id)
    result_map = {}
    for r in results:
        key = f"{r['stage']}_{r['result_type']}"
        result_map[key] = r["result_data"]

    os.makedirs(Config.EXPORT_DIR, exist_ok=True)

    if format == "json":
        filepath = os.path.join(Config.EXPORT_DIR, f"{task_id}_result.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result_map, f, ensure_ascii=False, indent=2)
        return send_file(filepath, as_attachment=True)

    elif format == "csv":
        reviews = get_reviews(task_id)
        filepath = os.path.join(Config.EXPORT_DIR, f"{task_id}_reviews.csv")
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            if reviews:
                writer = csv.DictWriter(f, fieldnames=reviews[0].keys())
                writer.writeheader()
                writer.writerows(reviews)
        return send_file(filepath, as_attachment=True)

    elif format == "md":
        prd_data = result_map.get("generate_prd", {})
        prd_content = prd_data.get("content", "# 无 PRD 数据")
        filepath = os.path.join(Config.EXPORT_DIR, f"{task_id}_prd.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(prd_content)
        return send_file(filepath, as_attachment=True)

    return jsonify({"error": "不支持的格式"}), 400


if __name__ == "__main__":
    print(f"启动服务: http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
