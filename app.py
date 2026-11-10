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

# 宽屏模式
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
    /* 卡片紧凑化 */
    .apple-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 10px 14px; /* 大幅缩小内边距 */
        margin-bottom: 8px; /* 缩小间距 */
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        border: 1px solid #e5e5ea;
    }
    .apple-title { font-size: 12px; font-weight: 600; color: #86868b !important; margin-bottom: 2px; }
    .pick-number {
        font-size: 28px; /* 字号缩小 */
        font-weight: 800; color: #007aff !important;
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
        padding: 12px;
        margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        font-size: 14px;
    }
    /* 评估报告样式 */
    .eval-card {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        border: 1px solid #e5e5ea;
    }
    .star-text { color: #ff9500 !important; font-size: 24px; }
    
    /* 调整图表所在容器高度对齐 */
    [data-testid="column"] { padding: 0 10px; }
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
    except:
        pass
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
    return df

# ========== 核心：复盘与策略进化 ==========
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
    finally:
        conn.close()

    default_weights = {"cold": 0.30, "hot": 0.20}
    if last_weights_row:
        last_weights = {
            "cold": last_weights_row.get("weights_cold") if last_weights_row.get("weights_cold") is not None else 0.30,
            "hot": last_weights_row.get("weights_hot") if last_weights_row.get("weights_hot") is not None else 0.20
        }
    else:
        last_weights = default_weights.copy()

    if not record:
        return last_weights, None

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

    direct_hit = any(p == actual_code for p in picks)
    sorted_actual = "".join(sorted(actual_code))
    group_hit = any("".join(sorted(p)) == sorted_actual for p in picks)
    
    new_weights = last_weights.copy()
    if cold_cnt >= 2:
        new_weights["cold"] = min(0.40, new_weights["cold"] + 0.02)
        new_weights["hot"] = max(0.10, new_weights["hot"] - 0.02)
        reflect_text = "本期冷号偏多（回补强烈），下期加大冷号搜索。"
    elif hot_cnt >= 2:
        new_weights["hot"] = min(0.30, new_weights["hot"] + 0.05)
        new_weights["cold"] = max(0.20, new_weights["cold"] - 0.05)
        reflect_text = "本期热号较多，下期降低纯冷号权重，适当跟热。"
    else:
        new_weights["cold"] = 0.30
        new_weights["hot"] = 0.20
        reflect_text = "形态温和平稳，下期回归均衡权重。"

    return new_weights, {
        "qihao": latest_qihao, "actual_code": actual_code, "picks": picks,
        "cold_cnt": cold_cnt, "hot_cnt": hot_cnt, "direct_hit": direct_hit,
        "group_hit": group_hit, "reflect_text": reflect_text
    }

# ========== 趋势与评估功能 ==========
def analyze_cold_hot_trend(df):
    results = []
    for window in [10, 20, 50]:
        recent_df = df.iloc[1:window+1]
        base_df = df.iloc[window+1:window+101]
        freq_counter = Counter()
        for _, r in base_df.iterrows():
            for c in ["百位", "十位", "个位"]: freq_counter[r[c]] += 1
            
        c_count, h_count, w_count = 0, 0, 0
        for _, r in recent_df.iterrows():
            for c in ["百位", "十位", "个位"]:
                num = r[c]
                f = freq_counter.get(num, 0)
                if f <= 5: c_count += 1
                elif f >= 12: h_count += 1
                else: w_count += 1
        
        total = c_count + h_count + w_count
        results.append({"周期": f"近{window}期", "冷号": c_count/total if total else 0, "温号": w_count/total if total else 0, "热号": h_count/total if total else 0})
    return pd.DataFrame(results)

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
    
    if any(m >= 15 for m in miss): 
        pros.append(f"长遗漏(百/十/个: {miss[0]}/{miss[1]}/{miss[2]})")
        score += 1
    if any(m <= 3 for m in miss):
        cons.append("近期过热防转冷")
        score -= 1
        
    if abs(total_sum - recent_avg_sum) <= 3:
        pros.append(f"和值{total_sum}贴近均值")
        score += 1
    elif abs(total_sum - recent_avg_sum) >= 8:
        cons.append(f"和值{total_sum}偏离均值")
        score -= 1
        
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

# ========== 推荐生成逻辑 ==========
def generate_picks_core(df, current_weights, num_picks=5, is_extra=False):
    exclude_set = set(df.head(EXCLUDE_RANGE)["完整号码"].tolist())
    recent_df = df.head(RECENT_ANALYZE)
    avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in recent_df.iterrows()) / RECENT_ANALYZE
    
    hot_pool, cold_pool, warm_pool = {}, {}, {}
    for col in ["百位", "十位", "个位"]:
        counts = Counter(recent_df[col].tolist())
        hot_pool[col] = [n for n, _ in counts.most_common(4)]
        cold_pool[col] = [n for n, c in counts.items() if c <= 5] or [str(i) for i in range(10) if str(i) not in hot_pool[col]][:3]
        warm_pool[col] = [str(i) for i in range(10) if str(i) not in hot_pool[col] and str(i) not in cold_pool[col]]

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

# --- 顶部：复盘与状态 ---
if review_data:
    st.markdown(f"""
    <div class="review-card">
        <b style="color:#ff9500;">📝 昨日复盘：</b> 第 {review_data['qihao']} 期开奖号 <code>{review_data['actual_code']}</code> (冷{review_data['cold_cnt']}/热{review_data['hot_cnt']})。
        推荐号 {', '.join(review_data['picks'])}。命中：{'🎉直选' if review_data['direct_hit'] else '✅组选' if review_data['group_hit'] else '❌未中'}。<br>
        <b>🧠 策略进化：</b>{review_data['reflect_text']}
    </div>
    """, unsafe_allow_html=True)
else:
    st.info(f"当前基准: 第 {latest_qihao} 期。正在使用基础策略权重。")

# ================= 核心布局：分栏仪表盘 =================
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

    # 将精选推荐以双列排版，更加紧凑
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
        st.session_state.extra_picks = generate_picks_core(df, current_weights, num_picks=5, is_extra=True)
    
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
        st.info("点击上方按钮生成灵感号码。")

# ---------------- 右侧：冷热趋势与重号统计 ----------------
with col_right:
    st.markdown("### 🌡️ 近期冷热形态追踪")
    trend_df = analyze_cold_hot_trend(df)
    chart_df = trend_df.melt(id_vars=["周期"], value_vars=["冷号", "温号", "热号"], var_name="类型", value_name="比例")
    chart_trend = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X('周期:N', sort=None),
        y=alt.Y('比例:Q', stack='normalize', axis=alt.Axis(format='%')),
        color=alt.Color('类型:N', scale=alt.Scale(domain=['冷号', '温号', '热号'], range=['#00BCD4', '#8BC34A', '#FF5722'])),
        tooltip=['周期', '类型', alt.Tooltip('比例:Q', format='.1%')]
    ).properties(height=200, background='transparent')
    st.altair_chart(chart_trend, use_container_width=True)
    
    c10 = trend_df[trend_df["周期"]=="近10期"].iloc[0]
    if c10["热号"] > 0.4: st.caption("🔥 **近10期热号偏多**，注意防范强者恒强。")
    elif c10["冷号"] > 0.4: st.caption("❄️ **近10期冷号偏多**，处于冷号回补期。")
    else: st.caption("⚖️ 近期冷热较均衡，温号主导。")

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

# ================= Row 3: 走势图与定制评估 (左右并排) =================
st.markdown("### 📈 深度分析与定制评估")
col_chart, col_eval = st.columns([2, 1], gap="large")

with col_chart:
    st.markdown("**走势图 (综合走势)**")
    chart_data = df.head(30).copy().sort_values("期号", ascending=True)
    chart_data["期号简写"] = chart_data["期号"].astype(str).str[-3:]
    for c in ["百位", "十位", "个位"]: chart_data[c] = chart_data[c].astype(int)

    # 强制显示所有 Y 轴刻度（取消隐藏重叠）
    y_axis = alt.Y('期号简写:N', 
                   sort=chart_data['期号简写'].tolist(), 
                   axis=alt.Axis(labelAngle=0, labelOverlap=False, tickCount=chart_data.shape[0]))
    
    melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
    x_axis = alt.X('数值:Q', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10))))
    
    chart = alt.Chart(melted_df).mark_line(point=alt.OverlayMarkDef(size=40, filled=True, stroke='white', strokeWidth=2), strokeWidth=2).encode(
        x=x_axis, y=y_axis, 
        color=alt.Color('位置:N', scale=alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#00BCD4', '#8BC34A'])),
        tooltip=['期号简写', '位置', '数值']
    ).properties(height=600, background='transparent').interactive()
    
    st.altair_chart(chart, use_container_width=True)

with col_eval:
    st.markdown("**定制号码评估**")
    col_b, col_s, col_g = st.columns(3)
    sel_b = col_b.selectbox("百位", options=[str(i) for i in range(10)], key="sb_b")
    sel_s = col_s.selectbox("十位", options=[str(i) for i in range(10)], key="sb_s")
    sel_g = col_g.selectbox("个位", options=[str(i) for i in range(10)], key="sb_g")
    custom_code = f"{sel_b}{sel_s}{sel_g}"
    
    if st.button("生成综合评估报告", use_container_width=True):
        score, pros, cons, miss = evaluate_custom_number(df, custom_code)
        count, _, _ = check_history_appearance(df, custom_code, 1000)
        
        st.markdown(f"""
        <div class="eval-card">
            <h4 style="margin-top:0;">号码 <span style="color:#007aff;">{custom_code}</span></h4>
            <div style="margin-bottom:10px;">
                <span style="font-weight:bold; font-size:14px;">推荐星级：</span> <span class="star-text">{'★'*score}{'☆'*(5-score)}</span>
                <div style="color:#86868b; font-size:12px; margin-top:4px;">近千期开出 {count} 次</div>
            </div>
            
            <div style="background:#f5f5f7; padding:10px; border-radius:8px; margin-bottom:10px; font-size:13px;">
                <b>📍 位置遗漏</b><br>
                百: {miss[0]} 期 | 十: {miss[1]} 期 | 个: {miss[2]} 期
            </div>
            
            <div style="background:#e8f8ee; padding:10px; border-radius:8px; color:#28cd41; font-size:13px; margin-bottom:10px;">
                <b>✅ 优势</b><br>{"<br>".join(['· ' + p for p in pros]) if pros else '· 无'}
            </div>
            
            <div style="background:#fff4e6; padding:10px; border-radius:8px; color:#ff9500; font-size:13px;">
                <b>⚠️ 风险</b><br>{"<br>".join(['· ' + c for c in cons]) if cons else '· 无'}
            </div>
        </div>
        """, unsafe_allow_html=True)
