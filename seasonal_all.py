"""
全品种季节性走势网页生成脚本
运行：python seasonal_all.py
输出：全品种季节性分析.html
"""

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

# ── 数据加载 ─────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
df = pd.read_csv(_HERE / "合并数据.csv", parse_dates=["Date"])
df["Year"]      = df["Date"].dt.year
df["DayOfYear"] = df["Date"].dt.dayofyear

years      = sorted(df["Year"].dropna().unique().astype(int))
MONTH_DOY  = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTH_TICK = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]

COLOR_MAP = {
    2018: "rgba(100,149,237,0.85)",
    2019: "rgba(102,205,102,0.85)",
    2020: "rgba(220,200,80,0.85)",
    2021: "rgba(180,180,180,0.85)",
    2022: "rgba(186,130,210,0.85)",
    2023: "rgba(100,100,100,0.85)",
    2024: "rgba(64,210,210,0.85)",
    2025: "rgba(255,160,40,0.85)",
    2026: "rgb(220,30,30)",
}

# ── 三个选项卡的图表定义 ──────────────────────────────────────────────
TABS = [
    {
        "id":    "tab-overseas",
        "label": "外盘价格",
        "charts": [
            ("GC1 Comdty",          "CME金",  "美元/盎司"),
            ("SI1 Comdty",          "CME银",  "美元/盎司"),
            ("HG1 Comdty",          "CME铜",  "美分/磅"),
            ("LMAHDS03 Comdty",     "LME铝",  "美元/吨"),
            ("LMCADS03 LME Comdty", "LME铜",  "美元/吨"),
            ("LMNIDS03 LME Comdty", "LME镍",  "美元/吨"),
            ("LMZSDS03 LME Comdty", "LME锌",  "美元/吨"),
            ("LMSNDS03 LME Comdty", "LME锡",  "美元/吨"),
        ],
    },
    {
        "id":    "tab-domestic",
        "label": "内盘价格",
        "charts": [
            ("CU2 Comdty",          "沪铜",       "元/吨"),
            ("AA2 Comdty",          "沪铝",       "元/吨"),
            ("AUA2 Comdty",         "沪金",       "元/克"),
            ("SAI2 COMB Comdty",    "沪银",       "元/千克"),
            ("XII2 Comdty",         "沪镍",       "元/吨"),
            ("ZNA2 Comdty",         "沪锌",       "元/吨"),
            ("XOO2 Comdty",         "沪锡",       "元/吨"),
            ("USDCNY REGN Curncy",  "离岸人民币", "CNH/USD"),
        ],
    },
    {
        "id":    "tab-spread",
        "label": "跨市价差",
        "charts": [
            ("CU COMEX-LME价差", "铜 COMEX-LME价差", "美元/吨"),
            ("CU SHFE-LME价差",  "铜 SHFE-LME价差",  "美元/吨"),
            ("AL SHFE-LME价差",  "铝 SHFE-LME价差",  "美元/吨"),
            ("CME金银比",        "CME金银比",         "倍"),
            ("黄金SHFE-CME",     "黄金 SHFE-CME价差", "美元/盎司"),
            ("白银SHFE-CME",     "白银 SHFE-CME价差", "美元/盎司"),
            ("镍SHFE-LME",       "镍 SHFE-LME价差",   "美元/吨", (2022,)),
            ("锌SHFE-LME",       "锌 SHFE-LME价差",   "美元/吨"),
            ("锡SHFE-LME",       "锡 SHFE-LME价差",   "美元/吨"),
        ],
    },
]

# ── 单个季节图生成 ────────────────────────────────────────────────────
def make_chart(col, title, unit, exclude_years=()):
    sub = df[["Date", "Year", "DayOfYear", col]].dropna(subset=[col])
    fig = go.Figure()

    for year in years:
        if year in exclude_years:
            continue
        yd = sub[sub["Year"] == year].sort_values("DayOfYear")
        if yd.empty:
            continue
        is_cur = (year == years[-1])
        fig.add_trace(go.Scatter(
            x=yd["DayOfYear"],
            y=yd[col],
            mode="lines",
            name=str(year),
            line=dict(color=COLOR_MAP.get(year, "grey"),
                      width=2.5 if is_cur else 1.2),
            hovertemplate=(
                f"<b>{year}</b><br>"
                "日期: %{customdata}<br>"
                f"{title}: %{{y:,.2f}} {unit}<extra></extra>"
            ),
            customdata=yd["Date"].dt.strftime("%Y-%m-%d"),
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="grey",
                  line_width=0.7, opacity=0.5)
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=13), x=0.5),
        xaxis=dict(tickvals=MONTH_DOY, ticktext=MONTH_TICK,
                   range=[1, 366], tickfont=dict(size=10)),
        yaxis=dict(title=unit, tickfont=dict(size=10),
                   tickformat=",.0f"),
        legend=dict(orientation="v", font=dict(size=9),
                    bgcolor="rgba(255,255,255,0.7)",
                    bordercolor="lightgrey", borderwidth=1),
        hovermode="x unified",
        template="plotly_white",
        margin=dict(l=55, r=10, t=45, b=35),
        height=340,
        font=dict(family="Microsoft YaHei, Arial"),
    )
    return fig

# ── 转为 HTML div（共享同一个 plotly.js） ────────────────────────────
def fig_to_div(fig, div_id):
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )

# ── 构建 HTML ─────────────────────────────────────────────────────────
def build_html():
    # 图例色块 HTML
    legend_html = "".join(
        f'<span style="display:inline-flex;align-items:center;margin:0 8px 4px 0;">'
        f'<span style="width:28px;height:3px;background:{COLOR_MAP[y]};'
        f'border-radius:2px;margin-right:4px;"></span>'
        f'<span style="font-size:12px;">{y}</span></span>'
        for y in years
    )

    # 选项卡按钮
    tab_btns = "".join(
        f'<button class="tab-btn{" active" if i==0 else ""}" '
        f'onclick="switchTab(\'{t["id"]}\')">{t["label"]}</button>'
        for i, t in enumerate(TABS)
    )

    # 各 tab 内容
    tab_sections = ""
    for i, tab in enumerate(TABS):
        display = "block" if i == 0 else "none"
        charts_html = ""
        for j, entry in enumerate(tab["charts"]):
            col, title, unit = entry[0], entry[1], entry[2]
            exclude = entry[3] if len(entry) > 3 else ()
            fig = make_chart(col, title, unit, exclude_years=exclude)
            div_id = f"{tab['id']}-chart-{j}"
            charts_html += f'<div class="chart-wrap">{fig_to_div(fig, div_id)}</div>'

        tab_sections += f"""
        <div id="{tab['id']}" class="tab-content" style="display:{display};">
          <div class="chart-grid">{charts_html}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全品种金属季节性分析</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", Arial, sans-serif;
          background: #f5f6fa; color: #333; }}

  /* ── 顶部标题栏 ── */
  .header {{
    background: linear-gradient(135deg, #1a3a5c 0%, #2d6a9f 100%);
    color: #fff; padding: 18px 24px 14px;
  }}
  .header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: 1px; }}
  .header .subtitle {{ font-size: 12px; opacity: .75; margin-top: 4px; }}

  /* ── 图例栏 ── */
  .legend-bar {{
    background: #fff; border-bottom: 1px solid #ddd;
    padding: 8px 20px; display: flex; flex-wrap: wrap; align-items: center;
  }}
  .legend-bar .lbl {{ font-size: 12px; color: #888; margin-right: 12px; }}

  /* ── 选项卡 ── */
  .tab-bar {{
    background: #fff; border-bottom: 2px solid #e0e0e0;
    padding: 0 20px; display: flex; gap: 4px;
  }}
  .tab-btn {{
    border: none; background: none; padding: 12px 22px;
    font-size: 14px; font-family: inherit; cursor: pointer;
    color: #666; border-bottom: 3px solid transparent;
    transition: all .2s;
  }}
  .tab-btn:hover {{ color: #2d6a9f; }}
  .tab-btn.active {{
    color: #2d6a9f; font-weight: 700;
    border-bottom-color: #2d6a9f;
  }}

  /* ── 图表网格：每行 2 列 ── */
  .chart-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
    padding: 16px 20px;
  }}
  .chart-wrap {{
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 6px rgba(0,0,0,.08);
    overflow: hidden;
  }}

  @media (max-width: 900px) {{
    .chart-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>全品种金属  季节性走势分析</h1>
  <div class="subtitle">数据来源：Bloomberg &nbsp;|&nbsp;
    日期范围：2018-01-01 ~ 2026-05-05 &nbsp;|&nbsp;
    鲜红线 = 当前年份（2026）</div>
</div>

<div class="legend-bar">
  <span class="lbl">年份颜色：</span>
  {legend_html}
</div>

<div class="tab-bar">
  {tab_btns}
</div>

{tab_sections}

<script>
function switchTab(id) {{
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(id).style.display = 'block';
  document.querySelector('[onclick="switchTab(\\''+id+'\\')"]').classList.add('active');
}}
</script>
</body>
</html>"""
    return html


# ── 主程序 ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("正在生成图表（共25张）...")
    html = build_html()
    from pathlib import Path
    OUT = Path(__file__).parent / "全品种季节性分析.html"
    OUT.write_text(html, encoding="utf-8")
    print(f"已生成: {OUT}")
