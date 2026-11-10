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

st.set_page_config(page_title="福彩3D 智能分析", page_icon="🎯", layout="centered")

# ================= 苹果明亮风 + 马卡龙晕染 + 组件深度美化 CSS =================
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
    [data-testid="stRadio"] > div, [data-testid="stSelectbox"] > div {
        background-color: #ffffff !important;
        padding: 10px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.9) !important;
        padding: 15px;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid rgba(0,0,0,0.03);
    }
    [data-testid="stMetricValue"] { color: #1d1d1f !important; font-weight: 800; font-size: 28px; }
    [data-testid="stMetricLabel"] { color: #86868b !important; }
    .stInfo {
        background-color: #ffffff !important;
        border: 1px solid #e5e5ea !important;
        border-radius: 14px;
    }
    .apple-card {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        border: 1px solid #e5e5ea;
    }
    .apple-title { font-size: 15px; font-weight: 600; color: #86868b !important; margin-bottom: 8px; }
    .pick-number {
        font-size: 48px; font-weight: 800; color: #007aff !important;
        letter-spacing: 8px; margin-bottom: 12px; font-family: monospace;
    }
    .reason-text { font-size: 14px; color: #1d1d1f !important; line-height: 1.5; margin-top: 10px; }
    .badge { display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }
    .badge-success { background-color: #e8f8ee; color: #28cd41 !important; }
    .badge-warning { background-color: #fff4e6; color: #ff9500 !important; }
    
    /* 复盘卡片专用样式 */
    .review-card {
        background-color: #fff9f0;
        border-left: 6px solid #ff9500;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
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
            st.info("首次运行：正在初始化云端数据库，全量抓取历史数据（约需几十秒）...")
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
                    VALUES %s
                    ON CONFLICT (qihao) DO UPDATE SET
                        riqi = EXCLUDED.riqi, bai = EXCLUDED.bai, shi = EXCLUDED.shi, ge = EXCLUDED.ge;
                """
                values = [(d["code"], d["day"], str(d["one"]), str(d["two"]), str(d["three"])) for d in records_to_insert]
                psycopg2.extras.execute_values(cur, insert_query, values)
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"同步数据时出错: {e}")
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

# ========== 进阶分析算法 ==========
def check_history_appearance(df, code, lookback=1000):
    recent_df = df.head(lookback)
    matches = recent_df[recent_df["完整号码"] == code]
    periods = matches["期号"].tolist()
    dates = []
    today = datetime.now()
    for d in matches["开奖日期"]:
        if pd.notna(d):
            days_ago = (today - d).days
            dates.append(f"{d.strftime('%Y-%m-%d')}(距今{days_ago}天)")
        else:
            dates.append("日期未知")
    return len(matches), periods, dates

def calculate_actual_repeat_stats(df, window):
    window_df = df.head(window)
    counts = window_df["完整号码"].value_counts()
    duplicated_codes = counts[counts >= 2]
    return len(duplicated_codes), duplicated_codes.sum(), (duplicated_codes.sum()/window)*100 if window>0 else 0, duplicated_codes

def get_missing_values(df, col_name, lookback=100):
    recent_df = df.head(lookback)
    missing = {}
    for num in range(10):
        num_str = str(num)
        matches = recent_df[recent_df[col_name] == num_str]
        missing[num_str] = lookback if matches.empty else matches.index[0]
    return dict(sorted(missing.items(), key=lambda item: item[1], reverse=True))

def get_recent_gap(df, code):
    """获取某个号码距离最近一次出现的间隔期数"""
    matches_idx = df.index[df["完整号码"] == code].tolist()
    if matches_idx:
        return min(matches_idx)
    return -1 # 没出现过

# ========== 核心：复盘与策略进化 ==========
def review_and_optimize(df):
    """每日复盘前一期推荐，并根据最新开奖结果调整冷热权重"""
    latest_row = df.iloc[0]
    latest_qihao = latest_row["期号"]
    
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 查找是否有针对最新这一期的推荐
            cur.execute("SELECT * FROM strategy_records WHERE target_qihao = %s;", (latest_qihao,))
            record = cur.fetchone()
            
            # 获取上一次的权重作为默认值
            cur.execute("SELECT weights_cold, weights_hot FROM strategy_records ORDER BY id DESC LIMIT 1;")
            last_weights_row = cur.fetchone()
    finally:
        conn.close()

    default_weights = {"cold": 0.30, "hot": 0.20} # 调整默认基础权重
    
    # 修复 KeyError：安全地将数据库字段映射为标准键名
    if last_weights_row:
        last_weights = {
            "cold": last_weights_row.get("weights_cold") if last_weights_row.get("weights_cold") is not None else 0.30,
            "hot": last_weights_row.get("weights_hot") if last_weights_row.get("weights_hot") is not None else 0.20
        }
    else:
        last_weights = default_weights.copy()

    if not record:
        # 如果没找到这一期的推荐，直接返回上次权重，不生成复盘数据
        return last_weights, None

    picks = record["picks"].split(", ")
    reasons = record["reasons"].split(" | ")
    
    actual_code = latest_row["完整号码"]
    
    # 分析最新开奖号的冷热形态（基于开奖前100期）
    recent_100 = df.iloc[1:101]
    freq_counter = Counter()
    for _, r in recent_100.iterrows():
        for c in ["百位", "十位", "个位"]:
            freq_counter[r[c]] += 1
            
    actual_nums = [latest_row["百位"], latest_row["十位"], latest_row["个位"]]
    cold_cnt, hot_cnt = 0, 0
    for n in actual_nums:
        f = freq_counter.get(n, 0)
        if f <= 5: cold_cnt += 1
        elif f >= 12: hot_cnt += 1

    # 命中检测
    direct_hit = any(p == actual_code for p in picks)
    sorted_actual = "".join(sorted(actual_code))
    group_hit = any("".join(sorted(p)) == sorted_actual for p in picks)
    
    # 进化逻辑
    new_weights = last_weights.copy()
    
    if cold_cnt >= 2:
        # 再次开出冷号，说明冷号在回补，适当维持冷号高权重，热号降低
        new_weights["cold"] = min(0.40, new_weights["cold"] + 0.02)
        new_weights["hot"] = max(0.10, new_weights["hot"] - 0.02)
        reflect_text = "本期开奖结果中冷号偏多（回补强烈），说明防守策略有效。下一期将**加大冷号搜索力度**。"
    elif hot_cnt >= 2:
        # 开出热号，说明极寒策略失效，要拉回一点热号权重
        new_weights["hot"] = min(0.30, new_weights["hot"] + 0.05)
        new_weights["cold"] = max(0.20, new_weights["cold"] - 0.05)
        reflect_text = "本期开奖结果中热号较多，冷号回补未如期而至。下一期将**降低纯冷号权重，适当跟热**。"
    else:
        # 温号主导，回归均衡
        new_weights["cold"] = 0.30
        new_weights["hot"] = 0.20
        reflect_text = "本期开奖形态温和平稳，下一期将**回归均衡权重，冷温热搭配**。"

    review_data = {
        "qihao": latest_qihao,
        "actual_code": actual_code,
        "picks": picks,
        "reasons": reasons,
        "cold_cnt": cold_cnt,
        "hot_cnt": hot_cnt,
        "direct_hit": direct_hit,
        "group_hit": group_hit,
        "reflect_text": reflect_text,
        "new_weights": new_weights
    }
    
    return new_weights, review_data

# ========== 推荐生成逻辑 ==========
def generate_picks_core(df, current_weights, num_picks=5, is_extra=False):
    """核心选号函数，is_extra 用来区分是精选还是额外推荐"""
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
        
        # 额外推荐的权重稍微均衡一些，避免和精选完全重样
        w_cold = current_weights["cold"] + 0.05 if is_extra else current_weights["cold"]
        w_hot = current_weights["hot"] + 0.05 if is_extra else current_weights["hot"]
        
        b = random.choice(cold_pool["百位"]) if random.random() < w_cold else (random.choice(hot_pool["百位"]) if random.random() < w_hot else random.choice(warm_pool["百位"]))
        s = random.choice(cold_pool["十位"]) if random.random() < w_cold else (random.choice(hot_pool["十位"]) if random.random() < w_hot else random.choice(warm_pool["十位"]))
        g = random.choice(cold_pool["个位"]) if random.random() < w_cold else (random.choice(hot_pool["个位"]) if random.random() < w_hot else random.choice(warm_pool["个位"]))
        
        code = f"{b}{s}{g}"
        if code in exclude_set: continue
            
        nums = [int(b), int(s), int(g)]
        total_sum = sum(nums)
        span = max(nums) - min(nums)
        odd_cnt = sum(1 for n in nums if n % 2 != 0)
        
        if not (avg_sum - 4 <= total_sum <= avg_sum + 4): continue
        if not (2 <= span <= 9): continue
        if odd_cnt in (0, 3): continue
        
        sorted_nums = sorted(nums)
        if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1 and random.random() < 0.8:
            continue

        # 生成推荐理由
        cold_count = sum(1 for x in [b,s,g] if x in cold_pool["百位"]+cold_pool["十位"]+cold_pool["个位"])
        hot_count = sum(1 for x in [b,s,g] if x in hot_pool["百位"]+hot_pool["十位"]+hot_pool["个位"])
        reason = f"和值{total_sum}，跨度{span}，奇偶比{odd_cnt}:{3-odd_cnt}。"
        if cold_count > 0: reason += " 侧重冷号回补。"
        elif hot_count > 0: reason += " 倾向热号延续。"

        picks.append(code)
        reasons.append(reason)
        exclude_set.add(code)
        
    return picks, reasons

# ================= 页面 UI 渲染 =================
st.title("🎯 福彩3D 智能分析终端")
st.caption("动态策略进化 | 每日深度复盘 | 马卡龙明亮风")

with st.sidebar:
    st.header("🔍 号码查重 (近1000期)")
    search_code = st.text_input("输入3位数字", max_chars=3)
    st.markdown("---")
    if st.button("🔄 手动触发云端数据同步", use_container_width=True):
        sync_database()
        st.success("同步成功！")

with st.spinner("正在同步最新数据并复盘..."):
    sync_database()
    df = load_data_from_db()

if df.empty: 
    st.error("云端数据为空，请稍后刷新重试。")
    st.stop()

# ================= 1. 核心：每日复盘与调仓 =================
current_weights, review_data = review_and_optimize(df)
latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]

if review_data:
    st.markdown("""
    <div class="review-card">
        <h3 style="margin-top:0; color:#ff9500;">📝 昨日复盘与策略进化</h3>
    """, unsafe_allow_html=True)
    
    st.write(f"**第 {review_data['qihao']} 期开奖结果：** `{review_data['actual_code']}` (冷号{review_data['cold_cnt']}个, 热号{review_data['hot_cnt']}个)")
    st.write(f"**昨日推荐号码：** {', '.join(review_data['picks'])}")
    
    hit_msg = "❌ 未命中"
    if review_data['direct_hit']: hit_msg = "🎉 直选命中！"
    elif review_data['group_hit']: hit_msg = "✅ 组选命中！"
    st.write(f"**命中情况：** {hit_msg}")
    
    st.info(f"🧠 **分析师反思**：{review_data['reflect_text']}")
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info(f"最新开奖为第 {latest_qihao} 期。当前无对应复盘记录，已加载基础策略权重。")

# 顶部固定信息
st.success(f"**当前数据基准**：第 {latest_qihao} 期，下期目标：第 {int(latest_qihao)+1 if latest_qihao.isdigit() else latest_qihao+'_next'} 期")
st.write(f"今日策略权重配置：冷号 **{current_weights['cold']*100:.0f}%** | 热号 **{current_weights['hot']*100:.0f}%** (其余为温号)")

if search_code and len(search_code) == 3 and search_code.isdigit():
    count, periods, dates = check_history_appearance(df, search_code, 1000)
    if count > 0:
        st.sidebar.warning(f"⚠️ {search_code} 出现 {count} 次:\n" + "\n".join([f"{p} ({d})" for p, d in zip(periods, dates)]))
    else:
        st.sidebar.success(f"✨ {search_code} 近1000期未开出")

# ================= 2. 今日精选推荐 =================
st.markdown("### 🎯 今日精选推荐 (5注)")
st.caption("由动态权重算法生成，每日固定，已入库供次日复盘。")

target_qihao = str(int(latest_qihao) + 1) if latest_qihao.isdigit() else latest_qihao + "_next"

conn = get_db_connection()
try:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM strategy_records WHERE target_qihao = %s;", (target_qihao,))
        today_record = cur.fetchone()
finally:
    conn.close()

if today_record:
    picks = today_record["picks"].split(", ")
    reasons = today_record["reasons"].split(" | ")
    st.caption("今日推荐已锁定，次日将自动复盘。")
else:
    picks, reasons = generate_picks_core(df, current_weights, num_picks=5, is_extra=False)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO strategy_records (date, target_qihao, picks, reasons, weights_cold, weights_hot)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (datetime.now().strftime("%Y-%m-%d %H:%M"), target_qihao, ", ".join(picks), " | ".join(reasons), current_weights["cold"], current_weights["hot"]))
        conn.commit()
    finally:
        conn.close()
    st.caption("已根据今日策略生成最新推荐并保存至云端。")

for i, code in enumerate(picks):
    count, periods, dates = check_history_appearance(df, code, 1000)
    gap = get_recent_gap(df, code)
    gap_text = f"距今间隔 {gap} 期" if gap != -1 else "近千期未开"
    
    status_html = f"<span class='badge badge-warning'>⚠️ 近千期出现 {count} 次 ({gap_text})</span>" if count > 0 else "<span class='badge badge-success'>✨ 近千期未开出</span>"
    history_html = f"<div style='font-size:13px; color:#86868b; margin-top:12px;'>最近出现: {', '.join(dates[:3])}...</div>" if count > 0 else ""
    
    st.markdown(f"""
    <div class="apple-card">
        <div class="apple-title">第 {i+1} 注</div>
        <div class="pick-number">{code}</div>
        <div>{status_html}</div>
        <div class="reason-text">💡 <b>策略逻辑:</b> {reasons[i]}</div>
        {history_html}
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ================= 3. 灵感号码池 (额外推荐) =================
st.markdown("### 💡 灵感号码池 (额外推荐)")
st.caption("独立于精选号，不参与复盘。可随时手动刷新，提供更多选号参考。")

if "extra_picks" not in st.session_state:
    st.session_state.extra_picks = ([], [])

col_btn, _ = st.columns([1, 3])
with col_btn:
    if st.button("🔄 刷新灵感号码池", use_container_width=True):
        extra_p, extra_r = generate_picks_core(df, current_weights, num_picks=5, is_extra=True)
        st.session_state.extra_picks = (extra_p, extra_r)

extra_picks, extra_reasons = st.session_state.extra_picks

if not extra_picks:
    st.info("点击上方按钮生成一组灵感号码。")
else:
    # 使用列来布局，让额外推荐更紧凑
    cols = st.columns(5)
    for i, (code, reason) in enumerate(zip(extra_picks, extra_reasons)):
        gap = get_recent_gap(df, code)
        gap_text = f"间隔{gap}期" if gap != -1 else "近千期未开"
        count, _, _ = check_history_appearance(df, code, 1000)
        
        with cols[i]:
            st.markdown(f"""
            <div style="background:#ffffff; border-radius:12px; padding:15px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); text-align:center;">
                <div style="font-size:24px; font-weight:bold; color:#007aff; margin-bottom:8px;">{code}</div>
                <div style="font-size:12px; color:#86868b; margin-bottom:8px;">{gap_text}</div>
                <div style="font-size:11px; color:#666; text-align:left; border-top:1px dashed #ccc; padding-top:8px;">
                    {reason.replace('。', '。<br>')}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ================= 4. 图与分析模块 (向下折叠) =================
st.divider()
with st.expander("📊 查看走势图与深度统计", expanded=False):
    st.markdown("##### 近期重号概率统计")
    show_repeat_details = st.toggle("显示重复号码明细", value=False, key="toggle_repeat")
    
    c1, c2, c3, c4 = st.columns(4)
    windows = [100, 200, 500, 1000]
    for col, window in zip([c1, c2, c3, c4], windows):
        num_types, num_draws, prob, dup_codes = calculate_actual_repeat_stats(df, window)
        with col:
            st.metric(label=f"近 {window} 期", value=f"{prob:.1f}%")
            st.caption(f"重号 {num_types}个")
            
    if show_repeat_details:
        cols_d = st.columns(4)
        for col, window in zip(cols_d, windows):
            _, _, _, dup_codes = calculate_actual_repeat_stats(df, window)
            with col:
                if not dup_codes.empty:
                    dup_df = pd.DataFrame({"号码": dup_codes.index, "次数": dup_codes.values})
                    st.dataframe(dup_df, hide_index=True, use_container_width=True)
                    
    st.markdown("##### 定位走势图")
    view_mode = st.radio("选择位置：", ["综合走势", "百位", "十位", "个位"], horizontal=True)
    chart_data = df.head(30).copy().sort_values("期号", ascending=True)
    chart_data["期号简写"] = chart_data["期号"].astype(str).str[-3:]
    chart_data["百位"] = chart_data["百位"].astype(int)
    chart_data["十位"] = chart_data["十位"].astype(int)
    chart_data["个位"] = chart_data["个位"].astype(int)

    y_axis = alt.Y('期号简写:N', title='期号', sort=chart_data['期号简写'].tolist(), axis=alt.Axis(labelAngle=0))
    
    if view_mode == "综合走势":
        melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
        color_scale = alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#00BCD4', '#8BC34A'])
        x_axis = alt.X('数值:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10))))
        chart = alt.Chart(melted_df).mark_line(point=alt.OverlayMarkDef(size=50, filled=True, stroke='white', strokeWidth=2), strokeWidth=3).encode(
            x=x_axis, y=y_axis, color=alt.Color('位置:N', scale=color_scale), tooltip=['期号简写', '位置', '数值']
        ).properties(height=500, background='transparent').interactive()
    else:
        target_col = view_mode
        color = '#FF5722' if view_mode == "百位" else '#00BCD4' if view_mode == "十位" else '#8BC34A'
        x_axis = alt.X(f'{target_col}:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10))))
        chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(size=60, filled=True, color=color, stroke='white', strokeWidth=2), strokeWidth=4, color=color).encode(
            x=x_axis, y=y_axis, tooltip=['期号简写', alt.Tooltip(f'{target_col}:Q', title='数值')]
        ).properties(height=500, background='transparent').interactive()
        
    st.altair_chart(chart, use_container_width=True)

    st.markdown("##### 定制号码评估")
    col_b, col_s, col_g = st.columns(3)
    sel_b = col_b.selectbox("百位", options=[str(i) for i in range(10)], key="sb_b")
    sel_s = col_s.selectbox("十位", options=[str(i) for i in range(10)], key="sb_s")
    sel_g = col_g.selectbox("个位", options=[str(i) for i in range(10)], key="sb_g")
    custom_code = f"{sel_b}{sel_s}{sel_g}"
    
    if st.button("生成评估报告", key="btn_eval"):
        gap = get_recent_gap(df, custom_code)
        gap_text = f"距今间隔 {gap} 期" if gap != -1 else "近千期从未开出"
        st.info(f"**综合评估**：{custom_code} 在近千期出现 {check_history_appearance(df, custom_code, 1000)[0]} 次。{gap_text}。")
