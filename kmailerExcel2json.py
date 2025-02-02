import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.styles import Alignment, Border, Side, PatternFill
from datetime import datetime
import json
import sys
import yaml  # PyYAML を利用。事前に pip install pyyaml を実施してください。
import os  # ファイル名操作用

class ExcelJsonConverter:
    def __init__(self, input_file):
        """
        Excelファイルを読み込み、対象シートを決定して内部状態として保持します。
        対象シートの決定ルール：
          - シート名が "JSON_START" のシートがあればそれを使用
          - なければシートがひとつの場合そのシートを使用
        """
        self.input_file = input_file
        self.wb = openpyxl.load_workbook(input_file)
        self.target_ws = self._select_target_sheet()
        self.duplicate_ws = None  # 複製したシートを後で設定

    def _select_target_sheet(self):
        if "JSON_START" in self.wb.sheetnames:
            return self.wb["JSON_START"]
        elif len(self.wb.sheetnames) == 1:
            return self.wb.active
        else:
            print("エラー：複数シートありますが、'JSON_START' という名前のシートが見つかりません。")
            sys.exit(1)

    def duplicate_sheet(self):
        """
        対象シートを複製し、シート名を「JSON_YYYYMMDD_HHMMSS」に変更します。
        複製したシートは self.duplicate_ws に保持されます。
        """
        self.duplicate_ws = self.wb.copy_worksheet(self.target_ws)
        dt_sheet_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.duplicate_ws.title = "JSON_" + dt_sheet_name

    def transform_data_markers(self):
        """
        複製シート内で、A列に記載されている
          #JSON_DATA_START ～ #JSON_DATA_END のブロック（もしくは
          #JSON_DATA_START からシート最終行まで）
        の各行について、セルの値を通常は "#JSON_DATA" に置換（補完）します。
        ※ セルの値が "#NOT" であれば、その行は変更しません。
        """
        ws = self.duplicate_ws
        inside_block = False
        max_row = ws.max_row
        for i in range(1, max_row + 1):
            cell = ws.cell(row=i, column=1)
            marker = ""
            if cell.value and isinstance(cell.value, str):
                marker = cell.value.strip()
            if marker == "#JSON_DATA_START":
                inside_block = True
                cell.value = "#JSON_DATA"
            elif marker == "#JSON_DATA_END":
                cell.value = "#JSON_DATA"
                inside_block = False
            elif inside_block:
                if marker != "#NOT":
                    cell.value = "#JSON_DATA"

    def _build_header_hierarchy(self):
        """
        複製シート内のヘッダー行（A列が "#JSON_START" の行）を走査し、
        各列ごとにキー階層（例：["mailset", "title"]）の辞書を作成して返します。
        """
        ws = self.duplicate_ws
        header_rows = []
        # ヘッダー行の抽出
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            cell_a = row[0].value
            if isinstance(cell_a, str) and cell_a.strip() == "#JSON_START":
                header_rows.append(row)
        
        if not header_rows:
            print("警告：ヘッダー行（#JSON_START）が見つかりませんでした。")
            return None

        header_hierarchy = {}  # key: 列文字（例 "B", "C", ...）、value: [上位キー, …, 下位キー]
        for header_row in header_rows:
            for cell in header_row:
                # A列はマーカーなのでスキップ
                if cell.column == 1:
                    continue
                if cell.value and isinstance(cell.value, str) and cell.value.strip().startswith("#"):
                    key_name = cell.value.strip().lstrip("#").strip()
                    col_letter = get_column_letter(cell.column)
                    if col_letter not in header_hierarchy:
                        header_hierarchy[col_letter] = []
                    header_hierarchy[col_letter].append(key_name)
        # 例: {"B": ["mailset", "title"], "C": ["mailset", "body"], "D": ["templates", "name"]}
        return header_hierarchy

    def convert_sheet_to_json(self):
        """
        複製シート内のデータ行（A列が "#JSON_DATA" の行）を、
        ヘッダー情報からネスト構造の辞書へ変換してリストで返します。
        ヘッダー行が複数ある場合は上側の行を上位階層、下側の行を下位階層として解釈します。
        """
        ws = self.duplicate_ws
        header_hierarchy = self._build_header_hierarchy()
        if header_hierarchy is None:
            return None

        # データ行の開始行：最初の "#JSON_DATA" を探す
        data_start_row = None
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            cell_a = row[0].value
            if isinstance(cell_a, str) and cell_a.strip() == "#JSON_DATA":
                data_start_row = row[0].row
                break

        if data_start_row is None:
            print("警告：データ行（#JSON_DATA）が見つかりませんでした。")
            return None

        data_list = []
        # データ行を処理
        for row in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row):
            cell_a_val = row[0].value
            if not (isinstance(cell_a_val, str) and cell_a_val.strip() == "#JSON_DATA"):
                continue  # "#NOT" などは無視
            record = {}
            for col_letter, key_list in header_hierarchy.items():
                col_idx = column_index_from_string(col_letter)
                cell = ws.cell(row=row[0].row, column=col_idx)
                current_dict = record
                # キー階層のうち、最後以外を入れ子の辞書として生成
                for key in key_list[:-1]:
                    if key not in current_dict or not isinstance(current_dict[key], dict):
                        current_dict[key] = {}
                    current_dict = current_dict[key]
                # 最後のキーにセルの値をセット
                current_dict[key_list[-1]] = cell.value
            data_list.append(record)
        return data_list

    def _set_title_cell(self, ws, row, column, text, fill, border):
        """
        指定されたセルにタイトル用の値とスタイルを設定して返します。
        """
        cell = ws.cell(row=row, column=column, value=text)
        cell.fill = fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
        return cell

    def _setup_output_cell(self, ws, row, column, text, border):
        """
        指定されたセルにテキストを設定し、テキスト形式(@)、
        折り返し表示、罫線を設定したセルオブジェクトを返します。
        """
        cell = ws.cell(row=row, column=column, value=text)
        cell.number_format = "@"
        cell.alignment = Alignment(wrap_text=True)
        cell.border = border
        return cell

    def output_json_yaml(self, json_data, offset=10):
        """
        変換したJSONデータ（リスト）を JSON 形式と YAML 形式に変換し、
        複製シートの最終行から offset 行下に出力します。
        JSON は A列、YAML は B列に出力し、各セルの書式をテキスト形式かつ折り返し表示に設定します。
        また、JSON/YAMLの出力セルの１つ上のセルにタイトル（出力JSON、出力YAML）を
        背景を明るい紫色にし、タイトルと内容を罫線で囲むようにします。
        """
        ws = self.duplicate_ws
        json_text = json.dumps(json_data, ensure_ascii=False, indent=2)
        yaml_text = yaml.dump(json_data, allow_unicode=True, default_flow_style=False)

        last_row = ws.max_row
        output_row = last_row + offset
        title_row = output_row - 1  # タイトルを出力する行

        # 罫線の設定（全辺に薄い線）
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # タイトルセルの背景（明るい紫色：lavender）
        title_fill = PatternFill(fill_type='solid', start_color='E6E6FA')

        # タイトルセルは既存の _set_title_cell() を使用
        self._set_title_cell(ws, title_row, 1, "出力JSON", title_fill, thin_border)
        self._set_title_cell(ws, title_row, 2, "出力YAML", title_fill, thin_border)

        # JSON出力セルの設定（リファクタ後）
        json_cell = self._setup_output_cell(ws, output_row, 1, json_text, thin_border)
        # YAML出力セルの設定（リファクタ後）
        yaml_cell = self._setup_output_cell(ws, output_row, 2, yaml_text, thin_border)

    def save(self, output_file):
        """Workbook を指定のファイル名で保存します。"""
        self.wb.save(output_file)
        print(f"新しい出力Excelファイルを作成しました： {output_file}")

    def run(self, output_file):
        """
        全体の処理を実行します。
          1. 対象シートの複製
          2. データマーカーの変換
          3. JSONデータへの変換
          4. JSON/YAMLの出力
          5. ファイルの保存
        """
        self.duplicate_sheet()
        self.transform_data_markers()
        json_data = self.convert_sheet_to_json()
        if json_data is None:
            print("JSON変換に失敗しました。")
            sys.exit(1)
        self.output_json_yaml(json_data)
        self.save(output_file)

def print_usage():
    print("使い方: python script.py 入力ファイル.xlsx [出力ファイル.xlsx] [-r|--replace]")
    print("  ・出力ファイル名を省略した場合、入力ファイル名に _出力日時 を付加した名前になります。")
    print("  ・-r または --replace を指定すると、処理後に出力ファイルで入力ファイルを差し替えます。")

if __name__ == "__main__":
    # ヘルプオプションがあれば利用方法を表示して終了
    if any(arg in ("-h", "--help") for arg in sys.argv):
        print_usage()
        sys.exit(0)

    # オプション引数を抽出し、残りを位置引数とする
    replace_flag = False
    positional_args = []
    for arg in sys.argv[1:]:
        if arg in ("-r", "--replace"):
            replace_flag = True
        else:
            positional_args.append(arg)

    if len(positional_args) < 1:
        print_usage()
        sys.exit(1)

    input_filename = positional_args[0]

    # 出力ファイル名が指定されていない場合は自動生成
    if len(positional_args) >= 2:
        output_filename = positional_args[1]
    else:
        base, ext = os.path.splitext(input_filename)
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{base}_{dt_str}.xlsx"

    converter = ExcelJsonConverter(input_filename)
    converter.run(output_filename)

    # オプションが指定されている場合、出力ファイルで入力ファイルを差し替え
    if replace_flag:
        try:
            os.replace(output_filename, input_filename)
            print(f"入力ファイル {input_filename} を更新しました。")
        except Exception as e:
            print(f"入力ファイルの差し替えに失敗しました: {e}")
