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
LOTTERY_TYPE = "pls"  # 排列三的彩种代码

st.set_page_config(page_title="排列三 终极量化终端", page_icon="🏆", layout="wide")

# ================= 体彩竞速风 CSS (加固防黑版) =================
st.markdown("""
<style>
    /* 强制全局背景 */
    .stApp {
        background-color: #f4f6f9 !important;
        background-image: 
            radial-gradient(circle at 10% 10%, rgba(255, 87, 34, 0.1) 0%, transparent 40%),
            radial-gradient(circle at 90% 90%, rgba(26, 35, 126, 0.1) 0%, transparent 40%);
        background-attachment: fixed;
    }
    body, p, h1, h2, h3, h4, h5, h6, div, span { color: #1d1d1f !important; }
    
    /* 侧边栏 */
    [data-testid="stSidebar"] { 
        background-color: #ffffff !important; 
        border-right: 1px solid #e5e5ea; 
    }
    
    /* 输入框、下拉框、数字输入框防黑加固 */
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, .stTextInput input {
        background-color: #ffffff !important;
        color: #1d1d1f !important;
        border-radius: 10px;
        border: 1px solid #e5e5ea;
    }
    /* 下拉菜单弹出层防黑加固 */
    ul[data-testid="stSelectboxVirtualDropdown"] {
        background-color: #ffffff !important;
    }
    
    /* 滑块防黑加固 */
    [data-testid="stSlider"] div { color: #1d1d1f !important; }

    /* 表格防黑加固 */
    [data-testid="stDataFrame"] { background-color: #ffffff !important; }
    
    /* 提示框防黑加固 */
    .stAlert { background-color: #ffffff !important; border: 1px solid #e5e5ea; }
    
    /* 卡片样式 */
    .apple-card { background-color: #ffffff; border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); border-left: 4px solid #FF5722; }
    .pick-number { font-size: 32px; font-weight: 800; color: #FF5722 !important; letter-spacing: 4px; margin-bottom: 4px; font-family: monospace; line-height: 1.2; }
    .reason-text { font-size: 13px; color: #666 !important; line-height: 1.4; }
    
    .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
    .badge-success { background-color: #e8f8ee; color: #28cd41 !important; }
    .badge-warning { background-color: #fff4e6; color: #ff9500 !important; }
    
    /* 复盘卡片 */
    .review-card { background: linear-gradient(135deg, #1A237E 0%, #3949AB 100%); border-radius: 12px; padding: 20px; margin-bottom: 20px; color: white !important; box-shadow: 0 8px 24px rgba(26, 35, 126, 0.2); }
    .review-card h4 { color: #FFD54F !important; margin-top: 0; }
    .review-card div { color: #E8EAF6 !important; }
    .review-card b { color: #ffffff !important; }
    
    .insp-hit { background-color: #e8f8ee; border-left: 4px solid #28cd41; padding: 10px; margin-top: 10px; border-radius: 6px; color: #1d1d1f; font-weight: bold; }
    .eval-card { background-color: #ffffff; border-radius: 16px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.05); border: 1px solid #e5e5ea; }
    .star-text { color: #FF5722 !important; font-size: 24px; }
    
    .stSelectbox { margin-bottom: -10px; }
    
    @media (max-width: 768px) { [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; } }
</style>
""", unsafe_allow_html=True)

# ========== 核心抓取与数据库 ==========
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
    return psycopg2.connect(st.secrets["DATABASE_URL"], sslmode='require')

def sync_database():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT qihao FROM pl3_lottery_history ORDER BY qihao DESC LIMIT 1;")
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
                    INSERT INTO pl3_lottery_history (qihao, riqi, bai, shi, ge)
                    VALUES %s ON CONFLICT (qihao) DO UPDATE SET riqi = EXCLUDED.riqi, bai = EXCLUDED.bai, shi = EXCLUDED.shi, ge = EXCLUDED.ge;
                """
                values = [(d["code"], d["day"], str(d["one"]), str(d["two"]), str(d["three"])) for d in records_to_insert]
                psycopg2.extras.execute_values(cur, insert_query, values)
            conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        conn.close()

@st.cache_data(ttl=600)
def load_data_from_db():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT qihao, riqi, bai, shi, ge FROM pl3_lottery_history ORDER BY qihao DESC;")
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.rename(columns={"qihao": "期号", "riqi": "开奖日期", "bai": "百位", "shi": "十位", "ge": "个位"})
    df["完整号码"] = df["百位"] + df["十位"] + df["个位"]
    df["开奖日期"] = pd.to_datetime(df["开奖日期"], errors='coerce')
    
    def analyze_shape(code):
        nums = sorted([int(c) for c in code])
        shape = "组六"
        if len(set(nums)) == 1: shape = "豹子"
        elif len(set(nums)) == 2: shape = "组三"
        r012 = f"{sum(1 for n in nums if n%3==0)}{sum(1 for n in nums if n%3==1)}{sum(1 for n in nums if n%3==2)}"
        lianhao = any(nums[i] + 1 == nums[i+1] for i in range(len(nums)-1))
        tonghao = len(set(nums)) < 3
        return shape, r012, lianhao, tonghao

    res = df["完整号码"].apply(analyze_shape)
    df["形态"] = [r[0] for r in res]
    df["012路"] = [r[1] for r in res]
    df["连号"] = ["是" if r[2] else "否" for r in res]
    df["同号"] = ["是" if r[3] else "否" for r in res]
    df["和值"] = df[["百位", "十位", "个位"]].astype(int).sum(axis=1)
    df["跨度"] = df[["百位", "十位", "个位"]].astype(int).max(axis=1) - df[["百位", "十位", "个位"]].astype(int).min(axis=1)
    return df

# ========== 深度复盘与策略进化 ==========
def review_and_optimize(df):
    latest_row = df.iloc[0]
    latest_qihao = latest_row["期号"]
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pl3_strategy_records WHERE target_qihao = %s;", (latest_qihao,))
            record = cur.fetchone()
            cur.execute("SELECT weights_cold, weights_hot FROM pl3_strategy_records ORDER BY id DESC LIMIT 1;")
            last_weights_row = cur.fetchone()
            cur.execute("SELECT picks FROM pl3_inspiration_pool WHERE target_qihao = %s;", (latest_qihao,))
            insp_records = cur.fetchall()
    finally: conn.close()

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

    detailed_analysis = []
    for p in picks:
        p_nums = [int(c) for c in p]
        pos_hits = sum(1 for a, b in zip(p, actual_code) if a == b)
        is_direct = (p == actual_code)
        is_group = ("".join(sorted(p)) == "".join(sorted(actual_code)))
        
        analysis_str = f"<b>【{p}】</b>: "
        if is_direct: analysis_str += "<span style='color:#69F0AE'>直选命中！</span> "
        elif is_group: analysis_str += "<span style='color:#69F0AE'>组选命中！</span> "
        else: analysis_str += "未中。 "
        
        analysis_str += f"位置命中 {pos_hits} 个 | 和值 {sum(p_nums)} (开奖 {latest_row['和值']})。"
        detailed_analysis.append(analysis_str)

    insp_hits = []
    all_insp_picks = []
    for r in insp_records: all_insp_picks.extend(r["picks"].split(", "))
    all_insp_picks = list(set(all_insp_picks)) 
    
    for p in all_insp_picks:
        if p == actual_code or "".join(sorted(p)) == "".join(sorted(actual_code)):
            insp_hits.append(p)

    new_weights = last_weights.copy()
    if cold_cnt >= 2:
        new_weights["cold"] = min(0.40, new_weights["cold"] + 0.02)
        new_weights["hot"] = max(0.10, new_weights["hot"] - 0.02)
        reflect_text = "本期冷号偏多，下期加大冷号防守。"
    elif hot_cnt >= 2:
        new_weights["hot"] = min(0.30, new_weights["hot"] + 0.05)
        new_weights["cold"] = max(0.20, new_weights["cold"] - 0.05)
        reflect_text = "本期热号较多，下期降低极寒权重，适当顺应热态。"
    else:
        new_weights["cold"] = 0.30
        new_weights["hot"] = 0.20
        reflect_text = "开奖温和平稳，下期回归均衡配置。"

    return new_weights, {
        "qihao": latest_qihao, "actual_code": actual_code, 
        "picks": picks, "cold_cnt": cold_cnt, "hot_cnt": hot_cnt, 
        "detailed_analysis": detailed_analysis, "reflect_text": reflect_text,
        "insp_hits": insp_hits, "total_insp_count": len(all_insp_picks)
    }

# ========== 进阶预测与评估 ==========
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
    
    trans_bias = {}
    latest_nums = [df.iloc[0]["百位"], df.iloc[0]["十位"], df.iloc[0]["个位"]]
    for i, col in enumerate(["百位", "十位", "个位"]):
        prev_num = latest_nums[i]
        mask = df[col].shift(-1) == prev_num
        next_nums = df[mask][col].tolist()
        if next_nums: trans_bias[col] = Counter(next_nums).most_common(1)[0][0]
            
    recent_10 = df.head(10)
    recent_cold_cnt = sum(1 for _, r in recent_10.iterrows() for c in ["百位", "十位", "个位"] if r[c] in cold_pool)
    
    if recent_cold_cnt > 15:
        trend_msg = "近期冷号活跃，防范温/热号反扑。"
        advise_ratio = "建议配比：1冷 + 1温 + 1热"
    else:
        trend_msg = "冷号回补周期即将到来。"
        advise_ratio = "建议配比：2冷 + 1温"
        
    return trend_msg, advise_ratio, sorted(cold_pool), sorted(warm_pool), sorted(hot_pool), trans_bias

def analyze_trial_number(test_code, current_picks):
    nums = [int(c) for c in test_code]
    total_sum = sum(nums)
    span = max(nums) - min(nums)
    combined_picks = "".join(current_picks)
    has_test_num = any(str(n) in combined_picks for n in nums)
    
    advice = []
    if has_test_num: advice.append("推荐号包含试机号数字，防重号。")
    else: advice.append("推荐号避开试机号，防邻码。")
    advice.append(f"杀号参考：杀和尾 <b>{total_sum % 10}</b>，杀跨度 <b>{span}</b>。")
    return total_sum, span, advice

def evaluate_custom_number(df, code):
    nums = [int(c) for c in code]
    total_sum, span = sum(nums), max(nums) - min(nums)
    odd_cnt = sum(1 for n in nums if n % 2 != 0)
    miss = [df.index[df[col] == str(nums[i])].min() if not df[df[col] == str(nums[i])].empty else 1000 for i, col in enumerate(["百位", "十位", "个位"])]
    recent_avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in df.head(100).iterrows()) / 100
    
    pros, cons, score = [], [], 3
    if any(m >= 15 for m in miss): pros.append(f"长遗漏({miss[0]}/{miss[1]}/{miss[2]})"); score += 1
    if any(m <= 3 for m in miss): cons.append("近期过热防转冷"); score -= 1
    if abs(total_sum - recent_avg_sum) <= 3: pros.append(f"和值{total_sum}贴近均值"); score += 1
    elif abs(total_sum - recent_avg_sum) >= 8: cons.append(f"和值{total_sum}偏离均值"); score -= 1
    if 4 <= span <= 8: pros.append(f"跨度{span}在黄金区")
    elif span < 2 or span > 9: cons.append(f"跨度{span}极端"); score -= 1
    if odd_cnt in (0, 3): cons.append("全奇/全偶"); score -= 1
    else: pros.append(f"奇偶比{odd_cnt}:{3-odd_cnt}")
    
    sorted_nums = sorted(nums)
    if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1: cons.append("顺子形态概率低"); score -= 1
    score = max(1, min(5, score))
    return score, pros, cons, miss

def get_recent_gap(df, code):
    matches_idx = df.index[df["完整号码"] == code].tolist()
    return min(matches_idx) if matches_idx else -1

def check_history_appearance(df, code, lookback=1000):
    if df.empty or "完整号码" not in df.columns: return 0, [], []
    recent_df = df.head(lookback)
    matches = recent_df[recent_df["完整号码"] == code]
    periods = matches["期号"].tolist()
    dates = [f"{d.strftime('%Y-%m-%d')}(距今{(datetime.now()-d).days}天)" if pd.notna(d) else "未知" for d in matches["开奖日期"]]
    return len(matches), periods, dates

def generate_picks_core(df, current_weights, exclude_range, analyze_range, num_picks=5, is_extra=False):
    exclude_set = set(df.head(exclude_range)["完整号码"].tolist())
    recent_df = df.head(analyze_range)
    avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in recent_df.iterrows()) / analyze_range
    
    pools = {"冷": {}, "温": {}, "热": {}}
    for col in ["百位", "十位", "个位"]:
        counts = Counter(recent_df[col].tolist())
        sorted_counts = sorted([(str(i), counts.get(str(i), 0)) for i in range(10)], key=lambda x: x[1])
        pools["冷"][col] = [n for n, _ in sorted_counts[:3]]
        pools["温"][col] = [n for n, _ in sorted_counts[3:7]]
        pools["热"][col] = [n for n, _ in sorted_counts[7:]]
        
    picks, reasons = [], []
    attempts = 0
    while len(picks) < num_picks and attempts < 100000:
        attempts += 1
        w_cold = current_weights["cold"] + 0.05 if is_extra else current_weights["cold"]
        w_hot = current_weights["hot"] + 0.05 if is_extra else current_weights["hot"]
        
        b = random.choice(pools["冷"]["百位"]) if random.random() < w_cold else (random.choice(pools["热"]["百位"]) if random.random() < w_hot else random.choice(pools["温"]["百位"]))
        s = random.choice(pools["冷"]["十位"]) if random.random() < w_cold else (random.choice(pools["热"]["十位"]) if random.random() < w_hot else random.choice(pools["温"]["十位"]))
        g = random.choice(pools["冷"]["个位"]) if random.random() < w_cold else (random.choice(pools["热"]["个位"]) if random.random() < w_hot else random.choice(pools["温"]["个位"]))
        
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

        cold_count = sum(1 for x in [b,s,g] if x in pools["冷"]["百位"]+pools["冷"]["十位"]+pools["冷"]["个位"])
        reason = f"和值{total_sum}，跨度{span}。" + ("侧重冷号回补。" if cold_count > 0 else "倾向热/温号。")
        picks.append(code); reasons.append(reason)
        exclude_set.add(code)
    return picks, reasons

# ================= 页面渲染 =================
st.title("🏆 排列三 终极量化终端")
st.caption("体彩专属 | 遗漏回归 | 试机号联动 | 全维度统计")

with st.spinner("同步体彩数据中..."):
    sync_database()
    df = load_data_from_db()

if df.empty: 
    st.error("云端数据为空，请点击左侧手动同步或稍后刷新。")
    st.stop()

with st.sidebar:
    st.header("⚙️ 参数调节")
    exclude_range = st.slider("排重期数", 50, 500, 100, step=10)
    analyze_range = st.slider("冷热分析期数", 50, 200, 100, step=10)
    
    st.markdown("---")
    st.header("🎲 今日试机号")
    test_b = st.selectbox("试机号 百位", [str(i) for i in range(10)], index=0, key="test_b")
    test_s = st.selectbox("试机号 十位", [str(i) for i in range(10)], index=0, key="test_s")
    test_g = st.selectbox("试机号 个位", [str(i) for i in range(10)], index=0, key="test_g")
    test_code = f"{test_b}{test_s}{test_g}"
    
    st.markdown("---")
    st.header("🔍 号码查重")
    search_code = st.text_input("输入3位数字", max_chars=3)
    if search_code and len(search_code) == 3 and search_code.isdigit():
        count, periods, dates = check_history_appearance(df, search_code, 1000)
        if count > 0: st.warning(f"⚠️ {search_code} 近千期出现 {count} 次:\n" + "\n".join([f"{p} ({d})" for p, d in zip(periods, dates)]))
        else: st.success(f"✨ {search_code} 近1000期未开出")
        
    st.markdown("---")
    if st.button("🔄 手动触发数据同步", use_container_width=True):
        st.cache_data.clear()
        sync_database()
        st.success("同步成功！")

current_weights, review_data = review_and_optimize(df)
latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]
target_qihao = str(int(latest_qihao) + 1) if latest_qihao.isdigit() else latest_qihao + "_next"

# --- 顶部：深度复盘 ---
if review_data:
    analysis_html = "<br>".join(review_data['detailed_analysis'])
    insp_html = ""
    if review_data['insp_hits']:
        hits_str = ", ".join(review_data['insp_hits'])
        insp_html = f'<div class="insp-hit">🎯 灵感池捕获！昨天生成的 {review_data["total_insp_count"]} 注中，命中：{hits_str}</div>'
    elif review_data['total_insp_count'] > 0:
        insp_html = f'<div style="margin-top:10px; color:#B0BEC5; font-size:13px;">(昨日共生成 {review_data["total_insp_count"]} 注灵感号码，未命中)</div>'

    st.markdown(f"""<div class="review-card">
<h4>📝 昨日深度复盘：第 {review_data['qihao']} 期</h4>
<div style="margin-bottom:12px; font-size:16px;">实际开奖：<b style="font-size:22px; color:#FFD54F !important;">{review_data['actual_code']}</b> (冷{review_data['cold_cnt']}/热{review_data['hot_cnt']})</div>
<div style="background:rgba(255,255,255,0.1); padding:12px; border-radius:8px;">{analysis_html}</div>
{insp_html}
<div style="margin-top:12px; font-weight:bold; color:#FFD54F !important;">🧠 策略进化：{review_data['reflect_text']}</div>
</div>""", unsafe_allow_html=True)
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
            cur.execute("SELECT * FROM pl3_strategy_records WHERE target_qihao = %s;", (target_qihao,))
            today_record = cur.fetchone()
    finally: conn.close()

    if today_record:
        picks = today_record["picks"].split(", ")
        reasons = today_record["reasons"].split(" | ")
    else:
        picks, reasons = generate_picks_core(df, current_weights, exclude_range, analyze_range, num_picks=5, is_extra=False)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO pl3_strategy_records (date, target_qihao, picks, reasons, weights_cold, weights_hot) VALUES (%s, %s, %s, %s, %s, %s);",
                    (datetime.now().strftime("%Y-%m-%d %H:%M"), target_qihao, ", ".join(picks), " | ".join(reasons), current_weights["cold"], current_weights["hot"]))
            conn.commit()
        finally: conn.close()

    t_sum, t_span, t_advice = analyze_trial_number(test_code, picks)
    st.markdown(f"""<div style="background:#E3F2FD; padding:12px; border-radius:8px; margin-bottom:12px; font-size:13px; border-left:4px solid #1A237E;">
<b style="color:#1A237E;">🎲 试机号 [{test_code}] 联动：</b><br>
{"<br>".join(t_advice)}
</div>""", unsafe_allow_html=True)

    c_pick1, c_pick2 = st.columns(2)
    for i, code in enumerate(picks):
        count, _, _ = check_history_appearance(df, code, 1000)
        gap = get_recent_gap(df, code)
        status = f"<span class='badge badge-warning'>出{count}次(隔{gap}期)</span>" if count>0 else "<span class='badge badge-success'>未开</span>"
        
        target_col = c_pick1 if i % 2 == 0 else c_pick2
        with target_col:
            st.markdown(f"""<div class="apple-card">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;"><div class="pick-number">{code}</div> <div>{status}</div></div>
<div class="reason-text">💡 {reasons[i]}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("### 💡 灵感号码池")
    if "extra_picks" not in st.session_state: st.session_state.extra_picks = ([], [])
    if st.button("🔄 刷新灵感池", use_container_width=True):
        new_picks, new_reasons = generate_picks_core(df, current_weights, exclude_range, analyze_range, num_picks=5, is_extra=True)
        st.session_state.extra_picks = (new_picks, new_reasons)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur: cur.execute("INSERT INTO pl3_inspiration_pool (target_qihao, picks) VALUES (%s, %s);", (target_qihao, ", ".join(new_picks)))
            conn.commit()
        finally: conn.close()
    
    extra_picks, extra_reasons = st.session_state.extra_picks
    if extra_picks:
        c_ex1, c_ex2 = st.columns(2)
        for i, (code, reason) in enumerate(zip(extra_picks, extra_reasons)):
            gap = get_recent_gap(df, code)
            target_col = c_ex1 if i % 2 == 0 else c_ex2
            with target_col:
                st.markdown(f"""<div class="apple-card" style="padding: 8px 12px; border-left-color: #1A237E;">
<div style="display:flex; justify-content:space-between; align-items:center;"><div style="font-size:22px; font-weight:bold; color:#1A237E;">{code}</div><div style="font-size:11px; color:#86868b;">距今{gap}期</div></div>
<div style="font-size:11px; color:#666;">{reason}</div>
</div>""", unsafe_allow_html=True)

# ---------------- 右侧：冷热与形态统计 ----------------
with col_right:
    st.markdown("### 🌡️ 下期预测与形态统计")
    trend_msg, ratio_msg, colds, warms, hots, trans_bias = predict_next_cold_hot(df)
    
    st.markdown(f"""<div style="background:#fff; padding:15px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.03); margin-bottom:15px;">
<div style="font-size:15px; color:#1A237E; font-weight:bold; margin-bottom:8px;">🔮 趋势与马尔可夫预测</div>
<div style="margin-bottom:10px;">{trend_msg}</div>
<div style="background:#FFF3E0; display:inline-block; padding:4px 12px; border-radius:20px; color:#FF5722; font-weight:bold; font-size:14px;">{ratio_msg}</div>
<div style="margin-top:10px; font-size:13px; color:#666;">🧠 马尔可夫转移偏好：百位→<b>{trans_bias.get('百位','-')}</b> | 十位→<b>{trans_bias.get('十位','-')}</b> | 个位→<b>{trans_bias.get('个位','-')}</b></div>
</div>""", unsafe_allow_html=True)
    
    st.markdown(f"""<div style="display:flex; gap:10px; margin-bottom:15px;">
<div style="flex:1; background:#E0F7FA; padding:10px; border-radius:8px; text-align:center;"><b style="color:#00BCD4;">❄️ 冷号池</b><br>{', '.join(colds)}</div>
<div style="flex:1; background:#F1F8E9; padding:10px; border-radius:8px; text-align:center;"><b style="color:#8BC34A;">🌤️ 温号池</b><br>{', '.join(warms)}</div>
<div style="flex:1; background:#FBE9E7; padding:10px; border-radius:8px; text-align:center;"><b style="color:#FF5722;">🔥 热号池</b><br>{', '.join(hots)}</div>
</div>""", unsafe_allow_html=True)

    recent_100 = df.head(100)
    lian_rate = (recent_100["连号"] == "是").mean() * 100
    tong_rate = (recent_100["同号"] == "是").mean() * 100
    st.markdown(f"""<div style="background:#f5f5f7; padding:10px; border-radius:8px; font-size:13px; margin-bottom:15px;">
<b>📊 近100期形态特征：</b> 连号率 <b>{lian_rate:.1f}%</b> | 含同号率 <b>{tong_rate:.1f}%</b> (组三/豹子)
</div>""", unsafe_allow_html=True)

    # ===== 重号统计升级版 =====
    show_repeat_details = st.toggle("显示重复号码明细", value=False, key="toggle_repeat")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, window in zip([c1, c2, c3, c4, c5], [100, 200, 300, 500, 1000]):
        window_df = df.head(window)
        dup = window_df["完整号码"].value_counts()
        dup = dup[dup >= 2]
        prob = (dup.sum()/window)*100 if window > 0 else 0
        with col:
            st.metric(label=f"近 {window} 期", value=f"{prob:.1f}%")
            st.caption(f"重号 {len(dup)} 个")
            
    if show_repeat_details:
        st.markdown("---")
        cols_d = st.columns(5)
        for col, window in zip(cols_d, [100, 200, 300, 500, 1000]):
            window_df = df.head(window)
            dup = window_df["完整号码"].value_counts()
            dup = dup[dup >= 2]
            with col:
                if not dup.empty:
                    dup_df = pd.DataFrame({"号码": dup.index, "次数": dup.values})
                    st.dataframe(dup_df, hide_index=True, use_container_width=True)
                else:
                    st.caption("无重复")

st.divider()

# ================= Row 3: 走势与模拟评估 =================
st.markdown("### 📈 深度走势分析与模拟推演")
col_chart, col_shape = st.columns([2.2, 1], gap="small")

with col_chart:
    sim_cols = st.columns([1, 1, 1, 1.2])
    sim_b = sim_cols[0].selectbox("百位选号", options=[str(i) for i in range(10)], index=3, key="sim_b")
    sim_s = sim_cols[1].selectbox("十位选号", options=[str(i) for i in range(10)], index=4, key="sim_s")
    sim_g = sim_cols[2].selectbox("个位选号", options=[str(i) for i in range(10)], index=6, key="sim_g")
    custom_code = f"{sim_b}{sim_s}{sim_g}"
    
    pred_nums = [int(sim_b), int(sim_s), int(sim_g)]
    pred_012 = f"{sum(1 for n in pred_nums if n%3==0)}{sum(1 for n in pred_nums if n%3==1)}{sum(1 for n in pred_nums if n%3==2)}"
    pred_sum = sum(pred_nums)
    
    sim_cols[3].markdown(f"<div style='margin-top:28px; text-align:center; font-size:22px; font-weight:bold; color:#FF5722;'>预测: {custom_code}</div>", unsafe_allow_html=True)

    chart_data = df.head(30).copy().sort_values("期号", ascending=True)
    chart_data["期号简写"] = chart_data["期号"].astype(str).str[-3:]
    for c in ["百位", "十位", "个位"]: chart_data[c] = chart_data[c].astype(int)

    next_qihao_str = "下期预测"
    pred_row = pd.DataFrame([{"期号简写": next_qihao_str, "百位": int(sim_b), "十位": int(sim_s), "个位": int(sim_g), "形态": "预测", "012路": pred_012, "和值": pred_sum, "跨度": max(pred_nums) - min(pred_nums)}])
    chart_data = pd.concat([chart_data, pred_row], ignore_index=True)
    melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
    melted_df['x_pos'] = melted_df.apply(lambda r: r['数值'] if r['位置']=='百位' else (r['数值']+12 if r['位置']=='十位' else r['数值']+24), axis=1)
    melted_df['is_pred'] = melted_df['期号简写'] == next_qihao_str
    
    x_axis = alt.X('x_pos:Q', scale=alt.Scale(domain=[-1, 34]), axis=alt.Axis(values=[0,1,2,3,4,5,6,7,8,9, 12,13,14,15,16,17,18,19,20,21, 24,25,26,27,28,29,30,31,32,33], labelExpr="datum.value < 10 ? datum.value : (datum.value < 22 ? datum.value - 12 : datum.value - 24)", title="号码（百位 | 十位 | 个位）", labelColor='#1d1d1f', titleColor='#1d1d1f'))
    y_axis = alt.Y('期号简写:N', sort=chart_data['期号简写'].tolist(), axis=alt.Axis(labelAngle=0, labelOverlap=False, labelColor='#1d1d1f'))
    
    line_chart = alt.Chart(melted_df[~melted_df['is_pred']]).mark_line(point=alt.OverlayMarkDef(size=40, filled=True, stroke='white', strokeWidth=2), strokeWidth=2).encode(x=x_axis, y=y_axis, color=alt.Color('位置:N', scale=alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#1A237E', '#4CAF50'])), tooltip=['期号简写', '位置', '数值'])
    connect_df = melted_df[melted_df['期号简写'].isin([chart_data.iloc[-2]["期号简写"], next_qihao_str])]
    dashed_lines = alt.Chart(connect_df).mark_line(strokeDash=[5, 5], strokeWidth=2).encode(x=x_axis, y=y_axis, color='位置:N')
    pred_points = alt.Chart(melted_df[melted_df['is_pred']]).mark_point(size=150, filled=True, color='#FF5722', opacity=1).encode(x=x_axis, y=y_axis)
    
    vlines = pd.DataFrame({'x': [10.5, 22.5]})
    vline_chart = alt.Chart(vlines).mark_rule(color='#e5e5ea', strokeWidth=1, strokeDash=[4,4]).encode(x='x:Q')
    texts = pd.DataFrame({'x': [4.5, 16.5, 28.5], 'text': ['百位', '十位', '个位']})
    text_chart = alt.Chart(texts).mark_text(dy=-10, fontWeight='bold', color='#86868b').encode(x='x:Q', text='text:N')
    
    final_chart = (vline_chart + line_chart + dashed_lines + pred_points + text_chart).properties(height=550, background='transparent').interactive()
    st.altair_chart(final_chart, use_container_width=True)

with col_shape:
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.markdown("**形态与 012路**")
    shape_df = chart_data[["期号简写", "形态", "012路", "和值"]].copy()
    shape_df = shape_df.sort_values("期号简写", ascending=False).reset_index(drop=True)
    shape_df.columns = ["期号", "形态", "012路", "和值"]
    st.dataframe(shape_df, hide_index=True, use_container_width=True, height=550)

# --- 实时生成评估报告 ---
st.markdown("### 📋 预测号码综合评估报告")
score, pros, cons, miss = evaluate_custom_number(df, custom_code)
count, _, _ = check_history_appearance(df, custom_code, 1000)

pros_text = "<br>".join(['· ' + p for p in pros]) if pros else "· 无"
cons_text = "<br>".join(['· ' + c for c in cons]) if cons else "· 无"

eval_html = f"""<div class="eval-card">
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e5e5ea; padding-bottom:10px; margin-bottom:15px;">
<h4 style="margin:0;">预测号码 <span style="color:#FF5722;">{custom_code}</span></h4>
<div><span style="font-weight:bold; font-size:14px;">推荐星级：</span> <span class="star-text">{'★'*score}{'☆'*(5-score)}</span><span style="color:#86868b; font-size:12px; margin-left:10px;">近千期开出 {count} 次</span></div>
</div>
<div style="display:flex; gap:15px;">
<div style="flex:1; background:#f5f5f7; padding:12px; border-radius:8px; font-size:13px;"><b>📍 位置遗漏</b><br>百位: {miss[0]} 期<br>十位: {miss[1]} 期<br>个位: {miss[2]} 期</div>
<div style="flex:1; background:#E8F5E9; padding:12px; border-radius:8px; color:#2E7D32; font-size:13px;"><b>✅ 优势</b><br>{pros_text}</div>
<div style="flex:1; background:#FFF3E0; padding:12px; border-radius:8px; color:#E65100; font-size:13px;"><b>⚠️ 风险</b><br>{cons_text}</div>
</div>
</div>"""
st.markdown(eval_html, unsafe_allow_html=True)

# ================= Row 4: 历史推荐档案库 =================
st.divider()
with st.expander("📂 历史推荐档案库", expanded=False):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pl3_strategy_records ORDER BY id DESC LIMIT 10;")
            history_records = cur.fetchall()
    finally:
        conn.close()
        
    if history_records:
        hist_df = pd.DataFrame(history_records)
        hist_df = hist_df.rename(columns={"date": "生成时间", "target_qihao": "目标期号", "picks": "推荐号码", "reasons": "策略逻辑", "weights_cold": "冷号权重", "weights_hot": "热号权重"})
        hist_df = hist_df[["目标期号", "推荐号码", "生成时间", "冷号权重", "热号权重"]]
        st.dataframe(hist_df, hide_index=True, use_container_width=True)
    else:
        st.info("暂无历史推荐记录。")
