# Clawdmeter

Claude Code の利用状況を確認するためのダッシュボードです。

この Fork には、元の ESP32 版に加えて、iPhone の Safari などのブラウザから使える **Web 版ダッシュボード** も追加しています。

## 使い方の選択肢

### 1. Web 版: iPhone のブラウザで見る

ESP32 ボードや iOS アプリを作らず、iPhone の Safari で表示するだけならこちらを使います。

```bash
cd web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py --host 0.0.0.0 --port 8787
```

PC と iPhone を同じ Wi-Fi に接続し、iPhone の Safari で以下を開きます。

```text
http://PCのIPアドレス:8787
```

詳しい手順は [`web/README.md`](web/README.md) を参照してください。

### 2. ESP32 版: 専用ハードで動かす

[Waveshare ESP32-S3-Touch-AMOLED-2.16](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.16) 上で動作し、PC とは Bluetooth で接続します。スプラッシュ画面ではピクセルアートの Clawd アニメーションが再生され、利用率が上がるほど忙しそうなアニメーションに切り替わります。

左右の物理ボタンは BLE HID キーボードとして動作し、Claude Code の音声入力やモード切り替えに使えるショートカットを送信します。

|              使用量メーター              |              Clawd アニメーション画面              |
| :--------------------------------------: | :-----------------------------------------------: |
| ![Usage meter](assets/demo.jpeg) | ![Clawd animation screen](assets/demo.gif) |

Clawd アニメーションは [claudepix](https://claudepix.vercel.app) から取得しています。これは [@amaanbuilds](https://x.com/amaanbuilds) によるピクセルアート Clawd スプライトのライブラリです。

## 画面

起動後はスプラッシュ画面が表示されます。中央の PWR ボタンを押すと、Usage 画面と Bluetooth 画面を切り替えられます。画面をタップするとスプラッシュ表示に戻り、もう一度タップするとスプラッシュを閉じます。ただし Bluetooth 画面の Reset 領域は除きます。

|              Splash               |              Usage              |                Bluetooth                |
| :-------------------------------: | :-----------------------------: | :-------------------------------------: |
| ![Splash](screenshots/splash.png) | ![Usage](screenshots/usage.png) | ![Bluetooth](screenshots/bluetooth.png) |
| いつでもタッチで表示切り替え | セッション・週間の利用率 | 接続状態とペアリング情報のリセット |

スプラッシュ表示中は、中央ボタンで画面ではなくアニメーションを切り替えます。また、ファームウェアは現在の利用率グループ内で 20 秒ごとにアニメーションを自動ローテーションします。

## 必要なハードウェア

- [Waveshare ESP32-S3-Touch-AMOLED-2.16](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.16)
  - ESP32-S3R8
  - 2.16 インチ 480×480 AMOLED（CO5300 QSPI）
  - CST9220 静電容量式タッチ
  - AXP2101 PMU + Li-Po バッテリー対応
  - QMI8658 IMU
- ファームウェア書き込み・充電用 USB-C ケーブル
- 3.7V Li-Po バッテリー（MX1.25 2 ピンコネクタ、任意）

## 前提条件

- Linux（Ubuntu で動作確認）
- [PlatformIO CLI](https://docs.platformio.org/en/latest/core/installation/index.html)
- `curl`, `bluetoothctl`, `busctl`（BlueZ Bluetooth スタック）
- 有効な Claude Code サブスクリプション

## macOS 対応について

現状は Linux 前提です。

macOS 対応は未整備ですが、対応したい場合は Pull Request を歓迎します。作者の環境が Linux のため、macOS でのテストは難しい状態です。

## ファームウェアを書き込む

ESP32 ボードを USB-C で接続してから、以下を実行します。

```bash
cd firmware
pio run -t upload --upload-port /dev/ttyACM0
```

環境によっては `/dev/ttyACM0` ではなく別のポート名になることがあります。その場合は、接続されているシリアルポートを確認して読み替えてください。

## Bluetooth ペアリング

書き込み後、デバイスは `Claude Controller` という名前でアドバタイズされます。最初に一度だけペアリングします。

```bash
# デバイスをスキャン
bluetoothctl scan le

# "Claude Controller" が表示されたら、ペアリングして信頼済みにする
bluetoothctl pair F4:12:FA:C0:8F:E5    # 自分のデバイスの MAC アドレスに置き換える
bluetoothctl trust F4:12:FA:C0:8F:E5
```

MAC アドレスは Bluetooth 画面に表示されます。中央の PWR ボタンを押して Bluetooth 画面に切り替えて確認してください。

## daemon をインストールする

daemon は 60 秒ごとに Claude の利用状況を取得し、BLE 経由でディスプレイに送信します。

```bash
./install.sh
systemctl --user start claude-usage-daemon
```

状態確認:

```bash
systemctl --user status claude-usage-daemon
```

ログ確認:

```bash
journalctl --user -u claude-usage-daemon -f
```

## 仕組み

1. daemon が `~/.claude/.credentials.json` から Claude Code の OAuth トークンを読み込みます。
2. `api.anthropic.com/v1/messages` に最小限の API リクエストを送ります。
3. 使用量はレスポンスヘッダーから取得します。
   - `anthropic-ratelimit-unified-5h-utilization`
   - そのほか関連する rate limit ヘッダー
4. daemon が ESP32 に BLE で接続し、GATT RX characteristic に JSON ペイロードを書き込みます。
5. ファームウェアが JSON を解析し、LVGL ダッシュボードを更新します。
6. ファームウェアは 5 分間のセッション使用率の変化も見て、利用状況に合うスプラッシュアニメーションを選びます。
7. 左右の物理ボタンはこの処理とは独立しており、ペアリング済みホストに BLE HID キーボード入力として Space と Shift+Tab を送信します。

## 物理ボタン

ボードには 3 つのサイドボタンがあります。左右のボタンはどの画面でも同じ動作です。中央ボタンは表示中の画面によって動作が変わります。

| ボタン | GPIO | 機能 |
| ------ | ---- | ---- |
| **Left** | GPIO 0 | 長押しで Space を送信（Claude Code 音声モードの push-to-talk 用） |
| **Middle**（PWR） | AXP2101 PKEY | Usage / Bluetooth 画面を切り替え。スプラッシュ表示中はアニメーション切り替え |
| **Right** | GPIO 18 | Shift+Tab を送信（Claude Code のモード切り替え用） |

Space と Shift+Tab は標準の BLE HID キーボード入力として送信されます。そのため Claude Code だけでなく、ペアリング先 PC で現在フォーカスされているウィンドウに入力されます。

## BLE プロトコル

デバイスは標準 HID キーボードサービスに加えて、独自の GATT サービスもアドバタイズします。

|                            | UUID                                   |
| -------------------------- | -------------------------------------- |
| **Data Service**           | `4c41555a-4465-7669-6365-000000000001` |
| RX Characteristic（write） | `4c41555a-4465-7669-6365-000000000002` |
| TX Characteristic（notify）| `4c41555a-4465-7669-6365-000000000003` |
| **HID Service**            | `00001812-0000-1000-8000-00805f9b34fb` |

RX に書き込む JSON ペイロード例:

```json
{ "s": 45, "sr": 120, "w": 28, "wr": 7200, "st": "allowed", "ok": true }
```

フィールドの意味:

| フィールド | 意味 |
| ---------- | ---- |
| `s` | セッション使用率（%） |
| `sr` | セッションリセットまでの時間（分） |
| `w` | 週間使用率（%） |
| `wr` | 週間リセットまでの時間（分） |
| `st` | ステータス |
| `ok` | 成功フラグ |

## フォントを再コンパイルする

`firmware/src/font_*.c` は、あらかじめコンパイル済みの LVGL ビットマップフォントです。サイズは、このプロジェクトが当初使っていた Panlee 165 PPI パネルより約 1.9 倍大きく、2.16 インチ AMOLED の 314 PPI に合わせています。

まず `lv_font_conv` をインストールします。

```bash
npm install -g lv_font_conv
```

各フォントを生成します。`lv_font_conv` はループ実行で問題が出ることがあるため、必要に応じて 1 つずつ実行してください。LVGL 9 では `--no-compress` が必要です。

```bash
# Tiempos Text（タイトル、56px）
lv_font_conv --font assets/TiemposText-400-Regular.otf -r 0x20-0x7E \
  --size 56 --format lvgl --bpp 4 --no-compress \
  -o firmware/src/font_tiempos_56.c --lv-include "lvgl.h"

# Styrene B（大きな数字 48、パネルラベル 28、小テキスト 24、最小 20）
for size in 48 28 24 20; do
  lv_font_conv --font assets/StyreneB-Regular.otf -r 0x20-0x7E \
    --size $size --format lvgl --bpp 4 --no-compress \
    -o firmware/src/font_styrene_${size}.c --lv-include "lvgl.h"
done

# DejaVu Sans Mono（32px、スピナー用 Unicode 文字を含む）
lv_font_conv --font assets/DejaVuSansMono.ttf \
  -r 0x20-0x7E,0xB7,0x2026,0x2722,0x2733,0x2736,0x273B,0x273D \
  --size 32 --format lvgl --bpp 4 --no-compress \
  -o firmware/src/font_mono_32.c --lv-include "lvgl.h"
```

**重要:** `lv_font_conv` v1.5.3 は LVGL 8 形式のコードを出力します。LVGL 9 で使うには、生成された各ファイルに以下の修正が必要です。

1. `font_dsc` とフォント構造体を囲む `#if LVGL_VERSION_MAJOR >= 8` ガードを削除する
2. `font_dsc` から `.cache` フィールドを削除する
3. フォント構造体に `.release_glyph = NULL`, `.kerning = 0`, `.static_bitmap = 0` を追加する
4. フォント構造体に `.fallback = NULL`, `.user_data = NULL` を追加する

この修正をしないと、コンパイルは通ってもフォントが表示されないことがあります。

## Lucide アイコンを変換する

UI では [Lucide](https://lucide.dev) の一部アイコン（Bluetooth とバッテリー状態）を、LVGL 用の RGB565 / RGB565A8 C 配列に変換して使っています。

```bash
node tools/png_to_lvgl.js assets/icon_bluetooth_48.png icon_bluetooth_data ICON_BLUETOOTH_WIDTH ICON_BLUETOOTH_HEIGHT
```

デフォルトの tint は白（`0xFFFFFF`）です。Lucide の PNG は透過背景に黒で描かれているため、暗い UI 上ではそのままだと見えません。ロゴなど、すでに色が付いている画像には `--no-tint` を指定してください。

バッテリーアイコンは RGB565A8（アルファプレーンあり）で、スプラッシュ画面上に自然に合成されます。そのほかのアイコンはパネル色の上に RGB565 として焼き込まれます。変換結果は `firmware/src/icons.h` に貼り付けます。

## スプラッシュアニメーション

アニメーションは [claudepix.vercel.app](https://claudepix.vercel.app) の Clawd スプライトライブラリから取得しています。

`tools/scrape_claudepix.js` はサイトの JavaScript を Node VM 上で評価してフレームデータとパレットを取り出します。その後、`tools/convert_to_c.js` が RGB565 の C 配列に変換し、`firmware/src/splash_animations.h` を生成します。

再取得する場合は以下を実行します。

```bash
node tools/scrape_claudepix.js
node tools/convert_to_c.js
pio run -d firmware -t upload
```

詳細は `tools/README.md` を参照してください。

## クレジット

- Pixel-art Clawd animation: [@amaanbuilds](https://x.com/amaanbuilds)、取得元 [claudepix.vercel.app](https://claudepix.vercel.app)
- フレームデータとパレットの取得・変換: `tools/` 以下のスクリプト
- Lucide icon set: [lucide.dev](https://lucide.dev), MIT License
- Anthropic brand fonts: Tiempos Text, Styrene B（下記のライセンス注意を参照）

## ライセンス上の注意

このリポジトリには、Anthropic のブランドガイドラインに沿った表現、Anthropic がライセンスを持つプロプライエタリフォント、著作権のある Clawd マスコット由来の素材が含まれています。

そのため、コード自体は非プロプライエタリであっても、このリポジトリ全体を copyleft ライセンスとして再配布することはしていません。Fork やコピーを行う場合は、含まれているフォントや画像素材の権利関係に注意してください。

個人利用や学習目的で試す場合でも、公開配布・販売・再ブランド化を行う場合は、権利が明確な素材への差し替えを検討してください。
