import json
import sys
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Union


class JsonToTxtConverter:
    def __init__(self):
        # カラムパス（例: [["foo"], ["foo", "[]bar", "value"], ...]）を格納
        self.column_paths: List[List[str]] = []
        # 各カラムパスに対応するすべての値のリスト
        # 例: {tuple_path: ["val1", "val2"], ...}
        self.path_to_values: Dict[Tuple[str, ...], List[Any]] = defaultdict(list)

    def load_json(self, filename: str):
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._traverse_json(data, path=[])

        # self.column_paths を path_to_values のキーから作成
        # ソートなどの順序付けは任意
        unique_paths = list(self.path_to_values.keys())
        # 重複しないようにリスト化
        self.column_paths = [list(p) for p in unique_paths]

    def _traverse_json(self, node: Any, path: List[str]):
        """
        JSON を再帰的に走査し、leaf まで到達したら (path, value) を記録する。
        配列なら "[]key" というトークンで path を作り直して辿る。
        """
        if isinstance(node, dict):
            for k, v in node.items():
                # オブジェクト: キーを追加して再帰
                self._traverse_json(v, path + [k])
        elif isinstance(node, list):
            # リストの場合は、直前のキー名がわかるようにする
            # 例: path の末尾が "hoge" なら、それを []hoge に置き換える形にする
            if not path:
                # ルート直下が配列の場合など。キー名がないため "[]ROOT" 的なものを仮置きしても良い
                array_key = "[]ROOT"
                new_path = path + [array_key]
                for item in node:
                    self._traverse_json(item, new_path)
            else:
                # path の末尾の通常キーを取り出し、 "[]末尾キー" に差し替える
                *parent_tokens, last_key = path
                array_key = f"[]{last_key}"
                # 既存の末尾を置き換え
                new_path = parent_tokens + [array_key]
                for item in node:
                    self._traverse_json(item, new_path)
        else:
            # leaf (str, int, bool, None など)
            self.path_to_values[tuple(path)].append(node)

    def convert_to_txt_lines(self) -> List[str]:
        """
        HEAD/DATA 形式の行リストを生成する。
        """
        lines: List[str] = []
        if not self.column_paths:
            return lines

        # まずはカラムパスの最大深度を求める
        max_depth = max(len(p) for p in self.column_paths)

        # HEAD 行を作る
        # i 行目では「各カラム p の i 番目のトークン」を列 i に書く (なければ空)
        # ただし、最初の2列は 'HEAD', '' を固定し、3列目以降にトークンを書く
        # 行を深さ max_depth ぶん作る
        for depth in range(max_depth):
            # 行の先頭2列
            row = ["HEAD", ""]
            # 各カラム p における depth 番目のトークンを入れる（なければ空文字）
            for p in self.column_paths:
                if len(p) > depth:
                    row.append(p[depth])
                else:
                    row.append("")
            lines.append("\t".join(row))

        # 次に DATA 行を作る
        #
        # 各カラムパスについて、値の数だけ縦に並べたいので
        # 「列ごとに持っている値の最大数」を見る
        max_values_count = max(len(self.path_to_values[tuple(p)]) for p in self.column_paths)

        # 行は、「一番長いカラムの値数」だけ作り、その中で各カラムが i 番目の値を持つなら出す
        # i=0 の行は 2 列目を空欄、 i>=1 の行は 2 列目を "*"
        for i in range(max_values_count):
            # row の先頭2列
            if i == 0:
                base_row = ["DATA", ""]
            else:
                base_row = ["DATA", "*"]

            # カラム毎に i 番目の値があれば出す
            for p in self.column_paths:
                values = self.path_to_values[tuple(p)]
                if i < len(values):
                    val = values[i]
                    # Python の型 → txt 用の文字列へ
                    txt_val = self._to_str(val)
                else:
                    txt_val = ""
                base_row.append(txt_val)

            lines.append("\t".join(base_row))

        return lines

    def _to_str(self, val: Any) -> str:
        """
        Boolean や数字を、元コードに合わせて文字列化。
        TRUE, FALSE, int, それ以外は文字列。
        """
        if val is True:
            return "TRUE"
        elif val is False:
            return "FALSE"
        elif isinstance(val, int):
            return str(val)
        else:
            # None や文字列、その他オブジェクトの場合はそのまま文字列化
            # （本来は None なら "" にするなどの場合もあるかも）
            return str(val) if val is not None else ""

def main():
    if len(sys.argv) < 2:
        print("使い方: python json_to_txt.py input.json [output.txt]")
        sys.exit(1)

    input_json_file = sys.argv[1]
    if len(sys.argv) >= 3:
        output_txt_file = sys.argv[2]
    else:
        # 拡張子を変えて出力
        output_txt_file = input_json_file.rsplit('.', 1)[0] + '.txt'

    converter = JsonToTxtConverter()
    converter.load_json(input_json_file)
    lines = converter.convert_to_txt_lines()

    with open(output_txt_file, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + "\n")

    print(f"変換が完了しました: {output_txt_file}")


if __name__ == "__main__":
    main()
