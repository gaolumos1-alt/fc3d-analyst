import streamlit as st
import requests
import pandas as pd
import time
import random
import json
import io
from datetime import datetime
from collections import Counter

# ================= 配置区 =================
API_URL = "http://api.huiniao.top/interface/home/lotteryHistory"
LOTTERY_TYPE = "fcsd"  
EXCLUDE_RANGE = 100    
RECENT_ANALYZE = 100   

st.set_page_config(page_title="福彩3D 逆向分析师 (进阶版)", page_icon="🎯", layout="centered")

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
    return len(matches), matches["期号"].tolist()

def get_missing_values(df, col_name, lookback=100):
    """计算某个位置（百/十/个位）数字 0-9 的遗漏期数"""
    recent_df = df.head(lookback)
    missing = {}
    for num in range(10):
        num_str = str(num)
        # 找到该位置等于这个数字的所有行
        matches = recent_df[recent_df[col_name] == num_str]
        if matches.empty:
            missing[num_str] = lookback # 超过分析期数未出
        else:
            # 该数字最近一次出现是在第几行（行索引越小说明越近）
            missing[num_str] = matches.index[0] 
    # 按遗漏从大到小排序
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

    picks = []
    reasons = []
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
        
        # 逆向排除极端的顺子号
        sorted_nums = sorted(nums)
        if sorted_nums[1] == sorted_nums[0] + 1 and sorted_nums[2] == sorted_nums[1] + 1 and random.random() < 0.8:
            continue

        # 生成推荐原因
        reason = f"和值 {total_sum} (贴近均值)，跨度 {span}。"
        reason += f" 奇偶比 {odd_cnt}:{3-odd_cnt}。"
        if b in cold_pool["百位"] or s in cold_pool["十位"] or g in cold_pool["个位"]:
            reason += " 包含冷号回补逻辑。"
        else:
            reason += " 形态均衡防守。"

        picks.append(code)
        reasons.append(reason)
        exclude_set.add(code)
        
    return picks, reasons

# ================= 页面 UI 渲染 =================
st.title("🎯 福彩3D 进阶逆向分析师")
st.caption("趋势图表 | 选号因素分析 | 固定推荐")

# 侧边栏：上传与下载
with st.sidebar:
    st.header("📂 数据管理")
    uploaded_file = st.file_uploader("1. 上传上次的 Excel 文件", type=["xlsx"])
    
    # 查号功能移动到侧边栏更省空间
    st.markdown("---")
    st.header("🔍 号码查重 (近1000期)")
    search_code = st.text_input("输入3位数字", max_chars=3)
    if search_code and len(search_code) == 3 and search_code.isdigit():
        st.info(f"正在查询 {search_code}...")

# 1. 读取或抓取数据
df = pd.DataFrame()
strategy_history = []

if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        df = pd.read_excel(xls, sheet_name="开奖数据", dtype={'期号': str})
        if "开奖日期" in df.columns:
            df["开奖日期"] = pd.to_datetime(df["开奖日期"])
            
        if "策略记录" in xls.sheet_names:
            strategy_df = pd.read_excel(xls, sheet_name="策略记录")
            strategy_history = strategy_df.to_dict('records')
        st.sidebar.success("✅ 历史文件读取成功！")
    except Exception as e:
        st.sidebar.error(f"文件解析失败: {e}")
        st.stop()
else:
    with st.spinner("未检测到上传文件，正在全量抓取（请稍后并下载保存）..."):
        all_raw = []
        page = 1
        while True:
            data = fetch_page(page)
            if not data: break
            all_raw.extend(data)
            if len(data) < 100: break
            page += 1
            time.sleep(0.1)
        df = process_data(all_raw)

if df.empty:
    st.error("数据为空，请检查网络或上传文件。")
    st.stop()

# 2. 增量更新
with st.spinner("拉取最新开奖并合并..."):
    new_raw = fetch_page(1) + fetch_page(2)
    new_df = process_data(new_raw)
    if not new_df.empty:
        combined = pd.concat([new_df, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["期号"], keep="first")
        df = combined.sort_values("期号", ascending=False).reset_index(drop=True)

latest_row = df.iloc[0]
latest_qihao = latest_row["期号"]
st.info(f"**最新开奖**: 第 {latest_qihao} 期 | **号码**: {latest_row['完整号码']} | **日期**: {latest_row['开奖日期'].strftime('%Y-%m-%d') if pd.notna(latest_row['开奖日期']) else ''}")

# 3. 查重结果展示（如果侧边栏有输入）
if search_code and len(search_code) == 3 and search_code.isdigit():
    count, periods = check_history_appearance(df, search_code, 1000)
    if count > 0:
        st.sidebar.warning(f"⚠️ {search_code} 近1000期出现过 {count} 次。期号: {', '.join(periods)}")
    else:
        st.sidebar.success(f"✨ {search_code} 近1000期未开出过")

# ================= 核心图表区 =================
st.subheader("📈 近期走势折线图 (近30期)")
chart_data = df.head(30).copy()
chart_data["和值"] = chart_data["百位"].astype(int) + chart_data["十位"].astype(int) + chart_data["个位"].astype(int)
chart_data["跨度"] = chart_data[["百位", "十位", "个位"]].astype(int).max(axis=1) - chart_data[["百位", "十位", "个位"]].astype(int).min(axis=1)
chart_data = chart_data.sort_values("期号") # 按时间正序
st.line_chart(chart_data.set_index("期号")[["和值", "跨度"]], color=["#FF4B4B", "#1C83E1"])

# ================= 选号因素分析区 =================
with st.expander("🔍 点击查看：分位遗漏分析 (寻找冷号机会)", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("**百位遗漏**")
        st.write(get_missing_values(df, "百位"))
    with col2:
        st.write("**十位遗漏**")
        st.write(get_missing_values(df, "十位"))
    with col3:
        st.write("**个位遗漏**")
        st.write(get_missing_values(df, "个位"))
    st.caption("注：数字代表当前遗漏期数，数值越大说明越久未开出（冷号）。")

# ================= 固定推荐区 =================
st.subheader("🎯 今日 AI 精选推荐")

# 检查今天是否已经推荐过
target_qihao = None
try: 
    target_qihao = str(int(latest_qihao) + 1)
except: 
    target_qihao = latest_qihao + "_next"

today_record = next((r for r in strategy_history if r["target_qihao"] == target_qihao), None)

if today_record:
    # 如果已经推荐过，直接展示
    st.success(f"今日推荐已生成 (针对第 {target_qihao} 期)。为确保每日号码一致，不再重新生成。")
    picks = today_record["picks"].split(", ")
    reasons = today_record.get("reasons", ["历史记录无原因"] * 5) if "reasons" in today_record else ["历史记录无原因"] * 5
else:
    # 如果没有推荐过，生成新的
    if not strategy_history:
        current_weights = {"cold": 0.30, "hot": 0.10}
    else:
        last_weights = strategy_history[-1]
        current_weights = {"cold": last_weights.get("weights_cold", 0.30), "hot": last_weights.get("weights_hot", 0.10)}
        
    picks, reasons = generate_reverse_picks(df, current_weights)
    
    # 存入策略历史
    strategy_history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
        "target_qihao": target_qihao, 
        "picks": ", ".join(picks),
        "reasons": reasons,
        "weights_cold": current_weights["cold"],
        "weights_hot": current_weights["hot"]
    })
    st.success(f"已生成针对第 {target_qihao} 期的 5 注最新推荐！请尽快下载保存。")

# 展示推荐
for i, code in enumerate(picks, 1):
    count, periods = check_history_appearance(df, code, 1000)
    
    with st.container():
        st.markdown(f"### 第 {i} 注: <span style='color:#FF4B4B; font-size:32px;'>{code}</span>", unsafe_allow_html=True)
        # 推荐原因
        st.markdown(f"**💡 推荐理由**: {reasons[i-1]}")
        
        if count > 0:
            st.warning(f"⚠️ 近1000期出现过 **{count}** 次。期号: {', '.join(periods)}")
        else:
            st.success("✨ 近1000期未开出过")
        st.divider()

# ================= 侧边栏底部：下载功能 =================
with st.sidebar:
    st.markdown("---")
    st.header("💾 保存数据")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="开奖数据", index=False)
        if strategy_history:
            # 需要把 reasons 列表转为字符串存起来
            for r in strategy_history:
                if isinstance(r.get("reasons"), list):
                    r["reasons"] = " | ".join(r["reasons"])
            pd.DataFrame(strategy_history).to_excel(writer, sheet_name="策略记录", index=False)
            
    st.download_button(
        label="⬇️ 下载最新 Excel (含推荐记录)",
        data=output.getvalue(),
        file_name=f"福彩3D_备份_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )