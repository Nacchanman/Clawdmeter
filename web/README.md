# Clawdmeter Web Dashboard

iPhone SE などのスマートフォンから、ブラウザだけで Claude Code 使用量を見るための簡易 Web 版です。

ESP32 ファームウェアも iOS アプリも使いません。PC 側で小さなローカル Web サーバーを起動し、iPhone の Safari からその URL を開きます。

## 仕組み

```text
Claude Code が入っている PC
  ├─ ~/.claude/.credentials.json から token を読む
  ├─ Anthropic API に最小リクエストを送る
  ├─ rate limit ヘッダーから使用量を読む
  └─ http://0.0.0.0:8787 でダッシュボードを配信

同じ Wi-Fi 上の iPhone
  └─ Safari で http://PCのIPアドレス:8787 を開く
```

ブラウザから直接 Anthropic API を叩く方式にはしていません。理由は、トークンを iPhone のブラウザに保存・露出させたくないことと、CORS の制限で動かない可能性があるためです。

## 必要なもの

- Claude Code が使える PC
- Python 3.10 以上
- `requests`
- iPhone と PC が同じ Wi-Fi にいること

## セットアップ

```bash
cd web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py --host 0.0.0.0 --port 8787
```

PC 上で確認する場合:

```text
http://localhost:8787
```

iPhone から開く場合は、PC の IP アドレスを調べます。

Linux:

```bash
hostname -I
```

macOS:

```bash
ipconfig getifaddr en0
```

たとえば PC の IP が `192.168.1.23` なら、iPhone の Safari で以下を開きます。

```text
http://192.168.1.23:8787
```

## 画面をホーム画面に追加する

iPhone の Safari で開いたあと、共有ボタンから「ホーム画面に追加」を選ぶと、アプリのように起動できます。

## セキュリティ注意

この Web サーバーは個人の同一 Wi-Fi 内で使う前提です。インターネットに公開しないでください。

- `--host 0.0.0.0` は同じネットワーク内の端末からアクセスできる設定です。
- 外出先から使いたい場合でも、ポート開放ではなく Tailscale などの VPN を使う方が安全です。
- access token はブラウザへ送らず、PC 側のサーバーだけで使います。

## API

### `GET /api/usage`

使用量を JSON で返します。

```json
{
  "ok": true,
  "sessionPercent": 45,
  "sessionResetMinutes": 120,
  "weeklyPercent": 28,
  "weeklyResetMinutes": 7200,
  "status": "allowed",
  "updatedAt": "2026-05-13T00:00:00Z"
}
```

## うまく動かないとき

### iPhone から開けない

- PC と iPhone が同じ Wi-Fi にいるか確認してください。
- PC のファイアウォールで `8787` 番ポートがブロックされていないか確認してください。
- `localhost` は iPhone 自身を指すため、iPhone からは `http://PCのIPアドレス:8787` を使ってください。

### 使用量が 0% のまま

- `~/.claude/.credentials.json` が存在するか確認してください。
- Claude Code にログイン済みか確認してください。
- ターミナルに出ているエラーを確認してください。

### 401 / 403 エラー

Claude Code の token が無効、期限切れ、または API で利用できない状態の可能性があります。Claude Code に再ログインしてから、サーバーを再起動してください。
