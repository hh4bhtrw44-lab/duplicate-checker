#!/usr/bin/env python3
"""Update index.html with all 6 features"""
import re

with open('templates/index.html', 'r') as f:
    html = f.read()

# ============================================================
# Feature 1: Export tab - add filter fields
# ============================================================
old = '''    <div id="tab-export" class="tab-content">
        <div class="card">
            <h2>导出数据</h2>
            <p style="color:#888; font-size:14px; margin-bottom:16px;">将客户数据导出为 Excel 文件（.xlsx 格式）</p>
            <button class="btn btn-success" onclick="exportExcel()">📤 导出为 Excel</button>
        </div>
    </div>'''
new = '''    <div id="tab-export" class="tab-content">
        <div class="card">
            <h2>导出数据</h2>
            <p style="color:#888; font-size:14px; margin-bottom:16px;">将客户数据导出为 Excel 文件（.xlsx 格式），可选筛选条件</p>
            <div class="form-row" style="margin-bottom:16px;background:#f8f9ff;padding:14px;border-radius:8px;border:1px solid #e0e5ff;">
                <div class="form-group"><label>开始日期</label><input type="date" id="exportDateFrom"></div>
                <div class="form-group"><label>结束日期</label><input type="date" id="exportDateTo"></div>
                <div class="form-group"><label>归属地</label><select id="exportRegion"><option value="">全部</option></select></div>
                <div class="form-group"><label>搜索</label><input type="text" id="exportSearch" placeholder="姓名/电话/公司"></div>
            </div>
            <button class="btn btn-success" onclick="exportExcel()">📤 导出为 Excel</button>
        </div>
    </div>'''
assert old in html, "Export tab not found!"
html = html.replace(old, new)
print("✅ Export tab updated")

# ============================================================
# Feature 3: Import preview area
# ============================================================
# Find the input file element and insert preview area after it
marker = 'onchange="onFileSelect(this)">'
pos = html.find(marker)
assert pos > 0, "File input marker not found!"
# Find the closing </div> that follows the import-dropzone
close_div = html.find('</div>', pos)
preview_html = '''
            <div id="importPreviewArea" style="display:none;margin-top:12px;">
                <div class="table-container" style="max-height:300px;overflow-y:auto;margin-bottom:12px;">
                    <table>
                        <thead><tr><th>#</th><th>姓名</th><th>电话</th><th>邮箱</th><th>公司</th><th>备注</th><th>状态</th></tr></thead>
                        <tbody id="importPreviewTbody"></tbody>
                    </table>
                </div>
                <p id="importPreviewSummary" style="font-size:13px;color:#555;margin-bottom:12px;"></p>
                <div class="form-actions">
                    <button class="btn btn-success" id="importConfirmBtn" onclick="confirmImport()">✅ 确认导入</button>
                    <button class="btn btn-outline" onclick="cancelImport()">取消</button>
                </div>
            </div>'''
html = html[:close_div] + preview_html + html[close_div:]
print("✅ Import preview area added")

# ============================================================
# Feature 5: Advanced search panel
# ============================================================
old = '<button class="btn btn-sm" style="background:#9c27b0;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;" onclick="var p=document.getElementById(\'advancedSearchPanel\');if(p)p.style.display=p.style.display===\'none\'?\'flex\':\'none\';">🔍 高级</button>'
new = '<button class="btn btn-sm" style="background:#9c27b0;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;" onclick="toggleAdvancedSearch()">🔍 高级</button>'
assert old in html, "Advanced button not found!"
html = html.replace(old, new)

# Find the search bar end and insert advanced search panel
search_end = html.find('</div>\n            <div class="table-container">', html.find('search-bar'))
assert search_end > 0, "Search bar end not found!"
advanced_panel = '''            </div>
            <div id="advancedSearchPanel" style="display:none;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:flex-end;background:#f8f9ff;padding:12px;border-radius:8px;border:1px solid #d0d5ff;">
                <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;width:100%;">
                    <div><label style="font-size:12px;color:#888;display:block;">归属地</label><select id="searchRegion" style="padding:7px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;background:white;min-width:120px;"><option value="">全部</option></select></div>
                    <div><label style="font-size:12px;color:#888;display:block;">开始日期</label><input type="date" id="searchDateFrom" style="padding:7px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;"></div>
                    <div><label style="font-size:12px;color:#888;display:block;">结束日期</label><input type="date" id="searchDateTo" style="padding:7px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;"></div>
                    <div><label style="font-size:12px;color:#888;display:block;">公司名</label><input type="text" id="searchCompany" placeholder="公司名" style="padding:7px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;"></div>
                    <button class="btn btn-primary btn-sm" onclick="searchCustomers()" style="margin-top:14px;">筛选</button>
                    <button class="btn btn-outline btn-sm" onclick="clearAdvancedSearch()" style="margin-top:14px;">清除</button>
                </div>
            </div>
            <div class="table-container">'''
html = html[:search_end] + advanced_panel + html[search_end + len('</div>\n            <div class="table-container">'):]
print("✅ Advanced search panel added")

# ============================================================
# Feature 3: Replace onFileSelect to use preview
# ============================================================
old = '''        function onFileSelect(input) {
            if (input.files.length) showDataPasswordModal('uploadImport', input.files[0]);
        }'''
new = '''        var _pendingImportFile = null;
        function onFileSelect(input) {
            if (input.files.length) {
                _pendingImportFile = input.files[0];
                previewImportFile(input.files[0]);
            }
        }'''
assert old in html, "onFileSelect not found!"
html = html.replace(old, new)
print("✅ onFileSelect replaced")

# ============================================================
# Feature 3: Replace uploadImportConfirm with preview+confirm flow
# ============================================================
old = '''        async function uploadImportConfirm(file) {
            const resultEl = document.getElementById('importResult');
            const ext = file.name.split('.').pop().toLowerCase();
            if (!['csv', 'xlsx', 'txt'].includes(ext)) {
                resultEl.className = 'import-result error';
                resultEl.innerHTML = `<p style="color:#e74c3c;">❌ 仅支持 CSV 和 XLSX 格式</p>`;
                return;
            }

            resultEl.className = 'import-result success';
            resultEl.innerHTML = `<p>⏳ 正在导入 <strong>${file.name}</strong>，请稍候...</p>`;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/customers/import', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.ok) {
                    let html = `<p>✅ 导入完成：成功 ${data.imported}/${data.total} 条</p>`;
                    if (data.has_errors && data.errors.length > 0) {
                        html += `<div style="margin-top:8px; max-height:200px; overflow-y:auto;"><p style="color:#e74c3c; font-weight:500;">错误详情：</p><ul style="font-size:12px; color:#888;">`;
                        data.errors.forEach(err => { html += `<li>${err}</li>`; });
                        if (data.error_summary) html += `<li>${data.error_summary}</li>`;
                        html += `</ul></div>`;
                    }
                    resultEl.className = 'import-result success';
                    resultEl.innerHTML = html;
                    if (data.imported > 0) loadCustomers(1);
                } else {
                    resultEl.className = 'import-result error';
                    resultEl.innerHTML = `<p style="color:#e74c3c;">❌ ${data.error || '导入失败'}</p>`;
                }
            } catch {
                resultEl.className = 'import-result error';
                resultEl.innerHTML = `<p style="color:#e74c3c;">❌ 网络错误，导入失败</p>`;
            }
        }'''
new = '''        async function previewImportFile(file) {
            const ext = file.name.split('.').pop().toLowerCase();
            if (!['csv','xlsx','txt'].includes(ext)) { showToast('仅支持 CSV、XLSX 和 TXT 格式','error'); return; }
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/customers/import-preview', { method: 'POST', body: formData });
                const data = await res.json();
                if (!data.ok) { showToast(data.error||'预览失败','error'); return; }
                var tbody = document.getElementById('importPreviewTbody');
                tbody.innerHTML = '';
                data.preview.forEach(function(p) {
                    var tr = document.createElement('tr');
                    var status = p.is_duplicate ? '<span style="color:#e74c3c;">⚠️ 可能重复</span>' : '<span style="color:#27ae60;">✅ 新客户</span>';
                    tr.innerHTML = '<td>' + p.index + '</td><td>' + (p.name||'-') + '</td><td>' + (p.phone||'-') + '</td><td>' + (p.email||'-') + '</td><td>' + (p.company||'-') + '</td><td>' + (p.notes||'-') + '</td><td>' + status + '</td>';
                    tbody.appendChild(tr);
                });
                var summary = '共 ' + data.total + ' 条记录，其中 ' + data.duplicate_count + ' 条可能重复（显示前' + Math.min(20,data.preview.length) + '条预览）';
                document.getElementById('importPreviewSummary').textContent = summary;
                document.getElementById('importPreviewArea').style.display = 'block';
                document.getElementById('dropzone').style.display = 'none';
                document.getElementById('importResult').className = 'import-result';
                document.getElementById('importResult').style.display = 'none';
            } catch { showToast('预览失败','error'); }
        }
        async function confirmImport() {
            if (!_pendingImportFile) return;
            showDataPasswordModal('uploadImport', _pendingImportFile);
        }
        function cancelImport() {
            document.getElementById('importPreviewArea').style.display = 'none';
            document.getElementById('dropzone').style.display = 'block';
            document.getElementById('importFile').value = '';
            _pendingImportFile = null;
        }
        async function uploadImportConfirm(file) {
            const resultEl = document.getElementById('importResult');
            resultEl.innerHTML = '<p>⏳ 正在导入 <strong>' + file.name + '</strong>，请稍候...</p>';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/customers/import', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.ok) {
                    var html2 = '<p>✅ 导入完成：成功 ' + data.imported + '/' + data.total + ' 条</p>';
                    if (data.has_errors && data.errors.length > 0) {
                        html2 += '<div style="margin-top:8px; max-height:200px; overflow-y:auto;"><p style="color:#e74c3c; font-weight:500;">错误详情：</p><ul style="font-size:12px; color:#888;">';
                        data.errors.forEach(function(err2){ html2 += '<li>' + err2 + '</li>'; });
                        if (data.error_summary) html2 += '<li>' + data.error_summary + '</li>';
                        html2 += '</ul></div>';
                    }
                    resultEl.className = 'import-result success';
                    resultEl.innerHTML = html2;
                    document.getElementById('importPreviewArea').style.display = 'none';
                    document.getElementById('dropzone').style.display = 'block';
                    document.getElementById('importFile').value = '';
                    _pendingImportFile = null;
                    if (data.imported > 0) loadCustomers(1);
                } else {
                    resultEl.className = 'import-result error';
                    resultEl.innerHTML = '<p style="color:#e74c3c;">❌ ' + (data.error || '导入失败') + '</p>';
                }
            } catch {
                resultEl.className = 'import-result error';
                resultEl.innerHTML = '<p style="color:#e74c3c;">❌ 网络错误，导入失败</p>';
            }
        }'''
assert old in html, "uploadImportConfirm not found!"
html = html.replace(old, new)
print("✅ Import preview/confirm flow added")

# ============================================================
# Feature 5/6: Add toggleAdvancedSearch, clearAdvancedSearch, loadRegionsForSearch + update loadDashboard
# ============================================================
old = '''        async function loadCheckStats() {
            try {
                var res = await fetch('/api/analytics/check-stats');
                var d = await res.json();
                if (document.getElementById('csTodayChecks')) document.getElementById('csTodayChecks').textContent = d.today_checks || 0;
                if (document.getElementById('csTotalChecks')) document.getElementById('csTotalChecks').textContent = d.total_checks || 0;
                if (document.getElementById('csTodayDup')) document.getElementById('csTodayDup').textContent = d.today_duplicate || 0;
                if (document.getElementById('csTotalDup')) document.getElementById('csTotalDup').textContent = d.total_duplicate || 0;
                if (document.getElementById('csAvgRate')) document.getElementById('csAvgRate').textContent = (d.avg_duplicate_rate || 0) + '%';
                var ctx = document.getElementById('checkTrendChart');
                if (ctx) {
                    if (window._checkTrendChart) window._checkTrendChart.destroy();
                    var tr = d.weekly_trend || [];
                    window._checkTrendChart = new Chart(ctx, {
                        type:'line',
                        data:{labels:tr.map(function(x){return x.date.slice(5);}),datasets:[{label:'查重次数',data:tr.map(function(x){return x.count;}),borderColor:'#667eea',backgroundColor:'rgba(102,126,234,0.1)',fill:true,tension:0.3}]},
                        options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}}
                    });
                }
            } catch(e) {}
        }'''
new = '''        function toggleAdvancedSearch() {
            var p = document.getElementById('advancedSearchPanel');
            if (!p) return;
            var vis = p.style.display === 'flex';
            p.style.display = vis ? 'none' : 'flex';
            if (!vis) loadRegionsForSearch();
        }
        function clearAdvancedSearch() {
            if (document.getElementById('searchRegion')) document.getElementById('searchRegion').value = '';
            if (document.getElementById('searchDateFrom')) document.getElementById('searchDateFrom').value = '';
            if (document.getElementById('searchDateTo')) document.getElementById('searchDateTo').value = '';
            if (document.getElementById('searchCompany')) document.getElementById('searchCompany').value = '';
            searchCustomers();
        }
        async function loadRegionsForSearch() {
            try {
                var res = await fetch('/api/analytics/region-map');
                var d = await res.json();
                var sel = document.getElementById('searchRegion');
                if (!sel) return;
                var cur = sel.value;
                sel.innerHTML = '<option value="">全部</option>';
                var entries = Object.entries(d.regions || {}).sort(function(a,b){return b[1]-a[1];});
                for (var i = 0; i < entries.length; i++) {
                    var opt = document.createElement('option');
                    opt.value = entries[i][0];
                    opt.textContent = entries[i][0] + ' (' + entries[i][1] + ')';
                    sel.appendChild(opt);
                }
                sel.value = cur;
            } catch(e) {}
        }
        async function loadCheckStats() {
            try {
                var res = await fetch('/api/analytics/check-stats');
                var d = await res.json();
                if (document.getElementById('csTodayChecks')) document.getElementById('csTodayChecks').textContent = d.today_checks || 0;
                if (document.getElementById('csTotalChecks')) document.getElementById('csTotalChecks').textContent = d.total_checks || 0;
                if (document.getElementById('csTodayDup')) document.getElementById('csTodayDup').textContent = d.today_duplicate || 0;
                if (document.getElementById('csTotalDup')) document.getElementById('csTotalDup').textContent = d.total_duplicate || 0;
                if (document.getElementById('csAvgRate')) document.getElementById('csAvgRate').textContent = (d.avg_duplicate_rate || 0) + '%';
                var ctx = document.getElementById('checkTrendChart');
                if (ctx) {
                    if (window._checkTrendChart) window._checkTrendChart.destroy();
                    var tr = d.weekly_trend || [];
                    window._checkTrendChart = new Chart(ctx, {
                        type:'line',
                        data:{labels:tr.map(function(x){return x.date.slice(5);}),datasets:[{label:'查重次数',data:tr.map(function(x){return x.count;}),borderColor:'#667eea',backgroundColor:'rgba(102,126,234,0.1)',fill:true,tension:0.3}]},
                        options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}}
                    });
                }
            } catch(e) {}
        }'''
assert old in html, "loadCheckStats not found!"
html = html.replace(old, new)
print("✅ Helper functions for advanced search + check stats added")

# ============================================================
# Feature 6: Update dashboard to use real check-stats data
# ============================================================
old = '''        async function loadDashboard() {
            try {
                const res = await fetch('/api/analytics/overview');
                const data = await res.json();
                document.getElementById('totalCustomers').textContent = data.total_customers;
                document.getElementById('todayNew').textContent = data.today_new;
                document.getElementById('weekNew').textContent = data.week_new;
                document.getElementById('monthNew').textContent = data.month_new;
                document.getElementById('todayChecks').textContent = data.today_checks;
                document.getElementById('totalChecks').textContent = data.total_checks;
                document.getElementById('highDuplicate').textContent = data.high_duplicate;
            } catch { /* dashboard load failed */ }
            loadRegionMap();
        }'''
new = '''        async function loadDashboard() {
            try {
                const [overviewRes, statsRes] = await Promise.all([
                    fetch('/api/analytics/overview'),
                    fetch('/api/analytics/check-stats')
                ]);
                const data = await overviewRes.json();
                const stats = await statsRes.json();
                document.getElementById('totalCustomers').textContent = data.total_customers;
                document.getElementById('todayNew').textContent = data.today_new;
                document.getElementById('weekNew').textContent = data.week_new;
                document.getElementById('monthNew').textContent = data.month_new;
                document.getElementById('todayChecks').textContent = stats.today_checks || 0;
                document.getElementById('totalChecks').textContent = stats.total_checks || 0;
                document.getElementById('highDuplicate').textContent = data.high_duplicate;
            } catch { /* dashboard load failed */ }
            loadRegionMap();
        }'''
assert old in html, "loadDashboard not found!"
html = html.replace(old, new)
print("✅ loadDashboard updated with check-stats")

# ============================================================
# Write the file
# ============================================================
with open('templates/index.html', 'w') as f:
    f.write(html)

print("\n✅ All 6 features updated in index.html!")
print(f"Total chars: {len(html)}")
