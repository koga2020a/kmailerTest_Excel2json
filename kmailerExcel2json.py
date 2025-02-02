import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.styles import Alignment
from datetime import datetime
import json
import sys
import yaml  # PyYAML を利用。事前に pip install pyyaml を実施してください。

def transform_data_markers(ws):
    """
    ワークシート内で、A列に記載されている
      #JSON_DATA_START ～ #JSON_DATA_END のブロック（もしくは
      #JSON_DATA_START からシート最終行まで）
    の各行について、セルの値を通常は "#JSON_DATA" に置換（補完）します。
    ※ ただし、セルの値が "#NOT" であれば、その行は変更せず、
        データ対象外とします。
    """
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
            # セルの値が "#NOT" の場合は変更せずそのまま残す
            if marker != "#NOT":
                cell.value = "#JSON_DATA"

def convert_sheet_to_json(ws):
    """
    ヘッダー行は A列に "#JSON_START" が入っている行とし、
    複数行ある場合は上側の行が上位階層、下側の行が下位階層として解釈します。
    データ行は A列に "#JSON_DATA" が入っている行（※ transform_data_markers により補完済み）
    を対象とします。

    例:
      A列             B列              C列              D列
      ---------------------------------------------------------
      #JSON_START     #mailset         #mailset         #templates
      #JSON_START     #title           #body            #name
      #JSON_DATA      toFamily         ThanksFamilyTest Morning
      #JSON_DATA      toFamily         ThanksFamilyTest Evening
      #JSON_DATA      toFamily         ThanksFamilyTest Night

    → 各データ行は、以下のような辞書に変換されます。

       {
         "mailset": {
           "title": "toFamily",
           "body": "ThanksFamilyTest"
         },
         "templates": {
           "name": "Morning"
         }
       }
    """
    header_rows = []
    data_start_row = None  # 最初に "#JSON_DATA" を発見した行番号

    # 全行を走査してヘッダー行（#JSON_START）とデータ行開始位置を特定
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        cell_a = row[0].value
        if isinstance(cell_a, str):
            cell_a = cell_a.strip()
            if cell_a == "#JSON_START":
                header_rows.append(row)
            elif cell_a == "#JSON_DATA":
                if data_start_row is None:
                    data_start_row = row[0].row

    if not header_rows:
        print("警告：ヘッダー行（#JSON_START）が見つかりませんでした。")
        return None
    if data_start_row is None:
        print("警告：データ行（#JSON_DATA）が見つかりませんでした。")
        return None

    # ヘッダー行（A列以外）の各列について、上から順にキー階層のリストを作成
    header_hierarchy = {}  # key: 列文字（例 "B", "C", ...）、value: [上位キー, …, 下位キー]
    for header_row in header_rows:
        for cell in header_row:
            if cell.column == 1:  # A列はマーカー用なのでスキップ
                continue
            if cell.value and isinstance(cell.value, str) and cell.value.strip().startswith("#"):
                key_name = cell.value.strip().lstrip("#").strip()
                col_letter = get_column_letter(cell.column)
                if col_letter not in header_hierarchy:
                    header_hierarchy[col_letter] = []
                header_hierarchy[col_letter].append(key_name)
    # 例: {"B": ["mailset", "title"], "C": ["mailset", "body"], "D": ["templates", "name"]}

    data_list = []
    # データ行（A列に "#JSON_DATA" がある行）を処理
    for row in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row):
        cell_a_val = row[0].value
        if not (isinstance(cell_a_val, str) and cell_a_val.strip() == "#JSON_DATA"):
            continue  # マーカーが "#JSON_DATA" でない行（例：#NOT の行）は無視
        record = {}
        for col_letter, key_list in header_hierarchy.items():
            col_idx = column_index_from_string(col_letter)
            cell = ws.cell(row=row[0].row, column=col_idx)
            current_dict = record
            # キー階層のうち、最後以外は入れ子の辞書を生成
            for key in key_list[:-1]:
                if key not in current_dict or not isinstance(current_dict[key], dict):
                    current_dict[key] = {}
                current_dict = current_dict[key]
            # 最後のキーにセルの値をセット
            current_dict[key_list[-1]] = cell.value
        data_list.append(record)

    return data_list

def main(input_file, output_file):
    # 入力Excelファイルを読み込み
    wb = openpyxl.load_workbook(input_file)

    # 対象シートの決定：
    # ・シート名が "JSON_START" のシートがあればそれを使用、
    # ・なければシートがひとつの場合そのシートを使用
    if "JSON_START" in wb.sheetnames:
        target_ws = wb["JSON_START"]
    elif len(wb.sheetnames) == 1:
        target_ws = wb.active
    else:
        print("エラー：複数シートありますが、'JSON_START' という名前のシートが見つかりません。")
        sys.exit(1)

    # 対象シートを複製し、シート名を「JSON_YYYYMMDD_HHMMSS」（例：JSON_20250202_123456）に変更
    duplicate_ws = wb.copy_worksheet(target_ws)
    dt_sheet_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    duplicate_ws.title = "JSON_" + dt_sheet_name

    # --- ここで、#JSON_DATA_START ～ #JSON_DATA_END のブロックがあれば、
    #     その行の A列の値を "#JSON_DATA" に置換（補完）します（ただし "#NOT" はそのまま） ---
    transform_data_markers(duplicate_ws)

    # 複製シート内のデータを JSON に変換
    json_data = convert_sheet_to_json(duplicate_ws)
    if json_data is None:
        print("JSON変換に失敗しました。")
        sys.exit(1)

    # JSONテキストとYAMLテキストを作成
    json_text = json.dumps(json_data, ensure_ascii=False, indent=2)
    yaml_text = yaml.dump(json_data, allow_unicode=True, default_flow_style=False)

    # 出力位置の決定：
    # 複製シートの最終行から10行下の行に出力します。
    last_row = duplicate_ws.max_row
    output_row = last_row + 10

    # JSON を A列、YAML を B列に出力し、各セルの書式をテキスト形式かつ折り返し表示に設定
    json_cell = duplicate_ws.cell(row=output_row, column=1, value=json_text)
    json_cell.number_format = "@"
    json_cell.alignment = Alignment(wrap_text=True)

    yaml_cell = duplicate_ws.cell(row=output_row, column=2, value=yaml_text)
    yaml_cell.number_format = "@"
    yaml_cell.alignment = Alignment(wrap_text=True)

    # 新しい出力Excelファイルとして保存
    wb.save(output_file)
    print(f"新しい出力Excelファイルを作成しました： {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python script.py 入力ファイル.xlsx 出力ファイル.xlsx")
    else:
        input_filename = sys.argv[1]
        output_filename = sys.argv[2]
        main(input_filename, output_filename)
