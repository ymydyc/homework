// 全局变量
let currentTaskId = null;
let currentReviews = [];
let currentPage = 1;
let currentResults = null;  // 存储当前分析结果，用于溯源
const reviewsPerPage = 10;

// DOM 元素
const appUrlInput = document.getElementById('app-url');
const analysisTargetInput = document.getElementById('analysis-target');
const importFileInput = document.getElementById('import-file');
const startBtn = document.getElementById('start-btn');
const progressSection = document.getElementById('progress-section');
const resultSection = document.getElementById('result-section');
const reviewsSection = document.getElementById('reviews-section');
const traceModal = document.getElementById('trace-modal');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    startBtn.addEventListener('click', handleStart);
    importFileInput.addEventListener('change', handleFileImport);

    // 点击模态框外部关闭
    if (traceModal) {
        traceModal.addEventListener('click', (e) => {
            if (e.target === traceModal) {
                closeTraceModal();
            }
        });
    }

    // ESC 键关闭模态框
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeTraceModal();
        }
    });
});

// 处理开始按钮
async function handleStart() {
    const url = appUrlInput.value.trim();
    const analysisTarget = analysisTargetInput.value.trim();

    if (!url) {
        alert('请输入 App Store 链接');
        return;
    }

    startBtn.disabled = true;
    startBtn.textContent = '分析中...';

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                analysis_target: analysisTarget
            })
        });

        const data = await response.json();

        if (response.ok) {
            currentTaskId = data.task_id;
            progressSection.style.display = 'block';
            startPolling();
        } else {
            alert(data.error || '启动分析失败');
            startBtn.disabled = false;
            startBtn.textContent = '开始分析';
        }
    } catch (error) {
        alert('网络错误: ' + error.message);
        startBtn.disabled = false;
        startBtn.textContent = '开始分析';
    }
}

// 处理文件导入
async function handleFileImport() {
    const file = importFileInput.files[0];
    if (!file) return;

    const analysisTarget = analysisTargetInput.value.trim();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('analysis_target', analysisTarget);

    startBtn.disabled = true;
    startBtn.textContent = '导入中...';

    try {
        const response = await fetch('/api/import', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            currentTaskId = data.task_id;
            alert(`导入成功！共导入 ${data.count} 条评论`);
            // 直接显示结果
            await loadResults();
        } else {
            alert(data.error || '导入失败');
        }
    } catch (error) {
        alert('网络错误: ' + error.message);
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = '开始分析';
    }
}

// 轮询任务状态
function startPolling() {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${currentTaskId}`);
            const data = await response.json();

            updateProgress(data);

            if (data.status === 'completed') {
                clearInterval(interval);
                await loadResults();
            } else if (data.status === 'failed') {
                clearInterval(interval);
                alert('分析失败: ' + (data.error || '未知错误'));
                startBtn.disabled = false;
                startBtn.textContent = '开始分析';
            }
        } catch (error) {
            console.error('轮询失败:', error);
        }
    }, 1000);
}

// 更新进度显示
function updateProgress(data) {
    const progressFill = document.getElementById('progress-fill');
    const currentStage = document.getElementById('current-stage');
    const progressPercent = document.getElementById('progress-percent');
    const progressMessage = document.getElementById('progress-message');

    const percent = Math.round((data.progress || 0) * 100);
    progressFill.style.width = percent + '%';
    progressFill.textContent = percent + '%';
    currentStage.textContent = data.stage || '处理中';
    progressPercent.textContent = percent + '%';
    progressMessage.textContent = data.message || '';
}

// 加载分析结果
async function loadResults() {
    try {
        const response = await fetch(`/api/result/${currentTaskId}`);
        const data = await response.json();

        if (response.ok) {
            displayResults(data);
            resultSection.style.display = 'block';
            await loadReviews();
            reviewsSection.style.display = 'block';
            startBtn.disabled = false;
            startBtn.textContent = '开始新分析';
        } else {
            alert('加载结果失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        alert('网络错误: ' + error.message);
    }
}

// 显示分析结果
function displayResults(data) {
    const results = data.results || {};
    currentResults = data;  // 保存到全局变量供溯源使用

    // 显示应用信息
    if (results.scrape_raw_reviews) {
        const summary = data.summary || {};
        const appInfo = summary.app_info || {};
        displayAppInfo(appInfo);
    }

    // 显示统计数据
    if (results.clean_statistics) {
        displayStatistics(results.clean_statistics);
    }

    // 显示主题分析
    if (results.analyze_topics) {
        displayTopics(results.analyze_topics);
    }

    // 显示问题列表
    if (results.analyze_problems) {
        displayProblems(results.analyze_problems);
    }

    // 显示需求列表
    if (results.generate_requirements) {
        displayRequirements(results.generate_requirements);
    }

    // 显示版本规划
    if (results.generate_versions) {
        displayVersions(results.generate_versions);
    }

    // 显示测试用例
    if (results.generate_test_cases) {
        displayTestCases(results.generate_test_cases);
    }

    // 显示 PRD
    if (results.generate_prd) {
        displayPRD(results.generate_prd.content || '');
    }
}

// 显示应用信息
function displayAppInfo(appInfo) {
    const container = document.getElementById('app-info');
    container.innerHTML = `
        <div class="app-info-item">
            <div class="app-info-label">应用名称</div>
            <div class="app-info-value">${appInfo.app_name || 'N/A'}</div>
        </div>
        <div class="app-info-item">
            <div class="app-info-label">当前版本</div>
            <div class="app-info-value">${appInfo.version || 'N/A'}</div>
        </div>
        <div class="app-info-item">
            <div class="app-info-label">平均评分</div>
            <div class="app-info-value">${appInfo.average_rating ? appInfo.average_rating.toFixed(1) : 'N/A'}</div>
        </div>
        <div class="app-info-item">
            <div class="app-info-label">评分人数</div>
            <div class="app-info-value">${appInfo.rating_count || 'N/A'}</div>
        </div>
    `;
}

// 显示统计数据
function displayStatistics(stats) {
    const container = document.getElementById('statistics');
    container.innerHTML = `
        <div class="stat-item">
            <div class="stat-value">${stats.total || 0}</div>
            <div class="stat-label">评论总数</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">${stats.avg_rating || 0}</div>
            <div class="stat-label">平均评分</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">${stats.versions ? stats.versions.length : 0}</div>
            <div class="stat-label">版本数</div>
        </div>
    `;
}

// 显示主题分析
function displayTopics(topics) {
    const container = document.getElementById('topics');
    const topicList = topics.topics || [];

    if (topicList.length === 0) {
        container.innerHTML = '<p>暂无主题分析数据</p>';
        return;
    }

    container.innerHTML = topicList.map((topic, idx) => `
        <div class="topic-item">
            <div class="topic-header">
                <div class="topic-name">${topic.name || '未命名主题'}</div>
                <div class="topic-badges">
                    <span class="badge badge-severity-${topic.severity || 'low'}">${topic.severity || '低'}</span>
                    <span class="badge badge-frequency">${topic.frequency || '低'}频</span>
                    <button class="btn-trace" onclick="showTrace('topic', ${idx})">📋 溯源 (${(topic.review_ids || []).length})</button>
                </div>
            </div>
            <div class="topic-description">${topic.description || ''}</div>
        </div>
    `).join('');
}

// 显示问题列表
function displayProblems(problems) {
    const container = document.getElementById('problems');
    const problemList = problems.problems || [];

    if (problemList.length === 0) {
        container.innerHTML = '<p>暂无问题数据</p>';
        return;
    }

    container.innerHTML = problemList.map((problem, idx) => `
        <div class="problem-item">
            <div class="problem-header">
                <div class="problem-title">${problem.title || '未命名问题'}</div>
                <div>
                    <span class="problem-priority priority-${(problem.priority || 'p1').toLowerCase()}">${problem.priority || 'P1'}</span>
                    <button class="btn-trace" onclick="showTrace('problem', ${idx})">📋 溯源</button>
                </div>
            </div>
            <div class="problem-description">${problem.description || ''}</div>
            <div class="problem-meta">
                <span>置信度: ${problem.confidence || '中'}</span>
                <span>证据数: ${problem.evidence_count || 0}</span>
            </div>
        </div>
    `).join('');
}

// 显示需求列表
function displayRequirements(requirements) {
    const container = document.getElementById('requirements');
    const reqList = requirements.requirements || [];

    if (reqList.length === 0) {
        container.innerHTML = '<p>暂无需求数据</p>';
        return;
    }

    container.innerHTML = reqList.map((req, idx) => `
        <div class="requirement-item">
            <div class="requirement-header">
                <span class="requirement-id">${req.id || ''}</span>
                <div>
                    <span class="problem-priority priority-${(req.priority || 'p1').toLowerCase()}">${req.priority || 'P1'}</span>
                    <button class="btn-trace" onclick="showTrace('requirement', ${idx})">📋 溯源</button>
                </div>
            </div>
            <div class="requirement-title">${req.title || '未命名需求'}</div>
            <div class="requirement-description">${req.description || ''}</div>
            ${req.acceptance_criteria && req.acceptance_criteria.length > 0 ? `
                <div class="requirement-criteria">
                    <div class="requirement-criteria-title">验收标准:</div>
                    <ul>
                        ${req.acceptance_criteria.map(c => `<li>${c}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        </div>
    `).join('');
}

// 显示版本规划
function displayVersions(versions) {
    const container = document.getElementById('versions');
    const versionList = versions.versions || [];

    if (versionList.length === 0) {
        container.innerHTML = '<p>暂无版本规划</p>';
        return;
    }

    container.innerHTML = versionList.map(version => `
        <div class="version-item">
            <div class="version-header">
                <span class="version-number">${version.version || ''}</span>
                <span class="version-timeline">${version.timeline || ''}</span>
            </div>
            <div class="version-goal">${version.goal || ''}</div>
            <div class="version-requirements">包含需求: ${(version.requirements || []).join(', ')}</div>
        </div>
    `).join('');
}

// 显示测试用例
function displayTestCases(testCases) {
    const container = document.getElementById('test-cases');
    const tcList = testCases.test_cases || [];

    if (tcList.length === 0) {
        container.innerHTML = '<p>暂无测试用例</p>';
        return;
    }

    container.innerHTML = tcList.map((tc, idx) => `
        <div class="test-case-item">
            <div class="test-case-header">
                <span class="test-case-id">${tc.id || ''}</span>
                <div>
                    <span class="test-case-priority">${tc.priority || '中'}</span>
                    <button class="btn-trace" onclick="showTrace('test_case', ${idx})">📋 溯源</button>
                </div>
            </div>
            <div class="test-case-objective">${tc.objective || ''}</div>
            ${tc.steps && tc.steps.length > 0 ? `
                <div class="test-case-steps">
                    <div class="test-case-steps-title">测试步骤:</div>
                    <ol>
                        ${tc.steps.map(s => `<li>${s}</li>`).join('')}
                    </ol>
                </div>
            ` : ''}
            <div class="test-case-expected">预期结果: ${tc.expected_result || ''}</div>
        </div>
    `).join('');
}

// 显示 PRD
function displayPRD(content) {
    const container = document.getElementById('prd-content');
    container.textContent = content || '暂无 PRD 文档';
}

// 显示验证报告
function displayValidation(validation) {
    const container = document.getElementById('validation');
    const score = validation.statistics?.traceability_score || 0;

    let html = `
        <div class="validation-score">可追溯性得分: ${score}%</div>
    `;

    const allIssues = [
        ...(validation.topics?.issues || []),
        ...(validation.problems?.issues || []),
        ...(validation.requirements?.issues || []),
        ...(validation.test_cases?.issues || [])
    ];

    if (allIssues.length > 0) {
        html += '<div class="validation-issues">';
        allIssues.forEach(issue => {
            html += `<div class="validation-issue ${issue.type}">${issue.message}</div>`;
        });
        html += '</div>';
    } else {
        html += '<p style="text-align: center; color: #27ae60;">✅ 所有追溯链验证通过</p>';
    }

    container.innerHTML = html;
}

// 加载评论列表
async function loadReviews(page = 1) {
    try {
        const response = await fetch(`/api/reviews/${currentTaskId}?page=${page}&per_page=${reviewsPerPage}`);
        const data = await response.json();

        if (response.ok) {
            currentReviews = data.reviews;
            currentPage = page;
            displayReviews(data);
        }
    } catch (error) {
        console.error('加载评论失败:', error);
    }
}

// 显示评论列表
function displayReviews(data) {
    const container = document.getElementById('reviews-list');
    const reviews = data.reviews || [];

    if (reviews.length === 0) {
        container.innerHTML = '<p>暂无评论数据</p>';
        return;
    }

    container.innerHTML = reviews.map(review => `
        <div class="review-item">
            <div class="review-header">
                <span class="review-rating">${'★'.repeat(review.rating || 0)}${'☆'.repeat(5 - (review.rating || 0))}</span>
                <span class="review-meta">${review.date || ''}</span>
            </div>
            <div class="review-title">${review.title || ''}</div>
            <div class="review-content">${review.content || ''}</div>
            <div class="review-meta">
                版本: ${review.version || 'N/A'} | 作者: ${review.author || '匿名'}
            </div>
        </div>
    `).join('');

    // 显示分页
    displayPagination(data.total, data.page, data.per_page);
}

// 显示分页
function displayPagination(total, currentPage, perPage) {
    const container = document.getElementById('reviews-pagination');
    const totalPages = Math.ceil(total / perPage);

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';

    // 上一页
    if (currentPage > 1) {
        html += `<button onclick="loadReviews(${currentPage - 1})">上一页</button>`;
    }

    // 页码
    for (let i = 1; i <= totalPages; i++) {
        if (i === currentPage) {
            html += `<button class="active">${i}</button>`;
        } else if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `<button onclick="loadReviews(${i})">${i}</button>`;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += `<button disabled>...</button>`;
        }
    }

    // 下一页
    if (currentPage < totalPages) {
        html += `<button onclick="loadReviews(${currentPage + 1})">下一页</button>`;
    }

    container.innerHTML = html;
}

// 导出数据
function exportData(format) {
    if (!currentTaskId) {
        alert('没有可导出的数据');
        return;
    }

    window.open(`/api/export/${currentTaskId}/${format}`, '_blank');
}

// 显示溯源弹窗
async function showTrace(type, index) {
    if (!currentResults || !currentTaskId) {
        alert('暂无分析结果');
        return;
    }

    const results = currentResults.results || {};

    let sourceReviewIds = [];
    let title = '';
    let summary = '';
    let itemId = '';

    // 根据类型从 results 中获取对应的 source_review_ids
    if (type === 'requirement') {
        const requirements = results.generate_requirements?.requirements || [];
        const item = requirements[index];
        if (!item) {
            alert('未找到该需求');
            return;
        }
        sourceReviewIds = item.source_review_ids || [];
        title = `需求溯源: ${item.id} - ${item.title}`;
        summary = item.description || '';
        itemId = item.id;
    } else if (type === 'test_case') {
        const testCases = results.generate_test_cases?.test_cases || [];
        const item = testCases[index];
        if (!item) {
            alert('未找到该测试用例');
            return;
        }
        sourceReviewIds = item.source_review_ids || [];
        title = `测试用例溯源: ${item.id} - ${item.objective}`;
        summary = item.objective || '';
        itemId = item.id;
    } else if (type === 'problem') {
        const problems = results.analyze_problems?.problems || [];
        const item = problems[index];
        if (!item) {
            alert('未找到该问题');
            return;
        }
        // 问题用 evidence_reviews 里的 review_id
        sourceReviewIds = (item.evidence_reviews || []).map(e => e.review_id);
        title = `问题溯源: ${item.title}`;
        summary = item.description || '';
        itemId = item.title;
    } else if (type === 'topic') {
        const ratingResults = results.analyze_rating_results || [];
        // 主题可能跨多个rating_result
        const allTopics = [];
        for (const rr of ratingResults) {
            const topics = rr.topics?.topics || [];
            for (const t of topics) {
                allTopics.push(t);
            }
        }
        const item = allTopics[index];
        if (!item) {
            alert('未找到该主题');
            return;
        }
        sourceReviewIds = item.review_ids || [];
        title = `主题溯源: ${item.name}`;
        summary = item.description || '';
        itemId = item.name;
    } else {
        alert('未知的溯源类型');
        return;
    }

    // 从后端获取所有评论，然后根据 sourceReviewIds 过滤
    let sourceReviews = [];
    try {
        const response = await fetch(`/api/reviews/${currentTaskId}?page=1&per_page=10000`);
        const data = await response.json();
        const allReviews = data.reviews || [];
        const reviewMap = {};
        for (const r of allReviews) {
            reviewMap[r.review_id] = r;
        }
        for (const rid of sourceReviewIds) {
            if (reviewMap[rid]) {
                sourceReviews.push(reviewMap[rid]);
            }
        }
    } catch (e) {
        console.error('获取评论失败:', e);
    }

    renderTraceModal(title, summary, sourceReviews);
}

// 渲染溯源弹窗
function renderTraceModal(title, summary, sourceReviews) {
    const modal = document.getElementById('trace-modal');
    const modalTitle = document.getElementById('trace-modal-title');
    const modalBody = document.getElementById('trace-modal-body');

    modalTitle.textContent = title;

    let html = '';

    // 显示结论摘要
    if (summary) {
        html += `<div class="trace-summary">`;
        html += `<div class="trace-summary-title">AI 分析结论</div>`;
        html += `<div class="trace-summary-text">${escapeHtml(summary)}</div>`;
        html += `</div>`;
    }

    // 显示源评论
    if (sourceReviews.length === 0) {
        html += `<div class="trace-empty">该结论暂无关联的源评论（可能因评论数据中不包含相应 review_id）</div>`;
    } else {
        html += `<div class="trace-count">📋 共关联 ${sourceReviews.length} 条源评论</div>`;
        html += `<div class="trace-reviews">`;

        sourceReviews.forEach((review) => {
            const rating = review.rating || 0;
            const stars = '★'.repeat(rating) + '☆'.repeat(5 - rating);

            html += `<div class="trace-review">`;
            html += `<div class="trace-review-header">`;
            html += `<div class="trace-review-rating">${stars}</div>`;
            html += `<div class="trace-review-meta">${escapeHtml(review.date || '')}</div>`;
            html += `</div>`;

            if (review.title) {
                html += `<div class="trace-review-title">${escapeHtml(review.title)}</div>`;
            }

            html += `<div class="trace-review-content">${escapeHtml(review.content || '')}</div>`;
            html += `<div class="trace-review-footer">`;
            html += `<span>作者: ${escapeHtml(review.author || '匿名')}</span>`;
            if (review.version) {
                html += ` | <span>版本: ${escapeHtml(review.version)}</span>`;
            }
            if (review.review_id) {
                html += ` | <span>ID: ${escapeHtml(review.review_id)}</span>`;
            }
            html += `</div>`;
            html += `</div>`;
        });

        html += `</div>`;
    }

    modalBody.innerHTML = html;
    modal.style.display = 'flex';
}

// 关闭溯源弹窗
function closeTraceModal() {
    const modal = document.getElementById('trace-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
