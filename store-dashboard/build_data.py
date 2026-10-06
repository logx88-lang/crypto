#!/usr/bin/env python3
"""가게 매입·매출 엑셀 파일들을 읽어 대시보드 HTML을 만든다.

사용법:
    python3 build_data.py <엑셀폴더> [--password <암호>] [--out dist/dashboard.html]

폴더 안의 파일 종류는 내용으로 자동 판별한다.
  - 배달의민족 정산명세서 (암호 걸린 파일은 --password 로 해제)
  - 쿠팡이츠 부가세 신고자료 (merchant_sales_report)
  - 요기요 주문내역
  - 세무사 매입매출장 (매출/매입 시트)
  - 신용카드 이용내역 (카드사 두 가지 양식)
  - 사업자 통장 거래내역 (입금/출금/잔액 열이 있는 양식)
"""
import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- 공통

def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).replace(",", "").replace("원", "").strip()
    if s in ("", "-", "nan", "None"):
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def ymd(v):
    """여러 날짜 표기를 YYYY-MM-DD 로."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    m = re.match(r"(\d{4})[.\-/]?\s?(\d{1,2})[.\-/]?\s?(\d{1,2})", s)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def open_workbook_bytes(path, password):
    raw = path.read_bytes()
    if raw[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):  # OLE = 암호화된 xlsx
        try:
            import msoffcrypto
        except ImportError:
            sys.exit("암호 걸린 파일이 있습니다. `pip install msoffcrypto-tool` 후 다시 실행하세요.")
        if not password:
            sys.exit(f"{path.name}: 암호가 걸려 있습니다. --password 를 지정하세요.")
        office = msoffcrypto.OfficeFile(io.BytesIO(raw))
        office.load_key(password=password)
        out = io.BytesIO()
        office.decrypt(out)
        return out.getvalue()
    return raw


def sheets_as_frames(data):
    return pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object)


# ---------------------------------------------------------------- 판별

def detect(frames):
    names = list(frames)
    first = frames[names[0]]
    head = " ".join(str(x) for x in first.head(6).values.ravel() if x is not None)
    if "상세" in frames and "정산 상세내역" in str(frames["상세"].iloc[0, 0]):
        return "baemin"
    if "매출인식 시점" in head and "Store ID" in head:
        return "coupang"
    if "상호명" in head and "주문번호" in head and "주문중개이용료" in " ".join(
            str(x) for x in first.head(2).values.ravel()):
        return "yogiyo"
    if "매출" in frames and "매입" in frames:
        return "ledger"
    if "매출일자" in head and "가맹점명" in head and "승인번호" in head:
        return "card_a"
    if "국내이용내역" in " ".join(names):
        return "card_b"
    for df in frames.values():
        if bank_header_row(df) is not None:
            return "bank"
    return None


# ---------------------------------------------------------------- 배민

BAEMIN_GROUPS = {
    "orderNow": ["바로결제주문금액"],
    "orderMeet": ["만나서결제주문금액"],
    "refund": ["부분환불금액"],
    "commission": ["배민1중개이용료", "알뜰배달 중개이용료", "가게배달중개이용료", "픽업중개이용료"],
    "tipNow": ["바로결제배달팁"],
    "tipMeet": ["만나서결제배달팁"],
    "club": ["배민클럽(한집배달) 배달팁 할인", "배민클럽(한집배달) 배달팁 할인 지원",
             "배민클럽(알뜰배달) 배달팁 할인", "배민클럽(알뜰배달) 배달팁 할인 지원",
             "배민 부담 가게배달팁"],
    "delivery": ["배민1 한집배달 배달비", "알뜰배달 배달비"],
    "payFee": ["기본수수료(정률)", "우대수수료"],
    "meetCollected": ["배민 만나서결제주문금액", "배민 만나서결제배달팁"],
    "adjust": ["보정금액"],
    "vat": ["(E) 부가세"],
    "ad": ["(F) 우리가게클릭"],
    "order": ["(G) 배민오더"],
    "payout": ["(H) 입금금액"],
}


def parse_baemin(frames):
    df = frames["상세"]
    header = [str(x).strip() if x is not None else "" for x in df.iloc[4]]
    rows = []
    for _, r in df.iloc[5:].iterrows():
        paid = ymd(r.iloc[0])
        if not paid:
            continue
        vals = dict(zip(header, r.tolist()))
        rec = {"paid": paid, "date": ymd(vals.get("정산대상기간")), "type": str(vals.get("주문유형/기타") or ""),
               "status": str(vals.get("상태") or "")}
        for key, cols in BAEMIN_GROUPS.items():
            rec[key] = sum(num(vals.get(c)) for c in cols)
        rows.append(rec)
    return rows


# ---------------------------------------------------------------- 쿠팡이츠

def parse_coupang(frames):
    out = []
    for df in frames.values():
        header = [str(x).strip() for x in df.iloc[0]]
        if "매출인식 시점" not in header:
            continue
        for _, r in df.iloc[1:].iterrows():
            v = dict(zip(header, r.tolist()))
            t = v.get("매출인식 시점")
            if t is None or (isinstance(t, float) and pd.isna(t)):
                continue
            t = pd.to_datetime(t)
            out.append([
                str(v.get("주문번호")), t.strftime("%Y-%m-%d %H:%M"),
                num(v.get("신용카드(판매)")), num(v.get("현금(판매)")), num(v.get("기타(판매)")),
                num(v.get("상점부담할인(판매)")) + num(v.get("즉시할인(판매)")),
                num(v.get("신용카드(환불)")), num(v.get("현금(환불)")), num(v.get("기타(환불)")),
            ])
    return out


# ---------------------------------------------------------------- 요기요

def parse_yogiyo(frames):
    df = next(iter(frames.values()))
    top = [str(x).strip() if x is not None and not (isinstance(x, float) and pd.isna(x)) else "" for x in df.iloc[0]]
    sub = [str(x).strip() if x is not None and not (isinstance(x, float) and pd.isna(x)) else "" for x in df.iloc[1]]
    names = [s or t for t, s in zip(top, sub)]

    def col(*keys):
        for i, n in enumerate(names):
            if all(k in n for k in keys):
                return i
        return None

    ix = {
        "kind": col("주문구분"), "contract": col("계약유형"), "dt": col("주문일시"), "refund": col("환불일시"),
        "amount": col("주문금액"), "deliveryFee": col("배달료"),
        "onsite": col("현장결제"), "online": col("온라인결제"),
    }
    cost_cols = [i for i, n in enumerate(names) if i > (ix["online"] or 0) and n and "이용료율" not in n
                 and not n.startswith("기타") and "요기요부담" not in n and "일회용컵" not in n]
    out = []
    for _, r in df.iloc[2:].iterrows():
        vals = r.tolist()
        dt = vals[ix["dt"]]
        if dt is None or (isinstance(dt, float) and pd.isna(dt)):
            continue
        costs = {names[i]: num(vals[i]) for i in cost_cols if num(vals[i])}
        out.append({
            "dt": str(dt)[:16], "kind": str(vals[ix["kind"]]), "contract": str(vals[ix["contract"]]),
            "amount": num(vals[ix["amount"]]), "deliveryFee": num(vals[ix["deliveryFee"]]),
            "onsite": num(vals[ix["onsite"]]), "online": num(vals[ix["online"]]),
            "refunded": bool(vals[ix["refund"]]) and not (isinstance(vals[ix["refund"]], float) and pd.isna(vals[ix["refund"]])),
            "costs": costs,
        })
    return out


# ---------------------------------------------------------------- 세무사 매입매출장

def parse_ledger(frames):
    def table(df):
        header = [str(x).replace("\n", "").strip() if x is not None else "" for x in df.iloc[0]]
        seen = {}
        for i, h in enumerate(header):  # Code 열이 여러 개라 중복 이름 처리
            if h in seen:
                header[i] = f"{h}.{seen[h]}"
            seen[h] = seen.get(h, 0) + 1
        body = df.iloc[1:].copy()
        body.columns = header
        return body[body["전표일자"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")]

    sales = []
    for _, r in table(frames["매출"]).iterrows():
        sales.append({"date": ymd(r["전표일자"]), "partner": str(r["거래처"]).strip(), "item": str(r["품명"] or "").strip(),
                      "supply": num(r["공급가액"]), "vat": num(r["부가세"]), "total": num(r["합계"]),
                      "type": str(r["매입/매출유형"] or "")})
    purchases = []
    for _, r in table(frames["매입"]).iterrows():
        item = r["품명"]
        item = "" if item is None or (isinstance(item, float) and pd.isna(item)) else str(item).strip()
        card = r.get("카드사명")
        card = "" if card is None or (isinstance(card, float) and pd.isna(card)) else str(card)
        purchases.append({"date": ymd(r["전표일자"]), "vendor": re.sub(r"\s+", " ", str(r["거래처"]).strip()),
                          "bizno": str(r["사업자(주민)번호"] or "").strip(), "item": item,
                          "supply": num(r["공급가액"]), "vat": num(r["부가세"]), "total": num(r["합계"]),
                          "type": str(r["매입/매출유형"] or ""), "card": card, "src": "장부"})
    return sales, purchases


# ---------------------------------------------------------------- 카드

def parse_card_a(frames):
    df = next(iter(frames.values()))
    header = [str(x).strip() for x in df.iloc[0]]
    out = []
    for _, r in df.iloc[1:].iterrows():
        v = dict(zip(header, r.tolist()))
        if not ymd(v.get("매출일자")):
            continue
        out.append({"date": ymd(v["매출일자"]), "time": "", "vendor": str(v["가맹점명"]).strip(),
                    "amount": num(v["매출금액(원)"]), "vat": num(v.get("부가세(원)")),
                    "inst": num(v.get("할부개월수")), "approval": str(v["승인번호"]).strip(),
                    "card": str(v.get("카드번호") or "")[-4:], "bizno": str(v.get("사업자등록번호") or ""),
                    "cancel": False})
    return out


def parse_card_b(frames):
    key = next(k for k in frames if "국내이용내역" in k)
    df = frames[key]
    header = [str(x).strip() for x in df.iloc[0]]
    out = []
    for _, r in df.iloc[1:].iterrows():
        v = dict(zip(header, r.tolist()))
        if not ymd(v.get("승인일자")):
            continue
        out.append({"date": ymd(v["승인일자"]), "time": str(v.get("승인시각") or "")[:5],
                    "vendor": str(v["가맹점명"]).strip(), "amount": num(v["승인금액(원)"]), "vat": 0,
                    "inst": num(v.get("할부개월")), "approval": str(v["승인번호"]).strip(),
                    "card": str(v.get("카드번호") or "")[-4:], "bizno": "",
                    "cancel": str(v.get("취소여부") or "-").strip() not in ("-", "", "nan")})
    return out


# ---------------------------------------------------------------- 통장

BANK_DATE = ("거래일시", "거래일자", "거래일", "일자", "날짜")
BANK_IN = ("입금", "맡기신", "입금액")
BANK_OUT = ("출금", "찾으신", "지급", "출금액")
BANK_DESC = ("적요", "내용", "기재내용", "거래내용", "받는분", "보낸분", "메모", "거래점", "의뢰인", "수취인")


def bank_header_row(df):
    for i in range(min(25, len(df))):
        cells = [str(x) for x in df.iloc[i] if x is not None and not (isinstance(x, float) and pd.isna(x))]
        joined = " ".join(cells)
        if any(k in joined for k in BANK_DATE) and any(k in joined for k in BANK_IN) and any(
                k in joined for k in BANK_OUT) and "잔액" in joined:
            return i
    return None


def parse_bank(frames):
    out = []
    for df in frames.values():
        h = bank_header_row(df)
        if h is None:
            continue
        header = [str(x).strip() if x is not None else "" for x in df.iloc[h]]

        def find(keys, exclude=()):
            for i, c in enumerate(header):
                if any(k in c for k in keys) and not any(e in c for e in exclude):
                    return i
            return None

        di, ii, oi = find(BANK_DATE), find(BANK_IN), find(BANK_OUT)
        bi = find(("잔액",))
        desc_ix = [i for i, c in enumerate(header) if any(k in c for k in BANK_DESC)]
        for _, r in df.iloc[h + 1:].iterrows():
            vals = r.tolist()
            d = ymd(vals[di])
            if not d:
                continue
            inc, outv = num(vals[ii]), num(vals[oi])
            if not inc and not outv:
                continue
            desc = " ".join(str(vals[i]).strip() for i in desc_ix
                            if vals[i] is not None and not (isinstance(vals[i], float) and pd.isna(vals[i])))
            out.append({"date": d, "desc": desc, "in": inc, "out": outv, "balance": num(vals[bi]) if bi is not None else 0})
    return out


# ---------------------------------------------------------------- 메인

LABELS = {"baemin": "배달의민족 정산명세서", "coupang": "쿠팡이츠 부가세 신고자료", "yogiyo": "요기요 주문내역",
          "ledger": "세무사 매입매출장", "card_a": "신용카드 이용내역(매출일 기준)",
          "card_b": "신용카드 이용내역(승인일 기준)", "bank": "사업자 통장 거래내역"}


def dedupe(rows, key):
    seen, out = set(), []
    for r in rows:
        k = key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def build(folder, password):
    data = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "sources": [], "baemin": [], "coupang": [],
            "yogiyo": [], "ledgerSales": [], "purchases": [], "card": [], "bank": []}
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".xlsx", ".xls"))
    for p in files:
        try:
            frames = sheets_as_frames(open_workbook_bytes(p, password))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {p.name}: 읽기 실패 ({e})")
            continue
        kind = detect(frames)
        if kind is None:
            print(f"  ? {p.name}: 종류를 알 수 없어 건너뜀")
            continue
        if kind == "baemin":
            rows = parse_baemin(frames); data["baemin"] += rows
        elif kind == "coupang":
            rows = parse_coupang(frames); data["coupang"] += rows
        elif kind == "yogiyo":
            rows = parse_yogiyo(frames); data["yogiyo"] += rows
            name = next(iter(frames.values())).iloc[2, 0]
            if isinstance(name, str) and name.strip():
                data["storeName"] = name.strip()
        elif kind == "ledger":
            s, rows = parse_ledger(frames); data["ledgerSales"] += s; data["purchases"] += rows
        elif kind in ("card_a", "card_b"):
            rows = (parse_card_a if kind == "card_a" else parse_card_b)(frames); data["card"] += rows
        else:
            rows = parse_bank(frames); data["bank"] += rows
        data["sources"].append({"file": re.sub(r"^[0-9a-f]{8}-", "", p.name), "kind": kind, "label": LABELS[kind],
                                "rows": len(rows)})
        print(f"  - {p.name}: {LABELS[kind]} {len(rows)}건")

    data["baemin"] = dedupe(data["baemin"], lambda r: tuple(r.values()))
    data["coupang"] = dedupe(data["coupang"], lambda r: tuple(r))
    data["yogiyo"] = dedupe(data["yogiyo"], lambda r: (r["dt"], r["amount"], r["deliveryFee"]))
    # 같은 카드 내역이 두 양식으로 들어오면 승인번호로 합친다 (승인시각이 있는 쪽 우선, 부가세는 채워 넣음)
    merged = {}
    for c in sorted(data["card"], key=lambda c: c["time"] == ""):
        k = (c["approval"], c["amount"])
        if k in merged:
            merged[k]["vat"] = merged[k]["vat"] or c["vat"]
            merged[k]["bizno"] = merged[k]["bizno"] or c["bizno"]
        else:
            merged[k] = dict(c)
    data["card"] = sorted(merged.values(), key=lambda c: (c["date"], c["time"]))
    data["bank"] = dedupe(data["bank"], lambda r: (r["date"], r["desc"], r["in"], r["out"], r["balance"]))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--password", default="")
    ap.add_argument("--out", default=str(HERE / "dist" / "dashboard.html"))
    ap.add_argument("--json", help="데이터 JSON 도 따로 저장할 경로")
    args = ap.parse_args()

    print("파일 읽는 중…")
    data = build(args.folder, args.password)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if args.json:
        Path(args.json).write_text(payload, encoding="utf-8")
    template = (HERE / "template.html").read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/null", payload.replace("</", "<\\/"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"완료: {out}")


if __name__ == "__main__":
    main()
