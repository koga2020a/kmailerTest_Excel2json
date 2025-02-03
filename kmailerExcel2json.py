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
        ただし、セルの値が "*" で始まる場合（例: "*$1"）は継続行として扱うため、そのまま保持します。
        ※ 本例では、継続行の判断はB列の値が「$」で始まるかおよび空セルになるまでで行います。
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
                if marker.startswith("*"):
                    continue
                elif marker != "#NOT":
                    cell.value = "#JSON_DATA"

    def _build_header_hierarchy(self):
        """
        複製シート内のヘッダー行（A列が "#JSON_START" の行）を走査し、
        各列ごとにキー階層のリスト（例：
          [{"key": "mailSet", "arr": None}, {"key": "mailTemplates", "arr": "$1"}, {"key": "kintoneTemplateName", "arr": None}, …]
        ）の辞書を作成して返します。
        統合セルの場合は、先頭セルの値を取得します。
        """
        ws = self.duplicate_ws
        header_rows = []
        # ヘッダー行の抽出（A列に "#JSON_START" の行）
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            cell_a = row[0].value
            if isinstance(cell_a, str) and cell_a.strip() == "#JSON_START":
                header_rows.append(row)
        
        if not header_rows:
            print("警告：ヘッダー行（#JSON_START）が見つかりませんでした。")
            return None

        header_hierarchy = {}  # key: 列文字（例 "B", "C", ...）、value: list of dicts
        for header_row in header_rows:
            for cell in header_row:
                if cell.column == 1:
                    continue
                cell_value = cell.value
                # 統合セルの場合は、先頭セルの値を取得
                if cell_value is None:
                    for merged_range in ws.merged_cells.ranges:
                        if cell.coordinate in merged_range:
                            cell_value = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
                            break
                if cell_value and isinstance(cell_value, str) and cell_value.strip().startswith("#"):
                    key_text = cell_value.strip().lstrip("#").strip()
                    # '$' 以降は配列指示子として扱う
                    if '$' in key_text:
                        parts = key_text.split('$', 1)
                        key_name = parts[0].strip()
                        array_directive = '$' + parts[1].strip() if parts[1].strip() != "" else None
                    else:
                        key_name = key_text
                        array_directive = None
                    col_letter = get_column_letter(cell.column)
                    if col_letter not in header_hierarchy:
                        header_hierarchy[col_letter] = []
                    header_hierarchy[col_letter].append({"key": key_name, "arr": array_directive})
        return header_hierarchy

    def convert_sheet_to_json(self):
        """
        複製シート内のデータ行（A列が "#JSON_DATA" の行）を、  
        ヘッダー定義に沿ってネスト構造の辞書へ変換します。

        ・メイン行（A列が "#JSON_DATA" の行）の各セルについて、
          ヘッダー定義に "$" 指定子があれば、該当フィールドは単一のオブジェクトではなく、
          配列要素として格納します。
        ・継続行（B列に "$" 指定がある行）も同様に、対応する配列の新しい要素として処理します。

        例として、Excel内のヘッダーが以下の場合：
          #JSON_START, #mailSet, #mailSet, #mailTemplates$1, #mailTemplates$1, #mailTemplates$1
          (各セルの下段にフィールド名が設定されている想定)
        メイン行に mailTemplates 系の値があれば、それは最初の配列要素となり、
        継続行の mailTemplates 系の値は、その配列に新たな要素として追加されます。
        """
        ws = self.duplicate_ws
        header_hierarchy = self._build_header_hierarchy()
        if header_hierarchy is None:
            return None

        data_list = []
        rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row))
        i = 0

        while i < len(rows):
            row = rows[i]
            marker = row[0].value
            # メインレコード行として "#JSON_DATA" で始まる行を選択
            if marker is None or not isinstance(marker, str) or not marker.strip().startswith("#JSON_DATA"):
                i += 1
                continue

            # 新規レコード行グループの取得（メイン行と継続行）
            group_rows = [row]
            i += 1
            while i < len(rows):
                next_row = rows[i]
                # B列（インデックス1）の値が存在する場合は継続行と見なす
                next_marker = next_row[1].value if len(next_row) > 1 else None
                if next_marker is not None:
                    group_rows.append(next_row)
                    i += 1
                else:
                    break

            new_record = {}
            temp_arrays = {}  # メイン行の array 指定項目（例：mailTemplates）の一時格納領域

            # 【メイン行の処理】
            main_row = group_rows[0]
            main_row_num = main_row[0].row
            for col_letter, header_defs in header_hierarchy.items():
                col_idx = column_index_from_string(col_letter)
                cell_val = ws.cell(row=main_row_num, column=col_idx).value

                # ヘッダー定義内に "$" 指定子があれば array 項目として扱う
                if any(level.get("arr") for level in header_defs):
                    # 最初に見つかった array 指定子のキーを配列のルートキーとする
                    array_root_key = None
                    for level in header_defs:
                        if level.get("arr"):
                            array_root_key = level["key"]
                            break
                    # プロパティ名は、チェーンの最後のキー名（例：#mailTemplates$1 の後段にフィールド名が定義されている場合）
                    prop_name = header_defs[-1]["key"] if len(header_defs) > 1 else array_root_key
                    if array_root_key not in temp_arrays:
                        temp_arrays[array_root_key] = {}
                    temp_arrays[array_root_key][prop_name] = cell_val
                else:
                    # 通常のネスト構造の設定
                    cur = new_record
                    for j, level in enumerate(header_defs):
                        key = level["key"]
                        if j == len(header_defs) - 1:
                            cur[key] = cell_val
                        else:
                            if key not in cur:
                                cur[key] = {}
                            cur = cur[key]
            # メイン行で取得した array 指定項目を new_record に挿入（配列の要素として格納）
            for arr_key, arr_value in temp_arrays.items():
                new_record[arr_key] = [arr_value]

            # 【継続行の処理】
            # 各継続行は、array 項目の新要素として別個に追加する
            for cont_row in group_rows[1:]:
                cont_row_num = cont_row[0].row
                directive = ws.cell(row=cont_row_num, column=2).value
                if directive is None:
                    continue

                cont_obj = {}
                array_root_key = None
                # 各列について、該当する array 指定子のセルを探す
                for col_letter, header_defs in header_hierarchy.items():
                    for level in header_defs:
                        if level.get("arr") == f'${directive}':
                            array_root_key = level["key"]
                            prop_name = header_defs[-1]["key"] if len(header_defs) > 1 else array_root_key
                            col_idx = column_index_from_string(col_letter)
                            cell_val = ws.cell(row=cont_row_num, column=col_idx).value
                            cont_obj[prop_name] = cell_val
                            break
                # 指定された array 項目に継続行のデータを追加
                if cont_obj and array_root_key:
                    if array_root_key not in new_record:
                        new_record[array_root_key] = []
                    new_record[array_root_key].append(cont_obj)

            data_list.append(new_record)
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
        title_row = output_row - 1

        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        title_fill = PatternFill(fill_type='solid', start_color='E6E6FA')

        self._set_title_cell(ws, title_row, 1, "出力JSON", title_fill, thin_border)
        self._set_title_cell(ws, title_row, 2, "出力YAML", title_fill, thin_border)

        self._setup_output_cell(ws, output_row, 1, json_text, thin_border)
        self._setup_output_cell(ws, output_row, 2, yaml_text, thin_border)

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
    if any(arg in ("-h", "--help") for arg in sys.argv):
        print_usage()
        sys.exit(0)

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
    if len(positional_args) >= 2:
        output_filename = positional_args[1]
    else:
        base, ext = os.path.splitext(input_filename)
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{base}_{dt_str}.xlsx"

    converter = ExcelJsonConverter(input_filename)
    converter.run(output_filename)

    if replace_flag:
        try:
            os.replace(output_filename, input_filename)
            print(f"入力ファイル {input_filename} を更新しました。")
        except Exception as e:
            print(f"入力ファイルの差し替えに失敗しました: {e}")
