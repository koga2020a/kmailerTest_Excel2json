import json
import sys
import argparse
from collections import defaultdict
from typing import Any, Dict, List, Tuple


class JsonToTxtConverter:
    def __init__(self) -> None:
        # 読み込んだ JSON データ本体（オプション）
        self.data: Any = None
        # カラムパス（例: [["foo"], ["foo[]", "value"], ...]）
        self.column_paths: List[List[str]] = []
        # 各カラムパスに対応するすべての値のリスト
        # 例: {("foo",): ["val1", "val2"], ...}
        self.path_to_values: Dict[Tuple[str, ...], List[Any]] = defaultdict(list)
        # True の場合、LAYOUT 行で同じキーが連続しているときの置換処理をスキップする
        # （デフォルトでは連続キーは「<」に置換します）
        self.disable_duplicate_layout: bool = False

    def load_json(self, filename: str) -> None:
        """
        JSON ファイルを読み込み、内部状態（data, column_paths, path_to_values）を更新する。
        """
        with open(filename, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        self._reset_state()
        self._collect_leaf_paths(self.data, path=[])
        # カラムパスは path_to_values のキーから作成
        # ※再帰処理内で sorted() を使っているので、ここでのグローバルソートは不要です
        self.column_paths = [list(path) for path in self.path_to_values.keys()]
        # もしグローバルソートを行うと親キー内での順序が崩れるため、ここではソートしません。
        # self.column_paths.sort(key=lambda p: (len(p), p))

    def _reset_state(self) -> None:
        """
        内部状態をリセットする。
        JSON の再読み込み時などに利用。
        """
        self.column_paths.clear()
        self.path_to_values.clear()

    def _collect_leaf_paths(self, node: Any, path: List[str]) -> None:
        """
        JSON を再帰的に探索し、leaf（dict でも list でもない値）に到達した場合に
        現在のパスと値を内部状態に記録する。

        配列の場合はキーに "[]" を付与して区別する。

        また、dict のキーはソートして処理することで、親キーに属する子キーの範囲内で
        ソートした状態を保証する。
        """
        if isinstance(node, dict):
            # dict のキーをソートしてから処理する
            for key in sorted(node.keys()):
                self._collect_leaf_paths(node[key], path + [key])
        elif isinstance(node, list):
            if not path:
                # ルート直下が配列の場合
                array_key = "ROOT[]"
                new_path = path + [array_key]
            else:
                # 既存の最後のキーを "キー[]" に変更
                *parent, last = path
                array_key = f"{last}[]"
                new_path = parent + [array_key]
            for item in node:
                self._collect_leaf_paths(item, new_path)
        else:
            # node が leaf の場合、現在のパスと値を記録
            self.path_to_values[tuple(path)].append(node)

    def get_txt_lines(self) -> List[str]:
        """
        内部状態から、LAYOUT 行と DATA 行を生成し、TXT 出力用の行リストを返す。
        """
        lines: List[str] = []
        if not self.column_paths:
            return lines

        max_depth = self._get_max_column_depth()

        # LAYOUT 行の生成（各行はタブ区切り）
        for depth in range(max_depth):
            # 1列目は "LAYOUT" 固定、2列目は空文字
            row = ["LAYOUT", ""]
            for path in self.column_paths:
                # カラムパスが現在の深さを持っていれば、"#" を付けて出力
                row.append(f"#{path[depth]}" if len(path) > depth else "")
            # もし duplicate キーの連続置換処理が有効なら実施する
            if not self.disable_duplicate_layout:
                last_key = None
                # 先頭の2セルはタイトル等なので、インデックス2以降を処理
                for i in range(2, len(row)):
                    # 空文字は処理対象外
                    if row[i] != "":
                        if last_key is not None and row[i] == last_key:
                            row[i] = "<"
                        else:
                            last_key = row[i]
                    else:
                        # 空文字の場合は last_key をリセットしない
                        # ※必要に応じて処理を変更してください
                        last_key = row[i]
            lines.append("\t".join(row))

        # DATA 行の生成
        max_value_count = self._get_max_values_count()
        for i in range(max_value_count):
            # 1行目は "DATA"、2行目以降は "*" マーカー
            marker = "DATA" if i == 0 else "*"
            row = [marker, ""]
            for path in self.column_paths:
                values = self.path_to_values[tuple(path)]
                if i < len(values):
                    row.append(self._to_str(values[i]))
                else:
                    row.append("")
            lines.append("\t".join(row))

        return lines

    def _get_max_column_depth(self) -> int:
        """全カラムパスの中で最大の深さを返す。"""
        return max(len(p) for p in self.column_paths)

    def _get_max_values_count(self) -> int:
        """全カラムの中で最大の値の数を返す。"""
        return max(len(values) for values in self.path_to_values.values())

    def _to_str(self, val: Any) -> str:
        """
        値を文字列に変換する。
        Boolean は大文字の TRUE/FALSE、整数はそのまま文字列化、それ以外は str() を利用する。
        """
        if val is True:
            return "TRUE"
        elif val is False:
            return "FALSE"
        elif isinstance(val, int):
            return str(val)
        else:
            return str(val) if val is not None else ""

    def write_txt(self, filename: str) -> None:
        """
        内部状態から TXT 行リストを生成し、指定したファイルへ書き出す。
        """
        lines = self.get_txt_lines()
        with open(filename, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="JSON を読み込み、LAYOUT/DATA 形式の TXT を出力します。"
    )
    parser.add_argument("input_json", help="入力 JSON ファイル")
    parser.add_argument("output_txt", nargs="?", help="出力 TXT ファイル（省略時は入力ファイル名の拡張子を .txt にしたもの）")
    parser.add_argument(
        "--no-layout-dup",
        action="store_true",
        help="LAYOUT 行での連続する同一キーの置換処理を行わない（連続キーをそのまま出力する）"
    )
    args = parser.parse_args()

    input_json_file = args.input_json
    output_txt_file = args.output_txt if args.output_txt else input_json_file.rsplit('.', 1)[0] + '.txt'

    converter = JsonToTxtConverter()
    converter.disable_duplicate_layout = args.no_layout_dup
    converter.load_json(input_json_file)
    converter.write_txt(output_txt_file)
    print(f"変換が完了しました: {output_txt_file}")


if __name__ == "__main__":
    main()
