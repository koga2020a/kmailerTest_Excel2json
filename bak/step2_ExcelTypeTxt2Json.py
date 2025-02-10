import json
from typing import Dict, List, Any
import yaml
import sys


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

    def set_array_values_in_path(self, current: dict, path: List[str], array_index: int, values: List[str]) -> None:
        """
        パスに従って複数の値を配列として設定
        """
        # 前段階のノードに移動
        for i, token in enumerate(path[:-1]):
            if token.startswith('[]'):
                key = self.parse_array_header(token)
                if key not in current:
                    current[key] = []
                # array_index を使う（最初の [] だけ有効にするなら工夫が必要）
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
            # 配列に extend
            current[key].extend(self._convert_values(values))
        else:
            # 単なるリストを直接突っ込む
            current[last_token] = self._convert_values(values)

    def _convert_values(self, values: List[str]) -> List[Any]:
        """
        TRUE/FALSE/数字 などを適切に変換したリストを返す
        """
        converted = []
        for v in values:
            if v == "TRUE":
                converted.append(True)
            elif v == "FALSE":
                converted.append(False)
            elif v.isdigit():
                converted.append(int(v))
            else:
                converted.append(v)
        return converted

    def _process_data_group(self, group: List[List[str]]) -> None:
        """
        グループ化されたDATA行を処理する
        """
        if not group:
            return

        # 3列目以降の値を列ごとに集める
        # column_values[col_idx] = [値1, 値2, ...]
        column_values = {}
        for col_idx in range(2, len(group[0])):  # 2列目までは無視
            vals = []
            for row in group:
                if col_idx < len(row):
                    v = row[col_idx].strip()
                    if v:
                        vals.append(v)
            if vals:
                column_values[col_idx] = vals

        # まず、同じ「親パス」を共有する列をグループ化する
        # 親パス: column_paths[col_idx - 2] のうち、最後のトークンを除いた部分
        parent_path_map = {}
        for col_idx, _ in column_values.items():
            if (col_idx - 2) < len(self.column_paths):
                full_path = self.column_paths[col_idx - 2]
                if full_path:
                    parent = tuple(full_path[:-1])  # 親パス
                    last_token = full_path[-1]
                    if parent not in parent_path_map:
                        parent_path_map[parent] = []
                    parent_path_map[parent].append((col_idx, last_token))

        # 実際に処理する
        array_index = self.get_array_index('')  # とりあえず最初のDATA行は空欄として0固定
        processed_columns = set()  # 特別処理で使い終わった列は通常処理しない

        for parent, cols_info in parent_path_map.items():
            # parent が配列キー (例: ['[]rule']) を含むかどうか
            # 末尾が "[]xxxxx" になっているか、あるいは途中にあるか、など
            # 今回は「末尾に []rule があって、かつ last_token が field/type/value など複数…」を想定
            # もう少し一般化して「parent の末尾が []xxx なら、それを配列オブジェクトにする」などと判定してもOK
            if not parent:
                continue  # 親パスがない場合はスキップ
            
            # 親パスの末尾が配列キーなら…という簡易判定
            parent_last_token = parent[-1]
            if not parent_last_token.startswith('[]'):
                continue

            # cols_info の例: [ (col_idx, "field"), (col_idx, "type"), (col_idx, "value") ]
            # → 同じ配列に入るはずの複数列
            if len(cols_info) < 2:
                continue  # 1列しかないならまとめる意味ないのでスキップ

            # 「このカラム群は 1行 = 1オブジェクト としてまとめる」のを想定
            # group の各行について、cols_info の各列に値があれば、それらを { last_token: 値 } としてまとめる
            # まとめたオブジェクトを parent パスの配列に append する

            # 親パスをリスト化
            parent_list = list(parent)
            # parent の最後のトークン (例: "[]rule") は実際の追加先配列
            parent_array_key = self.parse_array_header(parent_last_token)
            # オブジェクトを追加する先を探す (parent のさらに一つ手前までをたどる)
            # 例: parent = ["[]conditions", "[]rule"] の場合は、["[]conditions"] の最後の要素にある "rule" 配列
            # ただし、実際には self.set_value_in_path と同じように辿る必要がある

            # まず、「parent の最後のトークンを除いたパス」(= 配列の親の親) に移動する
            actual_parent_path = parent_list[:-1]  # "[]rule" の手前まで
            # ここで current を見つける
            current = self.result
            used_array_index = False
            for token in actual_parent_path:
                if token.startswith('[]'):
                    k = self.parse_array_header(token)
                    if k not in current:
                        current[k] = []
                    if not used_array_index:
                        # 必要数だけ拡張
                        while len(current[k]) <= array_index:
                            current[k].append({})
                        current = current[k][array_index]
                        used_array_index = True
                    else:
                        if not current[k]:
                            current[k].append({})
                        current = current[k][-1]
                else:
                    if token not in current:
                        current[token] = {}
                    current = current[token]

            # これで current は "[]rule" の直前のオブジェクト
            # "[]rule" 自体を取得/初期化
            if parent_array_key not in current:
                current[parent_array_key] = []
            rules_array = current[parent_array_key]

            # cols_info を (col_idx の昇順) で固定
            cols_info_sorted = sorted(cols_info, key=lambda x: x[0])

            # group の各行についてオブジェクト化
            for row in group:
                # その行に対応する (col_idx, last_token) 列を探す
                rule_obj = {}
                value_found = False
                for col_idx, last_token in cols_info_sorted:
                    if col_idx < len(row):
                        val = row[col_idx].strip()
                        if val:
                            # TRUE/FALSE/数字 変換
                            val_converted = self._convert_values([val])[0]
                            rule_obj[last_token] = val_converted
                            value_found = True
                if value_found:
                    # 何らかの値があった場合のみ追加
                    rules_array.append(rule_obj)

            # この配列親パスに属する列は、通常処理（下の for col_idx, values in column_values のループ）から除外
            for (col_idx, _) in cols_info:
                processed_columns.add(col_idx)

        # 上記で特別処理した列以外は、通常の set_value_in_path / set_array_values_in_path へ
        for col_idx, values in column_values.items():
            if col_idx in processed_columns:
                # 既に特別処理した列はスキップ
                continue
            if (col_idx - 2) < len(self.column_paths):
                path = self.column_paths[col_idx - 2]
                if not path:
                    continue
                
                if len(values) == 1:
                    # 単一値の場合
                    self.set_value_in_path(self.result, path, array_index, values[0])
                else:
                    # 複数値の場合は配列として設定
                    self.set_array_values_in_path(self.result, path, array_index, values)
    def to_json(self) -> str:
        """結果をJSON文字列として返す"""
        return json.dumps(self.result, ensure_ascii=False, indent=2)

    def to_yaml(self) -> str:
        """結果をYAML文字列として返す"""
        return yaml.dump(self.result, allow_unicode=True, sort_keys=False)
    
def main():
    # コマンドライン引数の処理
    if len(sys.argv) < 2:
        print("使用方法: python スクリプト名.py 入力ファイル [出力ファイル]")
        sys.exit(1)

    input_file = sys.argv[1]
    
    # 出力ファイル名の設定
    if len(sys.argv) == 3:
        output_file = sys.argv[2]
    elif len(sys.argv) == 4:
        output_file = sys.argv[2]
        output_file_yaml = sys.argv[3]
    else:
        # 入力ファイル名から拡張子を除去し、.jsonを追加
        output_file = input_file.rsplit('.', 1)[0] + '.json'
        output_file_yaml = input_file.rsplit('.', 1)[0] + '.yaml'

    try:
        # データ処理をここに記述
        parser = StructureParser()
        parser.parse_file(input_file)
                
        # 結果を出力ファイルに保存
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(parser.to_json())
        with open(output_file_yaml, 'w', encoding='utf-8') as f:
            f.write(parser.to_yaml())
        print(f"処理が完了しました。JSONファイル: {output_file}")
        print(f"YAMLファイル: {output_file_yaml}")
            

    except FileNotFoundError:
        print(f"エラー: ファイル '{input_file}' が見つかりません。")
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()