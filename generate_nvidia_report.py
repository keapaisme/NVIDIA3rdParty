import json
import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# 1. 股票與 Ticker 對應表
TICKER_MAP = {
    # 晶片與封裝
    "台積電": "2330.TW",
    "日月光投控": "3711.TW",
    "聯電": "2303.TW",
    "京元電": "2449.TW",
    "華邦電": "2344.TW",
    
    # AI 伺服器與系統代工
    "鴻海": "2317.TW",
    "廣達": "2382.TW",
    "緯創": "3231.TW",
    "緯穎": "6669.TW",
    "英業達": "2356.TW",
    "和碩": "4938.TW",
    "仁寶": "2324.TW",
    "美超微": "SMCI",
    
    # 機器人與工業電腦
    "索羅門": "2359.TW",
    "研華": "2395.TW",
    # 達明機器人為廣達子公司，未在集中市場/上櫃掛牌（6585 是鈺齊-KY，抓了會拿到別家股價），故移除。
    # "達明": "6585.TWO",
    "凌華": "6166.TW",
    "立端": "6245.TWO",
    "新漢": "8234.TWO",
    "研揚": "6579.TW",
    "宸曜": "6922.TWO",
    "艾訊": "3088.TWO",
    "廣運": "6125.TWO",
    "飛捷": "6206.TW",
    "聰泰": "5474.TWO",
    "醫揚": "6569.TWO",
    
    # 電源、散熱與零組件
    "台達電": "2308.TW",
    "勤誠": "8210.TW",
    "光寶科": "2301.TW",
    "欣興": "3037.TW",
    "迎廣": "6117.TW",
    "德律": "3030.TW",
    "曜越": "3540.TWO",
    "元山": "6275.TWO",
    "益登": "3048.TW",
    "弘憶股": "3312.TW",
    "中強光電": "5371.TWO",
    
    # 顯卡與電競板卡
    "技嘉": "2376.TW",
    "微星": "2377.TW",
    "華擎": "3515.TW",
    "麗臺": "2465.TW",
    "圓剛": "2417.TW",
    "神達": "3706.TW",
    "宏碁": "2353.TW",
    "巨大": "9921.TW",
    "慧友": "5484.TW"
}

def fetch_shares_outstanding():
    """
    從證交所 OpenAPI 取得「已發行普通股數」，供前端計算週轉率。
    週轉率 = 當日成交股數 / 已發行股數 × 100%
    抓失敗不致命，只是週轉率欄位會顯示 —。
    """
    import urllib.request
    urls = [
        ("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
        ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"),
    ]
    shares = {}
    for label, url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                rows = json.loads(r.read().decode("utf-8"))
            n = 0
            for row in rows:
                code = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
                raw = row.get("已發行普通股數或TDR原股發行股數") or row.get("已發行普通股數") or ""
                try:
                    v = int(str(raw).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue
                if code and v > 0:
                    shares[code] = v
                    n += 1
            print(f"  ✓ {label}發行股數：{n} 檔")
        except Exception as e:
            print(f"  ✗ {label}發行股數抓取失敗（週轉率將顯示 —）：{e}")
    return shares


def fetch_stock_data():
    """使用 yfinance 抓取股票近 65 日走勢數據並寫入 stock_data.json"""
    # 注意：yfinance 的 end 是「不含」當日，必須 +1 天才會抓到今天的收盤
    end_date = datetime.now() + timedelta(days=1)
    start_date = datetime.now() - timedelta(days=65)
    print(f"📡 開始抓取 {len(TICKER_MAP)} 檔概念股歷史數據 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})...")

    print("📡 取得已發行股數（週轉率用）…")
    shares_map = fetch_shares_outstanding()

    stock_results = {}
    failed = []
    for name, symbol in TICKER_MAP.items():
        try:
            df = yf.download(symbol, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'),
                             progress=False, auto_adjust=False, threads=False)
            if df is None or df.empty:
                failed.append((name, symbol, "回傳空資料"))
                print(f"  ✗ {name} ({symbol}): 回傳空資料（ticker 可能錯誤或已下市）")
                continue
            else:
                if isinstance(df.columns, pd.MultiIndex):
                    close_series = df['Close']
                    close_prices = (close_series[symbol] if symbol in close_series.columns
                                    else close_series.iloc[:, 0]).tolist()
                else:
                    close_prices = df['Close'].tolist()
                dates = [d.strftime('%m/%d') for d in df.index]
                
                valid_data = [(d, round(float(p), 2)) for d, p in zip(dates, close_prices) if pd.notna(p)]
                if valid_data:
                    d_list, p_list = zip(*valid_data)
                    start_price = p_list[0]
                    latest_price = p_list[-1]
                    pct_change = round(((latest_price - start_price) / start_price) * 100, 2)
                    stock_results[name] = {
                        "symbol": symbol,
                        "dates": list(d_list),
                        "prices": list(p_list),
                        "latest": latest_price,
                        "start": start_price,
                        "change": pct_change,
                        "high": max(p_list),
                        "low": min(p_list),
                        "last_date": d_list[-1],
                        "shares": shares_map.get(symbol.split(".")[0])
                    }
                    print(f"  ✓ {name} ({symbol}): {d_list[-1]} 收盤={latest_price}, 2M漲跌={pct_change}%")
                else:
                    failed.append((name, symbol, "全為 NaN"))
        except Exception as e:
            failed.append((name, symbol, str(e)))
            print(f"  ✗ 抓取失敗 {name} ({symbol}): {e}")

    # 失敗率過高 = 抓取整體出問題，不要用半殘資料覆蓋掉舊檔
    if failed:
        print(f"\n⚠️ 共 {len(failed)} 檔抓取失敗：")
        for n, s, r in failed:
            print(f"    - {n} ({s}): {r}")
    if len(stock_results) < len(TICKER_MAP) * 0.5:
        print("❌ 成功筆數低於一半，判定為抓取失敗，保留既有 stock_data.json 不覆寫。")
        if os.path.exists("stock_data.json"):
            with open("stock_data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    payload = {
        "_meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ok": len(stock_results),
            "failed": [f"{n} ({s})" for n, s, _ in failed],
        },
        **stock_results,
    }
    with open("stock_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ 成功更新 stock_data.json（共 {len(stock_results)} 檔，資料日 {stock_results['台積電']['last_date'] if '台積電' in stock_results else 'N/A'}）")
    return stock_results

def build_report_html():
    """讀取數據並寫入 nvidia_taiwan_partners_report.html"""
    if not os.path.exists("stock_data.json"):
        stock_data = fetch_stock_data()
    else:
        with open("stock_data.json", "r", encoding="utf-8") as f:
            stock_data = json.load(f)

    meta = stock_data.pop("_meta", {})
    # 過期警告：資料超過 2 天就明講，不要靜靜產生一份看起來很新的報告
    gen = meta.get("generated_at")
    if gen:
        age = (datetime.now() - datetime.strptime(gen, "%Y-%m-%d %H:%M:%S")).days
        if age >= 2:
            print(f"⚠️ 警告：stock_data.json 已是 {age} 天前的資料（{gen}），請先跑 --fetch 再產生報告。")
    print(f"📄 使用資料日期：{gen or '未知（舊格式，無時間戳）'}")

    # 報導熱度 Top 15 排行榜
    news_citations = [
        {
            "rank": 1,
            "name": "台積電 (TSMC)",
            "ticker": "2330.TW",
            "category": "晶片製造與先進封裝",
            "citations": "1,580+",
            "badge": "權王 / 獨家晶圓代工",
            "trend_pct": stock_data.get("台積電", {}).get("change", 0),
            "price": stock_data.get("台積電", {}).get("latest", 0),
            "news_summary": "輝達下一代 Blackwell 及 Vera Rubin 晶片 100% 採用台積電 4nm/3nm 製程與 CoWoS-L 先進封裝。黃仁勳演說大讚「台積電是輝達最堅實的基石」。近兩月因受國際大盤拉回，但先進封裝產能擴張依然供不應求。",
            "role": "晶圓代工 (N4P/N3E)、CoWoS 先進封裝、矽光子 CPO"
        },
        {
            "rank": 2,
            "name": "鴻海 (Foxconn)",
            "ticker": "2317.TW",
            "category": "AI 伺服器與系統代工",
            "citations": "1,240+",
            "badge": "GB200/GB300 主導者",
            "trend_pct": stock_data.get("鴻海", {}).get("change", 0),
            "price": stock_data.get("鴻海", {}).get("latest", 0),
            "news_summary": "黃仁勳演講特別展示「手稿定義鴻海 AI 建廠 3 階段」。鴻海取得 NVLink GB200 機櫃絕大多數份額，並與輝達合作於高雄、北士科打造超級算力中心，引爆 Foxconn Brain AI 智慧工廠話題。",
            "role": "GB200/300 NVLink 伺服器機櫃總裝、智慧工廠 Omniverse 數位分身"
        },
        {
            "rank": 3,
            "name": "廣達 (Quanta) / 雲達 (QCT)",
            "ticker": "2382.TW",
            "category": "AI 伺服器與系統代工",
            "citations": "980+",
            "badge": "水冷整機首波量產",
            "trend_pct": stock_data.get("廣達", {}).get("change", 0),
            "price": stock_data.get("廣達", {}).get("latest", 0),
            "news_summary": "旗下雲達科技率先量產整機 Blackwell GB200 NVLink72 水冷伺服器。黃仁勳親自登門站台，稱讚廣達是輝達在資料中心與 AI 超級電腦量產上速度最快的神隊友。",
            "role": "GB200 水冷伺服器整機出貨、MGX 模組化伺服器"
        },
        {
            "rank": 4,
            "name": "緯創 (Wistron) & 緯穎 (Wiwyn)",
            "ticker": "3231.TW / 6669.TW",
            "category": "AI 伺服器與系統代工",
            "citations": "850+",
            "badge": "GPU 主板 UBB 獨家霸主",
            "trend_pct": stock_data.get("緯創", {}).get("change", 0),
            "price": stock_data.get("緯創", {}).get("latest", 0),
            "news_summary": "緯創掌控輝達 HGX/Blackwell GPU 運算板 (UBB) 近九成份額；緯穎則專攻北美大型雲端服務商 (CSP) 客製化 MGX 水冷機櫃，近兩個月緯創股價大漲近 28.4%！",
            "role": "NVIDIA GPU 運算主板 (UBB)、OAM 模組、MGX 伺服器"
        },
        {
            "rank": 5,
            "name": "索羅門 (Solomon)",
            "ticker": "2359.TW",
            "category": "機器人與邊緣 AI",
            "citations": "760+",
            "badge": "黃仁勳機器人概念股總司令",
            "trend_pct": stock_data.get("索羅門", {}).get("change", 0),
            "price": stock_data.get("索羅門", {}).get("latest", 0),
            "news_summary": "黃仁勳演講背板首度秀出索羅門 LOGO，索羅門結合 NVIDIA Isaac 與 Metropolis，推出 3D Vision 機器人視覺系統，引爆全台實體 AI (Physical AI) 機器人風潮。",
            "role": "3D 視覺辨識、AMR 自主移動機器人、NVIDIA Isaac 平台整合"
        },
        {
            "rank": 6,
            "name": "台達電 (Delta Electronics)",
            "ticker": "2308.TW",
            "category": "電源、散熱與關鍵零組件",
            "citations": "690+",
            "badge": "高壓電源龍頭 / 液冷 CDU",
            "trend_pct": stock_data.get("台達電", {}).get("change", 0),
            "price": stock_data.get("台達電", {}).get("latest", 0),
            "news_summary": "隨 GB200 機櫃功耗躍升至 120kW，台達電提供超高功率 15kW/33kW 電源與冷卻分配單元 (CDU)，為 AI 資料中心極致省電與水冷系統的核心支柱。",
            "role": "AI 伺服器超高密度電源、液冷水冷板、CDU 液冷分配系統"
        },
        {
            "rank": 7,
            "name": "研華 (Advantech)",
            "ticker": "2395.TW",
            "category": "機器人與邊緣 AI",
            "citations": "620+",
            "badge": "工業 AI (Industrial AI) 龍頭",
            "trend_pct": stock_data.get("研華", {}).get("change", 0),
            "price": stock_data.get("研華", {}).get("latest", 0),
            "news_summary": "研華全面導入 NVIDIA Jetson Orin 與 Omniverse，發表 Edge AI 邊緣系統與智慧自動化微服務，近兩個月股價表現極其亮眼 (漲幅達 26.5%)。",
            "role": "工業邊緣運算 (IPC)、NVIDIA Jetson 邊緣裝置、Omniverse 工廠模擬"
        },
        {
            "rank": 8,
            "name": "日月光投控 (ASE) / 矽品",
            "ticker": "3711.TW",
            "category": "晶片製造與先進封裝",
            "citations": "580+",
            "badge": "CoWoS 委外 / 矽光子夥伴",
            "trend_pct": stock_data.get("日月光投控", {}).get("change", 0),
            "price": stock_data.get("日月光投控", {}).get("latest", 0),
            "news_summary": "台積電先進封裝供不應求，日月光投控取得大量 CoWoS 後段 OSAT 封測訂單，並配合輝達推進矽光子 (CPO) 光電整合技術，近兩個月漲幅達 10.2%。",
            "role": "2.5D/3D 先進封裝委外、晶片測試、矽光子 CPO 模組封裝"
        },
        {
            "rank": 9,
            "name": "技嘉 (GIGABYTE) & 微星 (MSI)",
            "ticker": "2376.TW / 2377.TW",
            "category": "顯卡、板卡與消費電子",
            "citations": "510+",
            "badge": "RTX 50 / MGX 伺服器雙引擎",
            "trend_pct": stock_data.get("技嘉", {}).get("change", 0),
            "price": stock_data.get("技嘉", {}).get("latest", 0),
            "news_summary": "技嘉與微星雙雙發表搭載 Blackwell GPU 的 HGX/MGX 伺服器，並全力推進 RTX 50 系列顯示卡與 RTX AI PC，消費端與企業端需求同步回溫。",
            "role": "GeForce RTX AI PC 顯示卡、MGX 伺服器、邊緣運算工作站"
        },
        {
            "rank": 10,
            "name": "麗臺科技 (Leadtek)",
            "ticker": "2465.TW",
            "category": "顯卡、板卡與消費電子",
            "citations": "480+",
            "badge": "亞太區 Omniverse 總代理",
            "trend_pct": stock_data.get("麗臺", {}).get("change", 0),
            "price": stock_data.get("麗臺", {}).get("latest", 0),
            "news_summary": "麗臺為 NVIDIA 亞太區專業繪圖卡與 Omniverse 代理龍頭，引領台灣企業建立 Omniverse 3D 數位分身與 AI 工作站，獲黃仁勳背板重點列名。",
            "role": "NVIDIA RTX 專業繪圖卡 (Quadro)、Omniverse 數位分身平台代理"
        },
        {
            "rank": 11,
            "name": "廣運 (KENMECS)",
            "ticker": "6125.TWO",
            "category": "電源、散熱與關鍵零組件",
            "citations": "430+",
            "badge": "水冷解法 / 自動化物流機器人",
            "trend_pct": stock_data.get("廣運", {}).get("change", 0),
            "price": stock_data.get("廣運", {}).get("latest", 0),
            "news_summary": "廣運展示全直接水冷 (Direct Liquid Cooling) 系統與 AMR 自動化機器人，獲黃仁勳點名合作，成為伺服器水冷與自動化倉儲熱門股。",
            "role": "直接水冷板/機櫃解法、AMR 自主移動機器人系統"
        },
        {
            "rank": 12,
            "name": "勤誠 (CHENBRO)",
            "ticker": "8210.TW",
            "category": "電源、散熱與關鍵零組件",
            "citations": "390+",
            "badge": "MGX 伺服器機箱龍頭",
            "trend_pct": stock_data.get("勤誠", {}).get("change", 0),
            "price": stock_data.get("勤誠", {}).get("latest", 0),
            "news_summary": "勤誠為輝達 MGX 模組化伺服器機箱首選夥伴，提供標準化與客製化高效能伺服器外殼，大幅提升伺服器出貨量能。",
            "role": "NVIDIA MGX 規格伺服器機箱、高密度伺服器機構件"
        },
        {
            "rank": 13,
            "name": "達明機器人 & 凌華 (ADLINK)",
            "ticker": "6166.TW",
            "category": "機器人與邊緣 AI",
            "citations": "360+",
            "badge": "協作手臂 / Isaac AMR 平台",
            "trend_pct": stock_data.get("凌華", {}).get("change", 0),
            "price": stock_data.get("凌華", {}).get("latest", 0),
            "news_summary": "達明機器人（廣達集團）與凌華科技深耕 NVIDIA Isaac AMR 自主移動機器人平台，導入數位手臂與視覺自動化，近兩個月凌華暴漲 32.2%！",
            "role": "TM AI Cobot 協作手臂、Isaac AMR 智慧機器人控制器"
        },
        {
            "rank": 14,
            "name": "聯電 (UMC)",
            "ticker": "2303.TW",
            "category": "晶片製造與先進封裝",
            "citations": "320+",
            "badge": "Interposer 矽中介層支援",
            "trend_pct": stock_data.get("聯電", {}).get("change", 0),
            "price": stock_data.get("聯電", {}).get("latest", 0),
            "news_summary": "聯電配合台積電先進封裝體系，提供 12 吋 55nm/28nm 矽中介層 (Silicon Interposer) 產能，協助舒緩 CoWoS 產能吃緊問題，兩個月漲幅達 14.2%。",
            "role": "CoWoS 先進封裝矽中介層 (Interposer) 晶圓代工"
        },
        {
            "rank": 15,
            "name": "趨勢科技 & 台智雲 (TWS)",
            "ticker": "未上市/新創",
            "category": "軟體、新創與 AI 生態系",
            "citations": "290+",
            "badge": "NIM 微服務 / AI 安全防護",
            "trend_pct": 0,
            "price": 0,
            "news_summary": "趨勢科技結合 NVIDIA NIM 微服務推出企業級 AI 資料安全防護；台智雲則利用輝達算力建置台灣本土繁體中文大語言模型 (Formosa LLM)。",
            "role": "NVIDIA NIM 安全整合、AI 資料安全、台智雲 AI 超級電腦與大模型"
        }
    ]

    # 未上市 / 新創合作夥伴名單
    unlisted_partners = [
        {"name": "鴻佰 (Ingrasys)", "parent": "鴻海集團", "category": "AI 伺服器與系統代工", "role": "NVLink 伺服器與水冷機櫃主要製造商"},
        {"name": "雲達科技 (QCT)", "parent": "廣達集團", "category": "AI 伺服器與系統代工", "role": "Blackwell GB200 水冷整機伺服器架構商"},
        {"name": "矽品精密 (SPIL)", "parent": "日月光集團", "category": "晶片製造與先進封裝", "role": "CoWoS 2.5D/3D 高階晶片封裝測試"},
        {"name": "安提國際 (Aetina)", "parent": "宜鼎集團", "category": "機器人與邊緣 AI", "role": "NVIDIA Jetson 邊緣 AI 模組與邊緣伺服器"},
        {"name": "訊凱國際 (Cooler Master)", "parent": "獨立企業", "category": "電源、散熱與關鍵零組件", "role": "AI 伺服器高階散熱風扇與液冷腔體"},
        {"name": "映眾 (INNO3D)", "parent": "獨立企業", "category": "顯卡、板卡與消費電子", "role": "GeForce RTX 系列顯示卡製造與銷售"},
        {"name": "索泰 / 卓越 (ZOTAC)", "parent": "栢能集團", "category": "顯卡、板卡與消費電子", "role": "GeForce RTX AI 顯示卡與迷你工作站"},
        {"name": "同德 (Palit)", "parent": "獨立企業", "category": "顯卡、板卡與消費電子", "role": "NVIDIA 全球最大 AIC 顯示卡製造合作夥伴之一"},
        {"name": "萬利達 (Manli)", "parent": "獨立企業", "category": "顯卡、板卡與消費電子", "role": "GeForce RTX 系列專業繪圖與遊戲顯示卡"},
        {"name": "七彩虹 (Colorful)", "parent": "獨立企業", "category": "顯卡、板卡與消費電子", "role": "GeForce RTX 系列高階顯示卡與電競硬體"},
        {"name": "亞太智能機器 (APMIC)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "C-Suite 生成式 AI 工作流程與地端大模型"},
        {"name": "家家智能 (HOMEE.AI)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "空間 AI (Spatial AI) 與家具數位分身生成"},
        {"name": "宇見智能 (MetAI)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "Omniverse 工業機器人合成數據 (Synthetic Data)"},
        {"name": "Footprint-AI", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "MLOps 機器學習運營平台與微服務 MLOps"},
        {"name": "偲捷科技 (SPINGENCE)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "智能製造與智慧光學檢測 (AOI) 軟體"},
        {"name": "Fortune AI", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "金融與醫療垂直領域大語言模型服務"},
        {"name": "敦新科技 (Dawning)", "parent": "系統整合", "category": "軟體、新創與 AI 生態系", "role": "NVIDIA DGX AI 超級電腦代理與系統整合"},
        {"name": "樂達科技 (Leda)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "自動化 AI 檢測模型訓練平台"},
        {"name": "律果科技 (Legal Tech)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "法律專用生成式 AI 合約審查與分析"},
        {"name": "台智雲 (TWS)", "parent": "華碩集團", "category": "軟體、新創與 AI 生態系", "role": "NVIDIA H100/H200 超級算力雲端服務與大模型"},
        {"name": "澄風科技 (STREAMTECK)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "毫米波雷達與 AI 感測融合系統"},
        {"name": "杰倫智能 (PROFET AI)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "製造業 No-Code AutoAI 機器學習 AutoML"},
        {"name": "滿拓科技 (DeepMentor)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "邊緣端 AI 模型量化與晶片優化演算法"},
        {"name": "神瑞人工智慧 (DeepRad.AI)", "parent": "醫療新創", "category": "軟體、新創與 AI 生態系", "role": "NVIDIA Clara 醫療影像 AI 診斷微服務"},
        {"name": "英研智能 (AIMobile)", "parent": "英業達/英特爾合資", "category": "機器人與邊緣 AI", "role": "邊緣 AI 影像分析與智慧邊緣網關"},
        {"name": "城智科技 (AIRA)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "AI 人臉辨識與安防智慧監控"},
        {"name": "鑫蘊林科 (Linker Vision)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "5G AIoT 自動化車聯網與視覺 AI 平台"},
        {"name": "超恩 (VECOW)", "parent": "獨立企業", "category": "機器人與邊緣 AI", "role": "強固型邊緣 AI 電腦與車載運算系統"},
        {"name": "安宏生醫 (AnHorn)", "parent": "生技新創", "category": "軟體、新創與 AI 生態系", "role": "NVIDIA BioNeMo 蛋白標的 AI 新藥開發"},
        {"name": "集仕多 (ChoozMo)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "AI 虛擬主播與數位人 (Digital Human) 生成"},
        {"name": "集雅科技 (GliaCloud)", "parent": "新創企業", "category": "軟體、新創與 AI 生態系", "role": "AI 自動影音生成 (Text-to-Video)"},
        {"name": "樂方 (BigGO)", "parent": "獨立企業", "category": "軟體、新創與 AI 生態系", "role": "AI 比價引擎與購物搜尋推薦系統"},
        {"name": "金屬工業研究發展中心", "parent": "法人財團", "category": "機器人與邊緣 AI", "role": "金屬加工、智慧製造與機器人技術研發"}
    ]

    stock_json_str = json.dumps(stock_data, ensure_ascii=False)
    news_json_str = json.dumps(news_citations, ensure_ascii=False)
    unlisted_json_str = json.dumps(unlisted_partners, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>黃仁勳 NVIDIA 台灣合作夥伴概念股全剖析｜即時動態與近兩個月股價走勢</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        nvgreen: '#76B900',
                        nvdark: '#0f172a',
                        cardbg: '#1e293b',
                        borderbg: '#334155'
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: #0b0f19;
            color: #f1f5f9;
        }}
        .nv-glow {{
            box-shadow: 0 0 20px rgba(118, 185, 0, 0.15);
        }}
        .custom-scrollbar::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        .custom-scrollbar::-webkit-scrollbar-track {{
            background: #0f172a;
        }}
        .custom-scrollbar::-webkit-scrollbar-thumb {{
            background: #334155;
            border-radius: 4px;
        }}
        /* 即時跑馬燈動畫 */
        @keyframes marquee {{
            0% {{ transform: translateX(0%); }}
            100% {{ transform: translateX(-50%); }}
        }}
        .animate-marquee {{
            display: flex;
            width: 200%;
            animation: marquee 30s linear infinite;
        }}
        .animate-marquee:hover {{
            animation-play-state: paused;
        }}

        /* 排序索引列 */
        .sort-btn {{
            font-size: 11px; padding: 5px 10px; border-radius: 8px;
            background: #1e293b; color: #94a3b8;
            border: 1px solid #334155; transition: .15s; white-space: nowrap;
        }}
        .sort-btn:hover {{ background: #334155; color: #e2e8f0; }}
        .sort-btn.active {{
            background: rgba(118,185,0,.15); color: #76B900; border-color: rgba(118,185,0,.45);
            font-weight: 700;
        }}

        /* LED 20 格訊號條：一格接一格、不留間隔、統一方格無圓角 */
        .led-bar {{ display: flex; gap: 0; }}
        .led {{
            width: 14px; height: 14px; border-radius: 0;
            background: #1e293b; border-right: 1px solid #0f172a; flex: none;
        }}
        .led.buy  {{ background: #22c55e; }}
        .led.sell {{ background: #ef4444; }}
        .led-day {{
            width: 14px; flex: none; text-align: center;
            font-size: 8px; line-height: 10px; color: #64748b; font-family: monospace;
        }}
    </style>
</head>
<body class="min-h-screen pb-16 custom-scrollbar">

    <!-- Top Navigation Header -->
    <header class="border-b border-slate-800 bg-slate-900/95 sticky top-0 z-50 backdrop-blur-md shadow-lg">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-col md:flex-row justify-between items-center gap-3">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-green-600 to-[#76B900] flex items-center justify-center font-bold text-slate-950 text-xl shadow-lg shadow-green-500/20">
                    NV
                </div>
                <div>
                    <h1 class="text-lg md:text-xl font-bold tracking-tight text-white flex items-center gap-2">
                        黃仁勳 NVIDIA 台灣合作夥伴概念股全剖析
                        <span class="text-xs bg-[#76B900]/20 text-[#76B900] px-2.5 py-0.5 rounded-full border border-[#76B900]/30 font-medium">即時動態與走勢報告</span>
                    </h1>
                    <p class="text-xs text-slate-400">涵蓋 70+ 家台廠供應鏈、最新新聞報導引用排序與即時行情走勢分析</p>
                </div>
            </div>
            
            <div class="flex items-center gap-3">
                <button id="syncBtn" type="button" onclick="syncLiveQuotes()" class="flex items-center gap-1.5 bg-[#76B900]/10 hover:bg-[#76B900]/20 text-[#76B900] border border-[#76B900]/40 px-3 py-1.5 rounded-lg text-xs font-semibold transition active:scale-95 shadow">
                    <i class="fa-solid fa-rotate text-[#76B900] animate-spin-slow" id="syncIcon"></i>
                    <span id="syncBtnText">即時同步最新行情</span>
                </button>
                <div class="flex items-center gap-2 text-xs text-slate-400 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700">
                    <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" id="statusDot"></span>
                    <span id="syncStatus">連線即時行情中...</span>
                </div>
            </div>
        </div>

        <!-- Live Ticker Bar (即時訊息跑馬燈) -->
        <div class="bg-slate-950 border-t border-b border-slate-800/80 py-1.5 overflow-hidden relative">
            <div class="max-w-7xl mx-auto px-4 flex items-center gap-3">
                <span class="text-[11px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded shrink-0 flex items-center gap-1">
                    <i class="fa-solid fa-bolt text-amber-400"></i> 即時動態
                </span>
                <div class="overflow-hidden w-full relative">
                    <div class="animate-marquee whitespace-nowrap text-xs text-slate-300 gap-8" id="liveTickerContainer">
                        <!-- Dynamic ticker items -->
                    </div>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-8">

        <!-- Executive Summary & Key Highlights -->
        <section class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="bg-slate-800/80 border border-slate-700/60 p-5 rounded-2xl nv-glow">
                <div class="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">NVIDIA 合作夥伴生態</div>
                <div class="text-3xl font-extrabold text-white">122<span class="text-sm font-normal text-slate-400 ml-1" id="cardCount">家</span></div>
                <div class="text-xs text-[#76B900] mt-2 flex items-center gap-1">
                    <i class="fa-solid fa-microchip"></i> 晶圓、伺服器、散熱、機器人
                </div>
            </div>

            <div class="bg-slate-800/80 border border-slate-700/60 p-5 rounded-2xl">
                <div class="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">媒體報導引用排行榜冠亞軍</div>
                <div class="text-2xl font-bold text-emerald-400" id="cardTopCited">—</div>
                <div class="text-xs text-slate-300 mt-2" id="cardTopCitedSub">
                    新聞熱度超高，Blackwell 機櫃與 CoWoS 封裝焦點
                </div>
            </div>

            <div class="bg-slate-800/80 border border-slate-700/60 p-5 rounded-2xl">
                <div class="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">2 個月最大飆價榜</div>
                <div class="text-2xl font-bold text-green-400" id="cardTopGainer">—</div>
                <div class="text-xs text-slate-400 mt-2" id="cardTopGainerSub">計算中…</div>
            </div>

            <div class="bg-slate-800/80 border border-slate-700/60 p-5 rounded-2xl">
                <div class="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">核心技術三大熱點</div>
                <div class="text-lg font-bold text-sky-400">GB200 液冷 / 實體 AI / NIM</div>
                <div class="text-xs text-slate-400 mt-2">
                    直接水冷 CDU、Isaac 機器人與 Omniverse
                </div>
            </div>
        </section>

        <!-- Section 1: Multi-Stock Trend Comparator Chart -->
        <section class="bg-slate-800/60 border border-slate-700/80 rounded-2xl p-6 shadow-xl">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
                <div>
                    <h2 class="text-xl font-bold text-white flex items-center gap-2">
                        <i class="fa-solid fa-chart-line text-[#76B900]"></i>
                        台股輝達指標概念股：近 2 個月股價走勢對比
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">選取台積電、鴻海、廣達、緯創、台達電、索羅門等核心熱門股進行近 60 日股價變化趨勢比較</p>
                </div>
                <div class="flex flex-wrap gap-2 text-xs">
                    <button onclick="updateComparisonChart(['台積電', '鴻海', '廣達', '緯創', '台達電'])" class="bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded-lg text-slate-200 transition">權值五天王</button>
                    <button onclick="updateComparisonChart(['索羅門', '研華', '凌華', '廣運', '華邦電'])" class="bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded-lg text-slate-200 transition">機器人與中小型強勢股</button>
                </div>
            </div>
            <div class="h-80 w-full">
                <canvas id="multiStockChart"></canvas>
            </div>
        </section>

        <!-- Section 2: News Citations & Media Coverage Ranking Table -->
        <section class="space-y-4">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 class="text-2xl font-extrabold text-white flex items-center gap-2">
                        <i class="fa-solid fa-fire text-amber-500"></i>
                        台股新聞：依報導引用與提及熱度排序 (Top 15)
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">彙整 COMPUTEX 演講、Blackwell 機櫃拉貨、液冷散熱與機器人新聞中被引用與提及頻率最高之台廠</p>
                </div>
            </div>

            <!-- 排序索引列：點一下切換升／降序 -->
            <div class="flex flex-wrap gap-1.5 mb-3" id="sortBar">
                <button class="sort-btn" data-key="rank">熱度排名</button>
                <button class="sort-btn" data-key="change">漲跌幅</button>
                <button class="sort-btn" data-key="turnover">週轉率</button>
                <button class="sort-btn" data-key="amplitude">振幅</button>
                <button class="sort-btn" data-key="trend20">趨勢 20日</button>
            </div>

            <div class="bg-slate-800/80 border border-slate-700 rounded-2xl shadow-xl overflow-hidden">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-900/90 text-[11px] text-slate-500 border-b border-slate-700">
                        <tr>
                            <th class="py-2 px-2 sm:px-3 text-center w-9">#</th>
                            <th class="py-2 px-2 sm:px-3">企業</th>
                            <th class="py-2 px-2 text-right hidden sm:table-cell">週轉率</th>
                            <th class="py-2 px-2 text-right hidden md:table-cell">振幅</th>
                            <th class="py-2 px-2 text-right hidden md:table-cell">20日</th>
                            <th class="py-2 px-2 sm:px-3 text-right">股價 / 近2月</th>
                            <th class="py-2 px-2 w-8"></th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800/70" id="newsTableBody">
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Section 3: Interactive Stock Search & Individual Stock Trend Cards -->
        <section class="space-y-6">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
                <div>
                    <h2 class="text-2xl font-bold text-white flex items-center gap-2">
                        <i class="fa-solid fa-chart-area text-emerald-400"></i>
                        近 2 個月股價走勢圖與個股走勢明細
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">輸入關鍵字或點選類別，查看 45+ 檔輝達台股合作夥伴近兩個月完整 K 線走勢圖</p>
                </div>

                <div class="flex flex-wrap gap-2 w-full md:w-auto">
                    <input type="text" id="stockSearch" placeholder="搜尋個股或代號 (如: 2330, 鴻海, 水冷)..." 
                           class="bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-xl px-4 py-2 focus:outline-none focus:border-[#76B900] w-full md:w-64">
                </div>
            </div>

            <!-- Filter Badges -->
            <div class="flex flex-wrap gap-2 text-xs" id="categoryFilters">
                <button class="filter-btn active bg-[#76B900] text-slate-950 px-3 py-1.5 rounded-lg font-bold transition" onclick="filterStocks('ALL')">全部股票 (45)</button>
                <button class="filter-btn bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition" onclick="filterStocks('晶片製造與先進封裝')">晶片與封裝</button>
                <button class="filter-btn bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition" onclick="filterStocks('AI 伺服器與系統代工')">AI 伺服器/代工</button>
                <button class="filter-btn bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition" onclick="filterStocks('機器人與邊緣 AI')">機器人/工業電腦</button>
                <button class="filter-btn bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition" onclick="filterStocks('電源、散熱與關鍵零組件')">電源/散熱/零組件</button>
                <button class="filter-btn bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition" onclick="filterStocks('顯卡、板卡與消費電子')">顯卡/AI PC</button>
            </div>

            <!-- Grid of Individual Stock Cards -->
            <div id="stockHint" class="text-center text-slate-500 text-sm py-10 border border-dashed border-slate-700 rounded-2xl">
                👆 請點選上方類別，或於搜尋框輸入股名／代號，即顯示對應個股走勢
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="stockGrid">
                <!-- Stock cards dynamically rendered with canvas charts -->
            </div>
        </section>

        <!-- Section 4: Full NVIDIA Ecosystem Partner Categorization -->
        <section class="space-y-6 pt-6 border-t border-slate-800">
            <div>
                <h2 class="text-2xl font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-sitemap text-indigo-400"></i>
                    黃仁勳點名全合作夥伴目錄 (含未上市/子公司與新創)
                </h2>
                <p class="text-xs text-slate-400 mt-1">完整整理黃仁勳演講與背板列出之台灣企業、子公司、新創與研究機構</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="unlistedContainer">
                <!-- Category cards for non-listed and specialized partners -->
            </div>
        </section>

    </main>

    <footer class="mt-16 border-t border-slate-800 bg-slate-950 py-8 text-center text-xs text-slate-500">
        <div class="max-w-7xl mx-auto px-4">
            <p>黃仁勳 NVIDIA 台灣合作夥伴概念股全剖析報告｜資料來源：台灣證券交易所、櫃買中心 OpenAPI 與 Yahoo Finance</p>
            <p id="dataStamp" class="mt-1 font-mono text-[11px] text-slate-600">尚未同步</p>
            <p class="mt-1">本報告僅供資訊整理與研究參考，不構成任何投資建議。</p>
        </div>
    </footer>

    <!-- Embedded Data & Client Scripts -->
    <script>
        const stockData = {stock_json_str};
        const newsData = {news_json_str};
        const unlistedData = {unlisted_json_str};

        let currentCategory = 'ALL';
        let multiChartInstance = null;
        let currentChartKeys = ['台積電', '鴻海', '廣達', '緯創', '台達電'];

        // 即時動態訊息新聞列表
        const liveMessages = [
            "🔥 【即時市場】台積電 CoWoS 先進封裝產能全線滿載，輝達 Blackwell 訂單追單量超乎預期！",
            "🚀 【供應鏈動態】鴻海高雄超級算力中心建置順利，GB200 NVLink 伺服器整機拉貨動能強勁！",
            "💧 【液冷散熱】廣達與雲達率先出貨整機 Blackwell GB200 水冷系統，冷態測試數據優良！",
            "🤖 【實體 AI】索羅門 3D Vision 結合 NVIDIA Isaac 平台，接獲多家智慧工廠機器人訂單！",
            "⚡ 【高壓電源】台Delta 電源模組量產出貨 GB200 超高密度 33kW 系統，市佔率超七成！",
            "📈 【邊緣運算】研華與凌華推出搭載 Jetson Orin 的工業級 Edge AI 主機，股價展現強勢強攻！"
        ];

        document.addEventListener('DOMContentLoaded', () => {{
            renderSummaryCards();
            renderLiveTicker();
            renderNewsTable();

            // 排序索引列
            document.querySelectorAll('#sortBar .sort-btn').forEach(b => {{
                b.addEventListener('click', () => sortNews(b.dataset.key));
            }});

            // 股價走勢區：載入時不渲染任何卡片，等使用者點類別或搜尋才顯示
            renderUnlistedPartners();
            initComparisonChart(['台積電', '鴻海', '廣達', '緯創', '台達電']);

            document.getElementById('stockSearch').addEventListener('input', (e) => {{
                const v = e.target.value.trim();
                if (v) gridVisible = true;               // 一開始打字就顯示
                renderStockCards(currentCategory, v);
            }});

            // 頁面開啟時自動同步即時行情 (方案二)
            syncLiveQuotes();
        }});

        function renderLiveTicker() {{
            const container = document.getElementById('liveTickerContainer');

            // 一律由真實股價產生，不用編造的新聞文案。
            //   同步成功 → 用「當日漲跌」；尚未同步/同步失敗 → 退回「近 2 月漲跌」（仍是真數字）
            const hasDay = Object.keys(stockData).some(k => stockData[k] && stockData[k].dayChangePct !== undefined);
            const field = hasDay ? 'dayChangePct' : 'change';
            const label = hasDay ? `📅 ${{tickerDateLabel}} 收盤・當日漲跌` : '📊 近 2 個月漲跌幅';

            const live = Object.keys(stockData)
                .filter(k => stockData[k] && typeof stockData[k][field] === 'number')
                .sort((a, b) => stockData[b][field] - stockData[a][field]);

            let msgs;
            if (live.length >= 4) {{
                const fmt = (k, icon) => {{
                    const s = stockData[k];
                    const p = s[field];
                    return `${{icon}} ${{k}} ${{s.latest}} <span class="${{p >= 0 ? 'text-emerald-400' : 'text-rose-400'}} font-semibold">${{p >= 0 ? '+' : ''}}${{p}}%</span>`;
                }};
                msgs = [label]
                    .concat(live.slice(0, 5).map(k => fmt(k, '📈')))
                    .concat(live.slice(-3).reverse().map(k => fmt(k, '📉')));
            }} else {{
                msgs = liveMessages;
            }}

            const items = [...msgs, ...msgs].map(msg => `
                <span class="inline-flex items-center gap-2 mr-8">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                    ${{msg}}
                </span>
            `).join('');
            container.innerHTML = items;
        }}
        let tickerDateLabel = '';

        // 摘要卡片一律由資料現算，不寫死數字（原本寫死的「凌華 +32.3%」實際是 -1.09%、排第 18）
        function renderSummaryCards() {{
            const set = (id, html) => {{ const el = document.getElementById(id); if (el) el.innerHTML = html; }};

            const keys = Object.keys(stockData).filter(k => stockData[k] && typeof stockData[k].change === 'number');
            set('cardCount', `家 / ${{keys.length}} 檔台股`);

            const top2 = newsData.slice().sort((a, b) => a.rank - b.rank).slice(0, 2)
                .map(x => String(x.name).replace(/\s*\([^)]*\)/g, '').replace(/\s*([\/&])\s*/g, ' $1 ').trim());
            set('cardTopCited', top2.join(' & '));

            const ranked = keys.slice().sort((a, b) => stockData[b].change - stockData[a].change);
            if (ranked.length) {{
                const fmt = k => `${{k}} (${{stockData[k].change >= 0 ? '+' : ''}}${{stockData[k].change}}%)`;
                set('cardTopGainer', fmt(ranked[0]));
                set('cardTopGainerSub', ranked.slice(1, 4).map(fmt).join('、'));
            }}
        }}

        // ---------------------------------------------------------------
        // 行情同步：讀取 Cloud Run 定時更新的 GCS latest.json
        //   - Cloud Scheduler 每 1 分鐘觸發 Cloud Run 更新 JSON
        //   - 靜態網頁只讀自己的 GCS 檔案，避開 CORS / Proxy / API 封鎖
        // ---------------------------------------------------------------
        const LIVE_QUOTES_JSON = "https://storage.googleapis.com/portfolio-kas-use-pi/quotes/latest.json";

        let isSyncing = false;   // 防止手機連點觸發多次下載

        function num(v) {{
            const n = parseFloat(String(v ?? "").replace(/,/g, ""));
            return isNaN(n) ? null : n;
        }}

        function dateToMD(dateStr) {{
            // "2026-08-14" / "2026-08-14 13:30:00" -> "08/14"
            const s = String(dateStr || "").slice(0, 10);
            if (!/^\d{{4}}-\d{{2}}-\d{{2}}$/.test(s)) return null;
            return s.slice(5).replace("-", "/");
        }}

        async function syncLiveQuotes() {{
            if (isSyncing) return;
            isSyncing = true;

            const syncIcon = document.getElementById('syncIcon');
            const syncBtn = document.getElementById('syncBtn');
            const syncBtnText = document.getElementById('syncBtnText');
            const syncStatus = document.getElementById('syncStatus');
            const statusDot = document.getElementById('statusDot');

            syncIcon.classList.remove('animate-spin-slow');
            syncIcon.classList.add('animate-spin');
            syncBtnText.innerText = "同步中...";
            if (syncBtn) {{ syncBtn.disabled = true; syncBtn.classList.add('opacity-60', 'pointer-events-none'); }}
            statusDot.className = "inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse";
            syncStatus.innerText = "讀取 GCS 最新行情檔...";

            try {{
                const url = `${{LIVE_QUOTES_JSON}}?t=${{Date.now()}}`;
                const res = await fetch(url, {{ signal: AbortSignal.timeout(15000), cache: "no-store" }});
                if (!res.ok) throw new Error(`latest.json HTTP ${{res.status}}`);
                const payload = await res.json();
                const quotes = payload.quotes || {{}};
                const byCode = payload.by_code || {{}};

                let updated = 0, missed = [];
                Object.keys(stockData).forEach(name => {{
                    const s = stockData[name];
                    if (!s || !s.symbol) return;
                    const code = s.symbol.split(".")[0];
                    const q = quotes[s.symbol] || byCode[code];
                    const close = num(q?.price);
                    if (close === null) {{ missed.push(name); return; }}

                    s.latest = close;
                    if (s.start) s.change = roundToTwo((close - s.start) / s.start * 100);

                    const dayChg = num(q?.change);
                    const dayPct = num(q?.change_pct);
                    if (dayChg !== null) s.dayChange = roundToTwo(dayChg);
                    if (dayPct !== null) s.dayChangePct = roundToTwo(dayPct);

                    const vol = num(q?.volume);
                    if (vol !== null) {{
                        s.volume = vol;
                        if (s.shares) s.turnover = roundToTwo(vol / s.shares * 100);
                    }}

                    const md = dateToMD(q?.market_date || q?.market_time || payload.data_date);
                    if (md && Array.isArray(s.dates) && Array.isArray(s.prices)) {{
                        if (s.dates[s.dates.length - 1] === md) {{
                            s.prices[s.prices.length - 1] = close;
                        }} else {{
                            s.dates.push(md);
                            s.prices.push(close);
                        }}
                        s.high = Math.max(...s.prices);
                        s.low  = Math.min(...s.prices);
                    }}
                    updated++;
                }});

                if (updated === 0) throw new Error("latest.json 中找不到任何可用報價");

                const md = dateToMD(payload.data_date) || '最新';
                const updatedAt = payload.updated_at_taipei || new Date().toLocaleTimeString('zh-TW', {{ hour12: false }});
                syncStatus.innerText = `${{md}} 行情・已更新 ${{updated}} 檔`;
                lastSyncText = `資料來源 GCS latest.json｜更新時間 ${{updatedAt}}｜已更新 ${{updated}} 檔`
                             + (missed.length ? `｜${{missed.length}} 檔未取得` : '');
                statusDot.className = "inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
                updateStampBar();

                tickerDateLabel = md;
                renderSummaryCards();
                renderLiveTicker();
                renderNewsTable();
                renderStockCards(currentCategory, document.getElementById('stockSearch').value);
                refreshComparisonChart();
            }} catch (err) {{
                console.error("行情同步失敗：", err);
                syncStatus.innerText = "同步失敗，顯示快取資料";
                lastSyncText = `⚠️ 同步失敗：${{err.message}}（畫面為靜態快取，非最新）`;
                statusDot.className = "inline-block w-2 h-2 rounded-full bg-rose-500";
                updateStampBar();
            }} finally {{
                isSyncing = false;
                syncIcon.classList.remove('animate-spin');
                syncIcon.classList.add('animate-spin-slow');
                syncBtnText.innerText = "即時同步最新行情";
                if (syncBtn) {{ syncBtn.disabled = false; syncBtn.classList.remove('opacity-60', 'pointer-events-none'); }}
            }}
        }}

        let lastSyncText = "尚未同步";
        function updateStampBar() {{
            const el = document.getElementById('dataStamp');
            if (el) el.innerText = lastSyncText;
        }}

        function refreshComparisonChart() {{
            try {{
                if (typeof multiChartInstance !== 'undefined' && multiChartInstance) {{
                    updateComparisonChart(currentChartKeys || ['台積電', '鴻海', '廣達', '緯創', '台達電']);
                }}
            }} catch (e) {{ console.warn("圖表刷新略過", e); }}
        }}

        function roundToTwo(num) {{
            return Math.round((num + Number.EPSILON) * 100) / 100;
        }}

        // ===============================================================
        //  技術指標：20 日趨勢、振幅、MA5×MA20 買賣點訊號、LED 訊號條
        // ===============================================================
        const LED_DAYS = 20;

        function movingAvg(arr, i, k) {{
            if (i < k - 1) return null;
            let sum = 0;
            for (let j = i - k + 1; j <= i; j++) sum += arr[j];
            return sum / k;
        }}

        // 黃金交叉(MA5 上穿 MA20)=買點；死亡交叉(MA5 下穿 MA20)=賣點
        function detectSignals(prices) {{
            const out = {{}};
            for (let i = 20; i < prices.length; i++) {{
                const m5 = movingAvg(prices, i, 5),  m20 = movingAvg(prices, i, 20);
                const p5 = movingAvg(prices, i - 1, 5), p20 = movingAvg(prices, i - 1, 20);
                if (m5 == null || m20 == null || p5 == null || p20 == null) continue;
                if (p5 <= p20 && m5 > m20) out[i] = 'buy';
                else if (p5 >= p20 && m5 < m20) out[i] = 'sell';
            }}
            return out;
        }}

        // 20 個方格，一格一天，緊鄰不留間隔；只有有顏色的格子上方標「日」（不標月）
        function buildLedBar(s) {{
            if (!s || !Array.isArray(s.prices) || s.prices.length < 21) return '';
            const sig = detectSignals(s.prices);
            const start = Math.max(0, s.prices.length - LED_DAYS);

            let days = '', cells = '';
            for (let i = start; i < s.prices.length; i++) {{
                const kind = sig[i];
                const dd = String(s.dates[i] || '').split('/')[1] || '';
                days  += `<div class="led-day">${{kind ? dd : ''}}</div>`;
                cells += `<div class="led ${{kind || ''}}" title="${{s.dates[i]}}${{kind === 'buy' ? ' 買點' : kind === 'sell' ? ' 賣點' : ''}}"></div>`;
            }}
            return `<div class="led-bar">${{days}}</div><div class="led-bar">${{cells}}</div>`;
        }}

        // 個股各項指標（振幅與趨勢皆以近 20 日計算）
        function metricsOf(s) {{
            if (!s || !Array.isArray(s.prices) || !s.prices.length) return {{}};
            const p = s.prices, w = p.slice(-LED_DAYS);
            const hi = Math.max(...w), lo = Math.min(...w);
            const first = w[0], last = w[w.length - 1];
            return {{
                turnover: s.turnover,
                amplitude: lo ? roundToTwo((hi - lo) / lo * 100) : undefined,
                trend20: first ? roundToTwo((last - first) / first * 100) : undefined
            }};
        }}

        // 排序狀態
        let sortKey = 'rank', sortAsc = true;
        function sortNews(key) {{
            if (sortKey === key) sortAsc = !sortAsc;
            else {{ sortKey = key; sortAsc = (key === 'rank'); }}
            renderNewsTable();
        }}

        function renderNewsTable() {{
            // 清空舊的展開圖表實例以防記憶體殘留及重建失敗
            for (const rid in expandedCharts) {{
                if (expandedCharts[rid]) {{
                    try {{ expandedCharts[rid].destroy(); }} catch(e){{}}
                }}
                delete expandedCharts[rid];
            }}
            const tbody = document.getElementById('newsTableBody');
            // 先組出每列所需的資料與指標
            const rows = newsData.map(item => {{
                // item.name 是「台積電 (TSMC)」，stockData 的 key 是「台積電」，直接查會永遠落空
                // （同步後這張表因此不會更新），改用 ticker 反查。
                const firstTicker = String(item.ticker || '').split('/')[0].trim();
                const key = Object.keys(stockData).find(k => stockData[k].symbol === firstTicker);
                const s = (key && stockData[key]) || {{}};
                const m = metricsOf(s);
                return {{
                    item, key, s,
                    change: s.change !== undefined ? s.change : item.trend_pct,
                    price:  s.latest !== undefined ? s.latest : item.price,
                    turnover: m.turnover, amplitude: m.amplitude, trend20: m.trend20
                }};
            }});

            // 排序：rank 由小到大，其餘預設由大到小；undefined 一律排最後
            rows.sort((a, b) => {{
                const av = sortKey === 'rank' ? a.item.rank : a[sortKey];
                const bv = sortKey === 'rank' ? b.item.rank : b[sortKey];
                if (av === undefined || av === null) return 1;
                if (bv === undefined || bv === null) return -1;
                return sortAsc ? av - bv : bv - av;
            }});

            // 排序列的 active 狀態
            document.querySelectorAll('#sortBar .sort-btn').forEach(b => {{
                const on = b.dataset.key === sortKey;
                b.classList.toggle('active', on);
                const base = b.dataset.label || (b.dataset.label = b.textContent.trim());
                b.textContent = on ? `${{base}} ${{sortAsc ? '▲' : '▼'}}` : base;
            }});

            const pct = v => (v === undefined || v === null) ? '—'
                : `${{v >= 0 ? '' : ''}}${{v}}%`;

            tbody.innerHTML = rows.map((r, idx) => {{
                const {{ item, key, s }} = r;
                const isPositive = r.change >= 0;
                const unlisted = !(r.price > 0);
                const priceDisplay = unlisted ? '未上市' : `$${{r.price}}`;
                const changeDisplay = unlisted ? '' : `${{isPositive ? '+' : ''}}${{r.change}}%`;
                const shortName = item.name
                    .replace(/\s*\([^)]*\)/g, '')
                    .replace(/\s*([\/&])\s*/g, ' $1 ')
                    .replace(/\s+/g, ' ').trim();
                const rid = `row${{idx}}`;

                return `
                    <tr class="hover:bg-slate-700/25 transition cursor-pointer" onclick="toggleNewsRow('${{rid}}','${{key || ''}}')">
                        <td class="py-2 px-2 sm:px-3 text-center">
                            <span class="inline-flex items-center justify-center w-5 h-5 sm:w-6 sm:h-6 rounded-md text-[11px] sm:text-xs font-bold ${{item.rank <= 3 ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' : 'bg-slate-800 text-slate-400'}}">
                                ${{item.rank}}
                            </span>
                        </td>
                        <td class="py-2 px-2 sm:px-3">
                            <div class="flex items-baseline gap-1.5 whitespace-nowrap">
                                <span class="font-semibold text-white text-xs sm:text-sm">${{shortName}}</span>
                                <span class="text-[10px] sm:text-[11px] text-slate-500 font-mono">${{item.ticker}}</span>
                            </div>
                            <div class="mt-0.5 text-[10px] sm:text-[11px] text-slate-400 truncate max-w-[12rem] sm:max-w-none">
                                <span class="text-slate-300">${{item.badge}}</span>
                                <span class="text-slate-600 mx-1">·</span>${{item.category}}
                                <span class="text-slate-600 mx-1">·</span><span class="text-[#76B900] font-semibold">${{item.citations}}</span>
                            </div>
                        </td>
                        <td class="py-2 px-2 text-right text-[11px] text-slate-300 hidden sm:table-cell">${{pct(r.turnover)}}</td>
                        <td class="py-2 px-2 text-right text-[11px] text-slate-300 hidden md:table-cell">${{pct(r.amplitude)}}</td>
                        <td class="py-2 px-2 text-right text-[11px] font-semibold hidden md:table-cell ${{r.trend20 >= 0 ? 'text-emerald-400' : 'text-rose-400'}}">${{pct(r.trend20)}}</td>
                        <td class="py-2 px-2 sm:px-3 text-right whitespace-nowrap">
                            <div class="font-semibold text-slate-100 text-xs sm:text-sm">${{priceDisplay}}</div>
                            <div class="mt-0.5 text-[10px] sm:text-[11px] font-semibold ${{isPositive ? 'text-emerald-400' : 'text-rose-400'}}">${{changeDisplay}}</div>
                        </td>
                        <td class="py-2 px-1 text-center text-slate-500 text-[10px]" id="${{rid}}-caret">▼</td>
                    </tr>
                    <tr id="${{rid}}" class="hidden bg-slate-900/60">
                        <td colspan="7" class="px-3 sm:px-5 py-4">
                            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div>
                                    <div class="text-[11px] text-slate-500 mb-1">新聞重點摘要</div>
                                    <p class="text-xs text-slate-300 leading-relaxed">${{item.news_summary}}</p>
                                    <p class="text-[11px] text-slate-500 mt-2 font-mono">角色：${{item.role}}</p>
                                    <div class="mt-3">
                                        <div class="text-[11px] text-slate-500 mb-1">近 20 日買賣點訊號
                                            <span class="text-emerald-400 ml-2">■</span> 買
                                            <span class="text-rose-400 ml-1">■</span> 賣
                                        </div>
                                        ${{buildLedBar(s) || '<div class="text-[11px] text-slate-600">資料不足</div>'}}
                                    </div>
                                </div>
                                <div>
                                    <div class="text-[11px] text-slate-500 mb-1 flex justify-between">
                                        <span>近 2 個月走勢</span>
                                        <span class="text-[#76B900] font-mono font-semibold" id="${{rid}}-chart-date"></span>
                                    </div>
                                    <!-- 與其他走勢圖一致：canvas 必須包在固定高度容器，
                                         否則 maintainAspectRatio:false 會把圖表撐到滿版 -->
                                    <div class="h-32 w-full">
                                        <canvas id="${{rid}}-chart"></canvas>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }}).join('');
        }}

        // 點列展開／收合；展開時才建立走勢圖，避免一次畫 15 張
        const expandedCharts = {{}};
        function toggleNewsRow(rid, key) {{
            const tr = document.getElementById(rid);
            const caret = document.getElementById(rid + '-caret');
            if (!tr) return;
            const willShow = tr.classList.contains('hidden');
            tr.classList.toggle('hidden');
            if (caret) caret.textContent = willShow ? '▲' : '▼';
            if (!willShow || !key || !stockData[key]) return;

            const cv = document.getElementById(rid + '-chart');
            if (!cv || expandedCharts[rid]) return;
            const s = stockData[key];

            // 顯示最新日期與收盤價於圖表上方
            const dateEl = document.getElementById(rid + '-chart-date');
            if (dateEl && s.dates && s.dates.length) {{
                dateEl.textContent = `${{s.dates[s.dates.length - 1]}} 收盤: $${{s.latest}}`;
            }}

            expandedCharts[rid] = new Chart(cv.getContext('2d'), {{
                type: 'line',
                data: {{
                    labels: s.dates,
                    datasets: [{{
                        label: key, data: s.prices,
                        borderColor: '#76B900', backgroundColor: 'rgba(118,185,0,.12)',
                        borderWidth: 2, pointRadius: 0, tension: .3, fill: true
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ color: '#64748b', font: {{ size: 9 }}, maxTicksLimit: 6 }}, grid: {{ display: false }} }},
                        y: {{ ticks: {{ color: '#64748b', font: {{ size: 9 }} }}, grid: {{ color: 'rgba(51,65,85,.4)' }} }}
                    }}
                }}
            }});
        }}

        // 使用者尚未點選類別／搜尋前不渲染任何卡片，避免一進頁面就塞滿 45 張
        let gridVisible = false;
        function renderStockCards(cat, filterText) {{
            const grid = document.getElementById('stockGrid');
            const hint = document.getElementById('stockHint');
            if (!gridVisible) return;                       // 同步時不會偷偷把卡片叫出來
            if (hint) hint.classList.add('hidden');
            grid.innerHTML = '';

            let filteredKeys = Object.keys(stockData);

            if (cat !== 'ALL') {{
                filteredKeys = filteredKeys.filter(key => {{
                    const s = stockData[key];
                    return getStockCategory(key) === cat;
                }});
            }}

            if (filterText) {{
                const lower = filterText.toLowerCase();
                filteredKeys = filteredKeys.filter(key => {{
                    const s = stockData[key];
                    return key.toLowerCase().includes(lower) || s.symbol.toLowerCase().includes(lower);
                }});
            }}

            if (filteredKeys.length === 0) {{
                grid.innerHTML = `<div class="col-span-full text-center py-12 text-slate-400">沒有符合搜尋的股票數據</div>`;
                return;
            }}

            filteredKeys.forEach(name => {{
                const s = stockData[name];
                const isPositive = s.change >= 0;
                const cardId = `chart_${{s.symbol.replace('.', '_')}}`;

                const cardHtml = `
                    <div class="bg-slate-800/80 border border-slate-700/80 rounded-2xl p-5 hover:border-[#76B900]/50 transition space-y-3 shadow-lg">
                        <div class="flex justify-between items-start">
                            <div>
                                <h3 class="text-lg font-bold text-white flex items-center gap-2">
                                    ${{name}}
                                </h3>
                                <div class="text-xs font-mono text-slate-400">${{s.symbol}}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-xl font-extrabold text-white">$${{s.latest}}</div>
                                <span class="inline-block text-xs font-bold px-2 py-0.5 rounded ${{isPositive ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}}">
                                    2M: ${{isPositive ? '+' : ''}}${{s.change}}%
                                </span>
                            </div>
                        </div>

                        <div class="flex justify-between text-xs text-slate-400 pt-1 border-t border-slate-700/50">
                            <span>最高: <strong class="text-slate-200">${{s.high}}</strong></span>
                            <span>最低: <strong class="text-slate-200">${{s.low}}</strong></span>
                            <span>起點: <strong class="text-slate-200">${{s.start}}</strong></span>
                        </div>

                        <div class="h-32 w-full pt-2">
                            <canvas id="${{cardId}}"></canvas>
                        </div>
                    </div>
                `;

                grid.insertAdjacentHTML('beforeend', cardHtml);

                setTimeout(() => {{
                    const el = document.getElementById(cardId);
                    if (!el) return;
                    const ctx = el.getContext('2d');
                    new Chart(ctx, {{
                        type: 'line',
                        data: {{
                            labels: s.dates,
                            datasets: [{{
                                data: s.prices,
                                borderColor: isPositive ? '#10b981' : '#f43f5e',
                                backgroundColor: isPositive ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                pointRadius: 0,
                                tension: 0.2
                            }}]
                        }},
                        options: {{
                            responsive: fontResponsiveness(),
                            maintainAspectRatio: false,
                            plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: true }} }},
                            scales: {{
                                x: {{ display: false }},
                                y: {{ display: false }}
                            }}
                        }}
                    }});
                }}, 30);
            }});
        }}

        function fontResponsiveness() {{ return true; }}

        function getStockCategory(name) {{
            const map = {{
                '台積電': '晶片製造與先進封裝', '日月光投控': '晶片製造與先進封裝', '聯電': '晶片製造與先進封裝', '京元電': '晶片製造與先進封裝', '華邦電': '晶片製造與先進封裝',
                '鴻海': 'AI 伺服器與系統代工', '廣達': 'AI 伺服器與系統代工', '緯創': 'AI 伺服器與系統代工', '緯穎': 'AI 伺服器與系統代工', '英業達': 'AI 伺服器與系統代工', '和碩': 'AI 伺服器與系統代工', '仁寶': 'AI 伺服器與系統代工', '美超微': 'AI 伺服器與系統代工',
                '索羅門': '機器人與邊緣 AI', '研華': '機器人與邊緣 AI', '達明': '機器人與邊緣 AI', '凌華': '機器人與邊緣 AI', '立端': '機器人與邊緣 AI', '新漢': '機器人與邊緣 AI', '研揚': '機器人與邊緣 AI', '宸曜': '機器人與邊緣 AI', '艾訊': '機器人與邊緣 AI', '廣運': '機器人與邊緣 AI', '飛捷': '機器人與邊緣 AI', '聰泰': '機器人與邊緣 AI', '醫揚': '機器人與邊緣 AI',
                '台達電': '電源、散熱與關鍵零組件', '勤誠': '電源、散熱與關鍵零組件', '光寶科': '電源、散熱與關鍵零組件', '欣興': '電源、散熱與關鍵零組件', '迎廣': '電源、散熱與關鍵零組件', '德律': '電源、散熱與關鍵零組件', '曜越': '電源、散熱與關鍵零組件', '元山': '電源、散熱與關鍵零組件', '益登': '電源、散熱與關鍵零組件', '弘憶股': '電源、散熱與關鍵零組件', '中強光電': '電源、散熱與關鍵零組件',
                '技嘉': '顯卡、板卡與消費電子', '微星': '顯卡、板卡與消費電子', '華擎': '顯卡、板卡與消費電子', '麗臺': '顯卡、板卡與消費電子', '圓剛': '顯卡、板卡與消費電子', '神達': '顯卡、板卡與消費電子', '宏碁': '顯卡、板卡與消費電子', '巨大': '顯卡、板卡與消費電子', '慧友': '顯卡、板卡與消費電子'
            }};
            return map[name] || '其他概念股';
        }}

        function renderUnlistedPartners() {{
            const container = document.getElementById('unlistedContainer');
            
            const categories = [
                'AI 伺服器與系統代工',
                '晶片製造與先進封裝',
                '機器人與邊緣 AI',
                '電源、散熱與關鍵零組件',
                '顯卡、板卡與消費電子',
                '軟體、新創與 AI 生態系'
            ];

            container.innerHTML = categories.map(cat => {{
                const items = unlistedData.filter(x => x.category === cat);
                if (items.length === 0) return '';

                return `
                    <div class="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 space-y-3 shadow-lg">
                        <h3 class="text-md font-bold text-[#76B900] flex items-center gap-2 border-b border-slate-700 pb-2">
                            <i class="fa-solid fa-layer-group"></i> ${{cat}} (${{items.length}} 家)
                        </h3>
                        <div class="grid grid-cols-1 gap-2.5 max-h-80 overflow-y-auto custom-scrollbar pr-1">
                            ${{items.map(item => `
                                <div class="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex justify-between items-center gap-2">
                                    <div>
                                        <div class="text-sm font-semibold text-white">${{item.name}}</div>
                                        <div class="text-xs text-slate-400">${{item.role}}</div>
                                    </div>
                                    <span class="text-[10px] bg-slate-800 text-slate-300 px-2 py-1 rounded border border-slate-700 font-mono">
                                        ${{item.parent}}
                                    </span>
                                </div>
                            `).join('')}}
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function filterStocks(cat) {{
            currentCategory = cat;
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active', 'bg-[#76B900]', 'text-slate-950', 'font-bold');
                btn.classList.add('bg-slate-800', 'text-slate-300');
            }});

            event.target.classList.add('active', 'bg-[#76B900]', 'text-slate-950', 'font-bold');
            event.target.classList.remove('bg-slate-800', 'text-slate-300');

            gridVisible = true;      // 使用者主動點了類別，才開始顯示卡片
            const searchVal = document.getElementById('stockSearch').value;
            renderStockCards(cat, searchVal);
        }}

        function initComparisonChart(stockNames) {{
            const ctx = document.getElementById('multiStockChart').getContext('2d');
            const colors = ['#76B900', '#3b82f6', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6'];

            const labels = stockData[stockNames[0]] ? stockData[stockNames[0]].dates : [];

            const datasets = stockNames.map((name, idx) => {{
                const s = stockData[name];
                if (!s) return null;
                return {{
                    label: name,
                    data: s.prices,
                    borderColor: colors[idx % colors.length],
                    backgroundColor: colors[idx % colors.length],
                    borderWidth: 2.5,
                    pointRadius: 0,
                    tension: 0.2
                }};
            }}).filter(Boolean);

            multiChartInstance = new Chart(ctx, {{
                type: 'line',
                data: {{ labels, datasets }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'top',
                            labels: {{ color: '#cbd5e1', font: {{ size: 12 }} }}
                        }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false
                        }}
                    }},
                    scales: {{
                        x: {{
                            grid: {{ color: 'rgba(51, 65, 85, 0.4)' }},
                            ticks: {{ color: '#94a3b8' }}
                        }},
                        y: {{
                            grid: {{ color: 'rgba(51, 65, 85, 0.4)' }},
                            ticks: {{ color: '#94a3b8' }}
                        }}
                    }}
                }}
            }});
        }}

        function updateComparisonChart(stockNames) {{
            if (!multiChartInstance) return;
            currentChartKeys = stockNames;   // 記住目前選取，同步後才知道要重畫哪幾檔
            const colors = ['#76B900', '#3b82f6', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6'];
            const labels = stockData[stockNames[0]] ? stockData[stockNames[0]].dates : [];

            const datasets = stockNames.map((name, idx) => {{
                const s = stockData[name];
                if (!s) return null;
                return {{
                    label: name,
                    data: s.prices,
                    borderColor: colors[idx % colors.length],
                    backgroundColor: colors[idx % colors.length],
                    borderWidth: 2.5,
                    pointRadius: 0,
                    tension: 0.2
                }};
            }}).filter(Boolean);

            multiChartInstance.data.labels = labels;
            multiChartInstance.data.datasets = datasets;
            multiChartInstance.update();
        }}
    </script>
</body>
</html>
"""

    with open("nvidia_taiwan_partners_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("🎉 成功寫入 nvidia_taiwan_partners_report.html！")

def main():
    # 改為「預設就抓」。原本要手動加 --fetch 才更新，忘了加就會拿舊快取重產一份看似很新的報告。
    if "--no-fetch" not in sys.argv:
        fetch_stock_data()
    else:
        print("⏭️  已指定 --no-fetch，使用既有 stock_data.json")

    build_report_html()
    print("\n📌 提醒：本機檔案已更新，但線上版(GCS)不會自動同步，記得上傳：")
    print("   gsutil -h 'Cache-Control:no-cache, max-age=0' cp nvidia_taiwan_partners_report.html gs://portfolio-kas-use-pi/")

if __name__ == "__main__":
    main()
