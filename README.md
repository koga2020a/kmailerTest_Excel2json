# Excel-JSON 相互変換ツール

## 概要
このツールは、複雑なJSON構造をExcelで編集可能な形式に変換し、その逆変換も可能にする高機能な変換ユーティリティです。特に、階層構造を持つJSONデータの視覚的な編集を容易にすることを目的としています。

## 特徴
- 複雑なJSONの階層構造を見やすい表形式で表現
- 配列要素の縦方向展開による直感的な表現
- マージセルを活用した効率的なデータ表現
- 日本語を完全サポート
- 数値型の自動認識機能
- 継続行による柔軟なデータ入力

## 構成ファイル
- `excel2json_step1_excel2csv.py`: ExcelファイルからCSV形式への変換
- `excel2json_step2_csv2json.py`: CSV形式からJSONへの変換
- `json2ExcelTypeTxt.py`: JSONからExcel形式のテキストへの変換

## データ形式

### Excel形式の構造
データは以下のような形式で表現されます：

#### 例1：シンプルな階層構造
```
LAYOUT    user          name
LAYOUT    user          age
DATA      田中太郎      25
DATA      山田花子      30
```

#### 例2：配列を含む階層構造
```
LAYOUT    settings      colors[]      name
LAYOUT    settings      colors[]      code
DATA      基本設定      赤           #FF0000
DATA   *               青           #0000FF
```

### 特殊行の説明
- `LAYOUT`: 階層構造を定義する行
- `DATA`: 実データを含む行
- `DATA *`: 配列要素の継続行を示す
- `START`: データブロックの開始（オプション）
- `END`: データブロックの終了

### 特殊記法
- `[]`: 配列を示す（例：`colors[]`）
- `#`: オプション項目を示すプレフィックス
- `<`: 上のセルの値を継承
- `*`: 継続行を示すマーカー

## 使用方法

### ExcelからJSONへの変換

#### 例1：基本的な変換
```bash
python excel2json_step1_excel2csv.py input.xlsx
python excel2json_step2_csv2json.py input.csv
```

#### 例2：シート指定での変換
```bash
python excel2json_step1_excel2csv.py input.xlsx --sheet "データ" --start B2
python excel2json_step2_csv2json.py input.csv
```

### JSONからExcelテキスト形式への変換

```bash
python json2ExcelTypeTxt.py input.json output.txt
```

## 入力例と出力例

### 例1：シンプルな構造

入力（Excel）:
```
LAYOUT    user          name
LAYOUT    user          age
DATA      田中太郎      25
```

出力（JSON）:
```json
{
    "user": {
        "name": "田中太郎",
        "age": 25
    }
}
```

### 例2：配列構造

入力（Excel）:
```
LAYOUT    colors[]      name
LAYOUT    colors[]      code
DATA      赤           #FF0000
DATA   *  青           #0000FF
```

出力（JSON）:
```json
{
    "colors": [
        {
            "name": "赤",
            "code": "#FF0000"
        },
        {
            "name": "青",
            "code": "#0000FF"
        }
    ]
}
```

## 動作要件
- Python 3.6以上
- 必要なライブラリ：
  - openpyxl
  - pyyaml

## インストール
```bash
pip install openpyxl pyyaml
```

## 制限事項
- 循環参照を含むJSONは非対応
- 非常に大規模なデータの場合、メモリ使用量に注意が必要

## ライセンス
このプロジェクトはMITライセンスの下で公開されています。
