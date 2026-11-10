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

def generate_reverse_picks(df, current_weights):
    exclude_set = set(df.head(EXCLUDE_RANGE)["完整号码"].tolist())
    recent_df = df.head(RECENT_ANALYZE)
    avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in recent_df.iterrows()) / RECENT_ANALYZE
    
    hot_pool, cold_pool = {}, {}
    for col in ["百位", "十位", "个位"]:
        counts = Counter(recent_df[col].tolist())
        hot_pool[col] = [n for n, _ in counts.most_common(4)]
        cold_pool[col] = [n for n, c in counts.items() if c <= 5] or [str(i) for i in range(10) if str(i) not in hot_pool[col]][:3]

    picks, reasons = [], []
    attempts = 0
    
    while len(picks) < 5 and attempts < 100000:
        attempts += 1
        b = random.choice(cold_pool["百位"]) if random.random() < current_weights["cold"] else random.choice(hot_pool["百位"]) if random.random() < current_weights["hot"] else str(random.randint(0,9))
        s = random.choice(cold_pool["十位"]) if random.random() < current_weights["cold"] else random.choice(hot_pool["十位"]) if random.random() < current_weights["hot"] else str(random.randint(0,9))
        g = random.choice(cold_pool["个位"]) if random.random() < current_weights["cold"] else random.choice(hot_pool["个位"]) if random.random() < current_weights["hot"] else str(random.randint(0,9))
        
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

        reason = f"和值 {total_sum}，跨度 {span}，奇偶比 {odd_cnt}:{3-odd_cnt}。"
        if b in cold_pool["百位"] or s in cold_pool["十位"] or g in cold_pool["个位"]:
            reason += " 包含冷号回补逻辑。"
        else:
            reason += " 顺应近期热号趋势。"

        picks.append(code)
        reasons.append(reason)
        exclude_set.add(code)
        
    return picks, reasons

# ================= 页面 UI 渲染 =================
st.title("🎯 福彩3D 智能分析终端")
st.caption("云端全自动托管 | 马卡龙明亮风格 | 重号明细追踪")

with st.sidebar:
    st.header("🔍 号码查重 (近1000期)")
    search_code = st.text_input("输入3位数字", max_chars=3)
    st.markdown("---")
    if st.button("🔄 手动触发云端数据同步", use_container_width=True):
        sync_database()
        st.success("同步成功！")

# 1. 自动同步最新数据并加载
with st.spinner("正在同步云端数据库..."):
    sync_database()
    df = load_data_from_db()

if df.empty: 
    st.error("云端数据为空，请稍后刷新重试。")
    st.stop()

latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]
st.info(f"**第 {latest_qihao} 期**  |  开奖号码: **{latest_row['完整号码']}**  |  {latest_row['开奖日期'].strftime('%Y-%m-%d') if pd.notna(latest_row['开奖日期']) else ''}")

if search_code and len(search_code) == 3 and search_code.isdigit():
    count, periods, dates = check_history_appearance(df, search_code, 1000)
    if count > 0:
        st.sidebar.warning(f"⚠️ {search_code} 出现 {count} 次:\n" + "\n".join([f"{p} ({d})" for p, d in zip(periods, dates)]))
    else:
        st.sidebar.success(f"✨ {search_code} 近1000期未开出")

# ================= 模块：重号统计 =================
st.markdown("### 📊 近期重号概率统计")
st.caption("统计：在选定周期内，开出2次及以上的号码数量及比例。")
show_repeat_details = st.toggle("显示重复号码明细", value=False)

c1, c2, c3, c4 = st.columns(4)
windows = [100, 200, 500, 1000]
dup_data_store = {}

for col, window in zip([c1, c2, c3, c4], windows):
    num_types, num_draws, prob, dup_codes = calculate_actual_repeat_stats(df, window)
    dup_data_store[window] = dup_codes
    with col:
        st.metric(label=f"近 {window} 期", value=f"{prob:.1f}% 重号率")
        st.caption(f"重复号码: {num_types} 个\n共占据: {num_draws} 期")

if show_repeat_details:
    st.markdown("---")
    st.write("**🔍 各周期重复号码明细**")
    cols = st.columns(4)
    for col, window in zip(cols, windows):
        with col:
            st.write(f"**近 {window} 期**")
            dup_series = dup_data_store[window]
            if not dup_series.empty:
                dup_df = pd.DataFrame({"号码": dup_series.index, "出现次数": dup_series.values}).sort_values(by="出现次数", ascending=False)
                st.dataframe(dup_df, hide_index=True, use_container_width=True)
            else:
                st.write("无重复号码")

# ================= 模块：竖向走势图 =================
st.markdown("### 📈 定位走势图 (右图模式)")
st.caption("X轴为数字0-9，Y轴为期号（从上往下）。")
view_mode = st.radio("选择位置：", ["综合走势", "百位", "十位", "个位"], horizontal=True)

chart_data = df.head(30).copy().sort_values("期号", ascending=True)
chart_data["期号简写"] = chart_data["期号"].astype(str).str[-3:]
chart_data["百位"] = chart_data["百位"].astype(int)
chart_data["十位"] = chart_data["十位"].astype(int)
chart_data["个位"] = chart_data["个位"].astype(int)

y_axis = alt.Y('期号简写:N', title='期号', sort=chart_data['期号简写'].tolist(), axis=alt.Axis(labelAngle=0, labelColor='#1d1d1f', titleColor='#1d1d1f'))

if view_mode == "综合走势":
    melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
    color_scale = alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#00BCD4', '#8BC34A'])
    x_axis = alt.X('数值:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10)), labelColor='#1d1d1f', titleColor='#1d1d1f'))
    
    chart = alt.Chart(melted_df).mark_line(point=alt.OverlayMarkDef(size=60, filled=True, stroke='white', strokeWidth=2), strokeWidth=3).encode(
        x=x_axis, y=y_axis, color=alt.Color('位置:N', scale=color_scale), tooltip=['期号简写', '位置', '数值']
    ).properties(height=550, background='transparent').interactive()
else:
    target_col = view_mode
    color = '#FF5722' if view_mode == "百位" else '#00BCD4' if view_mode == "十位" else '#8BC34A'
    x_axis_single = alt.X(f'{target_col}:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10)), labelColor='#1d1d1f', titleColor='#1d1d1f'))
    
    chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(size=70, filled=True, color=color, stroke='white', strokeWidth=2), strokeWidth=4, color=color).encode(
        x=x_axis_single, y=y_axis, tooltip=['期号简写', alt.Tooltip(f'{target_col}:Q', title='数值')]
    ).properties(height=550, background='transparent').interactive()

st.altair_chart(chart, use_container_width=True)


# ================= 新增模块：定制号码评估 =================
st.markdown("### 🔍 定制号码评估 (选号分析)")
st.caption("请选择您想分析的百、十、个位数字，系统将提取历史数据进行专业评估。")

col_b, col_s, col_g = st.columns(3)
with col_b:
    sel_b = st.selectbox("百位数字", options=[str(i) for i in range(10)], index=0)
with col_s:
    sel_s = st.selectbox("十位数字", options=[str(i) for i in range(10)], index=0)
with col_g:
    sel_g = st.selectbox("个位数字", options=[str(i) for i in range(10)], index=0)

custom_code = f"{sel_b}{sel_s}{sel_g}"

# 评估逻辑
if st.button("生成评估报告", type="primary", use_container_width=True):
    st.markdown(f"#### 📝 号码 **{custom_code}** 专项分析")
    
    # 1. 计算整体遗漏和历史出现次数
    total_count, periods, dates = check_history_appearance(df, custom_code, 1000)
    
    # 找出最近一次出现的索引（即间隔期数）
    matches_idx = df.index[df["完整号码"] == custom_code].tolist()
    if matches_idx:
        # 因为 df 是按期号降序排列，最小的索引就是最近一次出现的期数。
        # 如果索引是 5，说明它距离最新一期之间隔了 5 期（在最新一期出现的话索引是0）
        recent_gap = min(matches_idx)
        last_period = df.loc[recent_gap, "期号"]
        gap_text = f"**距离最近一次出现：** 第 {last_period} 期，距今间隔 **{recent_gap}** 期。"
    else:
        gap_text = "**距离最近一次出现：** 近1000期内从未开出。"
    
    st.info(f"📊 **整体历史表现**：该号码在近1000期内共出现 **{total_count}** 次。{gap_text}")

    # 2. 位置遗漏分析
    miss_b = df.index[df["百位"] == sel_b].min() if not df[df["百位"] == sel_b].empty else ">1000"
    miss_s = df.index[df["十位"] == sel_s].min() if not df[df["十位"] == sel_s].empty else ">1000"
    miss_g = df.index[df["个位"] == sel_g].min() if not df[df["个位"] == sel_g].empty else ">1000"
    
    # 3. 形态、优缺点及推荐指数评估算法
    nums = [int(sel_b), int(sel_s), int(sel_g)]
    total_sum = sum(nums)
    span = max(nums) - min(nums)
    odd_cnt = sum(1 for n in nums if n % 2 != 0)
    
    # 获取近期均值作为参考
    recent_avg_sum = sum(int(r["百位"]) + int(r["十位"]) + int(r["个位"]) for _, r in df.head(100).iterrows()) / 100
    
    pros = []
    cons = []
    score = 3 # 基础分 3 星

    # 位置遗漏评判
    if isinstance(miss_b, int) and miss_b >= 15: pros.append(f"百位 {sel_b} 遗漏 {miss_b} 期，具备回补潜力")
    if isinstance(miss_s, int) and miss_s >= 15: pros.append(f"十位 {sel_s} 遗漏 {miss_s} 期，具备回补潜力")
    if isinstance(miss_g, int) and miss_g >= 15: pros.append(f"个位 {sel_g} 遗漏 {miss_g} 期，具备回补潜力")
    
    if isinstance(miss_b, int) and miss_b <= 3: cons.append(f"百位 {sel_b} 近期过热，谨防转冷")
    if isinstance(miss_s, int) and miss_s <= 3: cons.append(f"十位 {sel_s} 近期过热，谨防转冷")
    if isinstance(miss_g, int) and miss_g <= 3: cons.append(f"个位 {sel_g} 近期过热，谨防转冷")

    # 形态评判
    if abs(total_sum - recent_avg_sum) <= 3:
        pros.append(f"和值 {total_sum} 贴近近期均值 {recent_avg_sum:.1f}，形态健康")
        score += 1
    elif abs(total_sum - recent_avg_sum) >= 8:
        cons.append(f"和值 {total_sum} 偏离近期均值较大，偏态严重")
        score -= 1

    if 4 <= span <= 8:
        pros.append(f"跨度 {span} 位于高概率黄金区间")
        score += 1
    elif span < 2 or span > 9:
        cons.append(f"跨度 {span} 过于极端")
        score -= 1

    if odd_cnt in (0, 3):
        cons.append("全奇/全偶，偏离常规比例")
        score -= 1
    else:
        pros.append(f"奇偶比 {odd_cnt}:{3-odd_cnt}，比例均衡")

    # 顺子/豹子过滤（如果是大概率下注，不建议买顺子）
    sorted_nums = sorted(nums)
    if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1:
        cons.append("当前为顺子形态，开出概率相对较低")
        score -= 1
    if len(set(nums)) == 1:
        cons.append("当前为豹子形态，开出概率极低")
        score -= 2

    # 限制分数在 1-5 之间
    score = max(1, min(5, score))
    stars = "⭐" * score

    # 渲染评估结果卡片
    st.markdown(f"""
    <div class="apple-card">
        <div style="font-size:18px; font-weight:bold; margin-bottom:15px;">
            综合推荐指数：<span style="color:#ff9500;">{stars}</span> ({score}/5)
        </div>
        <div style="margin-bottom:10px;">
            <b>📍 位置遗漏追踪：</b><br>
            百位 <b>{sel_b}</b>：距今 {miss_b} 期<br>
            十位 <b>{sel_s}</b>：距今 {miss_s} 期<br>
            个位 <b>{sel_g}</b>：距今 {miss_g} 期
        </div>
        <hr style="border:0; border-top:1px solid #e5e5ea; margin:15px 0;">
        <div style="margin-bottom:10px; color:#34c759;">
            <b>✅ 优势分析：</b><br>
            {"<br>".join(["· " + p for p in pros]) if pros else "· 无明显优势"}
        </div>
        <div style="color:#ff3b30;">
            <b>⚠️ 劣势风险：</b><br>
            {"<br>".join(["· " + c for c in cons]) if cons else "· 无明显劣势"}
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("收起报告"):
        pass


# ================= 模块：精选推荐 (直接读写云端) =================
st.markdown("### 🎯 今日精选推荐")

target_qihao = str(int(latest_qihao) + 1) if latest_qihao.isdigit() else latest_qihao + "_next"

conn = get_db_connection()
try:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM strategy_records WHERE target_qihao = %s;", (target_qihao,))
        today_record = cur.fetchone()
finally:
    conn.close()

if today_record:
    st.success(f"今日推荐已固定 (针对第 {target_qihao} 期)，云端已记住，刷新不变。")
    picks = today_record["picks"].split(", ")
    reasons = today_record["reasons"].split(" | ")
else:
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT weights_cold, weights_hot FROM strategy_records ORDER BY id DESC LIMIT 1;")
            last_weights = cur.fetchone()
    finally:
        conn.close()

    if last_weights:
        current_weights = {"cold": last_weights["weights_cold"], "hot": last_weights["weights_hot"]}
    else:
        current_weights = {"cold": 0.30, "hot": 0.10}
        
    picks, reasons = generate_reverse_picks(df, current_weights)
    
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
    st.success(f"已生成针对第 {target_qihao} 期的新推荐，并自动保存至云端！")

for i, code in enumerate(picks):
    count, periods, dates = check_history_appearance(df, code, 1000)
    status_html = f"<span class='badge badge-warning'>⚠️ 近千期出现 {count} 次</span>" if count > 0 else "<span class='badge badge-success'>✨ 近千期未开出</span>"
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

# ================= 模块：缺失分析 =================
with st.expander("🔍 分位遗漏深度分析 (寻找冷号)", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1: st.write("**百位**", get_missing_values(df, "百位"))
    with c2: st.write("**十位**", get_missing_values(df, "十位"))
    with c3: st.write("**个位**", get_missing_values(df, "个位"))
