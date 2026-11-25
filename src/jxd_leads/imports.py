import csv
import io
import zipfile

from openpyxl import load_workbook
from pydantic import ValidationError

from .schemas import CandidateInput

HEADERS = {
    "公司": "company",
    "项目": "project",
    "地区": "region",
    "地址": "address",
    "来源链接": "source_url",
    "来源类型": "source_type",
    "证据": "evidence",
    "匹配理由": "reason",
    "需求证据": "demand_evidence",
    "发现日期": "discovered_at",
}


def preview_import(data: bytes, filename: str, model=CandidateInput, headers=None):
    headers = HEADERS if headers is None else headers
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("文件不能超过2MB")
    if filename.lower().endswith(".xlsx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(x.file_size for x in z.infolist()) > 20 * 1024 * 1024:
                raise ValueError("表格解压后过大")
        w = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        try:
            it = w.active.iter_rows(values_only=True)
            heads = [str(x or "").strip() for x in next(it)]
            rows = []
            for index, row in enumerate(it):
                if index >= 100:
                    raise ValueError("每次最多导入100行，请分批")
                if any(x is not None for x in row):
                    rows.append(dict(zip(heads, row)))
        finally:
            w.close()
    elif filename.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        if len(rows) > 100:
            raise ValueError("每次最多导入100行")
    else:
        raise ValueError("仅支持 UTF-8 CSV 或 XLSX")
    valid = []
    errors = []
    for i, row in enumerate(rows, 2):
        normalized = {headers.get(k, k): v for k, v in row.items() if v is not None and str(v).strip()}
        try:
            item = model(**normalized)
            if model is CandidateInput and item.source_type != "已有关系" and not item.source_url:
                raise ValueError("网络线索缺少来源链接")
            valid.append(item.model_dump(mode="json"))
        except (ValueError, ValidationError):
            errors.append({"row": i, "message": "字段不完整或格式错误：检查公司、项目、地区、证据、来源链接及日期"})
    if not rows:
        raise ValueError("文件中没有数据")
    return {"items": valid, "errors": errors, "total": len(rows)}


def safe_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    for row in rows:
        clean = []
        for value in row:
            text = str(value if value is not None else "")
            if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                text = "'" + text
            clean.append(text)
        writer.writerow(clean)
    return "\ufeff" + out.getvalue()
