#!/usr/bin/env python
import csv
import json
import sys
from typing import List, Tuple, Dict, Any, Optional
import yaml


# ─────────────────────────────
# 補助関数群（内部で利用する関数）
# ─────────────────────────────

def set_value(record: Dict[str, Any],
              path: List[Tuple[str, bool]],
              value: str,
              cont_elements: Optional[Dict[Tuple[str, ...], Dict[str, Any]]] = None) -> None:
    """
    指定された record 辞書に対し、path の階層に沿って value をセットする。
    path は [(フィールド名, is_array), …] のリスト。
    cont_elements が指定されている場合は、継続行で新規作成した要素を管理するために利用する。
    """
    current = record
    array_path = []  # 配列フィールドの階層（キー用タプル）
    for i, (field, is_array) in enumerate(path):
        if is_array:
            array_path.append(field)
            key = tuple(array_path)
            if field not in current or not isinstance(current[field], list):
                current[field] = []
            if cont_elements is not None:
                if key not in cont_elements:
                    new_elem = {}
                    current[field].append(new_elem)
                    cont_elements[key] = new_elem
                current = cont_elements[key]
            else:
                if not current[field]:
                    current[field].append({})
                current = current[field][-1]
        else:
            if i == len(path) - 1:
                # 葉ノードなら値をセット（数値変換も試みる）
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


def find_deepest_list(data: Any) -> Optional[list]:
    """
    入れ子になったデータ構造中で、一番深い階層にあるリストを返す。
    """
    if isinstance(data, list):
        for item in data:
            deeper_list = find_deepest_list(item)
            if deeper_list is not None:
                return deeper_list
        return data
    elif isinstance(data, dict):
        for value in data.values():
            deeper_list = find_deepest_list(value)
            if deeper_list is not None:
                return deeper_list
    return None


def merge_yaml_dicts(yaml_str1: str, yaml_str2: str) -> Dict[str, Any]:
    """
    2つの YAML 文字列を統合し、辞書として返す。
    - 配列の場合は、最も深い階層のリスト同士でマージを行う。
    """
    combined_yaml = yaml_str1 + "\n---\n" + yaml_str2
    merged_dict = {}

    for doc in yaml.safe_load_all(combined_yaml):
        for key, value in doc.items():
            if key in merged_dict:
                if isinstance(merged_dict[key], list):
                    deepest_list = find_deepest_list(merged_dict[key])
                    if deepest_list is not None:
                        if isinstance(value, list):
                            deepest_value_list = find_deepest_list(value)
                            if deepest_value_list is not None:
                                deepest_list.extend(deepest_value_list)
                            else:
                                deepest_list.extend(value)
                        else:
                            deepest_list.append(value)
                    else:
                        if isinstance(value, list):
                            merged_dict[key].extend(value)
                        else:
                            merged_dict[key].append(value)
                elif isinstance(merged_dict[key], dict) and isinstance(value, dict):
                    merged_dict[key] = merge_yaml_dicts(yaml.dump(merged_dict[key]), yaml.dump(value))
                else:
                    merged_dict[key] = value
            else:
                merged_dict[key] = value
    return merged_dict


# ─────────────────────────────
# ヘッダー部を管理するクラス
# ─────────────────────────────

class Header:
    """
    CSV のヘッダー部（LAYOUT 行）から、各列の階層パス情報を生成・保持するクラス。
    """
    def __init__(self, header_rows: List[List[str]]):
        self.raw_rows = header_rows
        self.grid = self._build_header_grid()
        self.col_to_path = self._build_col_to_path()
        self.num_cols = max(len(row) for row in self.grid)
        # ヘッダー情報：各列番号に対する階層パスの一覧
        self.header_info = {str(col): self.col_to_path[col]
                            for col in sorted(self.col_to_path.keys())}

    def _fill_header_row(self, row: List[str], max_cols: int) -> List[str]:
        """
        セルが "<" の場合、直前の非空セルで置換し、右端が不足している場合は最終セルで補完する。
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
                filled.append("")
        while len(filled) < max_cols:
            filled.append(last)
        return filled

    def _build_header_grid(self) -> List[List[str]]:
        max_cols = max(len(row) for row in self.raw_rows)
        grid = []
        for row in self.raw_rows:
            grid.append(self._fill_header_row(row, max_cols))
        return grid

    def _build_col_to_path(self) -> Dict[int, List[Tuple[str, bool]]]:
        """
        ヘッダーグリッドから、各列ごとのフィールドパス（フィールド名と配列かどうかのフラグの組）
        を生成する。
        """
        col_to_path = {}
        num_cols = len(self.grid[0])
        num_levels = len(self.grid)
        for col in range(num_cols):
            path = []
            for level in range(num_levels):
                val = self.grid[level][col].strip() if col < len(self.grid[level]) else ""
                if val:
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
# １レコード（複数行にまたがる）の状態を管理するクラス
# ─────────────────────────────

class Record:
    """
    CSV のレコード（新規行および継続行）から、入れ子構造の辞書データを生成・更新するクラス。
    """
    def __init__(self,
                 col_to_path: Dict[int, List[Tuple[str, bool]]],
                 num_cols: int,
                 base_row: List[str]):
        self.col_to_path = col_to_path
        self.num_cols = num_cols
        self.data = self._create_nested_record(base_row)

    def _create_nested_record(self, row: List[str]) -> Dict[str, Any]:
        """
        １行分のデータから、ヘッダー情報に沿った入れ子構造の辞書を生成する。
        """
        record: Dict[str, Any] = {}
        # 列数が足りなければ右側を空文字で補完
        if len(row) < self.num_cols:
            row = row + [""] * (self.num_cols - len(row))
        for col in range(self.num_cols):
            cell = row[col].strip() if col < len(row) else ""
            if cell and col in self.col_to_path:
                set_value(record, self.col_to_path[col], cell)
        return record

    def add_continuation_row(self, row: List[str]) -> None:
        """
        継続行として新たな行データをマージする。
        """
        new_record = self._create_nested_record(row)
        base_yaml = yaml.dump(self.data, allow_unicode=True)
        new_yaml = yaml.dump(new_record, allow_unicode=True)
        merged_dict = merge_yaml_dicts(base_yaml, new_yaml)
        self.data = merged_dict

    def to_json(self) -> str:
        """
        内部の辞書データを JSON 文字列に変換して返す。
        """
        return json.dumps(self.data, indent=4, ensure_ascii=False)


# ─────────────────────────────
# CSV 全体の処理を管理するクラス
# ─────────────────────────────

class CSVLayoutParser:
    """
    CSV ファイル全体を読み込み、ヘッダー解析と各レコードの入れ子辞書変換を行うクラス。
    """
    def __init__(self, csv_filename: str):
        self.filename = csv_filename
        self.header_rows: List[List[str]] = []
        self.data_rows: List[List[str]] = []
        self.records: List[Record] = []
        self.header: Optional[Header] = None
        self.header_info: Dict[str, Any] = {}
        self.col_to_path: Dict[int, List[Tuple[str, bool]]] = {}
        self.num_cols: int = 0

    def parse(self) -> Dict[str, Any]:
        """
        CSV を解析し、ヘッダー情報と各レコード（入れ子辞書）の一覧を返す。
        戻り値の形式は { "header": ヘッダー情報, "records": [各レコード, ...] } となる。
        """
        self._read_csv()
        self._process_header()
        self._process_data()
        return {
            "header": self.header_info,
            "records": [record.data for record in self.records]
        }

    def _read_csv(self) -> None:
        """
        CSV ファイルを読み込み、ヘッダー部（"LAYOUT" 行）とデータ部に分ける。
        """
        with open(self.filename, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        for row in rows:
            if row and row[0].strip().upper() == "LAYOUT":
                # ヘッダー行は先頭セル "LAYOUT" を除く
                self.header_rows.append(row[1:])
            else:
                self.data_rows.append(row)
        if not self.header_rows:
            raise ValueError("ヘッダー部（LAYOUT 行）が見つかりません。")

    def _process_header(self) -> None:
        """
        ヘッダー部から階層情報を生成し、状態として保持する。
        """
        self.header = Header(self.header_rows)
        self.col_to_path = self.header.col_to_path
        self.num_cols = self.header.num_cols
        self.header_info = self.header.header_info

    def _process_data(self) -> None:
        """
        データ部の各行をレコードグループ（新規行＋継続行）ごとにまとめ、各レコードを生成する。
        """
        record_groups: List[List[List[str]]] = []  # 1レコード＝複数行のリスト
        current_group: List[List[str]] = []
        for row in self.data_rows:
            if not row or all(not cell.strip() for cell in row):
                continue
            marker = row[0].strip()
            if marker != "*":
                if current_group:
                    record_groups.append(current_group)
                current_group = [row[1:]]  # マーカーは除去
            else:
                current_group.append(row[1:])
        if current_group:
            record_groups.append(current_group)

        for group in record_groups:
            # グループの先頭行から新規レコードを生成し、
            # 継続行があれば順次マージする。
            record = Record(self.col_to_path, self.num_cols, group[0])
            for cont_row in group[1:]:
                record.add_continuation_row(cont_row)
            self.records.append(record)


# ─────────────────────────────
# メイン処理
# ─────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py csv_filename", file=sys.stderr)
        sys.exit(1)
    filename = sys.argv[1]
    parser = CSVLayoutParser(filename)
    result = parser.parse()
    # レコードが存在する場合は JSON 文字列として出力
    if result["records"]:
        print(json.dumps(result["records"], indent=4, ensure_ascii=False))
    else:
        print("{}")
