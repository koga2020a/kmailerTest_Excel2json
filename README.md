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

## データ形式

### Excel形式の構造
データは以下のような形式で表現されます：

```
LAYOUT    [階層1]       [階層2]       [階層3]
LAYOUT    [配列名][]    [項目名]      #[オプション項目]
DATA      値1           値2           値3
DATA   *  継続値1       継続値2       継続値3
```

### 特殊行の説明
- `LAYOUT`: 階層構造を定義する行
- `DATA`: 実データを含む行
- `DATA *`: 配列要素の継続行を示す
- `START`: データブロックの開始（オプション）
- `END`/`FINISH`/`FIN`: データブロックの終了
- `NONE`/`NOT`/`NO`: 無視される行

### 特殊記法
- `[]`: 配列を示す（例：`users[]`）
- `#`: オプション項目を示すプレフィックス
- `<`: 上のセルの値を継承（マージセル）
- `*`: 継続行を示すマーカー（2列目）

## 使用方法

### ExcelからJSONへの変換

1. ExcelからCSVへの変換：
```bash
python excel2json_step1_excel2csv.py input.xlsx [--sheet シート名] [--start 開始セル]
```

2. CSVからJSONへの変換：
```bash
python excel2json_step2_csv2json.py output.csv
```

### 入力例
Excel:
```
LAYOUT    users         name
LAYOUT    users[]       auth
DATA      user1         password123
DATA   *   user2        password456
```

出力JSON:
```json
{
    "users": [
        {
            "name": "user1",
            "auth": "password123"
        },
        {
            "name": "user2",
            "auth": "password456"
        }
    ]
}
```

## 高度な機能

### マージセルのサポート
- 縦方向マージ：配列要素の継続を示す
- 横方向マージ：同一値の繰り返しを簡略化

### データ型の自動認識
- 整数値の自動変換
- 小数値の自動変換
- 文字列型の保持

### 継続行による柔軟なデータ構造
- 配列要素の追加
- 既存要素の更新
- 複雑な階層構造の表現

## 動作要件
- Python 3.6以上
- 必要なライブラリ：
  - openpyxl
  - pyyaml
  - typing

## インストール
```bash
pip install openpyxl pyyaml
```

## 制限事項
- 循環参照を含むJSONは非対応
- 非常に大規模なデータの場合、メモリ使用量に注意
- 特定の複雑なJSON構造では表現が困難な場合あり

## エラー処理
- 不正なExcelフォーマット時のエラーメッセージ
- シート不在時の適切なエラー通知
- データ型変換エラーの適切な処理

## ライセンス
このプロジェクトはMITライセンスの下で公開されています。
