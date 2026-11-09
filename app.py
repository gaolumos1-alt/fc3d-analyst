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

# ================= 苹果风 CSS 注入 =================
st.markdown("""
<style>
    /* 全局字体与背景 */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    /* 卡片样式 */
    .apple-card {
        background-color: var(--secondary-background-color);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid rgba(128, 128, 128, 0.1);
    }
    .apple-title {
        font-size: 20px;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .pick-number {
        font-size: 42px;
        font-weight: 800;
        color: #007aff; /* 苹果经典蓝 */
        letter-spacing: 4px;
        margin-bottom: 15px;
    }
    .reason-text {
        font-size: 15px;
        color: #86868b;
        line-height: 1.5;
    }
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .badge-success { background-color: rgba(52, 199, 89, 0.15); color: #34c759; }
    .badge-warning { background-color: rgba(255, 149, 0, 0.15); color: #ff9500; }
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

def calculate_repeat_stats(df, window):
    """统计最近 window 期内，与上一期重号的概率"""
    recent_df = df.head(window + 1) # 多取一期用于对比
    zero_repeat, one_repeat, two_repeat = 0, 0, 0
    total = len(recent_df) - 1
    if total <= 0: return 0, 0, 0
    
    for i in range(total):
        curr_nums = set([recent_df.iloc[i]["百位"], recent_df.iloc[i]["十位"], recent_df.iloc[i]["个位"]])
        prev_nums = set([recent_df.iloc[i+1]["百位"], recent_df.iloc[i+1]["十位"], recent_df.iloc[i+1]["个位"]])
        overlap = len(curr_nums & prev_nums)
        if overlap == 0: zero_repeat += 1
        elif overlap == 1: one_repeat += 1
        else: two_repeat += 1
        
    return (zero_repeat/total)*100, (one_repeat/total)*100, (two_repeat/total)*100

def get_missing_values(df, col_name, lookback=100):
    recent_df = df.head(lookback)
    missing = {}
    for num in range(10):
        num_str = str(num)
        matches = recent_df[recent_df[col_name] == num_str]
        missing[num_str] = lookback if matches.empty else matches.index[0]
    return dict(sorted(missing.items(), key=lambda item: item[1], reverse=True))

# ========== 推荐生成与原因分析 ==========
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
            reason += " 采取冷号回补防守策略。"
        else:
            reason += " 结合近期热号趋势顺推。"

        picks.append(code)
        reasons.append(reason)
        exclude_set.add(code)
        
    return picks, reasons

# ================= 页面 UI 渲染 =================
st.title("🎯 福彩3D 智能分析终端")
st.caption("苹果风UI | 趋势追踪 | 策略自我进化")

with st.sidebar:
    st.header("📂 数据同步")
    uploaded_file = st.file_uploader("上传昨天下载的 Excel", type=["xlsx"])
    st.markdown("---")
    st.header("🔍 号码查重 (近1000期)")
    search_code = st.text_input("输入3位数字", max_chars=3)

# 1. 读取数据
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
    with st.spinner("正在初始化全量数据（建议上传文件以加快速度）..."):
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

# 2. 增量更新
with st.spinner("拉取最新开奖数据..."):
    new_raw = fetch_page(1) + fetch_page(2)
    new_df = process_data(new_raw)
    if not new_df.empty:
        combined = pd.concat([new_df, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["期号"], keep="first")
        df = combined.sort_values("期号", ascending=False).reset_index(drop=True)

latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]
st.info(f"**第 {latest_qihao} 期**  |  开奖号码: **{latest_row['完整号码']}**  |  {latest_row['开奖日期'].strftime('%Y-%m-%d') if pd.notna(latest_row['开奖日期']) else ''}")

# 3. 查重结果
if search_code and len(search_code) == 3 and search_code.isdigit():
    count, periods, dates = check_history_appearance(df, search_code, 1000)
    if count > 0:
        st.sidebar.warning(f"⚠️ {search_code} 出现 {count} 次:\n" + "\n".join([f"{p} ({d})" for p, d in zip(periods, dates)]))
    else:
        st.sidebar.success(f"✨ {search_code} 近1000期未开出")

# ================= 模块：重号统计 =================
st.markdown("### 📊 重号概率统计")
col1, col2, col3 = st.columns(3)
for col, window in zip([col1, col2, col3], [100, 200, 500]):
    z, o, t = calculate_repeat_stats(df, window)
    with col:
        st.metric(label=f"近{window}期", value=f"{o:.1f}%", delta="1个重号概率", delta_color="off")
        st.caption(f"0重号: {z:.1f}% | 2重号: {t:.1f}%")

# ================= 模块：走势图 =================
st.markdown("### 📈 近30期定位走势")
chart_data = df.head(30).copy().sort_values("期号")
chart_data["期号尾数"] = chart_data["期号"].str[-3:]
chart_data["百位"] = chart_data["百位"].astype(int)
chart_data["十位"] = chart_data["十位"].astype(int)
chart_data["个位"] = chart_data["个位"].astype(int)

# 使用 Altair 画更漂亮的折线图
melted_df = chart_data.melt(id_vars=['期号尾数'], value_vars=['百位', '十位', '个位'], 
                            var_name='位置', value_name='数值')

chart = alt.Chart(melted_df).mark_line(point=True).encode(
    x=alt.X('期号尾数:N', title='期号', axis=alt.Axis(labelAngle=-45)),
    y=alt.Y('数值:Q', scale=alt.Scale(domain=[0, 9]), title='号码'),
    color=alt.Color('位置:N', scale=alt.Scale(domain=['百位', '十位', '个位'], range=['#ff3b30', '#007aff', '#34c759'])),
    tooltip=['期号尾数', '位置', '数值']
).properties(height=300).interactive()

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

# 渲染精美卡片
for i, code in enumerate(picks):
    count, periods, dates = check_history_appearance(df, code, 1000)
    
    status_html = f"<span class='badge badge-warning'>⚠️ 近千期出现 {count} 次</span>" if count > 0 else "<span class='badge badge-success'>✨ 近千期未开出</span>"
    history_html = f"<div style='font-size:12px; color:#86868b; margin-top:10px;'>最近记录: {', '.join(dates[:3])}...</div>" if count > 0 else ""
    
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
with st.expander("🔍 分位遗漏深度分析", expanded=False):
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
        label="⬇️ 下载最新 Excel (含记忆)",
        data=output.getvalue(),
        file_name=f"福彩3D_备份_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
