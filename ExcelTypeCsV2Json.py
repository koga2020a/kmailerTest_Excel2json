import json
from typing import Dict, List, Any

class StructureParser:
    def __init__(self):
        self.result = {}
        self.column_paths = []
        self.data_lines = []

    def parse_file(self, filename: str) -> None:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [line.strip().split('\t') for line in f if line.strip()]
            
        # HEADとDATA行を分けて処理
        for line in lines:
            if not line:
                continue
                
            if line[0] == 'HEAD':
                self.process_head_line(line)
            elif line[0] == 'DATA':
                self.data_lines.append(line)
        
        # すべてのDATA行をまとめて処理
        self.process_data_lines(self.data_lines)

    def process_head_line(self, items: List[str]) -> None:
        """
        HEAD行を処理し、カラムパスを構築
        """
        if len(items) < 2:
            return

        # 最初のHEAD行の場合、column_pathsを初期化
        if not self.column_paths:
            self.column_paths = [[] for _ in range(len(items) - 2)]  # 最初の2列を除く

        # 3列目以降の各カラムに対してパスを更新
        for i, value in enumerate(items[2:]):
            if value.strip():  # 空でない値のみ処理
                self.column_paths[i].append(value)

    def process_data_lines(self, lines: List[List[str]]) -> None:
        """
        DATA行をグループ化して処理する
        """
        current_group = []
        
        for line in lines:
            if len(line) < 2:
                continue
                
            if line[0] == 'DATA':
                # 新しいグループの開始（2列目が空）または継続（2列目が*）
                if not line[1].strip():  # 空の場合は新しいグループ開始
                    if current_group:  # 既存グループがあれば処理
                        self._process_data_group(current_group)
                    current_group = [line]
                elif line[1].strip() == '*':  # 継続行
                    current_group.append(line)
        
        # 最後のグループを処理
        if current_group:
            self._process_data_group(current_group)

    def parse_array_header(self, header: str) -> str:
        """
        配列ヘッダーから実際のキー名を取得
        """
        if header.startswith('[]'):
            return header[2:]
        return header

    def get_array_index(self, index_marker: str) -> int:
        """
        配列のインデックスを取得
        """
        if not index_marker or index_marker == '*':
            return 0
        try:
            return int(index_marker)
        except ValueError:
            return 0

    def set_value_in_path(self, base: Dict[str, Any], path: List[str], array_index: int, value: Any) -> None:
        """
        パスに沿ってオブジェクト/配列を辿り、最終的に値を設定する。
        path 内に "[]xxx" が複数含まれる場合、それぞれ配列として扱うが、
        最初の配列だけに対して `array_index` を適用し、2つ目以降の配列は「最後の要素を使う／無ければ新規作成」する。
        """

        # TRUE / FALSE / 数字 などの文字列をPythonの型に変換
        if value == "TRUE":
            value = True
        elif value == "FALSE":
            value = False
        else:
            # 整数文字列を int 化 (純粋な数字の場合のみ)
            if value.isdigit():
                value = int(value)

        current = base
        used_array_index = False  # 最初に見つかった配列に対してのみ array_index を適用

        # 最後の要素を除いた部分でノードを辿る
        for token in path[:-1]:
            if token.startswith('[]'):
                # 配列キー
                key = self.parse_array_header(token)  # '[]xxx' → 'xxx'
                if key not in current:
                    current[key] = []
                # 最初の配列キーだけ array_index を使う
                if not used_array_index:
                    # 必要数まで拡張
                    while len(current[key]) <= array_index:
                        current[key].append({})
                    current = current[key][array_index]
                    used_array_index = True
                else:
                    # 2番目以降の配列キーは常に「最後の要素」を使う／無ければ追加
                    if not current[key]:
                        current[key].append({})
                    current = current[key][-1]
            else:
                # 通常キー
                if token not in current:
                    current[token] = {}
                current = current[token]

        # 最後の要素（末尾のキー）に対して値を設定
        last_token = path[-1]
        if last_token.startswith('[]'):
            # 最終キーも配列の場合
            key = self.parse_array_header(last_token)
            if key not in current:
                current[key] = []
            # 最終キーが配列の場合は、その配列に「値」を1つ append する想定
            current[key].append(value)
        else:
            # 通常キー
            current[last_token] = value

    def _process_data_group(self, group: List[List[str]]) -> None:
        """
        グループ化されたDATA行を処理する
        """
        if not group:
            return

        # 3列目以降の値を列ごとに集める
        column_values = {}
        for col_idx in range(2, len(group[0])):
            values = []
            for row in group:
                if col_idx < len(row):
                    value = row[col_idx].strip()
                    if value:  # 空でない値のみ追加
                        values.append(value)
            if values:  # 値が存在する列のみ処理
                column_values[col_idx] = values

        # 列ごとの値を適切なパスに設定
        array_index = self.get_array_index('')  # 最初の行は空欄なので
        for col_idx, values in column_values.items():
            if col_idx - 2 < len(self.column_paths):
                path = self.column_paths[col_idx - 2]
                if not path:
                    continue
                
                if len(values) == 1:
                    # 単一値の場合
                    self.set_value_in_path(self.result, path, array_index, values[0])
                else:
                    # 複数値の場合は配列として設定
                    self.set_array_values_in_path(self.result, path, array_index, values)

    def set_array_values_in_path(self, current: dict, path: List[str], array_index: int, values: List[str]) -> None:
        """
        パスに従って複数の値を配列として設定
        """
        for i, token in enumerate(path[:-1]):
            if token.startswith('[]'):
                key = self.parse_array_header(token)
                if key not in current:
                    current[key] = []
                if array_index >= len(current[key]):
                    current[key].append({})
                current = current[key][array_index]
            else:
                if token not in current:
                    current[token] = {}
                current = current[token]

        last_token = path[-1]
        if last_token.startswith('[]'):
            key = self.parse_array_header(last_token)
            if key not in current:
                current[key] = []
            current[key].extend(values)
        else:
            current[last_token] = values

    def to_json(self) -> str:
        """結果をJSON文字列として返す"""
        return json.dumps(self.result, ensure_ascii=False, indent=2)

# 使用例
if __name__ == "__main__":
    parser = StructureParser()
    parser.parse_file("ExcelTypeCsv_input.txt")
    print(parser.to_json())
