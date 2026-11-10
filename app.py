import streamlit as st
import requests
import pandas as pd
import time
import random
import altair as alt
from datetime import datetime
from collections import Counter
import psycopg2
import psycopg2.extras

# ================= 配置区 =================
API_URL = "http://api.huiniao.top/interface/home/lotteryHistory"
LOTTERY_TYPE = "fcsd"  
EXCLUDE_RANGE = 100    
RECENT_ANALYZE = 100   

st.set_page_config(page_title="福彩3D 智能分析", page_icon="🎯", layout="wide")

# ================= 苹果明亮风 + 优化大屏布局 CSS =================
st.markdown("""
<style>
    .stApp {
        background-color: #fbfbfd;
        background-image: 
            radial-gradient(circle at 10% 10%, rgba(255, 182, 193, 0.25) 0%, transparent 40%),
            radial-gradient(circle at 90% 20%, rgba(176, 224, 230, 0.3) 0%, transparent 50%),
            radial-gradient(circle at 80% 90%, rgba(221, 160, 221, 0.2) 0%, transparent 40%),
            radial-gradient(circle at 20% 80%, rgba(255, 228, 196, 0.3) 0%, transparent 50%);
        background-attachment: fixed;
    }
    body, p, h1, h2, h3, h4, h5, h6, div, span { color: #1d1d1f !important; }
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(0,0,0,0.05);
    }
    .apple-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 10px 14px;
        margin-bottom: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        border: 1px solid #e5e5ea;
    }
    .apple-title { font-size: 12px; font-weight: 600; color: #86868b !important; margin-bottom: 2px; }
    .pick-number {
        font-size: 28px; font-weight: 800; color: #007aff !important;
        letter-spacing: 4px; margin-bottom: 4px; font-family: monospace; line-height: 1.2;
    }
    .reason-text { font-size: 12px; color: #1d1d1f !important; line-height: 1.3; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
    .badge-success { background-color: #e8f8ee; color: #28cd41 !important; }
    .badge-warning { background-color: #fff4e6; color: #ff9500 !important; }
    
    .review-card {
        background-color: #fff9f0;
        border-left: 6px solid #ff9500;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        font-size: 14px;
    }
    .insp-hit {
        background-color: #e8f8ee;
        border-left: 4px solid #28cd41;
        padding: 10px;
        margin-top: 10px;
        border-radius: 6px;
        color: #1d1d1f;
        font-weight: bold;
    }
    .eval-card {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        border: 1px solid #e5e5ea;
    }
    .star-text { color: #ff9500 !important; font-size: 24px; }
    
    div[data-testid="stSelectbox"] > div {
        background-color: #f5f5f7;
        border-radius: 10px;
        border: 1px solid #e5e5ea;
    }
    .stSelectbox {
        margin-bottom: -10px; 
    }
</style>
""", unsafe_allow_html=True)

# ========== 核心抓取与 Neon 数据库操作 ==========
@st.cache_data(ttl=3600)
def fetch_page(page, limit=100):
    params = {"type": LOTTERY_TYPE, "page": page, "limit": limit}
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 1:
            return result.get("data", {}).get("data", {}).get("list", [])
    except: pass
    return []

def get_db_connection():
    db_url = st.secrets["DATABASE_URL"]
    return psycopg2.connect(db_url, sslmode='require')

def sync_database():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT qihao FROM lottery_history ORDER BY qihao DESC LIMIT 1;")
            res = cur.fetchone()
            max_qihao = res['qihao'] if res else None

        if max_qihao is None:
            all_raw = []
            page = 1
            while True:
                data = fetch_page(page)
                if not data: break
                all_raw.extend(data)
                if len(data) < 100: break
                page += 1
            records_to_insert = all_raw
        else:
            new_raw = fetch_page(1) + fetch_page(2)
            records_to_insert = [d for d in new_raw if d["code"] > max_qihao]

        if records_to_insert:
            with conn.cursor() as cur:
                insert_query = """
                    INSERT INTO lottery_history (qihao, riqi, bai, shi, ge)
                    VALUES %s ON CONFLICT (qihao) DO UPDATE SET riqi = EXCLUDED.riqi, bai = EXCLUDED.bai, shi = EXCLUDED.shi, ge = EXCLUDED.ge;
                """
                values = [(d["code"], d["day"], str(d["one"]), str(d["two"]), str(d["three"])) for d in records_to_insert]
                psycopg2.extras.execute_values(cur, insert_query, values)
            conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        conn.close()

def load_data_from_db():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT qihao, riqi, bai, shi, ge FROM lottery_history ORDER BY qihao DESC;")
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.rename(columns={"qihao": "期号", "riqi": "开奖日期", "bai": "百位", "shi": "十位", "ge": "个位"})
    df["完整号码"] = df["百位"] + df["十位"] + df["个位"]
    df["开奖日期"] = pd.to_datetime(df["开奖日期"], errors='coerce')
    
    def get_shape(code):
        nums = sorted([int(c) for c in code])
        if len(set(nums)) == 1: return "豹子"
        elif len(set(nums)) == 2: return "组三"
        else: return "组六"
    df["形态"] = df["完整号码"].apply(get_shape)
    df["和值"] = df[["百位", "十位", "个位"]].astype(int).sum(axis=1)
    df["跨度"] = df[["百位", "十位", "个位"]].astype(int).max(axis=1) - df[["百位", "十位", "个位"]].astype(int).min(axis=1)
    df["奇偶比"] = df.apply(lambda r: f"{sum(1 for c in [r['百位'], r['十位'], r['个位']] if int(c)%2!=0)}:{3 - sum(1 for c in [r['百位'], r['十位'], r['个位']] if int(c)%2!=0)}", axis=1)
    return df

def save_inspiration_picks(target_qihao, picks):
    """将当日刷新的灵感号码保存到数据库"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO inspiration_pool (target_qihao, picks) VALUES (%s, %s);", (target_qihao, ", ".join(picks)))
        conn.commit()
    finally:
        conn.close()

# ========== 核心：深度复盘与策略进化 ==========
def review_and_optimize(df):
    latest_row = df.iloc[0]
    latest_qihao = latest_row["期号"]
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM strategy_records WHERE target_qihao = %s;", (latest_qihao,))
            record = cur.fetchone()
            cur.execute("SELECT weights_cold, weights_hot FROM strategy_records ORDER BY id DESC LIMIT 1;")
            last_weights_row = cur.fetchone()
            
            # 查询当期的所有灵感号码
            cur.execute("SELECT picks FROM inspiration_pool WHERE target_qihao = %s;", (latest_qihao,))
            insp_records = cur.fetchall()
    finally:
        conn.close()

    default_weights = {"cold": 0.30, "hot": 0.20}
    if last_weights_row:
        last_weights = {
            "cold": last_weights_row.get("weights_cold") if last_weights_row.get("weights_cold") is not None else 0.30,
            "hot": last_weights_row.get("weights_hot") if last_weights_row.get("weights_hot") is not None else 0.20
        }
    else: last_weights = default_weights.copy()

    if not record: return last_weights, None

    picks = record["picks"].split(", ")
    actual_code = latest_row["完整号码"]
    
    # 统计冷热
    recent_100 = df.iloc[1:101]
    freq_counter = Counter()
    for _, r in recent_100.iterrows():
        for c in ["百位", "十位", "个位"]: freq_counter[r[c]] += 1
            
    actual_nums = [latest_row["百位"], latest_row["十位"], latest_row["个位"]]
    cold_cnt, hot_cnt = 0, 0
    for n in actual_nums:
        f = freq_counter.get(n, 0)
        if f <= 5: cold_cnt += 1
        elif f >= 12: hot_cnt += 1

    # 核心推荐比对
    actual_sum, actual_span = latest_row["和值"], latest_row["跨度"]
    detailed_analysis = []
    for p in picks:
        p_nums = [int(c) for c in p]
        p_sum = sum(p_nums)
        p_span = max(p_nums) - min(p_nums)
        pos_hits = sum(1 for a, b in zip(p, actual_code) if a == b)
        
        is_direct = (p == actual_code)
        is_group = ("".join(sorted(p)) == "".join(sorted(actual_code)))
        
        analysis_str = f"<b>【{p}】</b>: "
        if is_direct: analysis_str += "<span style='color:#28cd41'>直选命中！</span> "
        elif is_group: analysis_str += "<span style='color:#28cd41'>组选命中！</span> "
        else: analysis_str += "未中奖。 "
        
        analysis_str += f"位置命中 {pos_hits} 个。"
        analysis_str += f"和值 {p_sum} (开奖 {actual_sum}，差 {abs(p_sum-actual_sum)})。"
        analysis_str += f"跨度 {p_span} (开奖 {actual_span})。"
        detailed_analysis.append(analysis_str)

    # 灵感池比对
    insp_hits = []
    all_insp_picks = []
    for r in insp_records:
        all_insp_picks.extend(r["picks"].split(", "))
    all_insp_picks = list(set(all_insp_picks)) # 去重
    
    for p in all_insp_picks:
        if p == actual_code or "".join(sorted(p)) == "".join(sorted(actual_code)):
            insp_hits.append(p)

    # 策略进化
    new_weights = last_weights.copy()
    if cold_cnt >= 2:
        new_weights["cold"] = min(0.40, new_weights["cold"] + 0.02)
        new_weights["hot"] = max(0.10, new_weights["hot"] - 0.02)
        reflect_text = "本期开奖冷号偏多（回补强烈），下期加大冷号防守权重。"
    elif hot_cnt >= 2:
        new_weights["hot"] = min(0.30, new_weights["hot"] + 0.05)
        new_weights["cold"] = max(0.20, new_weights["cold"] - 0.05)
        reflect_text = "本期热号较多，下期降低极寒权重，适当顺应热态。"
    else:
        new_weights["cold"] = 0.30
        new_weights["hot"] = 0.20
        reflect_text = "开奖形态温和平稳，下期回归冷温热均衡配置。"

    return new_weights, {
        "qihao": latest_qihao, "actual_code": actual_code, "actual_sum": actual_sum, "actual_span": actual_span,
        "picks": picks, "cold_cnt": cold_cnt, "hot_cnt": hot_cnt, 
        "detailed_analysis": detailed_analysis, "reflect_text": reflect_text,
        "insp_hits": insp_hits, "total_insp_count": len(all_insp_picks)
    }

# ========== 预测与评估功能 ==========
def predict_next_cold_hot(df):
    recent_100 = df.head(100)
    freq_counter = Counter()
    for _, r in recent_100.iterrows():
        for c in ["百位", "十位", "个位"]: freq_counter[r[c]] += 1
            
    freqs = [(str(i), freq_counter.get(str(i), 0)) for i in range(10)]
    freqs_sorted = sorted(freqs, key=lambda x: x[1])
    
    cold_pool = [num for num, f in freqs_sorted[:3]]
    warm_pool = [num for num, f in freqs_sorted[3:7]]
    hot_pool = [num for num, f in freqs_sorted[7:]]
    
    recent_10 = df.head(10)
    recent_cold_cnt = sum(1 for _, r in recent_10.iterrows() for c in ["百位", "十位", "个位"] if r[c] in cold_pool)
    
    if recent_cold_cnt > 15:
        trend_msg = "近期冷号高度活跃，冷号池已大量消耗，下期防范**温号/热号**反扑。"
        advise_ratio = "建议配比：1冷 + 1温 + 1热"
    else:
        trend_msg = "冷号回补周期可能即将到来，下期建议关注**冷号回补**。"
        advise_ratio = "建议配比：2冷 + 1温"
        
    return trend_msg, advise_ratio, sorted(cold_pool), sorted(warm_pool), sorted(hot_pool)

def evaluate_custom_number(df, code):
    nums = [int(c) for c in code]
    total_sum, span = sum(nums), max(nums) - min(nums)
    odd_cnt = sum(1 for n in nums if n % 2 != 0)
    
    miss = []
    for i, col in enumerate(["百位", "十位", "个位"]):
        m = df.index[df[col] == str(nums[i])].min() if not df[df[col] == str(nums[i])].empty else 1000
        miss.append(m)
        
    recent_avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in df.head(100).iterrows()) / 100
    
    pros, cons, score = [], [], 3
    if any(m >= 15 for m in miss): pros.append(f"长遗漏(百/十/个: {miss[0]}/{miss[1]}/{miss[2]})"); score += 1
    if any(m <= 3 for m in miss): cons.append("部分位置近期过热防转冷"); score -= 1
        
    if abs(total_sum - recent_avg_sum) <= 3: pros.append(f"和值{total_sum}贴近均值"); score += 1
    elif abs(total_sum - recent_avg_sum) >= 8: cons.append(f"和值{total_sum}偏离均值"); score -= 1
        
    if 4 <= span <= 8: pros.append(f"跨度{span}在黄金区")
    elif span < 2 or span > 9: cons.append(f"跨度{span}极端"); score -= 1
    
    if odd_cnt in (0, 3): cons.append("全奇/全偶"); score -= 1
    else: pros.append(f"奇偶比{odd_cnt}:{3-odd_cnt}")
    
    sorted_nums = sorted(nums)
    if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1:
        cons.append("顺子形态概率低"); score -= 1
        
    score = max(1, min(5, score))
    return score, pros, cons, miss

def get_recent_gap(df, code):
    matches_idx = df.index[df["完整号码"] == code].tolist()
    return min(matches_idx) if matches_idx else -1

def check_history_appearance(df, code, lookback=1000):
    recent_df = df.head(lookback)
    matches = recent_df[recent_df["完整号码"] == code]
    periods = matches["期号"].tolist()
    dates = [f"{d.strftime('%Y-%m-%d')}(距今{(datetime.now()-d).days}天)" if pd.notna(d) else "未知" for d in matches["开奖日期"]]
    return len(matches), periods, dates

def generate_picks_core(df, current_weights, num_picks=5, is_extra=False):
    exclude_set = set(df.head(EXCLUDE_RANGE)["完整号码"].tolist())
    recent_df = df.head(RECENT_ANALYZE)
    avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in recent_df.iterrows()) / RECENT_ANALYZE
    
    hot_pool, cold_pool, warm_pool = {}, {}, {}
    for col in ["百位", "十位", "个位"]:
        counts = Counter(recent_df[col].tolist())
        sorted_counts = sorted([(str(i), counts.get(str(i), 0)) for i in range(10)], key=lambda x: x[1])
        cold_pool[col] = [n for n, _ in sorted_counts[:3]]
        warm_pool[col] = [n for n, _ in sorted_counts[3:7]]
        hot_pool[col] = [n for n, _ in sorted_counts[7:]]

    picks, reasons = [], []
    attempts = 0
    while len(picks) < num_picks and attempts < 100000:
        attempts += 1
        w_cold = current_weights["cold"] + 0.05 if is_extra else current_weights["cold"]
        w_hot = current_weights["hot"] + 0.05 if is_extra else current_weights["hot"]
        
        b = random.choice(cold_pool["百位"]) if random.random() < w_cold else (random.choice(hot_pool["百位"]) if random.random() < w_hot else random.choice(warm_pool["百位"]))
        s = random.choice(cold_pool["十位"]) if random.random() < w_cold else (random.choice(hot_pool["十位"]) if random.random() < w_hot else random.choice(warm_pool["十位"]))
        g = random.choice(cold_pool["个位"]) if random.random() < w_cold else (random.choice(hot_pool["个位"]) if random.random() < w_hot else random.choice(warm_pool["个位"]))
        
        code = f"{b}{s}{g}"
        if code in exclude_set: continue
            
        nums = [int(b), int(s), int(g)]
        total_sum, span = sum(nums), max(nums) - min(nums)
        odd_cnt = sum(1 for n in nums if n % 2 != 0)
        if not (avg_sum - 4 <= total_sum <= avg_sum + 4): continue
        if not (2 <= span <= 9): continue
        if odd_cnt in (0, 3): continue
        
        sorted_nums = sorted(nums)
        if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1 and random.random() < 0.8: continue

        cold_count = sum(1 for x in [b,s,g] if x in cold_pool["百位"]+cold_pool["十位"]+cold_pool["个位"])
        reason = f"和值{total_sum}，跨度{span}。 " + ("侧重冷号回补。" if cold_count > 0 else "倾向热/温号。")
        picks.append(code); reasons.append(reason); exclude_set.add(code)
    return picks, reasons

# ================= 页面渲染 =================
st.title("🎯 福彩3D 智能分析终端")
st.caption("宽屏仪表盘 | 动态策略 | 深度复盘")

with st.sidebar:
    st.header("🔍 号码查重")
    search_code = st.text_input("输入3位数字", max_chars=3)
    if search_code and len(search_code) == 3 and search_code.isdigit():
        count, periods, dates = check_history_appearance(df if 'df' in locals() else pd.DataFrame(), search_code, 1000)
        if count > 0: st.sidebar.warning(f"⚠️ {search_code} 出现 {count} 次:\n" + "\n".join([f"{p} ({d})" for p, d in zip(periods, dates)]))
        else: st.sidebar.success(f"✨ {search_code} 近1000期未开出")
    st.markdown("---")
    if st.button("🔄 手动触发数据同步", use_container_width=True):
        sync_database()
        st.success("同步成功！")

with st.spinner("同步数据中..."):
    sync_database()
    df = load_data_from_db()

if df.empty: st.stop()

current_weights, review_data = review_and_optimize(df)
latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]
target_qihao = str(int(latest_qihao) + 1) if latest_qihao.isdigit() else latest_qihao + "_next"

# --- 顶部：深度复盘 ---
if review_data:
    insp_html = ""
    if review_data['insp_hits']:
        hits_str = ", ".join(review_data['insp_hits'])
        insp_html = f'<div class="insp-hit">🎯 灵感池捕获！在昨天刷新的 {review_data["total_insp_count"]} 注灵感号码中，成功命中：{hits_str}</div>'
    elif review_data['total_insp_count'] > 0:
        insp_html = f'<div style="margin-top:10px; color:#86868b; font-size:13px;">(昨日共生成 {review_data["total_insp_count"]} 注灵感号码，未命中)</div>'

    st.markdown(f"""
    <div class="review-card">
        <h4 style="margin-top:0; color:#ff9500;">📝 昨日深度复盘：第 {review_data['qihao']} 期</h4>
        <div style="margin-bottom:10px; font-size:16px;">
            实际开奖：<b style="color:#007aff; font-size:20px;">{review_data['actual_code']}</b> 
            (和值 {review_data['actual_sum']}, 跨度 {review_data['actual_span']}, 冷{review_data['cold_cnt']}/热{review_data['hot_cnt']})
        </div>
        <div style="background:#fff; padding:10px; border-radius:8px;">
            {"<br>".join(review_data['detailed_analysis'])}
        </div>
        {insp_html}
        <div style="margin-top:10px; font-weight:bold; color:#28cd41;">
            🧠 策略进化：{review_data['reflect_text']}
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info(f"当前基准: 第 {latest_qihao} 期。正在使用基础策略权重。")

# ================= 核心布局 =================
col_left, col_right = st.columns([1, 1], gap="large")

# ---------------- 左侧：推荐号与灵感池 ----------------
with col_left:
    st.markdown("### 🎯 今日精选推荐 (5注)")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM strategy_records WHERE target_qihao = %s;", (target_qihao,))
            today_record = cur.fetchone()
    finally: conn.close()

    if today_record:
        picks = today_record["picks"].split(", ")
        reasons = today_record["reasons"].split(" | ")
    else:
        picks, reasons = generate_picks_core(df, current_weights, num_picks=5, is_extra=False)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO strategy_records (date, target_qihao, picks, reasons, weights_cold, weights_hot) VALUES (%s, %s, %s, %s, %s, %s);",
                    (datetime.now().strftime("%Y-%m-%d %H:%M"), target_qihao, ", ".join(picks), " | ".join(reasons), current_weights["cold"], current_weights["hot"]))
            conn.commit()
        finally: conn.close()

    c_pick1, c_pick2 = st.columns(2)
    for i, code in enumerate(picks):
        count, _, _ = check_history_appearance(df, code, 1000)
        gap = get_recent_gap(df, code)
        status = f"<span class='badge badge-warning'>出{count}次(隔{gap}期)</span>" if count>0 else "<span class='badge badge-success'>近千期未开</span>"
        
        target_col = c_pick1 if i % 2 == 0 else c_pick2
        with target_col:
            st.markdown(f"""
            <div class="apple-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <div class="pick-number">{code}</div> <div>{status}</div>
                </div>
                <div class="reason-text">💡 {reasons[i]}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("### 💡 灵感号码池")
    if "extra_picks" not in st.session_state: st.session_state.extra_picks = ([], [])
    if st.button("🔄 刷新灵感池", use_container_width=True):
        new_picks, new_reasons = generate_picks_core(df, current_weights, num_picks=5, is_extra=True)
        st.session_state.extra_picks = (new_picks, new_reasons)
        save_inspiration_picks(target_qihao, new_picks) # 刷新即入库记录！
    
    extra_picks, extra_reasons = st.session_state.extra_picks
    if extra_picks:
        c_ex1, c_ex2 = st.columns(2)
        for i, (code, reason) in enumerate(zip(extra_picks, extra_reasons)):
            gap = get_recent_gap(df, code)
            gap_text = f"间隔{gap}期" if gap != -1 else "近千期未开"
            
            target_col = c_ex1 if i % 2 == 0 else c_ex2
            with target_col:
                st.markdown(f"""
                <div class="apple-card" style="padding: 8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="font-size:22px; font-weight:bold; color:#007aff;">{code}</div>
                        <div style="font-size:11px; color:#86868b;">{gap_text}</div>
                    </div>
                    <div style="font-size:11px; color:#666;">{reason}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("点击上方按钮生成灵感号码。每次点击都会生成 5 注并记录在云端，供明日复盘使用。")

# ---------------- 右侧：冷热形态与重号 ----------------
with col_right:
    st.markdown("### 🌡️ 下一期冷热形态预测")
    trend_msg, ratio_msg, colds, warms, hots = predict_next_cold_hot(df)
    
    st.markdown(f"""
    <div style="background:#fff; padding:15px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.03); margin-bottom:15px;">
        <div style="font-size:15px; color:#ff9500; font-weight:bold; margin-bottom:8px;">🔮 趋势洞察</div>
        <div style="margin-bottom:10px;">{trend_msg}</div>
        <div style="background:#e8f8ee; display:inline-block; padding:4px 12px; border-radius:20px; color:#28cd41; font-weight:bold; font-size:14px;">{ratio_msg}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="display:flex; gap:10px; margin-bottom:15px;">
        <div style="flex:1; background:#e0f7fa; padding:10px; border-radius:8px; text-align:center;">
            <b style="color:#00bcd4;">❄️ 冷号池</b><br>{', '.join(colds) if colds else '无'}
        </div>
        <div style="flex:1; background:#f1f8e9; padding:10px; border-radius:8px; text-align:center;">
            <b style="color:#8bc34a;">🌤️ 温号池</b><br>{', '.join(warms) if warms else '无'}
        </div>
        <div style="flex:1; background:#fbe9e7; padding:10px; border-radius:8px; text-align:center;">
            <b style="color:#ff5722;">🔥 热号池</b><br>{', '.join(hots) if hots else '无'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📊 重号概率统计")
    show_repeat_details = st.toggle("显示重复号码明细", value=False, key="toggle_repeat")
    
    c1, c2, c3, c4 = st.columns(4)
    windows = [100, 200, 500, 1000]
    for col, window in zip([c1, c2, c3, c4], windows):
        window_df = df.head(window)
        counts = window_df["完整号码"].value_counts()
        dup = counts[counts >= 2]
        prob = (dup.sum()/window)*100 if window > 0 else 0
        with col:
            st.metric(label=f"近 {window} 期", value=f"{prob:.1f}%")
            st.caption(f"重号 {len(dup)} 个")
            
    if show_repeat_details:
        cols_d = st.columns(4)
        for col, window in zip(cols_d, windows):
            window_df = df.head(window)
            counts = window_df["完整号码"].value_counts()
            dup = counts[counts >= 2]
            with col:
                if not dup.empty:
                    dup_df = pd.DataFrame({"号码": dup.index, "次数": dup.values})
                    st.dataframe(dup_df, hide_index=True, use_container_width=True)
                else:
                    st.caption("无重复")

st.divider()

# ================= Row 3: 宽幅走势图与形态表 =================
st.markdown("### 📈 深度走势分析与模拟推演")

col_chart, col_shape = st.columns([3, 1], gap="small")

with col_chart:
    sim_cols = st.columns([1, 1, 1, 1])
    sim_b = sim_cols[0].selectbox("百位", options=[str(i) for i in range(10)], index=3, key="sim_b")
    sim_s = sim_cols[1].selectbox("十位", options=[str(i) for i in range(10)], index=4, key="sim_s")
    sim_g = sim_cols[2].selectbox("个位", options=[str(i) for i in range(10)], index=6, key="sim_g")
    custom_code = f"{sim_b}{sim_s}{sim_g}"
    sim_cols[3].markdown(f"<div style='margin-top:30px; font-size:20px; font-weight:bold;'>预测选号: <span style='color:#ff3b30;'>{custom_code}</span></div>", unsafe_allow_html=True)

    chart_data = df.head(30).copy().sort_values("期号", ascending=True)
    chart_data["期号简写"] = chart_data["期号"].astype(str).str[-3:]
    for c in ["百位", "十位", "个位"]: chart_data[c] = chart_data[c].astype(int)

    next_qihao_str = "下期预测"
    pred_row = pd.DataFrame([{
        "期号简写": next_qihao_str,
        "百位": int(sim_b), "十位": int(sim_s), "个位": int(sim_g),
        "形态": "-", "和值": int(sim_b)+int(sim_s)+int(sim_g),
        "跨度": max(int(sim_b), int(sim_s), int(sim_g)) - min(int(sim_b), int(sim_s), int(sim_g)),
        "奇偶比": "-"
    }])
    chart_data = pd.concat([chart_data, pred_row], ignore_index=True)

    melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
    
    melted_df['x_pos'] = melted_df.apply(lambda r: r['数值'] if r['位置']=='百位' else (r['数值']+12 if r['位置']=='十位' else r['数值']+24), axis=1)
    melted_df['is_pred'] = melted_df['期号简写'] == next_qihao_str
    
    x_axis = alt.X('x_pos:Q', 
                   scale=alt.Scale(domain=[-1, 34]), 
                   axis=alt.Axis(
                       values=[0,1,2,3,4,5,6,7,8,9, 12,13,14,15,16,17,18,19,20,21, 24,25,26,27,28,29,30,31,32,33],
                       labelExpr="datum.value < 10 ? datum.value : (datum.value < 22 ? datum.value - 12 : datum.value - 24)",
                       title="号码（百位 | 十位 | 个位）"
                   ))
    
    y_axis = alt.Y('期号简写:N', sort=chart_data['期号简写'].tolist(), axis=alt.Axis(labelAngle=0, labelOverlap=False))
    
    line_chart = alt.Chart(melted_df[~melted_df['is_pred']]).mark_line(point=alt.OverlayMarkDef(size=40, filled=True, stroke='white', strokeWidth=2), strokeWidth=2).encode(
        x=x_axis, y=y_axis, 
        color=alt.Color('位置:N', scale=alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#00BCD4', '#8BC34A'])),
        tooltip=['期号简写', '位置', '数值']
    )
    
    last_history_qihao = chart_data.iloc[-2]["期号简写"]
    connect_df = melted_df[melted_df['期号简写'].isin([last_history_qihao, next_qihao_str])]
    dashed_lines = alt.Chart(connect_df).mark_line(strokeDash=[5, 5], strokeWidth=2).encode(
        x=x_axis, y=y_axis, color='位置:N'
    )
    
    pred_points = alt.Chart(melted_df[melted_df['is_pred']]).mark_point(size=150, filled=True, color='#ff3b30', opacity=1).encode(
        x=x_axis, y=y_axis, tooltip=['位置', '数值']
    )
    
    vlines = pd.DataFrame({'x': [10.5, 22.5]})
    vline_chart = alt.Chart(vlines).mark_rule(color='#e5e5ea', strokeWidth=1, strokeDash=[4,4]).encode(x='x:Q')
    texts = pd.DataFrame({'x': [4.5, 16.5, 28.5], 'text': ['百位', '十位', '个位']})
    text_chart = alt.Chart(texts).mark_text(dy=-10, fontWeight='bold', color='#86868b').encode(x='x:Q', text='text:N')
    
    final_chart = (vline_chart + line_chart + dashed_lines + pred_points + text_chart).properties(height=600, background='transparent').interactive()
    
    st.altair_chart(final_chart, use_container_width=True)

with col_shape:
    st.markdown("<div style='margin-top:50px;'></div>", unsafe_allow_html=True)
    st.markdown("**形态与参数**")
    shape_df = chart_data[["期号简写", "形态", "和值", "跨度"]].copy()
    shape_df.loc[shape_df["期号简写"] == next_qihao_str, "形态"] = "预测"
    shape_df = shape_df.sort_values("期号简写", ascending=False).reset_index(drop=True)
    shape_df.columns = ["期号", "形态", "和值", "跨度"]
    
    st.dataframe(
        shape_df, 
        hide_index=True, 
        use_container_width=True, 
        height=600
    )

# --- 实时生成评估报告 ---
st.markdown("### 📋 预测号码综合评估报告")
score, pros, cons, miss = evaluate_custom_number(df, custom_code)
count, _, _ = check_history_appearance(df, custom_code, 1000)

pros_text = "<br>".join(['· ' + p for p in pros]) if pros else "· 无"
cons_text = "<br>".join(['· ' + c for c in cons]) if cons else "· 无"

eval_html = f"""<div class="eval-card">
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e5e5ea; padding-bottom:10px; margin-bottom:15px;">
    <h4 style="margin:0;">预测号码 <span style="color:#ff3b30;">{custom_code}</span></h4>
    <div>
        <span style="font-weight:bold; font-size:14px;">推荐星级：</span> <span class="star-text">{'★'*score}{'☆'*(5-score)}</span>
        <span style="color:#86868b; font-size:12px; margin-left:10px;">近千期开出 {count} 次</span>
    </div>
</div>
<div style="display:flex; gap:15px;">
    <div style="flex:1; background:#f5f5f7; padding:12px; border-radius:8px; font-size:13px;">
        <b>📍 位置遗漏</b><br>
        百位: {miss[0]} 期<br>十位: {miss[1]} 期<br>个位: {miss[2]} 期
    </div>
    <div style="flex:1; background:#e8f8ee; padding:12px; border-radius:8px; color:#28cd41; font-size:13px;">
        <b>✅ 优势</b><br>{pros_text}
    </div>
    <div style="flex:1; background:#fff4e6; padding:12px; border-radius:8px; color:#ff9500; font-size:13px;">
        <b>⚠️ 风险</b><br>{cons_text}
    </div>
</div>
</div>"""

st.markdown(eval_html, unsafe_allow_html=True)
