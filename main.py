import akshare as ak
import pandas as pd
import numpy as np
import datetime
import time
import ssl
import requests
import urllib3
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# SSL patch
urllib3.disable_warnings()
ssl._create_default_https_context = ssl._create_unverified_context
_orig = requests.Session.request
def _patched(self, method, url, **kwargs):
    kwargs.setdefault('verify', False)
    return _orig(self, method, url, **kwargs)
requests.Session.request = _patched

# ==========================================
# 設定區
# ==========================================
SHEET_NAME     = "A06-1_陸股回測績效表(建立中"
WORKSHEET_NAME = "產業乖離數據"
CREDS_FILE     = "creds.json"
N_BARS         = 30
MAX_RETRY      = 3
SLEEP_SEC      = 0.5

INDUSTRIES = {
    "農產品加工":   "801012", "飼料":         "801014",
    "漁業":         "801015", "種植業":       "801016",
    "養殖業":       "801017", "動物保健":     "801018",
    "化學纖維":     "801032", "化學原料":     "801033",
    "化學製品":     "801034", "塑料":         "801036",
    "橡膠":         "801037", "農化製品":     "801038",
    "非金屬材料":   "801039", "冶鋼原料":     "801043",
    "普鋼":         "801044", "特鋼":         "801045",
    "金屬新材料":   "801051", "貴金屬":       "801053",
    "小金屬":       "801054", "工業金屬":     "801055",
    "能源金屬":     "801056", "通用設備":     "801072",
    "專用設備":     "801074", "軌交設備":     "801076",
    "工程機械":     "801077", "自動化設備":   "801078",
    "半導體":       "801081", "其他電子":     "801082",
    "元件":         "801083", "光學光電子":   "801084",
    "消費電子":     "801085", "電子化學品":   "801086",
    "汽車服務":     "801092", "汽車零部件":   "801093",
    "乘用車":       "801095", "商用車":       "801096",
    "計算機設備":   "801101", "通信設備":     "801102",
    "IT服務":       "801103", "軟件開發":     "801104",
    "白色家電":     "801111", "黑色家電":     "801112",
    "小家電":       "801113", "廚衛電器":     "801114",
    "照明設備":     "801115", "家電零部件":   "801116",
    "食品加工":     "801124", "白酒":         "801125",
    "非白酒":       "801126", "飲料乳品":     "801127",
    "休閒食品":     "801128", "調味發酵品":   "801129",
    "紡織製造":     "801131", "服裝家紡":     "801132",
    "飾品":         "801133", "包裝印刷":     "801141",
    "家居用品":     "801142", "造紙":         "801143",
    "文娛用品":     "801145", "化學製藥":     "801151",
    "生物製品":     "801152", "醫療器械":     "801153",
    "醫藥商業":     "801154", "中藥":         "801155",
    "醫療服務":     "801156", "電力":         "801161",
    "燃氣":         "801163", "物流":         "801178",
    "鐵路公路":     "801179", "房地產開發":   "801181",
    "房地產服務":   "801183", "多元金融":     "801191",
    "證券":         "801193", "保險":         "801194",
    "貿易":         "801202", "一般零售":     "801203",
    "專業連鎖":     "801204", "互聯網電商":   "801206",
    "專業服務":     "801218", "酒店餐飲":     "801219",
    "通信服務":     "801223", "綜合":         "801231",
    "水泥":         "801711", "玻璃玻纖":     "801712",
    "裝修建材":     "801713", "房屋建設":     "801721",
    "裝修裝飾":     "801722", "基礎建設":     "801723",
    "專業工程":     "801724", "工程諮詢服務": "801726",
    "電機":         "801731", "其他電源設備": "801733",
    "光伏設備":     "801735", "風電設備":     "801736",
    "電池":         "801737", "電網設備":     "801738",
    "航天裝備":     "801741", "航空裝備":     "801742",
    "地面兵裝":     "801743", "航海裝備":     "801744",
    "軍工電子":     "801745", "遊戲":         "801764",
    "廣告營銷":     "801765", "影視院線":     "801766",
    "數字媒體":     "801767", "出版":         "801769",
    "銀行(國有大型)":"801782","銀行(股份制)": "801783",
    "銀行(城商行)": "801784", "銀行(農商行)": "801785",
    "摩托車及其他": "801881", "煤炭開採":     "801951",
    "焦炭":         "801952", "油服工程":     "801962",
    "煉化及貿易":   "801963", "環境治理":     "801971",
    "環保設備":     "801972", "個護用品":     "801981",
    "化妝品":       "801982", "航空機場":     "801991",
    "航運港口":     "801992", "旅遊及景區":   "801993",
    "教育":         "801994", "電視廣播":     "801995",
}

# ==========================================
# 新浪即時價（如果 GitHub IP 能訪問）
# ==========================================
def get_today_price_sina(code):
    try:
        url = f"https://hq.sinajs.cn/list=sw_{code}"
        headers = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, headers=headers, verify=False, timeout=5)
        r.encoding = 'gbk'
        content = r.text
        if '="' not in content or len(content) < 20:
            return None, None
        data = content.split('="')[1].rstrip('";').split(',')
        if len(data) < 32 or data[3] == '':
            return None, None
        price = float(data[3])
        date  = data[30][:10]
        return price, date
    except:
        return None, None

# ==========================================
# 抓取乖離
# ==========================================
def fetch_bias(name, code):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            # ① 歷史日線
            df = ak.index_hist_sw(symbol=code, period="day")
            if df is None or df.empty or len(df) < 10:
                return None

            close     = df["收盘"].astype(float).tolist()
            last_date = pd.to_datetime(df["日期"].iloc[-1]).strftime("%Y-%m-%d")

            # ② 嘗試新浪即時價
            today_price, today_date = get_today_price_sina(code)
            if today_price is not None and today_date != last_date:
                close.append(today_price)
                last_date = today_date
                print(f"(+即時 {today_price})", end=" ")
            else:
                print(f"(歷史 {last_date})", end=" ")

            # ③ 計算乖離
            close_s = pd.Series(close)
            ma3   = close_s.rolling(3).mean()
            ma9   = close_s.rolling(9).mean()
            bias3 = ((close_s - ma3) / ma3 * 100)
            bias9 = ((close_s - ma9) / ma9 * 100)
            d_bias = (bias9 - bias3).replace([np.inf, -np.inf], np.nan).fillna(0)
            d_bias = d_bias.tail(N_BARS).round(2).tolist()

            if len(d_bias) < N_BARS:
                d_bias = [0.0] * (N_BARS - len(d_bias)) + d_bias

            return [name, last_date] + d_bias

        except Exception as e:
            if attempt < MAX_RETRY:
                print(f"  ⚠️ {name} 第{attempt}次失敗，2秒後重試...", end=" ")
                time.sleep(2)
            else:
                print(f"  ❌ {name}({code}) 失敗: {e}")
                return None

# ==========================================
# 上傳 Google Sheets
# ==========================================
def upload_to_sheets(results, header):
    print(f"\n☁️ 上傳至 Google Sheets：{WORKSHEET_NAME}...")
    try:
        scope  = ["https://spreadsheets.google.com/feeds",
                   "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
        client = gspread.authorize(creds)
        sh     = client.open(SHEET_NAME)

        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows="200", cols="50")

        ws.clear()
        upload = [header] + results
        clean  = [[str(v) if isinstance(v, float) and (v != v) else v for v in row]
                  for row in upload]
        ws.update(values=clean, range_name="A1", value_input_option="USER_ENTERED")
        print(f"🎉 上傳成功！共 {len(results)} 個產業")
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")

# ==========================================
# 主程式
# ==========================================
def main():
    print(f"📊 共 {len(INDUSTRIES)} 個產業，開始抓取乖離數據...")
    print(f"🕐 執行時間：{datetime.datetime.utcnow()} UTC")

    results = []
    items   = list(INDUSTRIES.items())

    for i, (name, code) in enumerate(items):
        print(f"   [{i+1}/{len(items)}] {name}", end=" ")
        res = fetch_bias(name, code)
        if res:
            results.append(res)
            print("✅")
        else:
            print("❌ 跳過")
        time.sleep(SLEEP_SEC)

    print(f"\n✅ 成功抓取 {len(results)} / {len(items)} 個產業")

    if not results:
        print("❌ 沒有任何資料可輸出")
        return

    header = ["產業", "數據最後日期"] + [f"日D-{j}" for j in range(N_BARS, 0, -1)]
    upload_to_sheets(results, header)

if __name__ == "__main__":
    main()
