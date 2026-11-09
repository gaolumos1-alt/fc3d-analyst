import streamlit as st
import requests
import pandas as pd
import time
import random
import json
import io
import altair as alt
from datetime import datetime
from collections import Counter

# ================= 配置区 =================
API_URL = "http://api.huiniao.top/interface/home/lotteryHistory"
LOTTERY_TYPE = "fcsd"  
EXCLUDE_RANGE = 100    
RECENT_ANALYZE = 100   

st.set_page_config(page_title="福彩3D 智能分析", page_icon="🎯", layout="centered")

# ================= 苹果明亮风 + 马卡龙晕染 + 组件深度美化 CSS =================
st.markdown("""
<style>
    /* 强制全局浅灰背景与马卡龙晕染 */
    .stApp {
        background-color: #fbfbfd;
        background-image: 
            radial-gradient(circle at 10% 10%, rgba(255, 182, 193, 0.25) 0%, transparent 40%),
            radial-gradient(circle at 90% 20%, rgba(176, 224, 230, 0.3) 0%, transparent 50%),
            radial-gradient(circle at 80% 90%, rgba(221, 160, 221, 0.2) 0%, transparent 40%),
            radial-gradient(circle at 20% 80%, rgba(255, 228, 196, 0.3) 0%, transparent 50%);
        background-attachment: fixed;
    }
    
    /* 强制所有普通文字为深黑色 */
    body, p, h1, h2, h3, h4, h5, h6, div, span {
        color: #1d1d1f !important;
    }
    
    /* ======= 侧边栏与上传组件美化 ======= */
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(0,0,0,0.05);
    }
    [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        border-radius: 12px;
        padding: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    [data-testid="stFileUploader"] section {
        background-color: #f5f5f7 !important;
        border: 1px dashed #007aff !important;
    }
    [data-testid="stFileUploader"] small { color: #86868b !important; }
    
    /* 下载按钮美化 */
    [data-testid="stDownloadButton"] button {
        background-color: #007aff !important;
        color: #ffffff !important;
        border-radius: 12px;
        font-weight: 600;
        border: none;
        transition: all 0.3s;
    }
    [data-testid="stDownloadButton"] button:hover {
        background-color: #005bb5 !important;
        box-shadow: 0 4px 12px rgba(0, 122, 255, 0.3);
    }
    
    /* ======= 单选按钮 (走势图切换) 美化 ======= */
    [data-testid="stRadio"] > div {
        background-color: #ffffff !important;
        padding: 10px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .stRadio [data-baseweb="radio"] div { color: #1d1d1f !important; }
    
    /* ======= 重号统计指标卡美化 ======= */
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.9) !important;
        padding: 15px;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid rgba(0,0,0,0.03);
    }
    [data-testid="stMetricValue"] { color: #1d1d1f !important; font-weight: 800; font-size: 28px; }
    [data-testid="stMetricLabel"] { color: #86868b !important; }

    /* ======= 顶部 Info 框美化 ======= */
    .stInfo {
        background-color: #ffffff !important;
        border: 1px solid #e5e5ea !important;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }

    /* ======= 本期推荐卡片美化 ======= */
    .apple-card {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        border: 1px solid #e5e5ea;
    }
    .apple-title {
        font-size: 15px;
        font-weight: 600;
        color: #86868b !important;
        margin-bottom: 8px;
    }
    .pick-number {
        font-size: 48px;
        font-weight: 800;
        color: #007aff !important;
        letter-spacing: 8px;
        margin-bottom: 12px;
        font-family: -apple-system, BlinkMacSystemFont, monospace;
    }
    .reason-text {
        font-size: 14px;
        color: #1d1d1f !important;
        line-height: 1.5;
        margin-top: 10px;
    }
    .badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
    }
    .badge-success { background-color: #e8f8ee; color: #28cd41 !important; }
    .badge-warning { background-color: #fff4e6; color: #ff9500 !important; }
</style>
""", unsafe_allow_html=True)

# ========== 核心抓取与合并逻辑 ==========
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

def process_data(raw_list):
    if not raw_list: return pd.DataFrame()
    df = pd.DataFrame(raw_list)
    mapping = {"code": "期号", "day": "开奖日期", "one": "百位", "two": "十位", "three": "个位"}
    cols = {k: v for k, v in mapping.items() if k in df.columns}
    df = df[list(cols.keys())].rename(columns=cols)
    
    pos_cols = ["百位", "十位", "个位"]
    for col in pos_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)
            
    if all(col in df.columns for col in pos_cols):
        df["完整号码"] = df[pos_cols].apply(lambda x: "".join(x.astype(str)), axis=1)
        
    if "期号" in df.columns:
        df["期号"] = df["期号"].astype(str)
        if "开奖日期" in df.columns:
            df["开奖日期"] = pd.to_datetime(df["开奖日期"], errors='coerce')
        df = df.sort_values("期号", ascending=False).reset_index(drop=True)
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
    num_dup_types = len(duplicated_codes)
    num_dup_draws = duplicated_codes.sum()
    prob = (num_dup_draws / window) * 100 if window > 0 else 0
    return num_dup_types, num_dup_draws, prob, duplicated_codes

def get_missing_values(df, col_name, lookback=100):
    recent_df = df.head(lookback)
    missing = {}
    for num in range(10):
        num_str = str(num)
        matches = recent_df[recent_df[col_name] == num_str]
        missing[num_str] = lookback if matches.empty else matches.index[0]
    return dict(sorted(missing.items(), key=lambda item: item[1], reverse=True))

# ========== 推荐生成逻辑 ==========
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
st.caption("马卡龙明亮风格 | 竖向定位走势 | 重号明细追踪")

with st.sidebar:
    st.header("📂 数据同步")
    uploaded_file = st.file_uploader("上传昨天下载的 Excel", type=["xlsx"])
    st.markdown("---")
    st.header("🔍 号码查重 (近1000期)")
    search_code = st.text_input("输入3位数字", max_chars=3)

# 数据加载
df = pd.DataFrame()
strategy_history = []

if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        df = pd.read_excel(xls, sheet_name="开奖数据", dtype={'期号': str})
        if "开奖日期" in df.columns:
            df["开奖日期"] = pd.to_datetime(df["开奖日期"])
        if "策略记录" in xls.sheet_names:
            strategy_history = pd.read_excel(xls, sheet_name="策略记录").to_dict('records')
        st.sidebar.success("✅ 历史记忆已载入")
    except Exception as e:
        st.sidebar.error(f"文件解析失败: {e}")
        st.stop()
else:
    with st.spinner("正在初始化全量数据..."):
        all_raw = []
        page = 1
        while True:
            data = fetch_page(page)
            if not data: break
            all_raw.extend(data)
            if len(data) < 100: break
            page += 1
        df = process_data(all_raw)

if df.empty: st.stop()

# 增量更新
with st.spinner("更新最新数据..."):
    new_raw = fetch_page(1) + fetch_page(2)
    new_df = process_data(new_raw)
    if not new_df.empty:
        combined = pd.concat([new_df, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["期号"], keep="first")
        df = combined.sort_values("期号", ascending=False).reset_index(drop=True)

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

# 增加开关查看重号明细
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
                dup_df = pd.DataFrame({
                    "号码": dup_series.index,
                    "出现次数": dup_series.values
                }).sort_values(by="出现次数", ascending=False)
                st.dataframe(dup_df, hide_index=True, use_container_width=True)
            else:
                st.write("无重复号码")


# ================= 模块：竖向走势图 (向负Y轴更新) =================
st.markdown("### 📈 定位走势图 (右图模式)")
st.caption("X轴为数字0-9，Y轴为期号（从上往下）。通过连线观察号码跳跃轨迹。")
view_mode = st.radio("选择位置：", ["综合走势", "百位", "十位", "个位"], horizontal=True)

# 取最近 30 期，按时间正序（最旧的在上，最新的在下，满足向负Y轴更新）
chart_data = df.head(30).copy().sort_values("期号", ascending=True)
chart_data["期号"] = chart_data["期号"].astype(str)
chart_data["期号简写"] = chart_data["期号"].str[-3:]
chart_data["百位"] = chart_data["百位"].astype(int)
chart_data["十位"] = chart_data["十位"].astype(int)
chart_data["个位"] = chart_data["个位"].astype(int)

# 设置统一的背景和轴颜色
chart_base_config = dict(
    background='transparent',
)

y_axis = alt.Y('期号简写:N', title='期号', sort=chart_data['期号简写'].tolist(), axis=alt.Axis(labelAngle=0, labelColor='#1d1d1f', titleColor='#1d1d1f'))

if view_mode == "综合走势":
    melted_df = chart_data.melt(id_vars=['期号简写'], value_vars=['百位', '十位', '个位'], var_name='位置', value_name='数值')
    color_scale = alt.Scale(domain=['百位', '十位', '个位'], range=['#FF5722', '#00BCD4', '#8BC34A'])
    x_axis = alt.X('数值:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10)), labelColor='#1d1d1f', titleColor='#1d1d1f'))
    
    chart = alt.Chart(melted_df).mark_line(point=alt.OverlayMarkDef(size=60, filled=True, stroke='white', strokeWidth=2), strokeWidth=3).encode(
        x=x_axis, y=y_axis, color=alt.Color('位置:N', scale=color_scale),
        tooltip=['期号简写', '位置', '数值']
    ).properties(height=550, **chart_base_config).interactive()
else:
    col_map = {"百位": "百位", "十位": "十位", "个位": "个位"}
    target_col = col_map[view_mode]
    color = '#FF5722' if view_mode == "百位" else '#00BCD4' if view_mode == "十位" else '#8BC34A'
    # 【修复】X 轴动态指定为目标列
    x_axis_single = alt.X(f'{target_col}:Q', title='号码', scale=alt.Scale(domain=[-0.5, 9.5]), axis=alt.Axis(values=list(range(10)), labelColor='#1d1d1f', titleColor='#1d1d1f'))
    
    chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(size=70, filled=True, color=color, stroke='white', strokeWidth=2), strokeWidth=4, color=color).encode(
        x=x_axis_single, y=y_axis, tooltip=['期号简写', alt.Tooltip(f'{target_col}:Q', title='数值')]
    ).properties(height=550, **chart_base_config).interactive()

st.altair_chart(chart, use_container_width=True)


# ================= 模块：精选推荐 =================
st.markdown("### 🎯 今日精选推荐")

target_qihao = str(int(latest_qihao) + 1) if latest_qihao.isdigit() else latest_qihao + "_next"
today_record = next((r for r in strategy_history if r["target_qihao"] == target_qihao), None)

if today_record:
    st.success(f"今日推荐已固定 (针对第 {target_qihao} 期)。上传新文件前，刷新页面结果不变。")
    picks = today_record["picks"].split(", ")
    reasons = today_record.get("reasons", ["历史无原因"] * 5).split(" | ") if isinstance(today_record.get("reasons"), str) else ["历史无原因"] * 5
else:
    current_weights = strategy_history[-1] if strategy_history else {"cold": 0.30, "hot": 0.10}
    if isinstance(current_weights, dict) and "weights_cold" in current_weights:
        current_weights = {"cold": current_weights["weights_cold"], "hot": current_weights["weights_hot"]}
        
    picks, reasons = generate_reverse_picks(df, current_weights)
    strategy_history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
        "target_qihao": target_qihao, 
        "picks": ", ".join(picks),
        "reasons": " | ".join(reasons),
        "weights_cold": current_weights["cold"],
        "weights_hot": current_weights["hot"]
    })
    st.success(f"已生成针对第 {target_qihao} 期的新推荐！请下载保存。")

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
    with c1:
        st.write("**百位**")
        st.write(get_missing_values(df, "百位"))
    with c2:
        st.write("**十位**")
        st.write(get_missing_values(df, "十位"))
    with c3:
        st.write("**个位**")
        st.write(get_missing_values(df, "个位"))

# ================= 侧边栏：下载 =================
with st.sidebar:
    st.markdown("---")
    st.header("💾 保存记忆")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="开奖数据", index=False)
        if strategy_history:
            pd.DataFrame(strategy_history).to_excel(writer, sheet_name="策略记录", index=False)
            
    st.download_button(
        label="⬇️ 下载最新 Excel",
        data=output.getvalue(),
        file_name=f"福彩3D_备份_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
