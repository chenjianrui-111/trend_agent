const API_BASE = '/api/v1';

async function api(path, options = {}) {
    const resp = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    return resp.json();
}

async function refreshDashboard() {
    await Promise.all([loadStats(), loadPipelineRuns(), loadDrafts()]);
}

async function loadStats() {
    try {
        const stats = await api('/dashboard/stats');
        document.getElementById('stat-sources').textContent = stats.total_sources || 0;
        document.getElementById('stat-drafts').textContent = stats.total_drafts || 0;
        document.getElementById('stat-published').textContent = stats.total_published || 0;
        document.getElementById('stat-pipelines').textContent = stats.total_pipeline_runs || 0;
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

async function loadPipelineRuns() {
    try {
        const runs = await api('/pipeline/runs?limit=10');
        const tbody = document.getElementById('pipeline-runs');
        tbody.innerHTML = (runs || []).map(r => `
            <tr>
                <td>${(r.id || '').substring(0, 8)}...</td>
                <td>${r.trigger_type || '-'}</td>
                <td><span class="badge ${statusBadge(r.status)}">${r.status}</span></td>
                <td>${r.items_scraped || 0}</td>
                <td>${r.items_published || 0}</td>
                <td>${formatTime(r.started_at)}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load pipeline runs:', e);
    }
}

async function loadDrafts() {
    try {
        const status = document.getElementById('filter-status').value;
        const platform = document.getElementById('filter-platform').value;
        let url = '/content?limit=20';
        if (status) url += `&status=${status}`;
        if (platform) url += `&platform=${platform}`;
        const drafts = await api(url);
        const tbody = document.getElementById('drafts-list');
        tbody.innerHTML = (drafts || []).map(d => `
            <tr>
                <td title="${d.title || ''}">${(d.title || '').substring(0, 40)}${(d.title || '').length > 40 ? '...' : ''}</td>
                <td>${platformLabel(d.target_platform)}</td>
                <td><span class="badge ${statusBadge(d.status)}">${d.status}</span></td>
                <td>${(d.quality_score || 0).toFixed(2)}</td>
                <td>${formatTime(d.created_at)}</td>
                <td>
                    <button class="btn-sm" onclick="deleteDraft('${d.id}')">删除</button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load drafts:', e);
    }
}

function triggerPipeline() {
    document.getElementById('pipeline-dialog').showModal();
}

async function submitPipeline(e) {
    e.preventDefault();
    const form = e.target;
    const sources = [...form.querySelectorAll('input[name="source"]:checked')].map(i => i.value);
    const platforms = [...form.querySelectorAll('input[name="platform"]:checked')].map(i => i.value);
    const generateVideo = form.querySelector('#gen-video').checked;

    try {
        const result = await api('/pipeline/run', {
            method: 'POST',
            body: JSON.stringify({
                sources,
                target_platforms: platforms,
                generate_video: generateVideo,
            }),
        });
        alert(`Pipeline started: ${result.pipeline_run_id || 'OK'}`);
        document.getElementById('pipeline-dialog').close();
        setTimeout(refreshDashboard, 2000);
    } catch (e) {
        alert('Failed to start pipeline: ' + e.message);
    }
}

async function deleteDraft(id) {
    if (!confirm('确定删除此草稿？')) return;
    await api(`/content/${id}`, { method: 'DELETE' });
    loadDrafts();
}

function statusBadge(status) {
    const map = {
        running: 'badge-info', completed: 'badge-success', failed: 'badge-danger',
        summarized: 'badge-warning', quality_checked: 'badge-success',
        published: 'badge-success', rejected: 'badge-danger',
    };
    return map[status] || 'badge-info';
}

function platformLabel(p) {
    const map = { wechat: '公众号', xiaohongshu: '小红书', douyin: '抖音', weibo: '微博' };
    return map[p] || p;
}

function formatTime(t) {
    if (!t) return '-';
    try { return new Date(t).toLocaleString('zh-CN'); } catch { return t; }
}

// Auto-load on page init
refreshDashboard();
setInterval(refreshDashboard, 30000);
