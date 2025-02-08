#!/usr/bin/env python
import csv
import json
import sys
import string
from typing import List, Tuple, Dict, Any, Optional

# ─────────────────────────────
# ヘッダー部のパス（階層情報）を作成するための補助関数群
# ─────────────────────────────

def fill_header_row(row: List[str], max_cols: int) -> List[str]:
    """
    １行分のヘッダー行について、セルが "<" なら左側の直近の非空文字で置換し、
    行数が max_cols 未満の場合は、最後のセルの値で右側を補完する。
    """
    filled = []
    last = ""
    for cell in row:
        cell = cell.strip()
        if cell == "<":
            filled.append(last)
        elif cell:
            filled.append(cell)
            last = cell
        else:
            filled.append("")  # 空文字はそのまま
    # 右側が不足している場合は、最後の非空セルで補完
    while len(filled) < max_cols:
        filled.append(last)
    return filled

def build_header_grid(header_rows: List[List[str]]) -> List[List[str]]:
    """
    LAYOUT 行（"LAYOUT" を除いた部分）のリストを受け取り、各行を右側補完・"<" 置換して返す。
    すべての行の列数は、ヘッダー行の最大列数に合わせる。
    """
    max_cols = max(len(row) for row in header_rows)
    grid = []
    for row in header_rows:
        # すでに "LAYOUT" は除いている前提
        filled = fill_header_row(row, max_cols)
        grid.append(filled)
    return grid

def build_col_to_path(grid: List[List[str]]) -> Dict[int, List[Tuple[str, bool]]]:
    """
    ヘッダーグリッド（各行＝階層レベル）から、各列ごとのパス情報を生成する。
    各セルの値が "[]" 付きの場合は配列フィールドとみなす。
    戻り値は {列番号: [(フィールド名, is_array), ...]} となる。
    なお、空文字のセルはパスに含めません。
    """
    col_to_path = {}
    num_cols = len(grid[0])
    num_levels = len(grid)
    for col in range(num_cols):
        path = []
        for level in range(num_levels):
            # 各レベルのセル
            val = grid[level][col].strip() if col < len(grid[level]) else ""
            if val:
                # 配列フィールドの場合、末尾 "[]" が付いていると判断
                if val.endswith("[]"):
                    field_name = val[:-2]
                    is_array = True
                else:
                    field_name = val
                    is_array = False
                path.append((field_name, is_array))
        if path:
            col_to_path[col] = path
    return col_to_path

# ─────────────────────────────
# データ部の各行を入れ子の辞書へ反映するための補助関数
# ─────────────────────────────

def set_value(record: Dict[str, Any], path: List[Tuple[str, bool]], value: str,
              cont_elements: Optional[Dict[Tuple[str, ...], Dict[str, Any]]] = None) -> None:
    """
    record（辞書）に対し、path の階層に沿って value をセットする。
    path は [(フィールド名, is_array), …] のリスト。
    cont_elements が指定されている場合は、継続行で新規作成した要素を管理するために利用する。
    
    ★ cont_elements のキーは「その配列フィールドまでのパス」をタプルにしたもの。
    """
    current = record
    array_path = []  # 配列フィールドの階層（キーとなるタプル用）
    for i, (field, is_array) in enumerate(path):
        if is_array:
            array_path.append(field)
            key = tuple(array_path)
            # 該当フィールドがない場合は空リストをセット
            if field not in current or not isinstance(current[field], list):
                current[field] = []
            # 継続行の場合は、cont_elements 辞書を参照
            if cont_elements is not None:
                if key not in cont_elements:
                    # 新規要素を作成してリストに追加
                    new_elem = {}
                    current[field].append(new_elem)
                    cont_elements[key] = new_elem
                current = cont_elements[key]
            else:
                # 新規レコードの最初の行の場合
                if not current[field]:
                    current[field].append({})
                current = current[field][-1]
        else:
            # 非配列フィールド
            if i == len(path) - 1:
                # 葉ノードの場合は値をセット（数値変換はお好みで）
                # ここでは数値っぽい文字列は int/float に変換
                try:
                    if '.' in value:
                        conv = float(value)
                    else:
                        conv = int(value)
                    current[field] = conv
                except ValueError:
                    current[field] = value
            else:
                if field not in current or not isinstance(current[field], dict):
                    current[field] = {}
                current = current[field]

def process_record_group(rows: List[List[str]], col_to_path: Dict[int, List[Tuple[str, bool]]],
                         num_cols: int) -> Dict[str, Any]:
    """
    １レコードに属する複数行（最初の行は新規レコード、以降は "*" マーカーの継続行）
    を受け取り、col_to_path に従って入れ子構造の辞書（レコード）を作成して返す。
    
    ★ 新規レコード行では各セルの値をそのままセットし、
      継続行では、行内で非空セルがある各配列フィールドについて
      新規要素を生成して値をセットする（同じ配列フィールドは同じ継続行内では 1 つの要素にまとめる）。
    """
    record: Dict[str, Any] = {}
    # まず、新規レコード行（マーカーが空文字）の処理
    base = rows[0]
    # 右側不足分を補完
    if len(base) < num_cols:
        base += [""] * (num_cols - len(base))
    for col in range(num_cols):
        cell = base[col].strip() if col < len(base) else ""
        if cell and col in col_to_path:
            set_value(record, col_to_path[col], cell)
    # 継続行の処理
    for row in rows[1:]:
        # row[0] はマーカー（"*"）なので、以降のセルが対象
        data = row
        if len(data) < num_cols:
            data += [""] * (num_cols - len(data))
        # cont_elements: 継続行内で作成した各配列新規要素を記録する
        cont_elements: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        for col in range(num_cols):
            cell = data[col].strip() if col < len(data) else ""
            if cell and col in col_to_path:
                set_value(record, col_to_path[col], cell, cont_elements)
    return record

# ─────────────────────────────
# CSV 読み込み・前処理・レコード生成
# ─────────────────────────────

def process_csv(csv_filename: str) -> Dict[str, Any]:
    """
    CSV ファイルを読み込み、ヘッダー部からフィールドの階層構造を動的に構築するとともに、
    データ部の各レコードをネスト構造の辞書へ変換し、結果をまとめて返す。
    戻り値の辞書は { "header": ヘッダー解析結果, "records": [各レコード, ...] } となる。
    """
    with open(csv_filename, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    
    # ヘッダー部：先頭セルが "LAYOUT" の行
    header_rows = []
    data_rows = []
    for row in rows:
        if row and row[0].strip().upper() == "LAYOUT":
            # ヘッダー行は、最初のセル ("LAYOUT") を除いた部分とする
            header_rows.append(row[1:])
        else:
            data_rows.append(row)
    
    if not header_rows:
        raise ValueError("ヘッダー部（LAYOUT 行）が見つかりません。")
    
    # ヘッダーグリッドの作成（右側補完・"<" 置換）
    header_grid = build_header_grid(header_rows)
    # ヘッダーグリッドから、各列のフィールドパスを作成
    col_to_path = build_col_to_path(header_grid)
    num_cols = max(len(r) for r in header_grid)
    
    # ヘッダー解析結果（動的に構築したフィールドパス一覧）を整形
    header_info = { str(col): col_to_path[col] for col in sorted(col_to_path.keys()) }
    
    # データ部：先頭セルはレコード開始マーカー（空なら新規レコード、"*" なら継続行）
    # ここでは、最初のセル（レコードマーカー）はデータ処理には不要なので、
    # 各行はそのまま（先頭セルも含む）状態で保持する。
    # まず、レコード毎にグループ化する
    record_groups: List[List[List[str]]] = []  # １レコード＝複数行のリスト
    current_group: List[List[str]] = []
    for row in data_rows:
        # ここでは、空の行はスキップ
        if not row or all(not cell.strip() for cell in row):
            continue
        marker = row[0].strip()
        if marker != "*":
            # 新規レコード開始
            if current_group:
                record_groups.append(current_group)
            current_group = [row[1:]]  # マーカーを除いた部分
        else:
            # 継続行
            current_group.append(row[1:])
    if current_group:
        record_groups.append(current_group)
    
    # 各レコードグループを処理してレコードを作成
    records = []
    for group in record_groups:
        rec = process_record_group(group, col_to_path, num_cols)
        records.append(rec)
    
    return {
        "header": header_info,
        "records": records
    }

# ─────────────────────────────
# JSON 出力用クラス（レコードに対してメソッドを追加する例）
# ─────────────────────────────

class Record:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
    def to_json(self) -> str:
        return json.dumps(self.data, indent=4, ensure_ascii=False)

# ─────────────────────────────
# メイン処理
# ─────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py csv_filename", file=sys.stderr)
        sys.exit(1)
    filename = sys.argv[1]
    result = process_csv(filename)
    # ヘッダー解析結果とレコード情報をまとめて出力
    print(json.dumps(result, indent=4, ensure_ascii=False))
