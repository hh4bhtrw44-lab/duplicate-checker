#!/usr/bin/env python3
"""客户查重管理系统 - Flask + SQLite (完整功能版)"""
import re
import os
import io
import csv
import hashlib
import sqlite3
import phonenumbers
from phonenumbers import geocoder, carrier
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, g, send_file
import jieba
import jieba.analyse

app = Flask(__name__)

# ========= 云部署模式：不启动本地隧道 =========

# 稳定密钥
SECRET_KEY_FILE = os.path.join(app.root_path, '.secret_key')
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = os.urandom(24).hex()
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(app.secret_key)

# 持久化存储：优先使用 /app/data 目录（Railway Volume挂载点）
DATA_DIR = '/app/data'
if not os.path.exists(DATA_DIR):
    DATA_DIR = app.root_path
DB_PATH = os.path.join(DATA_DIR, 'data.db')

# 删除/导出/导入数据密码（不同于登录密码）
DATA_PASSWORD = 'sufahui520'

# 迁移旧数据

# 迁移旧数据：如果持久化目录有新的数据库且根目录有旧数据库则合并
OLD_DB = os.path.join(app.root_path, 'data.db')
if DATA_DIR != app.root_path and os.path.exists(OLD_DB) and not os.path.exists(DB_PATH):
    import shutil
    shutil.copy2(OLD_DB, DB_PATH)
    print(f"✅ 已迁移数据文件到 {DB_PATH}")

app.config['DATABASE'] = DB_PATH

# ========= 数据库初始化 =========

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    # 为旧数据库兼容添加 phone_region 列
    try:
        c.execute("ALTER TABLE customers ADD COLUMN phone_region TEXT DEFAULT ''")
    except:
        pass
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            company TEXT,
            notes TEXT,
            content TEXT DEFAULT '',
            phone_region TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS check_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer1_id INTEGER,
            customer2_id INTEGER,
            similarity REAL,
            level TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer1_id) REFERENCES customers(id),
            FOREIGN KEY (customer2_id) REFERENCES customers(id)
        );
    ''')
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin'))
    except sqlite3.IntegrityError:
        pass
    conn.commit()
    conn.close()

with app.app_context():
    init_db()

# ========= 登录装饰器 =========

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ========= 查重算法 =========

def preprocess_text(text):
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()

def split_words(text):
    words = jieba.lcut(text)
    return [w.strip() for w in words if w.strip() and len(w.strip()) > 1]

def get_shingles(words, k=3):
    if len(words) < k:
        return set([' '.join(words)])
    return set(' '.join(words[i:i+k]) for i in range(len(words) - k + 1))

def jaccard_similarity(set1, set2):
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0

def simhash_value(words):
    hash_size = 64
    v = [0] * hash_size
    for word in words[:200]:
        h = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
        for i in range(hash_size):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1
    fingerprint = 0
    for i in range(hash_size):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint

def simhash_similarity(fp1, fp2):
    x = fp1 ^ fp2
    return 1.0 - (bin(x).count('1') / 64.0)

def check_duplicate(text1, text2):
    clean1 = preprocess_text(text1)
    clean2 = preprocess_text(text2)
    words1 = split_words(clean1)
    words2 = split_words(clean2)

    if not words1 or not words2:
        return {"jaccard": 0, "simhash": 0, "overall": 0, "level": "文本过短", "word_count_1": len(words1), "word_count_2": len(words2)}

    shingles1 = get_shingles(words1, 3)
    shingles2 = get_shingles(words2, 3)
    jaccard = jaccard_similarity(shingles1, shingles2)

    fp1 = simhash_value(words1)
    fp2 = simhash_value(words2)
    simhash = simhash_similarity(fp1, fp2)

    overall = jaccard * 0.6 + simhash * 0.4

    if overall >= 0.85:
        level = "🔴 高度重复"
    elif overall >= 0.60:
        level = "🟡 中度重复"
    elif overall >= 0.30:
        level = "🟠 轻度重复"
    else:
        level = "🟢 基本不重复"

    return {
        "jaccard": round(jaccard * 100, 2),
        "simhash": round(simhash * 100, 2),
        "overall": round(overall * 100, 2),
        "level": level,
        "word_count_1": len(words1),
        "word_count_2": len(words2)
    }

# ========= 路由：认证 =========

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        username = data.get('username', '')
        password = data.get('password', '')
        hashed = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hashed)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json()
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')

    if not old_pw or not new_pw:
        return jsonify({"error": "旧密码和新密码不能为空"}), 400
    if len(new_pw) < 6:
        return jsonify({"error": "新密码长度不能少于6位"}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    if user['password'] != hashlib.sha256(old_pw.encode()).hexdigest():
        return jsonify({"error": "旧密码错误"}), 401

    db.execute("UPDATE users SET password=? WHERE id=?",
               (hashlib.sha256(new_pw.encode()).hexdigest(), session['user_id']))
    db.commit()
    return jsonify({"ok": True, "message": "密码修改成功"})

# ========= 路由：管理界面 =========

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/lite')
@login_required
def index_lite():
    return render_template('lite.html')

@app.route('/api/customers', methods=['GET'])
@login_required
def api_customers():
    db = get_db()
    search = request.args.get('search', '').strip()
    search_field = request.args.get('field', 'all')  # 增强搜索
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page

    # 限制最大每页条数
    if per_page > 100:
        per_page = 100

    if search:
        if search_field == 'name':
            condition = "name LIKE ?"
        elif search_field == 'phone':
            condition = "phone LIKE ?"
        elif search_field == 'email':
            condition = "email LIKE ?"
        elif search_field == 'company':
            condition = "company LIKE ?"
        else:
            condition = "name LIKE ? OR phone LIKE ? OR email LIKE ? OR company LIKE ? OR notes LIKE ?"

        if search_field == 'all':
            rows = db.execute(
                f"SELECT * FROM customers WHERE {condition} ORDER BY id DESC LIMIT ? OFFSET ?",
                (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', per_page, offset)
            ).fetchall()
            total = db.execute(
                f"SELECT COUNT(*) FROM customers WHERE {condition}",
                (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%')
            ).fetchone()[0]
        else:
            rows = db.execute(
                f"SELECT * FROM customers WHERE {condition} ORDER BY id DESC LIMIT ? OFFSET ?",
                (f'%{search}%', per_page, offset)
            ).fetchall()
            total = db.execute(
                f"SELECT COUNT(*) FROM customers WHERE {condition}",
                (f'%{search}%',)
            ).fetchone()[0]
    else:
        rows = db.execute("SELECT * FROM customers ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
        total = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

    return jsonify({
        "customers": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page
    })

def clean_phone(phone):
    """清洗电话号码：去空格、去+号、去横线、去括号"""
    if not phone:
        return phone
    return re.sub(r'[\s\+\-\(\)]', '', phone)

import phonenumbers
from phonenumbers import geocoder

def detect_phone_region(phone):
    """检测号码归属地，返回'国家 城市'格式的中文描述"""
    if not phone:
        return ''
    try:
        clean = phone.replace('+', '')
        # 先尝试解析带+号的完整号码
        try:
            parsed = phonenumbers.parse('+' + clean, None)
            desc = geocoder.description_for_number(parsed, 'zh')
            if desc:
                return desc
        except:
            pass
        # 如果没有+号前缀，尝试不同国家默认区域
        # 中国大陆手机号
        if len(clean) == 11 and clean.startswith('1'):
            parsed = phonenumbers.parse(clean, 'CN')
            desc = geocoder.description_for_number(parsed, 'zh')
            if desc:
                return desc
        # 香港8位号码
        if len(clean) == 8:
            parsed = phonenumbers.parse(clean, 'HK')
            desc = geocoder.description_for_number(parsed, 'zh')
            if desc:
                return desc
        # 台湾
        if len(clean) == 9 and clean.startswith('9'):
            parsed = phonenumbers.parse(clean, 'TW')
            desc = geocoder.description_for_number(parsed, 'zh')
            if desc:
                return desc
        # 美国/加拿大10位号码
        if len(clean) == 10:
            parsed = phonenumbers.parse(clean, 'US')
            desc = geocoder.description_for_number(parsed, 'zh')
            if desc:
                return desc
        # 最后尝试作为中国号码
        parsed = phonenumbers.parse(clean, 'CN')
        desc = geocoder.description_for_number(parsed, 'zh')
        if desc:
            return desc
        country = geocoder.country_name_for_number(parsed, 'zh')
        return country or ''
    except:
        return ''

@app.route('/api/customers/fix-data', methods=['POST'])
@login_required
def api_fix_customer_data():
    """自动修复数据：将电话栏中的姓名+电话混合数据拆分"""
    db = get_db()
    rows = db.execute('SELECT id, name, phone FROM customers').fetchall()
    fixed = 0
    import re as re_mod
    for r in rows:
        cid = r['id']
        name = (r['name'] or '').strip()
        phone = (r['phone'] or '').strip()

        # 情况1：电话栏里混了姓名
        if phone:
            parts = re_mod.split(r'[\s\t,，|;；]+', phone)
            phone_parts = []
            name_parts = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if re_mod.match(r'^[\+\d][\d\s\-\(\)]{4,}$', p):
                    phone_parts.append(p)
                else:
                    name_parts.append(p)

            if phone_parts and name_parts:
                new_phone = clean_phone(' '.join(phone_parts))
                new_name = ' '.join(name_parts)
                if name:
                    new_name = name + ' ' + new_name
                db.execute('UPDATE customers SET name=?, phone=? WHERE id=?', (new_name.strip(), new_phone, cid))
                fixed += 1
            elif not phone_parts and name_parts and not name:
                db.execute('UPDATE customers SET name=?, phone=? WHERE id=?', (name_parts[0], '', cid))
                fixed += 1

        # 情况2：姓名栏里混了电话
        if name:
            parts = re_mod.split(r'[\s\t,，|;；]+', name)
            phone_parts = []
            name_parts = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if re_mod.match(r'^[\+\d][\d\s\-\(\)]{4,}$', p):
                    phone_parts.append(p)
                else:
                    name_parts.append(p)

            if phone_parts and name_parts:
                new_name = ' '.join(name_parts)
                existing_phone = db.execute('SELECT phone FROM customers WHERE id=?', (cid,)).fetchone()['phone'] or ''
                new_phone = clean_phone((existing_phone + ' ' + ' '.join(phone_parts)).strip())
                if existing_phone and existing_phone == new_phone:
                    continue
                db.execute('UPDATE customers SET name=?, phone=? WHERE id=?', (new_name.strip(), new_phone, cid))
                fixed += 1

    db.commit()
    return jsonify({'ok': True, 'fixed': fixed, 'message': f'已修复 {fixed} 条数据'})

@app.route('/api/customers/quick-add', methods=['POST'])
@login_required
def api_quick_add():
    """快速添加：自动识别电话和姓名，返回去重结果"""
    data = request.get_json()
    lines = data.get('lines', '')
    if not lines:
        return jsonify({'error': '请输入客户信息'}), 400

    lines = [l.strip() for l in lines.split('\n') if l.strip()]
    db = get_db()
    imported = 0
    all_duplicates = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        all_segments = re.split(r'[\s\t,，|;；]+', line)
        phone_candidates = []
        name_candidates = []
        prefix_buf = ''  # 存+86等短前缀
        digit_segments = []  # 收集短的纯数字段

        for seg in all_segments:
            seg = seg.strip()
            if not seg:
                continue
            # 判断是否是国际区号前缀（+86、+852、+855等）
            if re.match(r'^\+', seg) and len(seg) <= 5:
                prefix_buf = re.sub(r'[\+\s]', '', seg)
                continue
            digit_only = re.sub(r'[\+\-\s\(\)\.\/]', '', seg)
            if digit_only.isdigit() and len(digit_only) >= 5:
                phone_candidates.append(prefix_buf + digit_only)
                prefix_buf = ''
            elif digit_only.isdigit() and len(digit_only) > 0:
                # 短数字段，先收集，看能否拼成完整号码
                digit_segments.append(digit_only)
            else:
                seg_clean = re.sub(r'[\+\-\s\(\)]', '', seg).strip()
                if seg_clean:
                    name_candidates.append(seg_clean)

        # 合并短数字段，够5位就当电话
        if digit_segments:
            combined_digits = ''.join(digit_segments)
            if len(combined_digits) >= 5:
                phone_candidates.append(prefix_buf + combined_digits)
                prefix_buf = ''
            else:
                name_candidates.append(' '.join(digit_segments))

        # 如果前缀还留着，说明没有电话跟它，当姓名处理
        if prefix_buf and not phone_candidates:
            name_candidates.insert(0, '+' + prefix_buf)

        # 如果还没分出来，从姓名中提取数字
        if not phone_candidates:
            combined = ''.join(name_candidates)
            found_nums = re.findall(r'\d{5,}', combined)
            if found_nums:
                phone_candidates = found_nums
                for n in found_nums:
                    combined = combined.replace(n, '', 1)
                name_candidates = [combined.strip()] if combined.strip() else []

        name = ' '.join(name_candidates) if name_candidates else ''
        phone = clean_phone(' '.join(phone_candidates)) if phone_candidates else ''

        if not name and not phone:
            continue

        # 去重检查
        dup_entry = {'line': line, 'name': name, 'phone': phone, 'duplicates': []}
        if name:
            same = db.execute('SELECT id, name, phone, company, created_at FROM customers WHERE name=?', (name,)).fetchall()
            for s in same:
                dup_entry['duplicates'].append({
                    'id': s['id'], 'name': s['name'], 'phone': s['phone'],
                    'company': s['company'], 'field': '姓名', 'created_at': s['created_at']
                })
        if phone:
            same = db.execute('SELECT id, name, phone, company, created_at FROM customers WHERE phone=? AND phone!=""', (phone,)).fetchall()
            for s in same:
                if not any(d['id'] == s['id'] for d in dup_entry['duplicates']):
                    dup_entry['duplicates'].append({
                        'id': s['id'], 'name': s['name'], 'phone': s['phone'],
                        'company': s['company'], 'field': '电话', 'created_at': s['created_at']
                    })

        if dup_entry['duplicates']:
            all_duplicates.append(dup_entry)
        else:
            try:
                db.execute('INSERT INTO customers (name, phone, company, phone_region) VALUES (?, ?, ?, ?)',
                           (name, phone, '', ''))
                imported += 1
            except:
                pass

    db.commit()
    return jsonify({
        'ok': True, 'imported': imported, 'total': len(lines),
        'duplicates': all_duplicates
    })

@app.route('/api/customers/detect-regions', methods=['POST'])
@login_required
def api_detect_regions():
    """批量检测电话归属地"""
    db = get_db()
    rows = db.execute("SELECT id, phone FROM customers WHERE phone IS NOT NULL AND phone != ''").fetchall()
    updated = 0
    for r in rows:
        phone = r['phone']
        region = ''
        clean = phone.replace('+', '')
        try:
            try:
                parsed = phonenumbers.parse('+' + clean, None)
                region = geocoder.description_for_number(parsed, 'zh') or geocoder.country_name_for_number(parsed, 'zh') or ''
            except:
                pass
            if not region:
                if len(clean) == 11 and clean.startswith('1'):
                    parsed = phonenumbers.parse(clean, 'CN')
                    region = geocoder.description_for_number(parsed, 'zh') or ''
                elif len(clean) == 8:
                    parsed = phonenumbers.parse(clean, 'HK')
                    region = geocoder.description_for_number(parsed, 'zh') or ''
                elif len(clean) == 9 and clean.startswith('9'):
                    parsed = phonenumbers.parse(clean, 'TW')
                    region = geocoder.description_for_number(parsed, 'zh') or ''
                elif len(clean) == 10:
                    parsed = phonenumbers.parse(clean, 'US')
                    region = geocoder.description_for_number(parsed, 'zh') or ''
                else:
                    parsed = phonenumbers.parse(clean, 'CN')
                    region = geocoder.description_for_number(parsed, 'zh') or ''
        except:
            pass
        if region:
            db.execute('UPDATE customers SET phone_region=? WHERE id=?', (region, r['id']))
            updated += 1
    db.commit()
    return jsonify({'ok': True, 'updated': updated, 'message': f'已检测 {updated} 个号码的归属地'})

@app.route('/api/customers', methods=['POST'])
@login_required
def api_add_customer():
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = clean_phone(data.get('phone', ''))
    email = data.get('email', '').strip()
    company = data.get('company', '').strip()
    notes = data.get('notes', '').strip()
    content = data.get('content', '').strip()

    if not name and not phone:
        return jsonify({"error": "姓名和电话至少填一项"}), 400

    db = get_db()

    # ====== 去重检测 ======
    duplicates = []
    if name:
        same_name = db.execute("SELECT id, name, phone, company, created_at FROM customers WHERE name = ? AND id != ?",
                               (name, request.json.get('id', 0) or 0)).fetchall()
        for r in same_name:
            duplicates.append({"id": r["id"], "name": r["name"], "phone": r["phone"], "company": r["company"], "field": "姓名", "created_at": r["created_at"]})
    if phone:
        same_phone = db.execute("SELECT id, name, phone, company, created_at FROM customers WHERE phone = ? AND phone != '' AND id != ?",
                                (phone, request.json.get('id', 0) or 0)).fetchall()
        for r in same_phone:
            duplicates.append({"id": r["id"], "name": r["name"], "phone": r["phone"], "company": r["company"], "field": "电话", "created_at": r["created_at"]})

    if duplicates:
        # 去重 2：如果勾选了 force_add，强制添加
        if request.json.get('force_add', False):
            pass
        else:
            return jsonify({
                "duplicate_warning": True,
                "duplicates": duplicates,
                "message": f"发现 {len(duplicates)} 个可能重复的客户"
            }), 409

    # 检测号码归属地
    region = ''
    if phone:
        try:
            parsed = phonenumbers.parse('+' + phone.replace('+', ''), None)
            region = geocoder.description_for_number(parsed, 'zh') or geocoder.country_name_for_number(parsed, 'zh') or ''
        except:
            pass

    c = db.execute("INSERT INTO customers (name, phone, email, company, notes, content, phone_region) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (name, phone, email, company, notes, content, region))
    db.commit()
    return jsonify({"ok": True, "id": c.lastrowid})

@app.route('/api/customers/<int:id>', methods=['PUT'])
@login_required
def api_update_customer(id):
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = clean_phone(data.get('phone', ''))
    email = data.get('email', '').strip()
    company = data.get('company', '').strip()
    notes = data.get('notes', '').strip()
    content = data.get('content', '').strip()

    if not name:
        return jsonify({"error": "客户姓名不能为空"}), 400

    db = get_db()

    # 编辑时去重检测
    duplicates = []
    if name:
        same_name = db.execute("SELECT id, name, phone, company, created_at FROM customers WHERE name = ? AND id != ?",
                               (name, id)).fetchall()
        for r in same_name:
            duplicates.append({"id": r["id"], "name": r["name"], "phone": r["phone"], "company": r["company"], "field": "姓名", "created_at": r["created_at"]})
    if phone:
        same_phone = db.execute("SELECT id, name, phone, company, created_at FROM customers WHERE phone = ? AND phone != '' AND id != ?",
                                (phone, id)).fetchall()
        for r in same_phone:
            duplicates.append({"id": r["id"], "name": r["name"], "phone": r["phone"], "company": r["company"], "field": "电话", "created_at": r["created_at"]})

    if duplicates:
        return jsonify({
            "duplicate_warning": True,
            "duplicates": duplicates,
            "message": f"检测到 {len(duplicates)} 个可能重复的客户"
        }), 409

    # 检测归属地
    region = ''
    if phone:
        try:
            parsed = phonenumbers.parse('+' + phone.replace('+', ''), None)
            region = geocoder.description_for_number(parsed, 'zh') or geocoder.country_name_for_number(parsed, 'zh') or ''
        except:
            pass
    db.execute("UPDATE customers SET name=?, phone=?, email=?, company=?, notes=?, content=?, phone_region=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
               (name, phone, email, company, notes, content, region, id))
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/customers/<int:id>', methods=['DELETE'])
@login_required
def api_delete_customer(id):
    pwd = request.args.get('pwd', '') or (request.get_json(silent=True) or {}).get('pwd', '')
    if pwd != DATA_PASSWORD:
        return jsonify({"error": "密码错误，无法删除"}), 403
    db = get_db()
    db.execute("DELETE FROM customers WHERE id=?", (id,))
    db.execute("DELETE FROM check_history WHERE customer1_id=? OR customer2_id=?", (id, id))
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/customers/batch-delete', methods=['POST'])
@login_required
def api_batch_delete():
    data = request.get_json()
    ids = data.get('ids', [])
    pwd = data.get('pwd', '')
    if pwd != DATA_PASSWORD:
        return jsonify({"error": "密码错误，无法批量删除"}), 403
    if not ids:
        return jsonify({"error": "请选择要删除的客户"}), 400
    db = get_db()
    placeholders = ','.join('?' * len(ids))
    db.execute(f"DELETE FROM customers WHERE id IN ({placeholders})", ids)
    db.commit()
    return jsonify({"ok": True, "deleted": len(ids)})

# ========= 验证数据操作密码 =========
@app.route('/api/verify-data-password', methods=['POST'])
@login_required
def api_verify_data_password():
    data = request.get_json()
    pwd = data.get('pwd', '')
    if pwd == DATA_PASSWORD:
        return jsonify({'ok': True})
    return jsonify({'ok': False}), 403

# ========= 导出 Excel =========

@app.route('/api/export/excel', methods=['GET'])
@login_required
def api_export_excel():
    pwd = request.args.get('pwd', '')
    if pwd != DATA_PASSWORD:
        return jsonify({"error": "密码错误，无法导出数据"}), 403
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return jsonify({"error": "导出功能需要安装 openpyxl：pip install openpyxl"}), 500

    db = get_db()
    customers = db.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "客户数据"

    # 表头样式
    header_font = Font(name='微软雅黑', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='667EEA', end_color='764BA2', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    headers = ['编号', '姓名', '电话', '邮箱', '公司', '备注', '查重内容', '创建时间', '更新时间']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # 数据行
    cell_font = Font(name='微软雅黑', size=10)
    for row_idx, c in enumerate(customers, 2):
        values = [c['id'], c['name'], c['phone'], c['email'], c['company'],
                  c['notes'], c['content'], c['created_at'], c['updated_at']]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = cell_font
            cell.alignment = Alignment(vertical='center')
            cell.border = thin_border

    # 列宽
    widths = [8, 16, 18, 24, 20, 24, 40, 20, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # 写入内存
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'客户数据_{timestamp}.xlsx'
    )

# ========= 批量导入 =========

@app.route('/api/customers/import', methods=['POST'])
@login_required
def api_import_customers():
    pwd = request.form.get('pwd', '')
    if pwd != DATA_PASSWORD:
        return jsonify({"error": "密码错误，无法导入数据"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "请上传文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "文件不能为空"}), 400

    # 解析文件
    records = []
    filename = file.filename.lower()

    try:
        if filename.endswith('.csv'):
            content = file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                records.append(row)
        elif filename.endswith('.xlsx'):
            try:
                import openpyxl
            except ImportError:
                return jsonify({"error": "导入xlsx需要安装openpyxl"}), 500
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            header_row = [cell.value for cell in ws[1]]
            for row in ws.iter_rows(min_row=2, values_only=True):
                record = {}
                for i, val in enumerate(row):
                    if i < len(header_row) and header_row[i]:
                        record[header_row[i]] = str(val) if val is not None else ''
                if record:
                    records.append(record)
        elif filename.endswith('.txt'):
            content = file.read().decode('utf-8-sig')
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            # 尝试识别格式
            for line in lines:
                record = {}
                parts = None
                
                # 尝试按常见分隔符分割
                for sep in ['\t', ',', '|', '，', ';', '；']:
                    test_parts = line.split(sep)
                    if len(test_parts) >= 2:
                        parts = test_parts
                        break
                
                # 如果常见分隔符都不行，尝试按空白分割（2个以上连续空格）
                if parts is None:
                    import re as re2
                    test_parts = re2.split(r'\s{2,}', line)  # 2个以上空格
                    if len(test_parts) >= 2:
                        parts = test_parts
                
                # 最后尝试单空格（但要排除电话号码中间的空格）
                if parts is None:
                    test_parts = line.split()
                    if len(test_parts) >= 2:
                        # 判断第一个是不是电话号码格式（包含+号或纯数字）
                        first = test_parts[0].strip()
                        if re.match(r'^[\+\d][\d\s\-\(\)]{4,}$', first.replace(' ', '')):
                            parts = test_parts
                        else:
                            # 可能有电话在第一列的情况，但也要考虑空格分割
                            for i, p in enumerate(test_parts):
                                p = p.strip()
                                if re.match(r'^[\+\d][\d\s\-\(\)]{6,}$', p.replace(' ', '')) and i > 0:
                                    # 在电话位置分割
                                    parts = [' '.join(test_parts[:i]), p] + test_parts[i+1:]
                                    break
                            if parts is None:
                                parts = [line]  # 无法智能分割，整行当姓名

                if parts is None:
                    parts = [line]

                if len(parts) >= 2:
                    first = parts[0].strip()
                    second = parts[1].strip()
                    if re.match(r'^[\+\d][\d\s\-\(\)]{4,}$', first):
                        record['电话'] = first
                        record['姓名'] = second
                    else:
                        record['姓名'] = first
                        record['电话'] = second
                    if len(parts) >= 3:
                        record['公司'] = parts[2].strip()
                    if len(parts) >= 4:
                        record['备注'] = parts[3].strip()
                    records.append(record)
                elif len(parts) == 1 and line:
                    record['姓名'] = parts[0].strip()
                    records.append(record)
        else:
            return jsonify({"error": "仅支持 CSV、XLSX 和 TXT 格式"}), 400
    except Exception as e:
        return jsonify({"error": f"文件解析失败: {str(e)}"}), 400

    if not records:
        return jsonify({"error": "文件中没有数据"}), 400

    # 字段映射
    field_map = {
        '姓名': 'name', '名字': 'name', 'name': 'name',
        '电话': 'phone', '手机': 'phone', 'phone': 'phone', 'tel': 'phone',
        '邮箱': 'email', '邮件': 'email', 'email': 'email',
        '公司': 'company', '企业': 'company', '单位': 'company', 'company': 'company',
        '备注': 'notes', '备注': 'notes', 'notes': 'notes',
        '查重内容': 'content', '内容': 'content', 'content': 'content',
    }

    db = get_db()
    imported = 0
    errors = []

    for idx, record in enumerate(records):
        mapped = {}
        for k, v in record.items():
            key = k.strip()
            if key in field_map:
                mapped[field_map[key]] = v.strip() if v else ''

        # 智能查找字段
        if 'name' not in mapped:
            for k in record:
                if any(term in k for term in ['姓名', '名字', '名称', 'name']):
                    mapped['name'] = record[k].strip() if record[k] else ''
                    break

        name = mapped.get('name', '')
        phone = clean_phone(mapped.get('phone', ''))
        email = mapped.get('email', '')

        if not name and not phone:
            errors.append(f"第{idx+2}行：姓名和电话均为空，跳过")
            continue

        try:
            db.execute("INSERT INTO customers (name, phone, email, company, notes, content) VALUES (?, ?, ?, ?, ?, ?)",
                       (name, phone, email, mapped.get('company', ''), mapped.get('notes', ''), mapped.get('content', '')))
            imported += 1
        except Exception as e:
            errors.append(f"第{idx+2}行（{name}）：导入失败 - {str(e)}")

    db.commit()

    result = {
        "ok": True,
        "imported": imported,
        "total": len(records),
        "errors": errors[:20]  # 最多返回20条错误
    }
    if errors:
        result["has_errors"] = True
        if len(errors) > 20:
            result["error_summary"] = f"共{len(errors)}条错误，仅显示前20条"

    return jsonify(result)

# ========= 电话号码归属地检测 =========

@app.route('/api/phone-lookup', methods=['POST'])
@login_required
def api_phone_lookup():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({"error": "请输入电话号码"}), 400

    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    
    try:
        # Try multiple formats
        parsed = None
        results = []
        
        if not clean_phone.startswith('+'):
            clean_phone_with_plus = '+' + clean_phone
        else:
            clean_phone_with_plus = clean_phone

        # Try to detect - try various countries
        for test in [clean_phone_with_plus, clean_phone]:
            for cc in [None, "CN", "US", "GB", "JP", "KR", "SG", "TW", "HK", "TH", "MY", "VN", "PH", "ID", "AU", "CA", "DE", "FR", "IT", "ES", "RU", "IN"]:
                try:
                    p = phonenumbers.parse(test, cc)
                    if phonenumbers.is_valid_number(p):
                        results.append(p)
                        break
                except:
                    pass
            if results:
                break

        if not results:
            if clean_phone.startswith('86') and len(clean_phone) > 7:
                try:
                    p = phonenumbers.parse('+' + clean_phone, "CN")
                    if phonenumbers.is_valid_number(p):
                        results.append(p)
                except:
                    pass
            if not results:
                try:
                    p = phonenumbers.parse(clean_phone, None)
                    results.append(p)
                except:
                    pass

        if not results:
            return jsonify({"phone": phone, "valid": False, "country": "未知", "country_code": ""})

        parsed = results[0]

        if not phonenumbers.is_valid_number(parsed):
            return jsonify({"phone": phone, "valid": False, "country": "未知", "country_code": ""})

        # Get info
        country = geocoder.country_name_for_number(parsed, "zh")
        if not country:
            country = geocoder.country_name_for_number(parsed, "en")
        if not country:
            country = geocoder.description_for_number(parsed, "zh")
        if not country:
            country = "未知"
        region = geocoder.description_for_number(parsed, "zh")
        carrier_name = carrier.name_for_number(parsed, "zh")
        country_code = str(parsed.country_code)

        return jsonify({
            "phone": phone, "valid": True,
            "country": country, "region": region or country,
            "carrier": carrier_name or "",
            "country_code": "+" + country_code,
            "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        })
    except Exception as e:
        return jsonify({"phone": phone, "valid": False, "country": "未知", "country_code": "", "error": str(e)})

# ========= 统计与图表分析 =========

@app.route('/api/analytics/overview')
@login_required
def api_analytics_overview():
    db = get_db()

    # 客户总数
    total_customers = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

    # 今日新增
    today = datetime.now().strftime("%Y-%m-%d")
    today_new = db.execute("SELECT COUNT(*) FROM customers WHERE DATE(created_at) = ?", (today,)).fetchone()[0]

    # 本周新增
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_new = db.execute("SELECT COUNT(*) FROM customers WHERE DATE(created_at) >= ?", (week_ago,)).fetchone()[0]

    # 本月新增
    month_start = datetime.now().strftime("%Y-%m-01")
    month_new = db.execute("SELECT COUNT(*) FROM customers WHERE DATE(created_at) >= ?", (month_start,)).fetchone()[0]

    # 今日查重
    today_checks = db.execute("SELECT COUNT(*) FROM check_history WHERE DATE(checked_at) = ?", (today,)).fetchone()[0]

    # 总查重次数
    total_checks = db.execute("SELECT COUNT(*) FROM check_history").fetchone()[0]

    # 高度重复记录数（>85%）
    high_duplicate = db.execute("SELECT COUNT(*) FROM check_history WHERE similarity >= 85").fetchone()[0]

    # 中度重复（60-85%）
    mid_duplicate = db.execute("SELECT COUNT(*) FROM check_history WHERE similarity >= 60 AND similarity < 85").fetchone()[0]

    # 轻度重复（30-60%）
    low_duplicate = db.execute("SELECT COUNT(*) FROM check_history WHERE similarity >= 30 AND similarity < 60").fetchone()[0]

    # 最近30天每日新增趋势
    daily_new = []
    for i in range(29, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = db.execute("SELECT COUNT(*) FROM customers WHERE DATE(created_at) = ?", (day,)).fetchone()[0]
        daily_new.append({"date": day, "count": count})

    # 最近30天查重趋势
    daily_checks = []
    for i in range(29, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = db.execute("SELECT COUNT(*) FROM check_history WHERE DATE(checked_at) = ?", (day,)).fetchone()[0]
        daily_checks.append({"date": day, "count": count})

    # 相似度等级分布
    distribution = {
        "high": high_duplicate,
        "mid": mid_duplicate,
        "low": low_duplicate,
        "none": total_checks - high_duplicate - mid_duplicate - low_duplicate
    }

    # 查重次数最多的10个客户
    top_checked = db.execute("""
        SELECT c.id, c.name, c.phone, COUNT(*) as check_count,
               ROUND(AVG(h.similarity), 2) as avg_similarity
        FROM check_history h
        JOIN customers c ON h.customer1_id = c.id
        GROUP BY c.id
        ORDER BY check_count DESC
        LIMIT 10
    """).fetchall()

    return jsonify({
        "total_customers": total_customers,
        "today_new": today_new,
        "week_new": week_new,
        "month_new": month_new,
        "today_checks": today_checks,
        "total_checks": total_checks,
        "high_duplicate": high_duplicate,
        "mid_duplicate": mid_duplicate,
        "low_duplicate": low_duplicate,
        "distribution": distribution,
        "daily_new": daily_new,
        "daily_checks": daily_checks,
        "top_checked": [dict(r) for r in top_checked]
    })

# ========= 查重 API =========

@app.route('/api/check', methods=['POST'])
@login_required
def api_check():
    data = request.get_json()
    customer_id = data.get('customer_id')
    compare_text = data.get('text', '').strip()

    if not customer_id or not compare_text:
        return jsonify({"error": "请选择客户并输入对比文本"}), 400

    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        return jsonify({"error": "客户不存在"}), 404

    # 全库查重：对比该客户的所有字段
    customer_text = ' '.join(filter(None, [
        customer['name'] or '',
        customer['phone'] or '',
        customer['company'] or '',
        customer['notes'] or '',
        customer['content'] or ''
    ]))

    result = check_duplicate(customer_text, compare_text)
    db.execute("INSERT INTO check_history (customer1_id, similarity, level) VALUES (?, ?, ?)",
               (customer_id, result['overall'], result['level']))
    db.commit()

    result['customer_name'] = customer['name']
    result['customer_phone'] = customer['phone']
    result['customer_company'] = customer['company']
    return jsonify(result)

@app.route('/api/check-between', methods=['POST'])
@login_required
def api_check_between():
    data = request.get_json()
    id1 = data.get('customer_id_1')
    id2 = data.get('customer_id_2')

    if not id1 or not id2:
        return jsonify({"error": "请选择两个客户"}), 400
    if id1 == id2:
        return jsonify({"error": "不能和同一个客户对比"}), 400

    db = get_db()
    c1 = db.execute("SELECT * FROM customers WHERE id=?", (id1,)).fetchone()
    c2 = db.execute("SELECT * FROM customers WHERE id=?", (id2,)).fetchone()
    if not c1 or not c2:
        return jsonify({"error": "客户不存在"}), 404

    text1 = (c1['content'] or '') + ' ' + (c1['name'] or '') + ' ' + (c1['phone'] or '') + ' ' + (c1['company'] or '')
    text2 = (c2['content'] or '') + ' ' + (c2['name'] or '') + ' ' + (c2['phone'] or '') + ' ' + (c2['company'] or '')

    result = check_duplicate(text1, text2)
    db.execute("INSERT INTO check_history (customer1_id, customer2_id, similarity, level) VALUES (?, ?, ?, ?)",
               (id1, id2, result['overall'], result['level']))
    db.commit()

    result['customer1'] = {'name': c1['name'], 'phone': c1['phone'], 'company': c1['company']}
    result['customer2'] = {'name': c2['name'], 'phone': c2['phone'], 'company': c2['company']}
    return jsonify(result)

@app.route('/api/batch-check', methods=['POST'])
@login_required
def api_batch_check():
    data = request.get_json()
    customer_id = data.get('customer_id')

    if not customer_id:
        return jsonify({"error": "请选择客户"}), 400

    db = get_db()
    target = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not target:
        return jsonify({"error": "客户不存在"}), 404

    all_others = db.execute("SELECT * FROM customers WHERE id != ?", (customer_id,)).fetchall()
    target_text = (target['content'] or '') + ' ' + (target['name'] or '') + ' ' + (target['phone'] or '')

    results = []
    for other in all_others:
        other_text = (other['content'] or '') + ' ' + (other['name'] or '') + ' ' + (other['phone'] or '')
        r = check_duplicate(target_text, other_text)
        results.append({
            'id': other['id'],
            'name': other['name'],
            'phone': other['phone'],
            'company': other['company'],
            'similarity': r['overall'],
            'level': r['level']
        })

    results.sort(key=lambda x: x['similarity'], reverse=True)
    return jsonify({
        'target': {'id': target['id'], 'name': target['name'], 'phone': target['phone']},
        'results': [r for r in results if r['similarity'] > 10]
    })

@app.route('/api/quick-check', methods=['POST'])
@login_required
def api_quick_check():
    """快速查重：输入姓名或电话，全局搜索匹配客户"""
    data = request.get_json()
    keyword = data.get('keyword', '').strip()
    if not keyword:
        return jsonify({"error": "请输入姓名或电话号码"}), 400

    db = get_db()
    keyword_like = f'%{keyword}%'
    
    # 在姓名、电话、公司、内容中搜索匹配项
    rows = db.execute("""
        SELECT id, name, phone, email, company, notes, content, created_at
        FROM customers
        WHERE name LIKE ? OR phone LIKE ? OR company LIKE ? OR email LIKE ? OR content LIKE ?
        ORDER BY id DESC
    """, (keyword_like, keyword_like, keyword_like, keyword_like, keyword_like)).fetchall()
    
    results = []
    for r in rows:
        match_fields = []
        if keyword.lower() in (r['name'] or '').lower():
            match_fields.append('姓名')
        if keyword in (r['phone'] or ''):
            match_fields.append('电话')
        if keyword.lower() in (r['company'] or '').lower():
            match_fields.append('公司')
        if keyword.lower() in (r['email'] or '').lower():
            match_fields.append('邮箱')
        if keyword.lower() in (r['content'] or '').lower():
            match_fields.append('内容')
            
        results.append({
            'id': r['id'],
            'name': r['name'],
            'phone': r['phone'],
            'company': r['company'],
            'email': r['email'],
            'notes': r['notes'],
            'match_fields': match_fields,
            'created_at': r['created_at']
        })

    return jsonify({
        'keyword': keyword,
        'total': len(results),
        'results': results,
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/quick-check-all', methods=['POST'])
@login_required
def api_quick_check_all():
    """批量快速查重：输入多个姓名/电话（每行一个），分别搜索匹配"""
    data = request.get_json()
    keywords = data.get('keywords', '').strip()
    if not keywords:
        return jsonify({"error": "请输入姓名或电话号码"}), 400

    lines = [k.strip() for k in keywords.split('\n') if k.strip()]
    if not lines:
        return jsonify({"error": "请输入至少一个关键词"}), 400

    db = get_db()
    all_results = []

    for keyword in lines:
        keyword_like = f'%{keyword}%'
        rows = db.execute("""
            SELECT id, name, phone, company, created_at
            FROM customers
            WHERE name LIKE ? OR phone LIKE ?
            ORDER BY id DESC
        """, (keyword_like, keyword_like)).fetchall()

        for r in rows:
            match_fields = []
            if keyword.lower() in (r['name'] or '').lower():
                match_fields.append('姓名')
            if keyword in (r['phone'] or ''):
                match_fields.append('电话')
            if keyword.lower() in (r['company'] or '').lower():
                match_fields.append('公司')

            all_results.append({
                'keyword': keyword,
                'id': r['id'],
                'name': r['name'],
                'phone': r['phone'],
                'company': r['company'],
                'match_fields': match_fields,
                'created_at': r['created_at'],
            })

    return jsonify({
        'keywords_count': len(lines),
        'total': len(all_results),
        'results': all_results,
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/history')
@login_required
def api_history():
    db = get_db()
    limit = min(int(request.args.get('limit', 50)), 200)
    rows = db.execute("""
        SELECT h.*, c1.name as c1_name, c1.phone as c1_phone, c2.name as c2_name, c2.phone as c2_phone
        FROM check_history h
        LEFT JOIN customers c1 ON h.customer1_id = c1.id
        LEFT JOIN customers c2 ON h.customer2_id = c2.id
        ORDER BY h.checked_at DESC LIMIT ?
    """, (limit,)).fetchall()
    return jsonify([dict(r) for r in rows])

# ========= 启动 =========
if __name__ == '__main__':
    print("=" * 60)
    print("  🚀 客户查重管理系统 (完整版)")
    print("=" * 60)
    print("  ✅ 生产模式启动: bash start.sh")
    print("  🌐 http://localhost:5000")
    print("  👤 admin / admin123")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
